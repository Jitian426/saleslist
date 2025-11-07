# run_delete_hyogo_selected_cities.py
# 兵庫県の指定市町村を含む住所の Company をバックアップして削除
# COMMIT=1 の時だけ実削除。UTF-8保存必須。

import os, sys, csv
from pathlib import Path
from django.utils import timezone

# --- Django 初期化 ---
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "saleslist.settings")  # ←プロジェクト名が違う場合は変更
import django
django.setup()

from django.apps import apps
from django.db.models import Q
from django.db import transaction

# --- 対象市町村 ---
target_cities = [
    "相生市","明石市","赤穂市","朝来市","芦屋市","淡路市","伊丹市","市川町",
    "猪名川町","稲美町","小野市","加古川市","加西市","加東市","香美町","神河町",
    "上郡町","川西市","佐用町","三田市","宍粟市","新温泉町","洲本市","太子町",
    "多可町","高砂市","宝塚市","たつの市","丹波市","丹波篠山市","豊岡市",
    "西脇市","播磨町","姫路市","福崎町","三木市","南あわじ市","養父市",
]

# --- Company モデル検出 ---
Company = None
for m in apps.get_models():
    if m.__name__ == "Company":
        Company = m
        break
if Company is None:
    print("[ERROR] Companyモデルが見つかりません。候補:", [(m._meta.app_label, m.__name__) for m in apps.get_models()])
    sys.exit(1)

# --- 住所フィールド検出（必要なら候補を追加）---
candidate_fields = ["address", "store_address", "store_address_full", "店舗住所"]
model_fields = [f.name for f in Company._meta.fields]
ADDRESS_FIELD = next((f for f in candidate_fields if f in model_fields), None)
if ADDRESS_FIELD is None:
    print("[ERROR] 住所フィールドが見つかりません。候補:", candidate_fields)
    print("モデルのフィールド一覧:", model_fields)
    sys.exit(1)

print(f"[INFO] 使用モデル: {Company._meta.app_label}.Company / 住所フィールド: {ADDRESS_FIELD}")

# --- 条件（市町村いずれかを含む）---
q = Q()
for city in target_cities:
    q |= Q(**{f"{ADDRESS_FIELD}__contains": city})

qs = Company.objects.filter(q)
count = qs.count()
print(f"[CHECK] 削除候補: {count} 件")

# --- バックアップ ---
ts = timezone.now().strftime("%Y%m%d-%H%M%S")
backup_path = Path(f"backup_delete_selected_hyogo_{ts}.csv")
fields = [f.name for f in Company._meta.fields]
with backup_path.open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(fields)
    for row in qs.values_list(*fields).iterator(chunk_size=1000):
        w.writerow(row)
print(f"[OK] バックアップ出力: {backup_path.resolve()}")

# --- COMMIT=1 の時だけ削除 ---
if os.environ.get("COMMIT") != "1":
    print("[DRY-RUN] 削除は実行しません。削除するには COMMIT=1 を指定してください。")
    sys.exit(0)

with transaction.atomic():
    deleted = qs.delete()
print("[DONE] 削除完了:", deleted)
