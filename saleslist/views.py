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

            expected_columns = ["店舗名", "電話番号", "住所", "法人名", "法人電話番号", "法人所在地", "代表者名", "開業日", "大業種", "小業種", "営業結果", "コメント"]
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
                        "corporation_name": row.get("法人名", "").strip(),
                        "corporation_phone": row.get("法人電話番号", "").strip(),
                        "corporation_address": row.get("法人所在地", "").strip(),
                        "representative": row.get("代表者名", "").strip(),
                        "established_date": formatted_date,
                        "industry": row.get("大業種", "").strip(),
                        "sub_industry": row.get("小業種", "").strip(),
                    }
                )

                # **営業履歴の登録**
                if row.get("営業結果"):
                    SalesActivity.objects.create(
                        company=company,
                        sales_person="CSVインポート",
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

logger = logging.getLogger(__name__)

def company_list(request):
    logger.debug("✅ company_list が呼び出されました")

    start_time = time.time()  # 🔹 クエリ実行時間の計測開始

    # 検索パラメータの取得
    search_params = {
        "query": request.GET.get("query", "").strip(),
        "phone": request.GET.get("phone", "").strip(),
        "address": request.GET.get("address", "").strip(),
        "corporation_name": request.GET.get("corporation_name", "").strip(),
        "corporation_phone": request.GET.get("corporation_phone", "").strip(),
        "industry": request.GET.get("industry", "").strip(),
        "sub_industry": request.GET.get("sub_industry", "").strip(),
        "start_date": request.GET.get("start_date", "").strip(),
        "end_date": request.GET.get("end_date", "").strip(),
        "sales_person": request.GET.get("sales_person", "").strip(),
        "result": request.GET.get("result", "").strip(),
        "next_action_start": request.GET.get("next_action_start", "").strip(),
        "next_action_end": request.GET.get("next_action_end", "").strip(),
    }

    logger.debug(f"🔍 取得した query: {search_params['query']}")
    logger.debug(f"🔍 取得した phone: {search_params['phone']}")
    logger.debug(f"🔍 取得した address: {search_params['address']}")
    logger.debug(f"🔍 取得した corporation_name: {search_params['corporation_name']}")
    
    
    # 🔹 検索条件がない場合は空のクエリセットを返す
    if not any(search_params.values()):
        companies = Company.objects.none()
    else:
        companies = Company.objects.all()

    # クエリの適用（会社情報）
    filters = Q()
    if search_params["query"]:
        filters &= Q(name__icontains=search_params["query"])
    if search_params["phone"]:
        filters &= Q(phone__icontains=search_params["phone"])
    if search_params["address"]:
        filters &= Q(address__icontains=search_params["address"])
    if search_params["corporation_name"]:
        filters &= Q(corporation_name__icontains=search_params["corporation_name"])
    if search_params["corporation_phone"]:
        filters &= Q(corporation_phone__icontains=search_params["corporation_phone"])
    if search_params["industry"]:
        filters &= Q(industry__icontains=search_params["industry"])
    if search_params["sub_industry"]:
        filters &= Q(sub_industry__icontains=search_params["sub_industry"])

    # 🔽 ここでログ出力
    logger.debug(f"🔎 会社フィルタ: {filters}")

    # 営業履歴のフィルタ適用
    sales_filters = Q()
    if search_params["sales_person"]:
        sales_filters &= Q(salesactivity__sales_person__icontains=search_params["sales_person"])
    if search_params["result"]:
        sales_filters &= Q(salesactivity__result=search_params["result"])
    if search_params["start_date"] and search_params["end_date"]:
        sales_filters &= Q(salesactivity__activity_date__range=[search_params["start_date"], search_params["end_date"]])
    if search_params["next_action_start"] and search_params["next_action_end"]:
        sales_filters &= Q(salesactivity__next_action_date__range=[search_params["next_action_start"], search_params["next_action_end"]])

    # 🔹 フィルタ適用前の状態をログに記録
    logger.debug(f"🔍 フィルタ適用前: {filters}")
    logger.debug(f"🔍 営業履歴のフィルタ適用前: {sales_filters}")

    # Qオブジェクトでフィルタ
    companies = companies.filter(filters)
    if sales_filters:
        companies = companies.filter(sales_filters)

    # ここで必ず .query を出す！
    logger.debug(f"📊 クエリ型: {type(companies)}")
    try:
        logger.debug(f"📊 実行クエリ: {companies.query}")
    except Exception as e:
        logger.warning(f"⚠️ クエリ出力時にエラー発生: {e}")

    # フィルタ結果件数
    logger.debug(f"📊 フィルタ適用後の会社数: {companies.count()} 件")

    # →そのあとにソート処理
    sort_column = request.GET.get("sort", "name")
    sort_order = request.GET.get("order", "asc")
    if sort_order == "desc":
        sort_column = f"-{sort_column}"
    companies = companies.order_by(sort_column)


    context = {
        "companies": companies,
        "sort_column": sort_column.lstrip("-"),
        "sort_order": sort_order,
        "sales_persons": SalesActivity.objects.values("sales_person").distinct(),
        "results": ["再コール", "追わない", "見込", "アポ成立", "受注", "失注", "不通留守", "担当不在"],
        **search_params,  # ←ここ重要！
    }


    
    return render(request, "company_list.html", context)




from django.shortcuts import render, get_object_or_404
from .models import Company, SalesActivity
from .forms import CompanyForm

def company_detail(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    sales_activities = SalesActivity.objects.filter(company=company).order_by('-activity_date')  # ✅ 日付降順に取得
    
    return render(request, 'company_detail.html', {'company': company, "sales_activities": sales_activities})

    

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
            sales_activity.sales_person = request.user
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

            return redirect("saleslist:company_detail", company_id=company.id)  # ✅ リダイレクトを正しい位置に修正
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
            'name', 'phone', 'address', 'corporation_name', 'corporation_phone',
            'corporation_address', 'representative', 'established_date', 'industry', 'sub_industry'
        ]

# ✅ 企業情報編集用のビュー
def edit_company(request, company_id):
    company = get_object_or_404(Company, id=company_id)

    if request.method == "POST":
        form = CompanyForm(request.POST, instance=company)
        if form.is_valid():
            form.save()
            return redirect("saleslist:company_detail", company_id=company.id)  # ✅ 更新後に詳細ページへリダイレクト
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

    return render(request, 'dashboard.html', context)


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
