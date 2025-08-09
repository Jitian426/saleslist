from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from saleslist.models import Company, SalesActivity, SalesPerson

print("🔹 admin.py が実行されました")

# すべて明示的に登録
admin.site.register(Company)
admin.site.register(SalesActivity)
admin.site.register(SalesPerson, UserAdmin)  # SalesPerson はカスタムユーザー


# saleslist/admin.py
from django.contrib import admin
from .models import Company, ImageLink

class ImageLinkInline(admin.TabularInline):
    model = ImageLink
    extra = 1

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    inlines = [ImageLinkInline]
    # 既存の設定があれば併記

