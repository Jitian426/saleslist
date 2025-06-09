import csv
import io
from datetime import datetime  # ← 追加
from threading import Timer
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.utils.timezone import now, make_aware, localtime
from django.core.mail import send_mail
from django.db.models import Q
from .models import Company
from .models import SalesActivity, EmailScheduledJob
from .forms import CompanyForm
from .forms import SalesActivityForm
from .forms import SalesPersonRegistrationForm
from django.http import JsonResponse
from django.urls import get_resolver
from .forms import CustomUserCreationForm
from django.db.models import Prefetch
from django.core.paginator import Paginator
from django.contrib.auth.decorators import user_passes_test
from .forms import CompanyForm  # ← 次に作るフォーム


@user_passes_test(lambda u: u.is_superuser or u.username == 'ryuji')
def upload_csv(request):
    if request.method == "POST":
        csv_file = request.FILES.get("csv_file")

        if not csv_file:
            messages.error(request, 'ファイルが選択されていません')
            return redirect('upload_csv')

        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'CSVファイルをアップロードしてください')
            return redirect('upload_csv')

        try:
            decoded_file = io.StringIO(csv_file.read().decode('utf-8-sig'))  # ✅ BOM削除
            reader = csv.DictReader(decoded_file)

            expected_columns = [
                "店舗名", "電話番号", "FAX番号", "携帯番号", "住所", "法人名", "法人電話番号",
                "法人所在地", "代表者名", "開業日", "許可番号", "大業種", "小業種", "営業担当者", "営業結果", "コメント"
            ]
            actual_columns = list(reader.fieldnames)

            if actual_columns != expected_columns:
                messages.error(request, f'CSVのヘッダーが正しくありません。\n期待するヘッダー: {expected_columns}\nCSVのヘッダー: {actual_columns}')
                return redirect('upload_csv')

            for row in reader:
                print(f"データ確認: {row}")  # ✅ 取得データを確認

                # **日付フォーマットの変換**
                formatted_date = None
                if row["開業日"]:
                    try:
                        formatted_date = datetime.strptime(row["開業日"], '%Y/%m/%d').strftime('%Y-%m-%d')
                    except ValueError:
                        try:
                            formatted_date = datetime.strptime(row["開業日"], '%Y-%m-%d').strftime('%Y-%m-%d')
                        except ValueError:
                            messages.error(request, f'日付フォーマットが間違っています（行: {row}）')
                            continue  # この行はスキップ

                # **企業がすでに存在するかチェック**
                company, created = Company.objects.get_or_create(
                    name=row["店舗名"].strip(),  
                    phone=row["電話番号"].strip(),
                    address=row["住所"].strip(),
                    defaults={  # 新規作成時のみ適用
                        "fax": row.get("FAX番号", "").strip(),
                        "mobile_phone": row.get("携帯番号", "").strip(),
                        "corporation_name": row.get("法人名", "").strip(),
                        "corporation_phone": row.get("法人電話番号", "").strip(),
                        "corporation_address": row.get("法人所在地", "").strip(),
                        "representative": row.get("代表者名", "").strip(),
                        "established_date": formatted_date,
                        "license_number": row.get("許可番号", "").strip(),
                        "industry": row.get("大業種", "").strip(),
                        "sub_industry": row.get("小業種", "").strip(),
                    }
                )

                # **営業履歴の登録**
                if row.get("営業結果"):
                    SalesActivity.objects.create(
                        company=company,
                        sales_person=row.get("営業担当者", "CSVインポート").strip(),  # ← 修正点
                        result=row.get("営業結果", "見込"),
                        memo=row.get("コメント", ""),
                        next_action_date=None
                    )
                    

            messages.success(request, 'CSVデータが正常に取り込まれました！')

        except Exception as e:
            messages.error(request, f'エラーが発生しました: {str(e)}')

        return redirect('saleslist:upload_csv')  # ✅ 名前空間を明示する

    return render(request, 'upload_csv.html')


import logging
from django.shortcuts import render
from .models import Company, SalesActivity
from django.db.models import Q, Prefetch
from django.db import connection
import time  # 🔹 実行時間を測定するために追加
from django.contrib.auth.decorators import login_required  # ← 追加
from django.db.models import OuterRef, Subquery, F, Value, CharField
from django.db.models.functions import Cast

