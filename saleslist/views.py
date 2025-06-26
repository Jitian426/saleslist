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
from django.utils import timezone
from .models import UserProfile


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
            sales_activity.activity_date = localtime(now())

            full_name = f"{request.user.last_name}{request.user.first_name}"
            sales_activity.sales_person = full_name if full_name.strip() else request.user.username

            # ✅ メールアドレス自動補完
            input_email = request.POST.get('sales_person_email')
            sales_activity.sales_person_email = input_email or request.user.email

            sales_activity.save()

            # ✅ メール送信スケジュール
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

                delay = (sales_activity.next_action_date - now()).total_seconds()
                Timer(delay, send_scheduled_email).start()

            return redirect("saleslist:company_detail", pk=company.id)
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
from .models import Company
from datetime import timedelta
from django.utils import timezone
from django.db.models import Max
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import SalesActivity

@login_required
def dashboard(request):
    # 会社ごとに最新の営業履歴IDを取得
    latest_activity_ids = (
        SalesActivity.objects
        .values("company_id")
        .annotate(latest_id=Max("id"))
        .values_list("latest_id", flat=True)
    )

    # 今日の営業予定：最新履歴の中から今日の予定だけ
    today_sales = (
        SalesActivity.objects
        .filter(id__in=latest_activity_ids, next_action_date__date=timezone.now().date())
        .select_related("company")
        .order_by("next_action_date")
    )

    # 期限超過の営業予定：最新履歴の中から期限超過しているもの
    overdue_sales = (
        SalesActivity.objects
        .filter(id__in=latest_activity_ids, next_action_date__lt=timezone.now().date())
        .select_related("company")
        .order_by("next_action_date")
    )

    # 今週の営業予定：最新履歴の中から今後7日間の予定
    upcoming_sales = (
        SalesActivity.objects
        .filter(
            id__in=latest_activity_ids,
            next_action_date__date__gte=timezone.now().date(),
            next_action_date__date__lte=(timezone.now().date() + timedelta(days=7))
        )
        .select_related("company")
        .order_by("next_action_date")
    )

    context = {
        "today_sales": today_sales,
        "overdue_sales": overdue_sales,
        "upcoming_sales": upcoming_sales,
    }

    return render(request, "dashboard.html", context)


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
        
        # ✅ メールアドレスが空なら request.user.email を補完
        sales_person_email = data.get("sales_person_email") or user.email

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
from django.db.models import Q, OuterRef, Subquery, F, CharField
from django.utils.http import urlencode
from django.db.models.functions import Cast
from .models import Company, SalesActivity
from .models import Company, SalesActivity, UserProfile
from .forms import UserProfileForm

