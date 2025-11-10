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
from django.urls import reverse
from django.db import transaction


@user_passes_test(lambda u: u.is_superuser or u.username == 'ryuji')
def upload_csv(request):
    if request.method == "POST":
        csv_file = request.FILES.get("csv_file")

        if not csv_file:
            messages.error(request, 'ファイルが選択されていません')
            return redirect('saleslist:upload_csv')

        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'CSVファイルをアップロードしてください')
            return redirect('saleslist:upload_csv')

        try:
            decoded_file = io.StringIO(csv_file.read().decode('utf-8-sig'))
            reader = csv.DictReader(decoded_file)

            expected_columns = [
                "店舗名", "電話番号", "FAX番号", "携帯番号", "住所", "法人名", "法人電話番号",
                "法人所在地", "代表者名", "開業日", "許可番号", "大業種", "小業種", "営業担当者", "営業結果", "コメント"
            ]
            if list(reader.fieldnames) != expected_columns:
                messages.error(request, f'CSVのヘッダーが正しくありません。\n期待: {expected_columns}\n実際: {reader.fieldnames}')
                return redirect('saleslist:upload_csv')

            companies_to_create = []
            activities_to_create = []
            existing_keys = set(Company.objects.values_list("name", "phone", "address"))

            for row in reader:
                name = row["店舗名"].strip()
                phone = row["電話番号"].strip()
                address = row["住所"].strip()

                # 名前と住所があれば登録対象（電話番号は空欄でも可）
                if not name or not address:
                    continue

                key = (name, phone, address)

                if key in existing_keys:
                    company = Company.objects.filter(name=name, phone=phone, address=address).first()
                    if not company:
                        continue  # 念のため安全に
                else:
                    formatted_date = None
                    if row["開業日"]:
                        try:
                            formatted_date = datetime.strptime(row["開業日"], '%Y/%m/%d').date()
                        except ValueError:
                            try:
                                formatted_date = datetime.strptime(row["開業日"], '%Y-%m-%d').date()
                            except ValueError:
                                continue  # スキップ

                    company = Company(
                        name=name,
                        phone=phone,
                        address=address,
                        fax=row.get("FAX番号", "").strip(),
                        mobile_phone=row.get("携帯番号", "").strip(),
                        corporation_name=row.get("法人名", "").strip(),
                        corporation_phone=row.get("法人電話番号", "").strip(),
                        corporation_address=row.get("法人所在地", "").strip(),
                        representative=row.get("代表者名", "").strip(),
                        established_date=formatted_date,
                        license_number=row.get("許可番号", "").strip(),
                        industry=row.get("大業種", "").strip(),
                        sub_industry=row.get("小業種", "").strip(),
                    )
                    companies_to_create.append(company)
                    existing_keys.add(key)

            # ✅ 一括登録（200件ずつ）
            created_companies = []
            with transaction.atomic():
                for i in range(0, len(companies_to_create), 200):
                    created = Company.objects.bulk_create(companies_to_create[i:i+200])
                    created_companies.extend(created)

            # ✅ 全Company取得しなおしてMap化（キー：name+phone+address）
            company_map = {
                (c.name, c.phone, c.address): c
                for c in Company.objects.filter(
                    name__in=[c.name for c in companies_to_create]
                )
            }

            # ファイルを先頭に戻して再走査
            decoded_file.seek(0)
            next(reader)

            for row in reader:
                name = row["店舗名"].strip()
                phone = row["電話番号"].strip()
                address = row["住所"].strip()
                if not name or not phone or not address:
                    continue
                key = (name, phone, address)
                company = company_map.get(key)
                if not company:
                    company = Company.objects.filter(name=name, phone=phone, address=address).first()
                if company and row.get("営業結果"):
                    activities_to_create.append(SalesActivity(
                        company=company,
                        sales_person=row.get("営業担当者", "CSVインポート").strip(),
                        result=row.get("営業結果", "見込"),
                        memo=row.get("コメント", ""),
                        next_action_date=None
                    ))

            # ✅ 営業履歴を一括登録
            with transaction.atomic():
                for i in range(0, len(activities_to_create), 200):
                    SalesActivity.objects.bulk_create(activities_to_create[i:i+200])

            messages.success(request, f'{len(companies_to_create)} 件の会社と {len(activities_to_create)} 件の営業履歴を登録しました。')

        except Exception as e:
            messages.error(request, f'エラーが発生しました: {str(e)}')

        return redirect('saleslist:upload_csv')

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
    


