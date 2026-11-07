# Add tenant management without changing existing project models or data.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0004_building_type_master_and_building_staff'),
    ]

    operations = [
        migrations.CreateModel(
            name='Tenant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=150)),
                ('mobile_number', models.CharField(max_length=30)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('identity_number', models.CharField(blank=True, max_length=100, null=True)),
                ('lease_start_date', models.DateField(blank=True, null=True)),
                ('lease_end_date', models.DateField(blank=True, null=True)),
                ('status', models.BooleanField(default=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('unit', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tenants', to='operations.unit')),
            ],
            options={
                'verbose_name': 'Tenant',
                'verbose_name_plural': 'Tenants',
                'ordering': ['unit__building__name', 'unit__name', 'full_name'],
            },
        ),
    ]