from django.shortcuts import render, get_object_or_404
from .models import Company, SalesActivity

def sales_activity_list(request): 
    query = request.GET.get('q')
    if query:
        activities = SalesActivity.objects.filter(company__name__icontains=query)
    else:
        activities = SalesActivity.objects.all()

    return render(request, 'sales_activity_list.html', {'activities': activities, 'query': query})

from django.utils.timezone import now  # ✅ 追加！
from django.core.mail import send_mail
from threading import Timer
from datetime import datetime
from django.utils.timezone import make_aware
from django.shortcuts import render, get_object_or_404, redirect
from .models import Company, SalesActivity
from datetime import datetime
from .models import SalesActivity, EmailScheduledJob

def add_sales_activity(request, company_id):
    company = get_object_or_404(Company, id=company_id)

    if request.method == "POST":
        form = SalesActivityForm(request.POST)
        if form.is_valid():
            sales_activity = form.save(commit=False)
            sales_activity.company = company
            sales_activity.activity_date = localtime(now())  # ✅ 日時を適用
            # ✅ 氏名で保存（空なら fallback で username）
            full_name = f"{request.user.last_name}{request.user.first_name}"
            sales_activity.sales_person = full_name if full_name.strip() else request.user.username
            sales_activity.sales_person_email = request.POST.get('sales_person_email')
            sales_activity.save()
            
            # ✅ メール送信の処理（次回営業予定がある場合のみ）
            if sales_activity.next_action_date and sales_activity.sales_person_email:
                EmailScheduledJob.objects.create(
                    recipient_email=sales_activity.sales_person_email,
                    subject=f"【リマインド】{company.name} の営業予定",
                    message=f"【営業予定リマインド】\n\n"
                            f"店舗名: {company.name}\n"
                            f"営業担当者: {sales_activity.sales_person}\n"
                            f"次回営業予定日: {localtime(sales_activity.next_action_date).strftime('%Y-%m-%d %H:%M')}\n"
                            f"営業メモ: {sales_activity.memo if sales_activity.memo else 'メモなし'}\n\n"
                            f"この予定を忘れずに対応してください。",
                    scheduled_time=sales_activity.next_action_date
                )

                # ✅ メール送信をスケジュール
                delay = (sales_activity.next_action_date - now()).total_seconds()
                Timer(delay, send_scheduled_email).start()

            return redirect("saleslist:company_detail", pk=company.id)  # ✅ リダイレクトを正しい位置に修正
    else:
        form = SalesActivityForm()

    return render(request, 'add_sales_activity.html', {"form": form, "company": company})

from django.shortcuts import render, get_object_or_404, redirect
from .models import Company
from django import forms

# ✅ 企業情報編集フォーム
class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            'name', 'phone', 'fax', 'mobile_phone', 'address', 'corporation_name', 'corporation_phone',
            'corporation_address', 'representative', 'established_date', 'license_number', 'industry', 'sub_industry'
        ]


@login_required
# ✅ 企業情報編集用のビュー
def edit_company(request, company_id):
    company = get_object_or_404(Company, id=company_id)

    if request.method == "POST":
        form = CompanyForm(request.POST, instance=company)
        
        if form.is_valid():
            company = form.save(commit=False)

            # ✅ None→空文字変換（対象フィールドのみ）
            for field in [
                'fax', 'mobile_phone', 'corporation_phone',
                'representative', 'license_number', 'sub_industry'
            ]:
                if getattr(company, field) is None:
                    setattr(company, field, "")

            company.save()

            # ✅ フォームで実際に変更されたフィールドのみ取得
            changed_fields = form.changed_data

            # ✅ 編集ログを記録
            if changed_fields:
                CompanyEditLog.objects.create(
                    company=company,
                    user=request.user,
                    action="情報編集",
                    changed_fields=changed_fields
                )

            return redirect("saleslist:company_detail", pk=company.id)
        
    else:
        form = CompanyForm(instance=company)

    return render(request, 'edit_company.html', {'form': form, 'company': company})