@login_required
def company_detail(request, pk):
    company = get_object_or_404(Company, id=pk)

    # クエリパラメータ取得
    query = request.GET.get("query", "")
    phone = request.GET.get("phone", "")
    address = request.GET.get("address", "")
    corporation_name = request.GET.get("corporation_name", "")
    industry = request.GET.get("industry", "")
    sub_industry = request.GET.get("sub_industry", "")
    sort = request.GET.get("sort", "id")
    order = request.GET.get("order", "asc")

    # 🔧 複合ソート対応（tie-breaker付き）
    if sort == "established_date":
        sort_keys = ["-established_date", "-id"] if order == "desc" else ["established_date", "id"]
    elif sort == "name":
        sort_keys = ["-name", "-id"] if order == "desc" else ["name", "id"]
    else:
        sort_keys = [f"-{sort}", "-id"] if order == "desc" else [sort, "id"]

    # フィルター構築
    filters = Q()
    if query:
        filters &= (
            Q(name__icontains=query) |
            Q(phone__icontains=query) |
            Q(address__icontains=query) |
            Q(corporation_name__icontains=query)
        )
    if phone:
        filters &= (
            Q(phone__icontains=phone) |
            Q(corporation_phone__icontains=phone) |
            Q(fax__icontains=phone) |
            Q(mobile_phone__icontains=phone)
        )
    if address:
        filters &= Q(address__icontains=address)
    if corporation_name:
        filters &= Q(corporation_name__icontains=corporation_name)
    if industry:
        filters &= Q(industry__icontains=industry)
    if sub_industry:
        filters &= Q(sub_industry__icontains=sub_industry)

    # クエリセット取得（annotateなし、純粋なCompany + 複合ソート）
    company_list = list(Company.objects.filter(filters).order_by(*sort_keys))

    try:
        index = [c.id for c in company_list].index(company.id)
    except ValueError:
        index = 0

    prev_company = company_list[index - 1] if index > 0 else None
    next_company = company_list[index + 1] if index < len(company_list) - 1 else None

    # 営業履歴・営業結果
    sales_activities = SalesActivity.objects.filter(company=company).order_by("-activity_date")
    # 営業履歴・営業結果（順番を固定）
    sales_results = [
        "再コール", "見込", "アポ成立", "受注", "失注", "追わない", "担当不在", "不通留守"
    ]

    # --- ユーザー情報フォーム（最新履歴が「受注」かつ管理者のみ） ---
    latest_result = sales_activities.first().result if sales_activities.exists() else None
    show_user_form = latest_result == "受注" and request.user.is_superuser

    user_profiles = UserProfile.objects.filter(company=company).order_by("-created_at")

    if request.method == "POST" and show_user_form:
        form = UserProfileForm(request.POST)
        if form.is_valid():
            user_profile = form.save(commit=False)
            user_profile.company = company  # ← 必須
            user_profile.save()
            messages.success(request, "✅ ユーザー情報を保存しました。")
            return redirect("saleslist:company_detail", pk=company.id)
    else:
        form = UserProfileForm() if show_user_form else None

    # --- パラメータ引継ぎ ---
    query_params = urlencode({
        "query": query,
        "phone": phone,
        "address": address,
        "corporation_name": corporation_name,
        "industry": industry,
        "sub_industry": sub_industry,
        "sort": sort,
        "order": order,
    })

    return render(request, "company_detail.html", {
        "company": company,
        "sales_activities": sales_activities,
        "sales_results": sales_results,
        "prev_company": prev_company,
        "next_company": next_company,
        "record_position": index + 1,
        "target_count": len(company_list),
        "total_count": Company.objects.count(),
        "query_params": query_params,
        "show_user_form": show_user_form,
        "user_form": form,
        "user_profiles": user_profiles,
    })



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
        "industry": request.GET.get("industry", "").strip(),  # ←追加
        "sub_industry": request.GET.get("sub_industry", "").strip(),  # ←追加
        "start_date": request.GET.get("start_date", "").strip(),  # ←追加
        "end_date": request.GET.get("end_date", "").strip(),  # ←追加
        "next_action_start": request.GET.get("next_action_start", "").strip(),  # ←追加
        "next_action_end": request.GET.get("next_action_end", "").strip(),  # ←追加
    }

    # 🔸 ソートパラメータの取得
    sort = request.GET.getlist("sort")[-1] if request.GET.getlist("sort") else "id"
    order = request.GET.getlist("order")[-1] if request.GET.getlist("order") else "asc"
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
    if search_params["industry"]:
        filters &= Q(industry__icontains=search_params["industry"])
    if search_params["sub_industry"]:
        filters &= Q(sub_industry__icontains=search_params["sub_industry"])

    if search_params["start_date"]:
        filters &= Q(latest_activity_date__date__gte=search_params["start_date"])
    if search_params["end_date"]:
        filters &= Q(latest_activity_date__date__lte=search_params["end_date"])
    if search_params["next_action_start"]:
        filters &= Q(latest_next_action_date__date__gte=search_params["next_action_start"])
    if search_params["next_action_end"]:
        filters &= Q(latest_next_action_date__date__lte=search_params["next_action_end"])


    companies = companies.filter(filters)

    # ✅ 並び順：複合キーによる安定化（company_detail との一致）
    if sort in ["established_date", "name", "address", "corporation_name"]:
        if order == "desc":
            companies = companies.order_by(f"-{sort}", "-id")
        else:
            companies = companies.order_by(sort, "id")
    else:
        # annotate 項目などは単独ソート（元のまま）
        companies = companies.order_by(sort_column)


    # 🔸 ページネーション
    paginator = Paginator(companies, 100)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # ✅ 件数取得
    total_records = Company.objects.count()
    target_count = companies.count()

    # ✅ next_order の計算を追加（ここがポイント！）
    next_order = "desc" if order == "asc" else "asc"

    return render(request, "company_list.html", {
        "companies": page_obj,
        "page_obj": page_obj,
        "sort_column": sort,
        "sort_order": order,
        "next_order": next_order,  # ← これを追加！
        "sales_persons": SalesActivity.objects.values("sales_person").distinct(),
        "results": ["再コール", "追わない", "見込", "アポ成立", "受注", "失注", "不通留守", "担当不在"],
        "total_records": total_records,
        "target_count": target_count,
        **search_params,
    })

