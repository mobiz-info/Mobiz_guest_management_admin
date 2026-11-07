from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0008_tenant_password_change_and_allocation_history'),
    ]

    operations = [
        migrations.CreateModel(
            name='TenantStaffMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150)),
                ('designation', models.CharField(blank=True, max_length=100)),
                ('mobile_number', models.CharField(max_length=30)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('status', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='staff_members', to='operations.tenant')),
            ],
            options={
                'verbose_name': 'Tenant Staff Member',
                'verbose_name_plural': 'Tenant Staff Members',
                'ordering': ['name'],
            },
        ),
    ]
