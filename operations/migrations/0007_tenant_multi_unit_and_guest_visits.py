from django.conf import settings
from django.db import migrations, models
from django.db.models import Count
import django.db.models.deletion


def backfill_tenant_unit_allocations(apps, schema_editor):
    Tenant = apps.get_model('operations', 'Tenant')
    Allocation = apps.get_model('operations', 'TenantUnitAllocation')

    db = schema_editor.connection.alias

    # --------------------------------------------------------
    # CHECK DUPLICATE LEGACY UNIT ASSIGNMENTS
    # --------------------------------------------------------

    duplicate = (
        Tenant.objects.using(db)
        .filter(unit_id__isnull=False)
        .values('unit_id')
        .annotate(total=Count('id'))
        .filter(total__gt=1)
        .order_by('unit_id')
        .first()
    )

    if duplicate:
        raise RuntimeError(
            "Cannot safely migrate tenant unit allocations: "
            f"unit_id {duplicate['unit_id']} is assigned to "
            "more than one existing tenant. Resolve duplicate "
            "assignments before rerunning migrate. "
            "No tenant rows have been deleted."
        )

    # --------------------------------------------------------
    # BACKFILL EXISTING TENANT UNIT ASSIGNMENTS
    # --------------------------------------------------------

    tenants = (
        Tenant.objects.using(db)
        .filter(unit_id__isnull=False)
        .order_by('pk')
    )

    for tenant in tenants.iterator():
        Allocation.objects.using(db).get_or_create(
            tenant_id=tenant.pk,
            unit_id=tenant.unit_id,
        )


def reverse_tenant_unit_allocations(apps, schema_editor):
    Allocation = apps.get_model(
        'operations',
        'TenantUnitAllocation'
    )

    Allocation.objects.using(
        schema_editor.connection.alias
    ).all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
        ('operations', '0006_tenant_login_and_family_members'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        # ----------------------------------------------------
        # TENANT ADDRESS
        # ----------------------------------------------------

        migrations.AddField(
            model_name='tenant',
            name='address',
            field=models.TextField(
                blank=True,
                default='',
            ),
        ),

        # ----------------------------------------------------
        # TENANT UNIT ALLOCATION
        # ----------------------------------------------------

        migrations.CreateModel(
            name='TenantUnitAllocation',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'allocated_at',
                    models.DateTimeField(
                        auto_now_add=True,
                    ),
                ),
                (
                    'tenant',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='unit_allocations',
                        to='operations.tenant',
                    ),
                ),
                (
                    'unit',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='tenant_allocations',
                        to='operations.unit',
                    ),
                ),
            ],
            options={
                'ordering': [
                    'unit__building__name',
                    'unit__name',
                ],
                'constraints': [
                    models.UniqueConstraint(
                        fields=('unit',),
                        name='unique_active_tenant_per_unit',
                    ),
                    models.UniqueConstraint(
                        fields=('tenant', 'unit'),
                        name='unique_tenant_unit_allocation',
                    ),
                ],
            },
        ),

        # ----------------------------------------------------
        # MULTIPLE UNITS PER TENANT
        # ----------------------------------------------------

        migrations.AddField(
            model_name='tenant',
            name='allocated_units',
            field=models.ManyToManyField(
                blank=True,
                related_name='allocated_tenants',
                through='operations.TenantUnitAllocation',
                to='operations.unit',
            ),
        ),

        # ----------------------------------------------------
        # BACKFILL LEGACY ASSIGNMENTS
        # ----------------------------------------------------

        migrations.RunPython(
            backfill_tenant_unit_allocations,
            reverse_code=reverse_tenant_unit_allocations,
        ),

        # ----------------------------------------------------
        # GUEST VISIT
        # ----------------------------------------------------

        migrations.CreateModel(
            name='GuestVisit',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'guest_name',
                    models.CharField(
                        max_length=150,
                    ),
                ),
                (
                    'visit_date',
                    models.DateField(),
                ),
                (
                    'visit_time',
                    models.TimeField(
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    'notes',
                    models.TextField(
                        blank=True,
                    ),
                ),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('pending', 'Pending Approval'),
                            ('approved', 'Approved'),
                            ('denied', 'Denied'),
                        ],
                        db_index=True,
                        default='pending',
                        max_length=10,
                    ),
                ),
                (
                    'gate_pass_code',
                    models.CharField(
                        blank=True,
                        max_length=32,
                        null=True,
                        unique=True,
                    ),
                ),
                (
                    'approved_at',
                    models.DateTimeField(
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    'created_at',
                    models.DateTimeField(
                        auto_now_add=True,
                    ),
                ),
                (
                    'updated_at',
                    models.DateTimeField(
                        auto_now=True,
                    ),
                ),
                (
                    'created_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='created_guest_visits',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'purpose_of_visit',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='guest_visits',
                        to='core.purposeofvisit',
                    ),
                ),
                (
                    'tenant',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='guest_visits',
                        to='operations.tenant',
                    ),
                ),
                (
                    'unit',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='guest_visits',
                        to='operations.unit',
                    ),
                ),
            ],
            options={
                'ordering': [
                    '-visit_date',
                    '-created_at',
                ],
            },
        ),
    ]