def send_scheduled_email():
    now_time = now()
    scheduled_emails = EmailScheduledJob.objects.filter(sent=False, scheduled_time__lte=now_time)

    for email_job in scheduled_emails:
        try:
            send_mail(
                email_job.subject,
                email_job.message,
                'your-email@example.com',  # 送信元メールアドレス
                [email_job.recipient_email],
                fail_silently=False,
            )
            email_job.sent = True
            email_job.save()
            print(f"✅ メール送信成功: {email_job.recipient_email} に送信しました")
        except Exception as e:
            print(f"⚠️ メール送信失敗: {email_job.recipient_email} - {str(e)}")

from django.utils.timezone import now, localtime, timedelta
from django.shortcuts import render
from .models import SalesActivity
from .models import Company
from django.db.models import Max

@login_required
def dashboard(request):
    today = localtime(now()).date()
    week_later = today + timedelta(days=7)

    # ✅ 今日の営業予定
    today_sales = SalesActivity.objects.filter(next_action_date__date=today)

    # ✅ 期限超過の営業予定（次回営業予定が過ぎている & 未対応）
    overdue_sales = SalesActivity.objects.filter(next_action_date__date__lt=today)

    # ✅ 今週の営業予定
    upcoming_sales = SalesActivity.objects.filter(next_action_date__date__range=[today, week_later])

    context = {
        'today_sales': today_sales,
        'overdue_sales': overdue_sales,
        'upcoming_sales': upcoming_sales,
    }

    latest_activities = (
        SalesActivity.objects
        .values("company_id")
        .annotate(latest_time=Max("activity_date"))
        .values_list("company_id", flat=True)
    )

    activities = (
        SalesActivity.objects
        .filter(company_id__in=latest_activities)
        .order_by("-next_action_date")
    )

    return render(request, 'dashboard.html', context)

@user_passes_test(lambda u: u.is_superuser or u.username == 'ryuji')
def register(request):
    if request.method == "POST":
        form = SalesPersonRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("saleslist:login")  # 登録後にログインページへ
    else:
        form = SalesPersonRegistrationForm()

    return render(request, "register.html", {"form": form})


def show_urls(request):
    urls = [str(url) for url in get_resolver().url_patterns]
    return JsonResponse({'urls': urls})


from django.contrib.auth.views import LoginView

class CustomLoginView(LoginView):
    template_name = "registration/login.html"


from django.http import HttpResponse
import csv
from django.contrib.auth.decorators import user_passes_test

@user_passes_test(lambda u: u.is_superuser or u.username == 'ryuji')
def export_companies_csv(request):
    # BOM付きUTF-8で文字化けを防止
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename=companies.csv'

    writer = csv.writer(response)
    writer.writerow([
        "店舗名", "電話番号", "FAX番号", "携帯番号", "住所", "法人名", "法人電話番号",
        "法人所在地", "代表者名", "開業日", "許可番号", "大業種", "小業種"
    ])

    for company in Company.objects.all():
        writer.writerow([
            company.name,
            company.phone,
            company.fax,
            company.mobile_phone,
            company.address,
            company.corporation_name,
            company.corporation_phone,
            company.corporation_address,
            company.representative,
            company.established_date.strftime('%Y/%m/%d') if company.established_date else '',
            company.license_number,
            company.industry,
            company.sub_industry,
        ])

    return response


from .models import CompanyEditLog

@login_required
def company_create(request):
    if request.method == "POST":
        form = CompanyForm(request.POST)
        if form.is_valid():
            company = form.save(commit=False)
            company.created_by = request.user

            # ✅ None → 空文字 変換（対象フィールドのみ）
            for field in [
                'fax', 'mobile_phone', 'corporation_phone',
                'corporation_address', 'representative',
                'license_number', 'sub_industry'
            ]:
                if getattr(company, field) is None:
                    setattr(company, field, "")

            company.save()

            # ✅ 新規登録ログを記録
            CompanyEditLog.objects.create(
                company=company,
                user=request.user,
                action="新規登録",
                changed_fields=None
            )

            return redirect("saleslist:company_list")
    else:
        form = CompanyForm()

    return render(request, "company_create.html", {"form": form})