from django.views.decorators.http import require_POST
from django.contrib import messages

@login_required
@require_POST
def update_company_note(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    company.note = request.POST.get("note", "")
    company.save()
    messages.success(request, "✅ メモを保存しました。")
    return redirect("saleslist:company_detail", pk=company.id)


from django.db import models
from django.utils import timezone
from datetime import date

from django.contrib.auth.decorators import login_required
from .models import UserProfile

@login_required
def user_list(request):
    users = UserProfile.objects.select_related("company").filter(
        Q(company__isnull=False) & (
            Q(customer_name__isnull=False) & ~Q(customer_name__exact="") |
            Q(order_date__isnull=False)
        )
    ).order_by("-order_date", "customer_name")[:100]

    user_data = [
        {
            "id": user.company.id,
            "customer_name": user.customer_name,
            "phone": user.company.phone,
            "address": user.company.address,
            "order_date": user.order_date,
            "shop_name": user.shop_name,
            "product": user.product,
            "appointment_staff": user.appointment_staff,
            "sales_staff": user.sales_staff,
        }
        for user in users
    ]

    return render(request, "user_list.html", {
        "users": user_data
    })


from django.contrib.auth.decorators import login_required
from .models import Company, UserProfile
from .forms import UserProfileForm

@login_required
def add_user_profile(request, company_id):
    company = get_object_or_404(Company, id=company_id)

    # 直近の既存ユーザー情報を取得（あれば）
    latest_profile = (
        UserProfile.objects.filter(company=company)
        .order_by("-created_at")
        .first()
    )

    if request.method == "POST":
        form = UserProfileForm(request.POST)
        if form.is_valid():
            new_profile = form.save(commit=False)
            new_profile.company = company
            new_profile.save()
            messages.success(request, "✅ 新しいユーザー情報を追加しました。")
            return redirect("saleslist:company_detail", pk=company.id)
    else:
        if latest_profile:
            # 既存の最新データから初期値をセット（必要項目のみ）
            initial_data = {
                field.name: getattr(latest_profile, field.name)
                for field in UserProfile._meta.fields
                if field.name in [
                    "customer_name_kana", "customer_name", "address",
                    "representative_name_kana", "representative_name", "representative_phone", "representative_birthday",
                    "contact_name_kana", "contact_name", "contact_phone"
                ]
            }
            form = UserProfileForm(initial=initial_data)
        else:
            form = UserProfileForm()

    return render(request, "add_user_profile.html", {
        "form": form,
        "company": company
    })


from django.shortcuts import get_object_or_404

@login_required
def edit_user_profile(request, pk):
    user_profile = get_object_or_404(UserProfile, pk=pk)
    company = user_profile.company

    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=user_profile)
        if form.is_valid():
            form.save()
            messages.success(request, "✅ ユーザー情報を更新しました。")
            return redirect("saleslist:company_detail", pk=company.id)
    else:
        form = UserProfileForm(instance=user_profile)

    return render(request, "edit_user_profile.html", {
        "form": form,
        "company": company,
        "user_profile": user_profile,
    })
