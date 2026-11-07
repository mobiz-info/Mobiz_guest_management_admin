# Add tenant login credentials and family members while preserving existing tenant rows.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('operations', '0005_tenant'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='tenant_type',
            field=models.CharField(
                choices=[('rental', 'Rental Tenant'), ('owner', 'Owner')],
                default='rental',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='tenant',
            name='user',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tenant_profile',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name='TenantFamilyMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150)),
                ('mobile_number', models.CharField(max_length=30)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='family_members',
                    to='operations.tenant',
                )),
            ],
            options={
                'verbose_name': 'Tenant Family Member',
                'verbose_name_plural': 'Tenant Family Members',
                'ordering': ['name'],
            },
        ),
    ]