from django.views.decorators.http import require_POST
from .models import CompanyEditLog  # 既にインポート済みならOK


@user_passes_test(lambda u: u.is_superuser or u.username == 'ryuji')
def confirm_delete_filtered_companies(request):
    search_params = request.GET.dict()
    filtered_qs = Company.objects.all()

    if search_params.get("query"):
        filtered_qs = filtered_qs.filter(name__icontains=search_params["query"])

    if search_params.get("phone"):
        phone = search_params["phone"]
        filtered_qs = filtered_qs.filter(
            Q(phone__icontains=phone) |
            Q(corporation_phone__icontains=phone) |
            Q(fax__icontains=phone) |
            Q(mobile_phone__icontains=phone)
        )

    if search_params.get("address"):
        filtered_qs = filtered_qs.filter(address__icontains=search_params["address"])

    if search_params.get("corporation_name"):
        filtered_qs = filtered_qs.filter(corporation_name__icontains=search_params["corporation_name"])

    if search_params.get("industry"):
        filtered_qs = filtered_qs.filter(industry__icontains=search_params["industry"])

    if search_params.get("sub_industry"):
        filtered_qs = filtered_qs.filter(sub_industry__icontains=search_params["sub_industry"])

    if search_params.get("exclude_query"):
        exclude_query = search_params["exclude_query"]
        filtered_qs = filtered_qs.exclude(
            Q(name__icontains=exclude_query) |
            Q(address__icontains=exclude_query) |
            Q(corporation_name__icontains=exclude_query)
        )

    # 営業履歴の条件を含めたい場合（オプション）
    latest_sales_qs = SalesActivity.objects.filter(
        company_id__in=filtered_qs.values("id")
    ).order_by("company_id", "-activity_date")

    # ※必要に応じて further refine

    count = filtered_qs.count()

    context = {
        "companies": filtered_qs,
        "count": count,
        "search_params": search_params,
    }
    return render(request, "confirm_delete.html", context)


from django.views.decorators.csrf import csrf_exempt

@csrf_exempt  # ← 一時的にCSRFチェックを外す（あとで戻す）
@require_POST
@user_passes_test(lambda u: u.is_superuser or u.username == 'ryuji')
def execute_delete_filtered_companies(request):
    print("✅ POST受信:", request.method)
    print("✅ 受信データ:", request.POST)    
    print("✅ execute_delete_filtered_companies が呼び出されました")
    print(f"📥 POST 内容: {request.POST.dict()}")
    search_params = request.POST.dict()
    filtered_qs = Company.objects.all()

    if 'query' in search_params and search_params['query']:
        filtered_qs = filtered_qs.filter(name__icontains=search_params['query'])

    if 'address' in search_params and search_params['address']:
        filtered_qs = filtered_qs.filter(address__icontains=search_params['address'])

    if 'industry' in search_params and search_params['industry']:
        filtered_qs = filtered_qs.filter(industry__icontains=search_params['industry'])


    deleted_ids = list(filtered_qs.values_list('id', flat=True))
    deleted_names = list(filtered_qs.values_list('name', flat=True))

    count = filtered_qs.count()
    filtered_qs.delete()

    # ログ記録
    for company_id, name in zip(deleted_ids, deleted_names):
        CompanyEditLog.objects.create(
            company_id=company_id,
            user=request.user,
            action="一括削除",
            changed_fields={"name": name}
        )

    messages.success(request, f"{count} 件の会社情報を削除しました。")
    return redirect("saleslist:company_list")


@user_passes_test(lambda u: u.is_superuser or u.username == 'ryuji')
def download_filtered_companies_csv(request):
    search_params = request.GET.dict()
    filtered_qs = Company.objects.all()

    if 'query' in search_params and search_params['query']:
        filtered_qs = filtered_qs.filter(name__icontains=search_params['query'])

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename=delete_targets.csv'
    writer = csv.writer(response)
    writer.writerow(["店舗名", "電話番号", "住所", "大業種", "法人名", "許可番号"])

    for company in filtered_qs:
        writer.writerow([company.name, company.phone, company.address, company.industry, company.corporation_name, company.license_number])

    return response


