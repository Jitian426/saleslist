app_name = "saleslist"  # ✅ 名前空間を定義
from django.urls import path, include
from .views import company_detail
from django.contrib.auth import views as auth_views
from .views import (
    upload_csv, company_list, sales_activity_list, company_detail,
    add_sales_activity, edit_company, dashboard, register
)
from django.conf import settings


urlpatterns = [
    path("upload/", upload_csv, name="upload_csv"),
    path("companies/", company_list, name="company_list"),
    path("sales_activities/", sales_activity_list, name="sales_activity_list"),
    path("company/<int:company_id>/", company_detail, name="company_detail"),  # ✅ 確認
    path("company/<int:company_id>/add_sales_activity/", add_sales_activity, name="add_sales_activity"),
    path("company/<int:company_id>/edit/", edit_company, name="edit_company"),
    path("dashboard/", dashboard, name="dashboard"),
    path("", company_list, name="home"),  # ✅ ホーム画面を企業リストにする

    # ✅ ログイン・ログアウト
    path("login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", register, name="register"),
]


urlpatterns += [
    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='password_reset.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='password_reset_complete.html'), name='password_reset_complete'),
]


if settings.DEBUG:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