from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, OuterRef, Subquery, F, CharField
from django.utils.http import urlencode
from django.db.models.functions import Cast
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from urllib.parse import urlencode
from .models import Company, SalesActivity, UserProfile, ImageLink
from .forms import UserProfileForm, ImageLinkForm

@login_required
def company_detail(request, pk):
    allowed_sorts = {"latest_activity_date", "latest_result", "latest_sales_person", "latest_next_action_date"}
    
    # ✅ 不正パラメータのクリーンアップ（既存仕様を維持）
    if (
        ("sort" in request.GET and request.GET["sort"] not in allowed_sorts)
        or "activity_date" in request.GET
        or "result" in request.GET
        or "sales_person" in request.GET
        or "next_action_date" in request.GET
    ):
        return redirect(reverse("saleslist:company_detail", args=[pk]))
    
    company = get_object_or_404(Company, id=pk)

    # 🔎 クエリパラメータ
    query = request.GET.get("query", "")
    phone = request.GET.get("phone", "")
    address = request.GET.get("address", "")
    corporation_name = request.GET.get("corporation_name", "")
    industry = request.GET.get("industry", "")
    sub_industry = request.GET.get("sub_industry", "")
    sort = request.GET.get("sort", "id")
    order = request.GET.get("order", "asc")

    # 🔧 複合ソートキー
    if sort == "established_date":
        sort_keys = ["-established_date", "-id"] if order == "desc" else ["established_date", "id"]
    elif sort == "name":
        sort_keys = ["-name", "-id"] if order == "desc" else ["name", "id"]
    else:
        sort_keys = [f"-{sort}", "-id"] if order == "desc" else [sort, "id"]

    # 🔍 フィルター構築
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

    # ✅ company.id だけを取得しメモリを節約
    filtered_ids = list(Company.objects.filter(filters).order_by(*sort_keys).values_list("id", flat=True))

    try:
        index = filtered_ids.index(company.id)
    except ValueError:
        index = 0

    prev_company = Company.objects.get(id=filtered_ids[index - 1]) if index > 0 else None
    next_company = Company.objects.get(id=filtered_ids[index + 1]) if index < len(filtered_ids) - 1 else None

    # ✅ 営業履歴
    sales_activities = SalesActivity.objects.filter(company=company).order_by("-activity_date")
    sales_results = [
        "再コール", "見込", "アポ成立", "受注", "失注", "追わない", "担当不在", "不通留守"
    ]

    # ✅ ユーザー情報フォームの表示条件
    latest_result = sales_activities.first().result if sales_activities.exists() else None
    show_user_form = latest_result == "受注" and request.user.is_superuser
    user_profiles = UserProfile.objects.filter(company=company).order_by("-created_at")
    can_view_user_info = request.user.groups.filter(name="user_info_viewers").exists()

    # -----------------------------
    # 🆕 画像リンクの追加/削除（最初に処理）
    # -----------------------------
    image_links = company.image_links.all()
    image_link_form = ImageLinkForm()

    if request.method == "POST":
        action = request.POST.get("action")

        # 画像リンク 追加
        if action == "add_image_link":
            image_link_form = ImageLinkForm(request.POST)
            if image_link_form.is_valid():
                obj = image_link_form.save(commit=False)
                obj.company = company
                obj.save()
                messages.success(request, "画像リンクを追加しました。")
            else:
                messages.error(request, "画像リンクの追加に失敗しました。入力内容をご確認ください。")
            # クエリを保ったまま自分へ
            return redirect(request.get_full_path())

        # 画像リンク 削除
        if action == "delete_image_link":
            link_id = request.POST.get("link_id")
            link = get_object_or_404(ImageLink, pk=link_id, company=company)
            link.delete()
            messages.success(request, "画像リンクを削除しました。")
            return redirect(request.get_full_path())

        # 受注ユーザー情報 登録（既存仕様を維持）
        if show_user_form:
            form = UserProfileForm(request.POST)
            if form.is_valid():
                user_profile = form.save(commit=False)
                user_profile.company = company
                user_profile.save()
                messages.success(request, "✅ ユーザー情報を保存しました。")
                return redirect("saleslist:company_detail", pk=company.id)
            else:
                # バリデ NG時にフォームを返す
                pass

    # 受注ユーザー情報フォーム（GET時）
    form = UserProfileForm() if show_user_form else None

    # パラメータ引継ぎ
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
        "target_count": len(filtered_ids),
        "total_count": Company.objects.count(),
        "query_params": query_params,
        "show_user_form": show_user_form,
        "user_form": form,
        "user_profiles": user_profiles,
        "can_view_user_info": can_view_user_info,
        "image_links": image_links,
        "image_link_form": image_link_form,
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
        "license_number": request.GET.get("license_number", "").strip(),
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
    ).only(
        'id', 'name', 'phone', 'mobile_phone', 'address',
        'corporation_name', 'established_date',
        'industry', 'sub_industry',
        'license_number',                             # ★表示用に追加
    )

    # 🔸 フィルタ適用
    from django.db.models import Q
    filters = Q()
    if search_params["query"]:
        filters &= (
            Q(name__icontains=search_params["query"]) |
            Q(phone__icontains=search_params["query"]) |
            Q(address__icontains=search_params["query"]) |
            Q(corporation_name__icontains=search_params["query"]) |
            Q(license_number__icontains=search_params["query"])          # ←クイック検索にも含めたいなら追加（任意）
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
    if search_params["license_number"]:                                  # ★追加
        filters &= Q(license_number__icontains=search_params["license_number"])

    if search_params["start_date"]:
        filters &= Q(latest_activity_date__date__gte=search_params["start_date"])
    if search_params["end_date"]:
        filters &= Q(latest_activity_date__date__lte=search_params["end_date"])
    if search_params["next_action_start"]:
        filters &= Q(latest_next_action_date__date__gte=search_params["next_action_start"])
    if search_params["next_action_end"]:
        filters &= Q(latest_next_action_date__date__lte=search_params["next_action_end"])

    # 🔸 フィルター適用
    companies = companies.filter(filters)

    # 🔸 並び順を定義（スライス前に順序決定）
    if sort in ["established_date", "name", "address", "corporation_name"]:
        if order == "desc":
            companies = companies.order_by(f"-{sort}", "-id")
        else:
            companies = companies.order_by(sort, "id")
    else:
        companies = companies.order_by(sort_column)

    # ✅ 初期表示だけ最大1000件に制限（検索条件が空のとき）
    if not any(search_params.values()):
        companies = companies[:1000]


    # 🔸 ページネーション
    paginator = Paginator(companies, 100)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # ✅ 件数取得
    total_records = Company.objects.count()
    target_count = companies.count()

    # ✅ next_order の計算を追加（ここがポイント！）
    next_order = "desc" if order == "asc" else "asc"

    can_view_user_info = request.user.groups.filter(name="user_info_viewers").exists()

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
        "can_view_user_info": can_view_user_info,
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

    can_view_user_info = request.user.groups.filter(name="user_info_viewers").exists()

    return render(request, "user_list.html", {
        "users": user_data,
        "can_view_user_info": can_view_user_info,
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

from django.shortcuts import render
from django.db.models import Q
from .models import UserProfile
from datetime import datetime
from django.shortcuts import redirect
from django.contrib import messages
from .forms import UserProgressForm
from django.db.models import F
from django.db.models.functions import Coalesce
from django.http import HttpResponseRedirect
from urllib.parse import urlencode
from django.urls import reverse
from django.db.models.expressions import OrderBy
from django.db.models import Q, F, Value, IntegerField
from datetime import datetime, date

def user_progress_view(request):
    # ① GETパラメータ取得
    month_str = request.GET.get("month", "")
    if not month_str:
        # 月指定がない場合は現在年月を初期値に
        month_str = datetime.today().strftime("%Y-%m")

    year, month = map(int, month_str.split("-"))
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)
    
    customer = request.GET.get("customer", "")
    appointment_staff = request.GET.get("appointment_staff", "")
    sales_staff = request.GET.get("sales_staff", "")
    product = request.GET.get("product", "")
    plan = request.GET.get("plan", "")
    query = request.GET.get("q", "")

    # ② ベースクエリ
    profiles = UserProfile.objects.all()

    # ③ 絞り込み
    if customer:
        profiles = profiles.filter(customer_name__icontains=customer)
    if appointment_staff:
        profiles = profiles.filter(appointment_staff__icontains=appointment_staff)
    if sales_staff:
        profiles = profiles.filter(sales_staff__icontains=sales_staff)
    if product:
        profiles = profiles.filter(product__icontains=product)
    if plan:
        profiles = profiles.filter(plan__icontains=plan)
    if query:
        profiles = profiles.filter(
            Q(customer_name__icontains=query) |
            Q(appointment_staff__icontains=query) |
            Q(sales_staff__icontains=query) |
            Q(product__icontains=query) |
            Q(plan__icontains=query)
        )

    # ④ 月別絞り込み（当月受注 or 完了、もしくは過去未完了）
    if month_str:
        try:
            year, month = map(int, month_str.split("-"))
            start_date = datetime(year, month, 1).date()
            if month == 12:
                end_date = datetime(year + 1, 1, 1).date()
            else:
                end_date = datetime(year, month + 1, 1).date()

            profiles = profiles.filter(
                Q(order_date__range=(start_date, end_date)) |
                Q(complete_date__range=(start_date, end_date)) |
                Q(order_date__lt=start_date, complete_date__isnull=True)
            )
        except:
            pass

    if request.method == "POST":
        profile_id = request.POST.get("profile_id")
        new_progress = request.POST.get("progress")
    
        try:
            profile = UserProfile.objects.get(id=profile_id)
            profile.progress = new_progress
            profile.save()
            messages.success(request, f"✅ {profile.customer_name} の進捗を「{new_progress}」に更新しました。")
        except UserProfile.DoesNotExist:
            messages.error(request, "❌ 該当ユーザーが見つかりませんでした。")

        # パラメータ保持してリダイレクト
        base_url = reverse('saleslist:user_progress')
        query_string = urlencode(request.GET)
        url = f"{base_url}?{query_string}" if query_string else base_url
        return HttpResponseRedirect(url)


    # ⑤ 並び順
    profiles = profiles.annotate(
        has_order_date=Coalesce('order_date', None)
    ).order_by(F('has_order_date').desc(nulls_last=True), F('order_date').desc(nulls_last=True))

    progress_choices = ["発注前", "後確待ち", "設置待ち", "マッチング待ち", "完了"]

    # ⑥ 完了案件だけ抽出
    complete_profiles = profiles.filter(progress="完了")

    # ✅ 完了粗利 → 完了日が当月内の案件に限定
    complete_profiles_in_month = complete_profiles.filter(
        complete_date__gte=start_date,
        complete_date__lt=end_date
    )

    gross_profit_sum = sum(
        (p.gross_profit or 0) - (p.cashback or 0) - (p.commission or 0)
        for p in complete_profiles_in_month
    )

    # ⑦ 完了見込粗利（全検索結果対象）
    expected_gross_profit_sum = sum(
        (p.gross_profit or 0) - (p.cashback or 0) - (p.commission or 0)
        for p in profiles
    )

    context = {
        "profiles": profiles,
        "month": month_str,
        "customer": customer,
        "appointment_staff": appointment_staff,
        "sales_staff": sales_staff,
        "product": product,
        "plan": plan,
        "gross_profit_sum": gross_profit_sum,
        "expected_gross_profit_sum": expected_gross_profit_sum,
        "progress_choices": progress_choices,
    }

    return render(request, "user_progress.html", context)


# ✅ views.py に追加
import csv
from django.http import HttpResponse
from .models import UserProfile
from datetime import datetime
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required

@login_required
def export_completed_progress_csv(request):
    # GETパラメータ取得
    month_str = request.GET.get("month", "")
    customer = request.GET.get("customer", "")
    appointment_staff = request.GET.get("appointment_staff", "")
    sales_staff = request.GET.get("sales_staff", "")
    product = request.GET.get("product", "")
    plan = request.GET.get("plan", "")

    # クエリ作成
    profiles = UserProfile.objects.filter(progress="完了")

    if customer:
        profiles = profiles.filter(customer_name__icontains=customer)
    if appointment_staff:
        profiles = profiles.filter(appointment_staff__icontains=appointment_staff)
    if sales_staff:
        profiles = profiles.filter(sales_staff__icontains=sales_staff)
    if product:
        profiles = profiles.filter(product__icontains=product)
    if plan:
        profiles = profiles.filter(plan__icontains=plan)

    # 月フィルタ
    if month_str:
        try:
            year, month = map(int, month_str.split("-"))
            start_date = datetime(year, month, 1).date()
            end_date = datetime(year + (month // 12), (month % 12) + 1, 1).date()
            profiles = profiles.filter(complete_date__gte=start_date, complete_date__lt=end_date)
        except:
            pass

    # 完了粗利合計
    gross_profit_sum = sum(
        (p.gross_profit or 0) - (p.cashback or 0) - (p.commission or 0)
        for p in profiles
    )

    # CSV作成
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="completed_progress.csv"'

    writer = csv.writer(response)
    writer.writerow([f"合計報酬：{gross_profit_sum} 円"])
    writer.writerow([])  # 空行

    headers = [
        "受注日", "完了日", "顧客名", "アポ担当", "営業担当", "獲得商材",
        "獲得プラン", "契約容量", "獲得使用量", "粗利", "キャッシュバック", "手数料"
    ]
    writer.writerow(headers)

    for p in profiles:
        writer.writerow([
            p.order_date,
            p.complete_date,
            p.customer_name,
            p.appointment_staff,
            p.sales_staff,
            p.product,
            p.plan,
            p.capacity,
            p.acquired_usage,
            p.gross_profit,
            p.cashback,
            p.commission,
        ])

    return response


# ✅ urls.py に追加
# path('user_progress/export_completed/', views.export_completed_progress_csv, name='export_completed_progress'),


# ✅ user_progress.html にダウンロードボタン追加
# <a href="{% url 'saleslist:export_completed_progress' %}?month={{ month }}&customer={{ customer }}&appointment_staff={{ appointment_staff }}&sales_staff={{ sales_staff }}&product={{ product }}&plan={{ plan }}" class="btn btn-success mb-3">
#   完了データをCSV出力
# </a>


from django.shortcuts import render
from django.db.models import Count, Q, Max
from .models import SalesActivity, Company
from .forms import KPIFilterForm
from datetime import datetime

def kpi_view(request):
    form = KPIFilterForm(request.GET or None)
    activities = SalesActivity.objects.all()

    # 🟢 初期化しておく（ここが重要）
    sales_person = None
    date = None
    month = None
    
    # フィルター処理
    if form.is_valid():
        sales_person = form.cleaned_data.get('sales_person')
        date = form.cleaned_data.get('date')
        month = form.cleaned_data.get('month')

        if sales_person:
            sales_person = sales_person.strip()
            activities = activities.filter(sales_person=sales_person)
        if date:
            activities = activities.filter(activity_date=date)
        elif month:
            activities = activities.filter(activity_date__year=month.year, activity_date__month=month.month)


    total_calls = activities.count()
    valid_calls = activities.filter(result__in=["再コール", "見込", "アポ成立", "追わない", "担当者不在", "不通留守"]).count()
    decision_makers = activities.filter(result__in=["再コール", "見込", "アポ成立", "追わない"]).count()
    prospect_count = activities.filter(result="見込").count()
    appointment_count = activities.filter(result="アポ成立").count()

    # 現状見込数（最新の履歴が「見込」の会社）
    latest_results = (
        SalesActivity.objects
        .order_by('company', '-activity_date')
        .distinct('company')
    )
    if sales_person:
        latest_results = latest_results.filter(sales_person=sales_person)
    prospect_now_count = latest_results.filter(result="見込").count()

    # 割合
    decision_rate = round(decision_makers / total_calls * 100, 1) if total_calls else 0
    appointment_rate = round(appointment_count / valid_calls * 100, 1) if valid_calls else 0

    context = {
        "form": form,
        "kpi": {
            "コール数": total_calls,
            "有効コール数": valid_calls,
            "決裁者数": decision_makers,
            "見込件数": prospect_count,
            "アポ件数": appointment_count,
            "現状見込数": prospect_now_count,
            "決裁者率": f"{decision_rate}%",
            "アポ率": f"{appointment_rate}%",
        },
    }
    return render(request, "kpi.html", context)


from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponse
import csv
from .models import Company, SalesActivity


# superuser または username='ryuji' のみ許可
def is_superuser_or_ryuji(user):
    return user.is_superuser or user.username == 'ryuji'


@user_passes_test(is_superuser_or_ryuji)
def export_companies_csv(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="companies_backup.csv"'

    writer = csv.writer(response)
    writer.writerow(['ID', '店舗名', '店舗電話番号', '住所', '法人名', '代表者名', '大業種', '小業種'])

    companies = Company.objects.all()
    for company in companies:
        writer.writerow([
            company.id,
            company.name,
            company.phone,
            company.address,
            company.corporation_name,
            company.representative,
            company.industry,
            company.sub_industry
        ])

    return response


@user_passes_test(is_superuser_or_ryuji)
def export_salesactivities_csv(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="salesactivities_backup.csv"'

    writer = csv.writer(response)
    writer.writerow(['営業ID', 'company_id', '店舗名', '活動日', '営業結果', '営業担当者', 'メモ', '次回営業予定日'])

    activities = SalesActivity.objects.select_related('company').only(
        'id', 'company__id', 'company__name', 'activity_date',
        'result', 'sales_person', 'memo', 'next_action_date'
    )

    for activity in activities:
        writer.writerow([
            activity.id,
            activity.company.id if activity.company else '',
            activity.company.name if activity.company else '',
            activity.activity_date,
            activity.result,
            activity.sales_person,
            activity.memo,
            activity.next_action_date,
        ])

    return response


from datetime import date
from django.db.models import (
    Count, Sum, Case, When, IntegerField, FloatField, Value, F, ExpressionWrapper
)
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils import timezone

from .models import SalesActivity  # activity_date(DateTime/Date), sales_person(CharField), result(CharField)

# KPIの分類定義（71番メモの定義に合わせる）
HIT_RESULTS = ["再コール", "見込", "アポ成立", "追わない", "担当不在"]  # ← ユーザー定義の有効コール（不通留守を除外）
DECISION_CONTACT_RESULTS = ["再コール", "見込", "アポ成立"]

def _selected_date_from_request(request):
    qs_date = request.GET.get("d")
    if qs_date:
        try:
            y, m, d = map(int, qs_date.split("-"))
            return date(y, m, d)
        except Exception:
            pass
    jst_now = timezone.localtime(timezone.now())
    return jst_now.date()

def daily_kpi(request):
    target_date = _selected_date_from_request(request)

    qs = SalesActivity.objects.filter(activity_date__date=target_date)
    person = Coalesce("sales_person", Value(""))

    calls = Count("id")
    hits = Sum(Case(When(result__in=HIT_RESULTS, then=1), default=0, output_field=IntegerField()))
    decisions = Sum(Case(When(result__in=DECISION_CONTACT_RESULTS, then=1), default=0, output_field=IntegerField()))
    mikomi = Sum(Case(When(result="見込", then=1), default=0, output_field=IntegerField()))
    apo = Sum(Case(When(result="アポ成立", then=1), default=0, output_field=IntegerField()))

    agg = (
        qs.values(name=person)
        .annotate(calls=calls, hits=hits, decisions=decisions, mikomi=mikomi, apo=apo)
        .order_by(F("calls").desc(nulls_last=True), F("name").asc(nulls_last=True))
    )

    rows = []
    totals = {"calls": 0, "hits": 0, "decisions": 0, "mikomi": 0, "apo": 0}
    for r in agg:
        c = r["calls"] or 0
        h = r["hits"] or 0
        dcnt = r["decisions"] or 0
        m = r["mikomi"] or 0
        a = r["apo"] or 0
        rows.append({
            "name": r["name"] or "（未指定）",
            "calls": c,
            "hits": h,
            "decisions": dcnt,
            "mikomi": m,
            "apo": a,
            "hit_rate": (h / c * 100) if c else 0.0,
            "decision_rate": (dcnt / c * 100) if c else 0.0,
            "mikomi_rate": (m / c * 100) if c else 0.0,
            "apo_rate": (a / c * 100) if c else 0.0,
        })
        totals["calls"] += c
        totals["hits"] += h
        totals["decisions"] += dcnt
        totals["mikomi"] += m
        totals["apo"] += a

    t_calls = totals["calls"] or 0
    totals["hit_rate"] = (totals["hits"] / t_calls * 100) if t_calls else 0.0
    totals["decision_rate"] = (totals["decisions"] / t_calls * 100) if t_calls else 0.0
    totals["mikomi_rate"] = (totals["mikomi"] / t_calls * 100) if t_calls else 0.0
    totals["apo_rate"] = (totals["apo"] / t_calls * 100) if t_calls else 0.0

    context = {"target_date": target_date, "rows": rows, "totals": totals}
    return render(request, "kpi/daily.html", context)


from datetime import date
from calendar import monthrange
from django.db.models import Count, Sum, Case, When, IntegerField, Value, F
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.shortcuts import render

from .models import SalesActivity

HIT_RESULTS = ["再コール", "見込", "アポ成立", "追わない", "担当不在"]
DECISION_CONTACT_RESULTS = ["再コール", "見込", "アポ成立"]  # ← 修正後の定義

def _selected_year_month(request):
    # ?ym=YYYY-MM 形式。未指定ならJSTの今月
    ym = request.GET.get("ym")
    if ym:
        try:
            y, m = map(int, ym.split("-"))
            return y, m
        except Exception:
            pass
    jst = timezone.localtime()
    return jst.year, jst.month

def monthly_kpi(request):
    year, month = _selected_year_month(request)
    start = date(year, month, 1)
    last_day = monthrange(year, month)[1]
    end = date(year, month, last_day)

    qs = SalesActivity.objects.filter(activity_date__date__range=(start, end))
    person = Coalesce("sales_person", Value(""))

    # ---- 集計定義 ----
    calls = Count("id")
    hits = Sum(Case(When(result__in=HIT_RESULTS, then=1), default=0, output_field=IntegerField()))
    decisions = Sum(Case(When(result__in=DECISION_CONTACT_RESULTS, then=1), default=0, output_field=IntegerField()))
    mikomi = Sum(Case(When(result="見込", then=1), default=0, output_field=IntegerField()))
    apo = Sum(Case(When(result="アポ成立", then=1), default=0, output_field=IntegerField()))
    ju = Sum(Case(When(result="受注", then=1), default=0, output_field=IntegerField()))
    ftsu = Sum(Case(When(result="不通留守", then=1), default=0, output_field=IntegerField()))
    owanai = Sum(Case(When(result="追わない", then=1), default=0, output_field=IntegerField()))

    # ---- 集計 ----
    agg = (
        qs.values(name=person)
          .annotate(calls=calls, hits=hits, decisions=decisions, mikomi=mikomi, apo=apo, ju=ju, ftsu=ftsu, owanai=owanai)
          .order_by(F("calls").desc(nulls_last=True), F("name").asc(nulls_last=True))
    )

    rows, totals = [], {"calls":0,"hits":0,"decisions":0,"mikomi":0,"apo":0,"ju":0,"nc_owanai":0}
    for r in agg:
        c  = r["calls"] or 0
        h  = r["hits"] or 0
        d  = r["decisions"] or 0
        m  = r["mikomi"] or 0
        a  = r["apo"] or 0
        ju = r["ju"] or 0
        nc_ow = (r["ftsu"] or 0) + (r["owanai"] or 0)

        rows.append({
            "name": r["name"] or "（未指定）",
            "calls": c,
            "hits": h,
            "decisions": d,
            "mikomi": m,
            "apo": a,
            "ju": ju,
            "ju_rate": (ju / a * 100) if a else 0.0,  # 受注率 = 受注 / アポ成立
            "nc_owanai": nc_ow,
            "hit_rate": (h/c*100) if c else 0.0,
            "decision_rate": (d/c*100) if c else 0.0,
            "mikomi_rate": (m/c*100) if c else 0.0,
            "apo_rate": (a/c*100) if c else 0.0,
        })

        totals["calls"]     += c
        totals["hits"]      += h
        totals["decisions"] += d
        totals["mikomi"]    += m
        totals["apo"]       += a
        totals["ju"]        += ju
        totals["nc_owanai"] += nc_ow

    t = totals["calls"] or 0
    totals.update({
        "hit_rate": (totals["hits"]/t*100) if t else 0.0,
        "decision_rate": (totals["decisions"]/t*100) if t else 0.0,
        "mikomi_rate": (totals["mikomi"]/t*100) if t else 0.0,
        "apo_rate": (totals["apo"]/t*100) if t else 0.0,
        "ju_rate": (totals["ju"]/totals["apo"]*100) if totals["apo"] else 0.0,
    })

    # ---- グラフ用 ----
    labels = [r["name"] for r in rows]
    chart_data = {
        "nc_owanai": [r["nc_owanai"] for r in rows],  # 不通留守＋追わない（棒：灰色）
        "hits":      [r["hits"] for r in rows],
        "decisions": [r["decisions"] for r in rows],
        "mikomi":    [r["mikomi"] for r in rows],
        "apo":       [r["apo"] for r in rows],
        "ju":        [r["ju"] for r in rows],
    }

    ctx = {
        "year": year, "month": month, "start": start, "end": end,
        "rows": rows, "totals": totals,
        "labels": labels, "chart_data": chart_data,
    }
    return render(request, "kpi/monthly.html", ctx)

