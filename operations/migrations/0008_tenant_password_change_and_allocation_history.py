from django.db import migrations, models
from django.db.models import Q
from django.utils import timezone


def release_allocations_for_inactive_tenants(apps, schema_editor):
    Tenant = apps.get_model('operations', 'Tenant')
    Allocation = apps.get_model('operations', 'TenantUnitAllocation')
    db = schema_editor.connection.alias
    inactive_ids = Tenant.objects.using(db).filter(status=False).values_list('pk', flat=True)
    Allocation.objects.using(db).filter(
        tenant_id__in=inactive_ids, released_at__isnull=True
    ).update(released_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0007_tenant_multi_unit_and_guest_visits'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='must_change_password',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='tenantunitallocation',
            name='released_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RemoveConstraint(
            model_name='tenantunitallocation',
            name='unique_active_tenant_per_unit',
        ),
        migrations.RemoveConstraint(
            model_name='tenantunitallocation',
            name='unique_tenant_unit_allocation',
        ),
        migrations.RunPython(
            release_allocations_for_inactive_tenants,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='tenantunitallocation',
            constraint=models.UniqueConstraint(
                fields=('unit',),
                condition=Q(released_at__isnull=True),
                name='unique_active_tenant_per_unit',
            ),
        ),
        migrations.AddConstraint(
            model_name='tenantunitallocation',
            constraint=models.UniqueConstraint(
                fields=('tenant', 'unit'),
                condition=Q(released_at__isnull=True),
                name='unique_tenant_unit_allocation',
            ),
        ),
    ]