from django.views.decorators.http import require_POST
from django.http import JsonResponse
import json
from .models import Company, SalesActivity
from django.utils.timezone import now
from datetime import datetime
from django.utils.timezone import make_aware

@require_POST
def add_sales_activity_ajax(request, pk):
    try:
        user = request.user
        company = Company.objects.get(pk=pk)
        data = json.loads(request.body)

        print("✅ Ajax受信データ:", data)

        # ✅ 日時変換（文字列 → datetime → aware）
        raw_next = data.get("next_scheduled_date")
        next_action = None
        if raw_next:
            try:
                naive_dt = datetime.strptime(raw_next, "%Y-%m-%dT%H:%M")
                next_action = make_aware(naive_dt)
            except Exception as dt_err:
                print("❌ 日付のパース失敗:", dt_err)

        # ✅ メールアドレスが空なら None
        sales_person_email = data.get("sales_person_email") or None

        # ✅ 登録処理
        activity = SalesActivity.objects.create(
            company=company,
            sales_person=f"{user.last_name}{user.first_name}",
            result=data.get("sales_result"),
            activity_date=now(),
            next_action_date=next_action,
            memo=data.get("memo"),
            sales_person_email=sales_person_email
        )

        # ✅ メール送信スケジューリング
        if next_action and sales_person_email:
            EmailScheduledJob.objects.create(
                recipient_email=sales_person_email,
                subject=f"【リマインド】{company.name} の営業予定",
                message=f"【営業予定リマインド】\n\n"
                        f"店舗名: {company.name}\n"
                        f"営業担当者: {activity.sales_person}\n"
                        f"次回営業予定日: {localtime(next_action).strftime('%Y-%m-%d %H:%M')}\n"
                        f"営業メモ: {activity.memo if activity.memo else 'メモなし'}\n\n"
                        f"この予定を忘れずに対応してください。",
                scheduled_time=next_action
            )

            delay = (next_action - now()).total_seconds()
            Timer(delay, send_scheduled_email).start()

        return JsonResponse({"status": "success"})

    except Exception as e:
        print("❌ Ajax営業履歴登録エラー:", str(e))
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
    


from django.shortcuts import get_object_or_404, render
from django.db.models import Q
from .models import Company, SalesActivity
from django.contrib.auth.decorators import login_required
from django.utils.http import urlencode

@login_required
def company_detail(request, pk):
    company = get_object_or_404(Company, id=pk)

    # GETパラメータ取得（検索・ソート用）
    query = request.GET.get("query", "")
    phone = request.GET.get("phone", "")
    address = request.GET.get("address", "")
    corporation_name = request.GET.get("corporation_name", "")
    sales_person = request.GET.get("sales_person", "")
    result = request.GET.get("result", "")
    sort = request.GET.get("sort", "id")
    order = request.GET.get("order", "asc")

    # 並び順の設定
    sort_key = f"-{sort}" if order == "desc" else sort

    # 検索・フィルタ処理
    qs = Company.objects.all()

    if query:
        qs = qs.filter(
            Q(name__icontains=query) |
            Q(phone__icontains=query) |
            Q(address__icontains=query) |
            Q(corporation_name__icontains=query)
        )
    if phone:
        qs = qs.filter(
            Q(phone__icontains=phone) |
            Q(corporation_phone__icontains=phone) |
            Q(fax__icontains=phone) |
            Q(mobile_phone__icontains=phone)
        )
    if address:
        qs = qs.filter(address__icontains=address)
    if corporation_name:
        qs = qs.filter(corporation_name__icontains=corporation_name)

    # ソート
    qs = qs.order_by(sort_key)

    # 対象ID一覧を取得
    filtered_ids = list(qs.values_list("id", flat=True))
    total_count = Company.objects.count()
    target_count = len(filtered_ids)

    try:
        current_index = filtered_ids.index(pk)
    except ValueError:
        current_index = 0

    prev_company = None
    next_company = None

    if current_index > 0:
        prev_company = Company.objects.get(id=filtered_ids[current_index - 1])
    if current_index < target_count - 1:
        next_company = Company.objects.get(id=filtered_ids[current_index + 1])

    # 営業履歴・営業結果
    sales_activities = SalesActivity.objects.filter(company=company).order_by('-activity_date')
    sales_results = ["再コール", "追わない", "見込", "アポ成立", "受注", "失注", "不通留守", "担当不在"]

    context = {
        "company": company,
        "sales_activities": sales_activities,
        "sales_results": sales_results,
        "prev_company": prev_company,
        "next_company": next_company,
        "record_position": current_index + 1,
        "target_count": target_count,
        "total_count": total_count,
        "query_params": urlencode({
            "query": query,
            "phone": phone,
            "address": address,
            "corporation_name": corporation_name,
            "sales_person": sales_person,
            "result": result,
            "sort": sort,
            "order": order,
        })
    }

    return render(request, "company_detail.html", context)


