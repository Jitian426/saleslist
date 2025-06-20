# Generated by Django 5.1.6 on 2025-06-21 18:23

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('saleslist', '0010_company_note'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer_name_kana', models.CharField(blank=True, max_length=255, verbose_name='顧客名カナ')),
                ('customer_name', models.CharField(blank=True, max_length=255, verbose_name='顧客名')),
                ('address', models.CharField(blank=True, max_length=255, verbose_name='住所')),
                ('representative_name_kana', models.CharField(blank=True, max_length=255, verbose_name='代表者名カナ')),
                ('representative_name', models.CharField(blank=True, max_length=255, verbose_name='代表者名')),
                ('representative_phone', models.CharField(blank=True, max_length=20, verbose_name='代表者電話番号')),
                ('representative_birthday', models.DateField(blank=True, null=True, verbose_name='代表者生年月日')),
                ('contact_name_kana', models.CharField(blank=True, max_length=255, verbose_name='担当者名カナ')),
                ('contact_name', models.CharField(blank=True, max_length=255, verbose_name='担当者名')),
                ('contact_phone', models.CharField(blank=True, max_length=20, verbose_name='担当者電話番号')),
                ('order_date', models.DateField(blank=True, null=True, verbose_name='受注日')),
                ('shop_name', models.CharField(blank=True, max_length=255, verbose_name='販売店名')),
                ('distribution', models.CharField(blank=True, max_length=255, verbose_name='商流')),
                ('product', models.CharField(blank=True, max_length=255, verbose_name='獲得商材')),
                ('plan', models.CharField(blank=True, max_length=255, verbose_name='獲得プラン')),
                ('capacity', models.CharField(blank=True, max_length=255, verbose_name='契約容量')),
                ('appointment_staff', models.CharField(blank=True, max_length=255, verbose_name='アポ担当')),
                ('sales_staff', models.CharField(blank=True, max_length=255, verbose_name='営業担当')),
                ('complete_date', models.DateField(blank=True, null=True, verbose_name='完了日')),
                ('gross_profit', models.IntegerField(blank=True, null=True, verbose_name='粗利(入金)')),
                ('cashback', models.IntegerField(blank=True, null=True, verbose_name='キャッシュバック')),
                ('commission', models.IntegerField(blank=True, null=True, verbose_name='手数料')),
                ('file_link', models.URLField(blank=True, max_length=500, verbose_name='ファイル保存先リンク')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='saleslist.company')),
            ],
        ),
    ]
