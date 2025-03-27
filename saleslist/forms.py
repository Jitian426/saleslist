from django import forms
from .models import Company
from .models import SalesActivity
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import SalesPerson
from datetime import datetime

class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            'name', 'phone', 'fax', 'mobile_phone', 'address', 'corporation_name', 'corporation_phone',
            'corporation_address', 'representative', 'established_date', 'license_number', 'industry', 'sub_industry'
        ]
        labels = {
            'name': '店舗名',
            'phone': '店舗電話番号',
            'fax': 'FAX番号',
            'mobile_phone': '携帯番号',
            'address': '住所',
            'corporation_name': '法人名',
            'corporation_phone': '法人電話番号',
            'corporation_address': '法人所在地',
            'representative': '代表者名',
            'established_date': '開業日',
            'license_number': '許可番号',
            'industry': '大業種',
            'sub_industry': '小業種',
            # 他も必要があれば追加できます
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # ✅ フィールドの必須設定
        self.fields['corporation_name'].required = False
        self.fields['industry'].required = True

        # ✅ カレンダー入力＋自由形式入力を許可する DateInput に変更
        self.fields['established_date'].widget = forms.DateInput(
            attrs={
                "type": "date",
                "class": "form-control"
            },
            format="%Y-%m-%d",  # type="date" のデフォルト形式に合わせる
        )

        # ✅ YYYY/MM/DD も受け付けるように input_formats を追加
        self.fields['established_date'].input_formats = ["%Y-%m-%d", "%Y/%m/%d"]


class SalesActivityForm(forms.ModelForm):
    sales_person_email = forms.EmailField(required=False, label="営業担当者のメールアドレス")
    
    class Meta:
        model = SalesActivity
        fields = ["sales_person", "result", "memo", "next_action_date"]
        widgets = {
            "next_action_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            'result': forms.Select(choices=SalesActivity.RESULT_CHOICES),  # ✅ 選択肢を適用
        }

class SalesPersonRegistrationForm(UserCreationForm):
    class Meta:
        model = SalesPerson
        fields = ["username", "email", "phone_number", "department", "password1", "password2"]
        
        labels = {
            "username": "ユーザー名",
            "email": "メールアドレス",
            "phone_number": "電話番号",
            "department": "部署",
            "password1": "パスワード",
            "password2": "パスワード（確認）",
        }

        help_texts = {
            "username": "※ ユーザー名を入力してください（英数字可）",
            "password1": "※ パスワードは8文字以上で設定してください",
            "password2": "※ 確認のため、もう一度同じパスワードを入力してください",
        }
    


class CustomUserCreationForm(UserCreationForm):
    username = forms.CharField(label="ユーザー名")
    email = forms.EmailField(label="メールアドレス")
    password1 = forms.CharField(label="パスワード", widget=forms.PasswordInput)
    password2 = forms.CharField(label="パスワード（確認用）", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]
