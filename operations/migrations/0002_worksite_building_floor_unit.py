# Generated for the Work Site, Building, Floor and Unit modules.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkSite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('address', models.TextField(blank=True)),
                ('location', models.CharField(blank=True, max_length=255)),
                ('status', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='work_sites', to='operations.company')),
            ],
            options={'verbose_name': 'Work Site', 'verbose_name_plural': 'Work Sites', 'ordering': ['company__name', 'name']},
        ),
        migrations.CreateModel(
            name='Building',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('building_type', models.CharField(choices=[('apartment', 'Apartment'), ('villa', 'Villa'), ('office', 'Office'), ('other', 'Other')], default='apartment', max_length=20)),
                ('address', models.TextField(blank=True)),
                ('location', models.CharField(blank=True, max_length=255)),
                ('number_of_floors', models.PositiveIntegerField(default=0)),
                ('number_of_flats', models.PositiveIntegerField(default=0)),
                ('number_of_villas', models.PositiveIntegerField(default=0)),
                ('number_of_office_units', models.PositiveIntegerField(default=0)),
                ('number_of_other_units', models.PositiveIntegerField(default=0)),
                ('other_type_name', models.CharField(blank=True, max_length=100)),
                ('status', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='buildings', to='operations.company')),
                ('work_site', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='buildings', to='operations.worksite')),
            ],
            options={'verbose_name': 'Building / Property', 'verbose_name_plural': 'Buildings / Properties', 'ordering': ['company__name', 'work_site__name', 'name']},
        ),
        migrations.CreateModel(
            name='Floor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('floor_number', models.PositiveIntegerField(blank=True, null=True)),
                ('status', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('building', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='floors', to='operations.building')),
            ],
            options={'verbose_name': 'Floor', 'verbose_name_plural': 'Floors', 'ordering': ['building__name', 'floor_number', 'name']},
        ),
        migrations.CreateModel(
            name='Unit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='Unit Name / Number')),
                ('unit_type', models.CharField(choices=[('flat', 'Flat'), ('villa', 'Villa'), ('office', 'Office'), ('other', 'Other')], default='flat', max_length=20)),
                ('status', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('building', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='units', to='operations.building')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='units', to='operations.company')),
                ('floor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='units', to='operations.floor')),
                ('work_site', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='units', to='operations.worksite')),
            ],
            options={'verbose_name': 'Unit', 'verbose_name_plural': 'Units', 'ordering': ['building__name', 'floor__floor_number', 'name']},
        ),
        migrations.AddConstraint(model_name='worksite', constraint=models.UniqueConstraint(fields=('company', 'name'), name='unique_work_site_company_name')),
        migrations.AddConstraint(model_name='building', constraint=models.UniqueConstraint(fields=('work_site', 'name'), name='unique_building_work_site_name')),
        migrations.AddConstraint(model_name='floor', constraint=models.UniqueConstraint(fields=('building', 'name'), name='unique_floor_building_name')),
        migrations.AddConstraint(model_name='unit', constraint=models.UniqueConstraint(fields=('building', 'name'), name='unique_unit_building_name')),
    ]
