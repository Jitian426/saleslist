# delete_hyogo_except.py
# 兵庫県 かつ（神戸市/西宮市/尼崎市 ではない）会社をバックアップして削除
# COMMIT=1 を環境変数で渡した時だけ本当に削除します

from django.apps import apps
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from pathlib import Path
import csv, os, sys

# 1) Company モデルを自動検出
Company = None
for m in apps.get_models():
    if m.__name__ == "Company":
        Company = m
        break

if Company is None:
    print("[ERROR] Company モデルが見つかりません。モデル名が違う可能性があります。")
    print("候補（app_label, ModelName）:", [(m._meta.app_label, m.__name__) for m in apps.get_models()])
    sys.exit(1)

# 2) 住所フィールドを自動推測（必要なら候補を足してください）
CANDIDATES = ["address", "store_address", "store_address_full", "店舗住所"]
FIELD_NAMES = [f.name for f in Company._meta.fields]
ADDRESS_FIELD = next((f for f in CANDIDATES if f in FIELD_NAMES), None)

if ADDRESS_FIELD is None:
    print("[ERROR] 住所フィールドが見つかりません。候補:", CANDIDATES)
    print("モデルのフィールド一覧:", FIELD_NAMES)
    sys.exit(1)

print(f"[INFO] モデル: {Company._meta.app_label}.Company / 住所フィールド: {ADDRESS_FIELD}")

# 3) クエリ（簡易 contains）
q = (
    Q(**{f"{ADDRESS_FIELD}__contains": "兵庫県"})
    & ~Q(**{f"{ADDRESS_FIELD}__contains": "神戸市"})
    & ~Q(**{f"{ADDRESS_FIELD}__contains": "西宮市"})
    & ~Q(**{f"{ADDRESS_FIELD}__contains": "尼崎市"})
)
qs = Company.objects.filter(q)
count = qs.count()
print(f"[CHECK] 削除候補: {count} 件")

# 4) バックアップ必須
ts = timezone.now().strftime("%Y%m%d-%H%M%S")
backup_path = Path(f"backup_hyogo_except_kobe_nishinomiya_ama_{ts}.csv")
FIELDS_TO_EXPORT = [f.name for f in Company._meta.fields]  # FKはIDで出力

with backup_path.open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(FIELDS_TO_EXPORT)
    for row in qs.values_list(*FIELDS_TO_EXPORT).iterator(chunk_size=1000):
        w.writerow(row)

print(f"[OK] バックアップ出力: {backup_path.resolve()}")

# 5) COMMIT=1 の時だけ削除
DO_COMMIT = os.environ.get("COMMIT") == "1"
if not DO_COMMIT:
    print("[DRY-RUN] 削除は実行していません。削除するには COMMIT=1 を指定してください。")
    sys.exit(0)

print("[EXEC] バックアップ完了を確認。削除を実行します…")
with transaction.atomic():
    deleted = qs.delete()  # (件数, 内訳dict)
print("[DONE] 削除完了:", deleted)
