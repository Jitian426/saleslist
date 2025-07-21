app_name = "saleslist"  # ✅ 名前空間を定義
from django.urls import path, include
from .views import company_detail
from django.contrib.auth import views as auth_views
from .views import (
    upload_csv, export_companies_csv, company_list, sales_activity_list, company_detail,
    add_sales_activity, edit_company, dashboard, register
)
from django.conf import settings
from .views import CustomLoginView
from . import views
from .views import user_list

app_name = 'saleslist'

urlpatterns = [
    path("upload/", upload_csv, name="upload_csv"),
    path('export_csv/', export_companies_csv, name='export_csv'),
    path("companies/", company_list, name="company_list"),
    path("sales_activities/", sales_activity_list, name="sales_activity_list"),
    path("company/<int:pk>/", company_detail, name="company_detail"),
    path("company/<int:company_id>/add_sales_activity/", add_sales_activity, name="add_sales_activity"),
    path("company/<int:company_id>/edit/", edit_company, name="edit_company"),
    path("company/<int:pk>/add_sales_activity_ajax/", views.add_sales_activity_ajax, name="add_sales_activity_ajax"),
    path('company/<int:company_id>/add_user/', views.add_user_profile, name='add_user_profile'),
    path("user_profile/<int:pk>/edit/", views.edit_user_profile, name="edit_user_profile"),
    path("dashboard/", dashboard, name="dashboard"),
    path("", company_list, name="home"),  # ✅ ホーム画面を企業リストにする
    path('export_csv/', views.export_companies_csv, name='export_companies_csv'),
    path("companies/add/", views.company_create, name="company_create"),
    path('companies/delete_filtered/confirm/', views.confirm_delete_filtered_companies, name='confirm_delete_filtered_companies'),
    path('companies/delete_filtered/execute/', views.execute_delete_filtered_companies, name='execute_delete_filtered_companies'),
    path('companies/delete_filtered/download_csv/', views.download_filtered_companies_csv, name='download_filtered_companies_csv'),
    path('company/<int:company_id>/update_note/', views.update_company_note, name='update_company_note'),
    path("users/", user_list, name="user_list"),
    path("user_progress/", views.user_progress_view, name="user_progress"),
    path("company/<int:pk>/", views.company_detail, name="company_detail"),
    path('user_progress/export_completed/', views.export_completed_progress_csv, name='export_completed_progress'),
    path('kpi/', views.kpi_view, name='kpi'),

    # ✅ ログイン・ログアウト
    path("login/", CustomLoginView.as_view(), name="login"),
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