from django.core.paginator import Paginator
from django.db.models import OuterRef, Subquery, F, Value, CharField
from django.db.models.functions import Cast

@login_required
def company_list(request):
    from django.db.models import OuterRef, Subquery, F, CharField
    from django.db.models.functions import Cast

    # 🔸 検索パラメータの取得
    search_params = {
        "query": request.GET.get("query", "").strip(),
        "phone": request.GET.get("phone", "").strip(),
        "address": request.GET.get("address", "").strip(),
        "corporation_name": request.GET.get("corporation_name", "").strip(),
        "sales_person": request.GET.get("sales_person", "").strip(),
        "result": request.GET.get("result", "").strip(),
    }

    # 🔸 ソートパラメータの取得
    sort = request.GET.get("sort", "id")
    order = request.GET.get("order", "asc")
    sort_map = {
        "activity_date": "latest_activity_date",
        "next_action_date": "latest_next_action_date",
        "sales_person": "latest_sales_person",
        "result": "latest_result",
    }
    sort_column = sort_map.get(sort, sort)
    sort_column = f"-{sort_column}" if order == "desc" else sort_column

    # 🔸 サブクエリで最新営業履歴を取得
    latest_activities = SalesActivity.objects.filter(company=OuterRef("pk")).order_by("-activity_date")

    companies = Company.objects.annotate(
        latest_activity_date=Subquery(latest_activities.values("activity_date")[:1]),
        latest_sales_person=Subquery(
            latest_activities.annotate(
                sales_person_str=Cast(F("sales_person"), output_field=CharField())
            ).values("sales_person_str")[:1]
        ),
        latest_result=Subquery(latest_activities.values("result")[:1]),
        latest_next_action_date=Subquery(latest_activities.values("next_action_date")[:1]),
    )

    # 🔸 フィルタ適用
    from django.db.models import Q
    filters = Q()
    if search_params["query"]:
        filters &= (
            Q(name__icontains=search_params["query"]) |
            Q(phone__icontains=search_params["query"]) |
            Q(address__icontains=search_params["query"]) |
            Q(corporation_name__icontains=search_params["query"])
        )
    if search_params["phone"]:
        filters &= (
            Q(phone__icontains=search_params["phone"]) |
            Q(corporation_phone__icontains=search_params["phone"]) |
            Q(fax__icontains=search_params["phone"]) |
            Q(mobile_phone__icontains=search_params["phone"])
        )
    if search_params["address"]:
        filters &= Q(address__icontains=search_params["address"])
    if search_params["corporation_name"]:
        filters &= Q(corporation_name__icontains=search_params["corporation_name"])
    if search_params["sales_person"]:
        filters &= Q(latest_sales_person__icontains=search_params["sales_person"])
    if search_params["result"]:
        filters &= Q(latest_result=search_params["result"])

    companies = companies.filter(filters)

    # 🔸 並び順
    companies = companies.order_by(sort_column)

    # 🔸 ページネーション
    paginator = Paginator(companies, 100)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # ✅ 件数取得
    total_records = Company.objects.count()
    target_count = companies.count()

    return render(request, "company_list.html", {
        "companies": page_obj,
        "page_obj": page_obj,
        "sort_column": sort,
        "sort_order": order,
        "sales_persons": SalesActivity.objects.values("sales_person").distinct(),
        "results": ["再コール", "追わない", "見込", "アポ成立", "受注", "失注", "不通留守", "担当不在"],
        "total_records": total_records,
        "target_count": target_count,
        **search_params,
    })
