from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0009_tenant_staff_members'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenantfamilymember',
            name='address',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='tenantfamilymember',
            name='unit',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tenant_family_members',
                to='operations.unit',
            ),
        ),
        migrations.AddField(
            model_name='tenantstaffmember',
            name='address',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='tenantstaffmember',
            name='unit',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tenant_staff_members',
                to='operations.unit',
            ),
        ),
    ]
