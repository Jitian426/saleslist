from django.db import models
from django.utils.timezone import now
from django.contrib.auth.models import AbstractUser


class Company(models.Model):
    name = models.CharField(max_length=255, db_index=True)  # 🔹 店舗名にインデックスを追加
    phone = models.CharField(max_length=100, db_index=True, default="なし")  # ✅ 「未設定」を「なし」に変更  # 🔹 電話番号にもインデックスを追加
    address = models.TextField()
    corporation_name = models.CharField(max_length=255, db_index=True)  # 🔹 法人名にもインデックス
    corporation_phone = models.CharField(max_length=100, verbose_name="法人電話番号", blank=True, null=True)  
    corporation_address = models.TextField(verbose_name="法人所在地", blank=True, null=True)  
    representative = models.CharField(max_length=100, verbose_name="代表者名", blank=True, null=True)  
    established_date = models.DateField(verbose_name="開業日", blank=True, null=True)  # ✅ 修正
    industry = models.CharField(max_length=100, verbose_name="大業種", blank=True, null=True)  # ✅ 修正
    sub_industry = models.CharField(max_length=100, verbose_name="小業種", blank=True, null=True)  # ✅ 修正



    def __str__(self):
        return self.name


class SalesActivity(models.Model):
    RESULT_CHOICES = [
        ("再コール", "再コール"),
        ("追わない", "追わない"),
        ("見込", "見込"),
        ("アポ成立", "アポ成立"),
        ("受注", "受注"),
        ("失注", "失注"),
        ("不通留守", "不通留守"),
        ("担当不在", "担当不在"),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name="企業")  
    sales_person = models.CharField(max_length=100, verbose_name="営業担当者")  
    sales_person_email = models.EmailField(verbose_name="営業担当者のメールアドレス", blank=True, null=True)  
    activity_date = models.DateTimeField(auto_now_add=True, verbose_name="営業活動日時")  
    result = models.CharField(max_length=20, choices=[
        ("再コール", "再コール"),
        ("追わない", "追わない"),
        ("見込", "見込"),
        ("アポ成立", "アポ成立"),
        ("受注", "受注"),
        ("失注", "失注"),
        ("不通留守", "不通留守"),
        ("担当不在", "担当不在"),
    ], default="見込", verbose_name="営業結果")  # ✅ CSVの営業結果を保存する
    memo = models.TextField(blank=True, null=True, verbose_name="メモ")  # ✅ CSVのコメントを保存する
    next_action_date = models.DateTimeField(blank=True, null=True, verbose_name="次回営業予定日")  

    def __str__(self):
        return f"{self.sales_person} - {self.company.name} ({self.activity_date})"


class EmailScheduledJob(models.Model):
    recipient_email = models.EmailField(verbose_name="送信先メールアドレス")
    subject = models.CharField(max_length=255, verbose_name="メール件名")
    message = models.TextField(verbose_name="メール内容")
    scheduled_time = models.DateTimeField(verbose_name="送信予定日時")
    sent = models.BooleanField(default=False, verbose_name="送信済み")

    def __str__(self):
        return f"{self.recipient_email} - {self.subject} ({self.scheduled_time})"



class SalesPerson(AbstractUser):
    """営業担当者モデル"""
    email = models.EmailField(unique=True)  # メールアドレスを必須にする
    phone_number = models.CharField(max_length=20, blank=True, null=True)  # ✅ 正しいフィールド名（phone → phone_number に修正）
    department = models.CharField(max_length=100, blank=True, null=True)  # ✅ 正しいフィールド名（position → department に修正）

    def __str__(self):
        return self.username

