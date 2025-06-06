# Generated by Django 5.1.6 on 2025-03-27 04:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('saleslist', '0008_companyeditlog'),
    ]

    operations = [
        migrations.AlterField(
            model_name='company',
            name='address',
            field=models.TextField(verbose_name='店舗住所'),
        ),
        migrations.AlterField(
            model_name='company',
            name='corporation_name',
            field=models.CharField(blank=True, max_length=255, verbose_name='法人名'),
        ),
        migrations.AlterField(
            model_name='company',
            name='license_number',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='許可番号'),
        ),
        migrations.AlterField(
            model_name='company',
            name='name',
            field=models.CharField(db_index=True, max_length=255, verbose_name='店舗名'),
        ),
        migrations.AlterField(
            model_name='company',
            name='phone',
            field=models.CharField(db_index=True, default='なし', max_length=100, verbose_name='店舗電話番号'),
        ),
    ]
