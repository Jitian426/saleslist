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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['established_date'].widget = forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "例: 2025/03/27 または 2025-03-27"
            }
        )

    def clean_established_date(self):
        date_input = self.cleaned_data.get('established_date')
        if isinstance(date_input, str):
            for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
                try:
                    return datetime.strptime(date_input, fmt).date()
                except ValueError:
                    continue
            raise forms.ValidationError("日付の形式が正しくありません。例: 2025/03/27 または 2025-03-27")
        return date_input


class SalesActivityForm(forms.ModelForm):
    sales_person_email = forms.EmailField(required=False, label="営業担当者のメールアドレス")
    
    class Meta:
        model = SalesActivity
        fields = ["result", "memo", "next_action_date", 'is_decision_maker']
        widgets = {
            "next_action_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            'result': forms.Select(choices=SalesActivity.RESULT_CHOICES),  # ✅ 選択肢を適用
            'step': '600',
        }
        labels = {
            'is_decision_maker': '決裁者',
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


from django import forms
from .models import UserProfile

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            'customer_name_kana', 'customer_name', 'address',
            'representative_name_kana', 'representative_name', 'representative_phone', 'representative_birthday',
            'contact_name_kana', 'contact_name', 'contact_phone',
            'distribution', 'plan', 'capacity', 'acquired_usage',
            'order_date', 'complete_date',
            'gross_profit', 'cashback', 'commission',
            'file_link', 'shop_name', 'product',
            'appointment_staff', 'sales_staff',
            'progress'
        ]
        widgets = {
            'representative_birthday': forms.DateInput(attrs={'type': 'date'}),
            'order_date': forms.DateInput(attrs={'type': 'date'}),
            'complete_date': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'customer_name_kana': '顧客名カナ',
            'customer_name': '顧客名',
            'address': '顧客住所',
            'representative_name_kana': '代表者名カナ',
            'representative_name': '代表者名',
            'representative_phone': '代表者電話番号',
            'representative_birthday': '代表者生年月日',
            'contact_name_kana': '担当者名カナ',
            'contact_name': '担当者名',
            'contact_phone': '担当者電話番号',
            'distribution': '商流',
            'plan': '獲得プラン',
            'capacity': '契約容量',
            "acquired_usage": '獲得使用量',
            'order_date': '申込日',
            'complete_date': '完了日',
            'gross_profit': '粗利',
            'cashback': 'ｷｬｯｼｭﾊﾞｯｸ',
            'commission': '手数料',
            'file_link': '獲得書類データ',
            'shop_name': '販売店名',
            'product': '獲得商材',
            'appointment_staff': 'アポ担当',
            'sales_staff': '営業担当',
        }


from django import forms

class UserProgressForm(forms.Form):
    progress = forms.ChoiceField(
        choices=[
            ("", "------"),
            ("発注前", "発注前"),
            ("後確待ち", "後確待ち"),
            ("設置待ち", "設置待ち"),
            ("マッチング待ち", "マッチング待ち"),
            ("完了", "完了"),
        ],
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"})
    )


from django import forms
from .models import SalesActivity

class KPIFilterForm(forms.Form):
    sales_person = forms.ChoiceField(label="営業担当者", required=False)
    date = forms.DateField(label="日付（単日）", required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    month = forms.DateField(label="月（年月単位）", required=False, widget=forms.DateInput(attrs={'type': 'month'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        persons = SalesActivity.objects.values_list('sales_person', flat=True).distinct()
        choices = [('', '--- 全員 ---')] + [(p, p) for p in persons if p]
        self.fields['sales_person'].choices = choices



from django import forms
from .models import ImageLink

class ImageLinkForm(forms.ModelForm):
    class Meta:
        model = ImageLink
        fields = ['title', 'url', 'note']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例）外観写真'}),
            'url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'GoogleドライブURL 等'}),
            'note': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '任意メモ'}),
        }
