from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Company, SalesActivity, SalesPerson, ImageLink

print("🔹 admin.py が実行されました")

# 画像リンクを Company のインラインで編集
class ImageLinkInline(admin.TabularInline):
    model = ImageLink
    extra = 1

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    inlines = [ImageLinkInline]
    list_display = ("id", "name", "phone", "industry", "sub_industry")
    search_fields = ("name", "phone", "address", "corporation_name")

@admin.register(SalesActivity)
class SalesActivityAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "activity_date", "result", "sales_person", "next_action_date")
    search_fields = ("company__name", "sales_person", "result")

@admin.register(SalesPerson)
class SalesPersonAdmin(UserAdmin):
    # 追加フィールドを管理画面で見えるように
    fieldsets = UserAdmin.fieldsets + (
        ("Sales fields", {"fields": ("phone_number", "department")}),
    )
