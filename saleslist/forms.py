from django import forms
from .models import Company
from .models import SalesActivity
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import SalesPerson

class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            'name', 'phone', 'address', 'corporation_name', 'corporation_phone',
            'corporation_address', 'representative', 'established_date', 'industry', 'sub_industry'
        ]

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
