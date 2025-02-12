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


from django.shortcuts import render
from .models import Company

def company_list(request):
    print("リクエストパラメータ:", request.GET)  # 🔍 デバッグ用

    # 🔹 検索条件の取得
    query = request.GET.get("query", "")
    phone = request.GET.get("phone", "")
    address = request.GET.get("address", "")
    corporation_name = request.GET.get("corporation_name", "")
    corporation_phone = request.GET.get("corporation_phone", "")
    industry = request.GET.get("industry", "")
    sub_industry = request.GET.get("sub_industry", "")

    # 🔹 営業履歴の検索条件
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    sales_person = request.GET.get("sales_person", "")
    result = request.GET.get("result", "")
    next_action_start = request.GET.get("next_action_start", "")
    next_action_end = request.GET.get("next_action_end", "")

    companies = Company.objects.all()

    # 🔹 基本情報の検索
    if query:
        companies = companies.filter(name__icontains=query)

    if phone:
        companies = companies.filter(Q(phone__icontains=phone) | Q(corporation_phone__icontains=phone))

    if address:
        companies = companies.filter(address__icontains=address)

    if corporation_name:
        companies = companies.filter(corporation_name__icontains=corporation_name)

    if corporation_phone:
        companies = companies.filter(corporation_phone__icontains=corporation_phone)

    if industry:
        companies = companies.filter(industry__icontains=industry)

    if sub_industry:
        companies = companies.filter(sub_industry__icontains=sub_industry)

    # 🔹 営業履歴の検索
    if start_date or end_date or sales_person or result or next_action_start or next_action_end:
        companies = companies.filter(salesactivity__isnull=False).distinct()

        if start_date:
            companies = companies.filter(salesactivity__activity_date__gte=start_date)

        if end_date:
            companies = companies.filter(salesactivity__activity_date__lte=end_date)

        if sales_person:
            companies = companies.filter(salesactivity__sales_person=sales_person)

        if result:
            companies = companies.filter(salesactivity__result=result)

        if next_action_start:
            companies = companies.filter(salesactivity__next_action_date__gte=next_action_start)

        if next_action_end:
            companies = companies.filter(salesactivity__next_action_date__lte=next_action_end)

    # 🔹 ソート処理
    sort_column = request.GET.get("sort", "id")  # デフォルトでID順
    sort_order = request.GET.get("order", "asc")

    # ソート可能なカラムのリスト
    valid_columns = ["name", "phone", "corporation_name", "corporation_address", "activity_date", "sales_person", "result", "next_action_date"]
    if sort_column.lstrip("-") not in valid_columns:
        sort_column = "id"  # 不正な値が来た場合はデフォルト値にする

    # 並び順の適用
    if sort_order == 'desc':
        sort_column = f"-{sort_column}"  # 降順の場合は `-` をつける

    # **修正点: ソート処理は一番最後に適用する**
    companies = companies.order_by(sort_column)

    return render(request, "company_list.html", {
        "companies": companies,
        "query": query,
        "sort_column": sort_column.lstrip("-"),  # マイナス記号を削除して渡す
        "sort_order": sort_order,
    })




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


from django.contrib.auth.decorators import login_required

@login_required
def company_list(request):
    companies = Company.objects.all()
    return render(request, 'company_list.html', {'companies': companies})