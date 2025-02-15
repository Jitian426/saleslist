from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Company, SalesActivity, SalesPerson

class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'address', 'corporation_name', 'corporation_phone', 'industry', 'sub_industry', 'established_date')

admin.site.register(Company, CompanyAdmin)
admin.site.register(SalesActivity)


class SalesPersonAdmin(UserAdmin):
    model = SalesPerson
    list_display = ["username", "email", "phone_number", "department"]
    fieldsets = UserAdmin.fieldsets + (
        (None, {"fields": ("phone_number", "department")}),
    )

admin.site.register(SalesPerson, SalesPersonAdmin)
