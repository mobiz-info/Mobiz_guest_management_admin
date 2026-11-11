from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Q

from core.models import (
    Country,
    State,
    District,
    Area,
    Designation,
    EstablishmentType,
)


# ============================================================
# COMPANY / CLIENT
# ============================================================

class Company(models.Model):

    name = models.CharField(max_length=200)
    address = models.TextField()

    tax_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    email = models.EmailField(
        max_length=254,
        blank=True,
        null=True,
    )

    phone = models.CharField(
        max_length=30,
        blank=True,
        null=True,
    )

    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name='companies',
    )

    state = models.ForeignKey(
        State,
        on_delete=models.PROTECT,
        related_name='companies',
    )

    district = models.ForeignKey(
        District,
        on_delete=models.PROTECT,
        related_name='companies',
    )

    area = models.ForeignKey(
        Area,
        on_delete=models.PROTECT,
        related_name='companies',
    )

    concerned_staff_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )

    concerned_staff_designation = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    concerned_staff_mobile = models.CharField(
        max_length=30,
        blank=True,
        null=True,
    )

    applicable_tax = models.BooleanField(default=False)

    enabled_designations = models.ManyToManyField(
        Designation,
        blank=True,
        related_name='enabled_companies',
    )

    status = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Company / Client'
        verbose_name_plural = 'Companies / Clients'

    def __str__(self):
        return self.name


# ============================================================
# COMPANY STAFF
# ============================================================

class CompanyStaff(models.Model):

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='staff_members',
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='company_staff',
    )

    status = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['company__name']
        verbose_name = 'Company Staff'
        verbose_name_plural = 'Company Staff'

    def __str__(self):
        return f'{self.user.username} - {self.company.name}'


# ============================================================
# COMPANY DESIGNATION
# ============================================================

class CompanyDesignation(models.Model):

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='company_designations',
    )

    name = models.CharField(max_length=100)
    status = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Company Designation'
        verbose_name_plural = 'Company Designations'

        constraints = [
            models.UniqueConstraint(
                fields=['company', 'name'],
                name='unique_company_designation',
            )
        ]

    def __str__(self):
        return f'{self.name} - {self.company.name}'


# ============================================================
# WORK SITE
# ============================================================

class WorkSite(models.Model):

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='work_sites',
    )

    name = models.CharField(max_length=200)
    address = models.TextField()
    location = models.CharField(max_length=255)

    status = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['company__name', 'name']

        constraints = [
            models.UniqueConstraint(
                fields=['company', 'name'],
                name='unique_work_site_company_name',
            )
        ]

        verbose_name = 'Work Site'
        verbose_name_plural = 'Work Sites'

    def clean(self):

        errors = {}

        if self.pk:
            previous = WorkSite.objects.filter(
                pk=self.pk
            ).first()

            if (
                previous
                and previous.company_id != self.company_id
                and self.buildings.exists()
            ):
                errors['company'] = (
                    'Company cannot be changed after buildings '
                    'have been added to this work site.'
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.name} - {self.company.name}'


# ============================================================
# BUILDING TYPE MASTER
# SUPER ADMIN
# ============================================================

class BuildingTypeMaster(models.Model):

    CATEGORY_CHOICES = (
        ('apartment', 'Apartment / Residential'),
        ('villa', 'Villa'),
        ('office', 'Office / Office Building'),
        ('other', 'Commercial / Other'),
    )

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    code = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='other',
    )

    description = models.CharField(
        max_length=255,
        blank=True,
    )

    status = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Building Type'
        verbose_name_plural = 'Building Types'

    def clean(self):

        errors = {}

        if self.pk:
            previous = BuildingTypeMaster.objects.filter(
                pk=self.pk
            ).first()

            if (
                previous
                and previous.code != self.code
                and previous.buildings.exists()
            ):
                errors['code'] = (
                    'Category cannot be changed while buildings '
                    'use this Building Type. Create a new type instead.'
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name


# ============================================================
# BUILDING / PROPERTY
# ============================================================

class Building(models.Model):

    BUILDING_TYPE_CHOICES = (
        ('apartment', 'Apartment'),
        ('villa', 'Villa'),
        ('office', 'Office'),
        ('other', 'Other'),
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='buildings',
    )

    work_site = models.ForeignKey(
        WorkSite,
        on_delete=models.CASCADE,
        related_name='buildings',
    )

    building_type_master = models.ForeignKey(
        BuildingTypeMaster,
        on_delete=models.PROTECT,
        related_name='buildings',
        blank=True,
        null=True,
    )

    name = models.CharField(max_length=200)

    building_type = models.CharField(
        max_length=20,
        choices=BUILDING_TYPE_CHOICES,
        default='apartment',
    )

    address = models.TextField()
    location = models.CharField(max_length=255)

    number_of_floors = models.PositiveIntegerField(default=0)
    number_of_flats = models.PositiveIntegerField(default=0)
    number_of_villas = models.PositiveIntegerField(default=0)
    number_of_office_units = models.PositiveIntegerField(default=0)
    number_of_other_units = models.PositiveIntegerField(default=0)

    other_type_name = models.CharField(
        max_length=100,
        blank=True,
    )

    status = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            'company__name',
            'work_site__name',
            'name',
        ]

        constraints = [
            models.UniqueConstraint(
                fields=['work_site', 'name'],
                name='unique_building_work_site_name',
            )
        ]

        verbose_name = 'Building / Property'
        verbose_name_plural = 'Buildings / Properties'

    def clean(self):

        errors = {}

        # Use the category defined by the Building Type Master.
        if self.building_type_master_id:
            self.building_type = self.building_type_master.code

        # The Work Site must belong to the selected Company.
        if self.work_site_id and self.company_id:
            if self.work_site.company_id != self.company_id:
                errors['work_site'] = (
                    'Selected work site does not belong '
                    'to the selected company.'
                )

        # Check existing floors and units before changing
        # company, work site, or building type.
        if self.pk:

            previous = Building.objects.filter(
                pk=self.pk
            ).first()

            has_children = (
                self.floors.exists()
                or self.units.exists()
            )

            if (
                previous
                and has_children
                and (
                    previous.company_id != self.company_id
                    or previous.work_site_id != self.work_site_id
                )
            ):
                errors['work_site'] = (
                    'Company / Work Site cannot be changed '
                    'after floors or units have been added.'
                )

            if self.floors.count() > self.number_of_floors:
                errors['number_of_floors'] = (
                    'Floor count cannot be lower than the '
                    'number of existing floor records.'
                )

            if (
                previous
                and previous.building_type != self.building_type
                and has_children
            ):
                errors['building_type'] = (
                    'Building type cannot be changed while '
                    'floors or units exist.'
                )

        # Validate counts required by the selected type.
        if self.building_type == 'apartment':

            if self.number_of_floors < 1:
                errors['number_of_floors'] = (
                    'Enter at least one floor for an apartment building.'
                )

            if self.number_of_flats < 1:
                errors['number_of_flats'] = (
                    'Enter at least one flat / unit for an apartment building.'
                )

        elif self.building_type == 'villa':

            if self.number_of_villas < 1:
                errors['number_of_villas'] = 'Enter at least one villa.'

        elif self.building_type == 'office':

            if self.number_of_floors < 1:
                errors['number_of_floors'] = (
                    'Enter at least one floor for an office building.'
                )

            if self.number_of_office_units < 1:
                errors['number_of_office_units'] = (
                    'Enter at least one office unit.'
                )

        elif self.building_type == 'other':

            if not self.other_type_name.strip():
                errors['other_type_name'] = (
                    'Please specify the other building type.'
                )

            if self.number_of_other_units < 1:
                errors['number_of_other_units'] = (
                    'Enter at least one unit for this property type.'
                )

        # The configured counts cannot be less than existing units.
        if self.pk:

            count_fields = {
                'apartment': {
                    'flat': 'number_of_flats',
                    'office': 'number_of_office_units',
                    'other': 'number_of_other_units',
                },
                'villa': {
                    'villa': 'number_of_villas',
                },
                'office': {
                    'office': 'number_of_office_units',
                },
                'other': {
                    'other': 'number_of_other_units',
                },
            }.get(self.building_type, {})

            for unit_type, count_field in count_fields.items():

                configured_count = (
                    getattr(self, count_field, 0) or 0
                )

                existing_count = self.units.filter(
                    unit_type=unit_type
                ).count()

                if existing_count > configured_count:
                    errors[count_field] = (
                        'Configured count cannot be lower than '
                        'the number of existing units.'
                    )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):

        if self.building_type_master_id:
            self.building_type = self.building_type_master.code

        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} ({self.get_building_type_display()})'


# ============================================================
# BUILDING STAFF LOGIN
# ============================================================

class BuildingStaff(models.Model):

    building = models.OneToOneField(
        Building,
        on_delete=models.CASCADE,
        related_name='staff_account',
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='building_staff',
    )

    staff_name = models.CharField(max_length=150)
    designation = models.CharField(max_length=100, blank=True)
    mobile = models.CharField(max_length=30, blank=True)
    email = models.EmailField(max_length=254, blank=True)

    status = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['building__name']
        verbose_name = 'Building Staff'
        verbose_name_plural = 'Building Staff'

    def __str__(self):
        return f'{self.staff_name} - {self.building.name}'


# ============================================================
# FLOOR
# ============================================================

class Floor(models.Model):

    building = models.ForeignKey(
        Building,
        on_delete=models.CASCADE,
        related_name='floors',
    )

    name = models.CharField(max_length=100)

    floor_number = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    status = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            'building__name',
            'floor_number',
            'name',
        ]

        constraints = [
            models.UniqueConstraint(
                fields=['building', 'name'],
                name='unique_floor_building_name',
            )
        ]

        verbose_name = 'Floor'
        verbose_name_plural = 'Floors'

    def clean(self):

        errors = {}

        if self.building_id:

            building = self.building

            if building.building_type == 'villa':
                errors['building'] = (
                    'Villa properties do not need floor records.'
                )

            if (
                self.floor_number is not None
                and self.floor_number > building.number_of_floors
            ):
                errors['floor_number'] = (
                    f'Floor number cannot exceed the configured '
                    f'building floor count ({building.number_of_floors}).'
                )

            existing_floors = Floor.objects.filter(
                building_id=self.building_id
            )

            if self.pk:
                existing_floors = existing_floors.exclude(
                    pk=self.pk
                )

            if (
                existing_floors.count()
                >= building.number_of_floors
            ):
                errors['building'] = (
                    f'This building is configured for only '
                    f'{building.number_of_floors} floor(s).'
                )

            if self.floor_number is not None:

                duplicate = Floor.objects.filter(
                    building_id=self.building_id,
                    floor_number=self.floor_number,
                )

                if self.pk:
                    duplicate = duplicate.exclude(pk=self.pk)

                if duplicate.exists():
                    errors['floor_number'] = (
                        'This floor number is already used '
                        'in this building.'
                    )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.building.name} - {self.name}'


# ============================================================
# UNIT
# ============================================================

class Unit(models.Model):

    UNIT_TYPE_CHOICES = (
        ('flat', 'Flat'),
        ('villa', 'Villa'),
        ('office', 'Office'),
        ('other', 'Other'),
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='units',
    )

    work_site = models.ForeignKey(
        WorkSite,
        on_delete=models.CASCADE,
        related_name='units',
    )

    building = models.ForeignKey(
        Building,
        on_delete=models.CASCADE,
        related_name='units',
    )

    floor = models.ForeignKey(
        Floor,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='units',
    )

    establishment_type = models.ForeignKey(
        EstablishmentType,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='units',
    )

    name = models.CharField(
        max_length=100,
        verbose_name='Unit Name / Number',
    )
    email = models.EmailField(max_length=254, blank=True, default='')
    mobile_number = models.CharField(max_length=30, blank=True, default='')
    user = models.OneToOneField(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='unit_profile')

    unit_type = models.CharField(
        max_length=20,
        choices=UNIT_TYPE_CHOICES,
        default='flat',
    )

    status = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            'building__name',
            'floor__floor_number',
            'name',
        ]

        constraints = [
            models.UniqueConstraint(
                fields=['building', 'name'],
                name='unique_unit_building_name',
            )
        ]

        verbose_name = 'Unit'
        verbose_name_plural = 'Units'

    def clean(self):

        errors = {}

        if not self.establishment_type_id:
            errors['establishment_type'] = (
                'Select an Establishment Type.'
            )

        if self.building_id:

            building = self.building

            # Company and Work Site must match the Building.
            if self.company_id != building.company_id:
                errors['company'] = (
                    'Company must match the selected building.'
                )

            if self.work_site_id != building.work_site_id:
                errors['work_site'] = (
                    'Work Site must match the selected building.'
                )

            # The selected floor must belong to this building.
            if (
                self.floor_id
                and self.floor.building_id != building.pk
            ):
                errors['floor'] = (
                    'Selected floor does not belong '
                    'to the selected building.'
                )

            # Determine capacity according to the building type.
            if building.building_type == 'villa':

                if self.floor_id:
                    errors['floor'] = (
                        'Floor selection is not required '
                        'for villa buildings.'
                    )

                if self.unit_type != 'villa':
                    errors['unit_type'] = (
                        'Units in this property must use '
                        'the Villa unit type.'
                    )

                count_field = 'number_of_villas'

            elif building.building_type == 'office':

                if self.unit_type != 'office':
                    errors['unit_type'] = (
                        'Units in this building must use '
                        'the Office unit type.'
                    )

                count_field = 'number_of_office_units'

            elif building.building_type == 'other':

                if self.unit_type != 'other':
                    errors['unit_type'] = (
                        'Units in this property must use '
                        'the Other unit type.'
                    )

                count_field = 'number_of_other_units'

            else:

                allowed_types = {
                    'flat',
                    'office',
                    'other',
                }

                if self.unit_type not in allowed_types:
                    errors['unit_type'] = (
                        'Apartment buildings can contain '
                        'flats, offices or other units.'
                    )

                count_field = {
                    'flat': 'number_of_flats',
                    'office': 'number_of_office_units',
                    'other': 'number_of_other_units',
                }.get(self.unit_type)

            # Floors are required for non-villa buildings
            # when the building is configured with floors.
            if (
                building.building_type != 'villa'
                and building.number_of_floors > 0
                and not self.floor_id
            ):
                errors['floor'] = (
                    'Select a floor for this building.'
                )

            # ------------------------------------------------
            # UNIT CAPACITY VALIDATION
            # ------------------------------------------------

            if count_field:

                limit = (
                    getattr(building, count_field, 0) or 0
                )

                existing = Unit.objects.filter(
                    building_id=building.pk,
                    unit_type=self.unit_type,
                )

                # Do not count the current record while editing.
                if self.pk:
                    existing = existing.exclude(pk=self.pk)

                existing_count = existing.count()

                if limit <= 0:
                    errors['name'] = (
                        f'No capacity is configured for '
                        f'{self.get_unit_type_display()} units '
                        f'in this building. Open the Building Edit '
                        f'page and set {count_field} to the '
                        f'number of units allowed.'
                    )

                elif existing_count >= limit:
                    errors['name'] = (
                        f'The configured capacity for this unit '
                        f'type is {limit}. There are already '
                        f'{existing_count} unit(s) of this type. '
                        f'Increase the building count before '
                        f'adding more units.'
                    )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.building.name} - {self.name}'


# ============================================================
# TENANT
# A tenant can be assigned multiple individual units. The legacy primary
# unit is retained for compatibility; allocation history is the source of truth.
# ============================================================

class Tenant(models.Model):

    TENANT_TYPE_CHOICES = [
        ('rental', 'Rental Tenant'),
        ('owner', 'Owner'),
    ]

    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='tenants',
    )

    # Source of truth for unit allocation. The legacy `unit` FK is retained
    # for compatibility with existing code/data and points to the first allocation.
    allocated_units = models.ManyToManyField(
        Unit,
        through='TenantUnitAllocation',
        related_name='allocated_tenants',
        blank=True,
    )

    # Every new tenant can have a separate Django login account.
    # Nullable to preserve existing tenant records created before accounts were added.
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        related_name='tenant_profile',
        blank=True,
        null=True,
    )

    full_name = models.CharField(max_length=150)
    mobile_number = models.CharField(max_length=30)
    email = models.EmailField(max_length=254, blank=True, null=True)
    address = models.TextField(blank=True, default='')
    tenant_type = models.CharField(
        max_length=10,
        choices=TENANT_TYPE_CHOICES,
        default='rental',
    )
    identity_number = models.CharField(max_length=100, blank=True, null=True)
    lease_start_date = models.DateField(blank=True, null=True)
    lease_end_date = models.DateField(blank=True, null=True)
    status = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    # New tenant accounts must change their initial password at first login.
    # Existing accounts remain unchanged by the migration.
    must_change_password = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['unit__building__name', 'unit__name', 'full_name']
        verbose_name = 'Tenant'
        verbose_name_plural = 'Tenants'

    def clean(self):
        errors = {}
        if self.lease_start_date and self.lease_end_date:
            if self.lease_end_date < self.lease_start_date:
                errors['lease_end_date'] = 'Lease end date cannot be earlier than lease start date.'
        if self.unit_id and not self.unit.status:
            # Existing tenants can remain assigned to an inactive unit,
            # but new tenant assignments should use active units.
            if not self.pk:
                errors['unit'] = 'Select an active unit.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.full_name} - {self.unit.name}'


class TenantFamilyMember(models.Model):
    """A family member belonging to one tenant in one unit."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='family_members',
    )
    name = models.CharField(max_length=150)
    mobile_number = models.CharField(max_length=30)
    relationship = models.CharField(max_length=100, blank=True, default='')
    email = models.EmailField(max_length=254, blank=True, null=True)
    address = models.TextField(blank=True, default='')
    unit = models.ForeignKey(
        Unit,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='tenant_family_members',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Tenant Family Member'
        verbose_name_plural = 'Tenant Family Members'

    def __str__(self):
        return f'{self.name} - {self.tenant.full_name}'



# ============================================================
# TENANT UNIT ALLOCATION
# One unit can be allocated to only one tenant at a time.
# Deleting a tenant releases all its allocations automatically.
# ============================================================

class TenantStaffMember(models.Model):
    """Household/domestic staff details managed under a tenant account."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='staff_members',
    )
    name = models.CharField(max_length=150)
    designation = models.CharField(max_length=100, blank=True)
    mobile_number = models.CharField(max_length=30)
    email = models.EmailField(max_length=254, blank=True, null=True)
    address = models.TextField(blank=True, default='')
    unit = models.ForeignKey(
        Unit,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='tenant_staff_members',
    )
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Tenant Staff Member'
        verbose_name_plural = 'Tenant Staff Members'

    def __str__(self):
        return f'{self.name} - {self.tenant.full_name}'


class TenantUnitAllocation(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='unit_allocations',
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='tenant_allocations',
    )
    allocated_at = models.DateTimeField(auto_now_add=True)
    # NULL means currently allocated. A timestamp releases the unit while
    # retaining the historical tenant/unit assignment.
    released_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['unit__building__name', 'unit__name', 'allocated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['unit'],
                condition=Q(released_at__isnull=True),
                name='unique_active_tenant_per_unit',
            ),
            models.UniqueConstraint(
                fields=['tenant', 'unit'],
                condition=Q(released_at__isnull=True),
                name='unique_tenant_unit_allocation',
            ),
        ]

    def clean(self):
        errors = {}
        if self.unit_id and not self.unit.status:
            errors['unit'] = 'Only active units can be allocated to a tenant.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.tenant.full_name} - {self.unit.name}'


# ============================================================
# GUEST / VISITOR VISIT
# ============================================================

class GuestVisit(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_DENIED = 'denied'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_DENIED, 'Rejected'),
    ]
    TYPE_ADVANCE = 'advance'
    TYPE_WALK_IN = 'walk_in'
    VISIT_TYPE_CHOICES = [
        (TYPE_ADVANCE, 'Advance Visit'),
        (TYPE_WALK_IN, 'Walk-in Visit'),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='guest_visits',
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='guest_visits',
    )
    guest_name = models.CharField(max_length=150)
    guest_photo = models.ImageField(upload_to='guest_photos/', blank=True, null=True)
    guest_mobile_number = models.CharField(max_length=30, blank=True, default='')
    # Number of additional visitors accompanying the primary guest (e.g. 4 means 5 people total).
    additional_visitors = models.PositiveSmallIntegerField(default=0)
    visitor_id_card_number = models.CharField(max_length=80, blank=True, default='', db_index=True)
    ID_TYPE_CHOICES = [
        ('national_id', 'National ID'),
        ('passport', 'Passport'),
        ('driving_license', 'Driving Licence'),
        ('other', 'Other ID'),
    ]
    id_type = models.CharField(max_length=20, choices=ID_TYPE_CHOICES, blank=True, default='')
    id_number = models.CharField(max_length=100, blank=True, default='')
    id_received_at = models.DateTimeField(blank=True, null=True)
    id_received_by = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='received_guest_ids')
    id_returned_at = models.DateTimeField(blank=True, null=True)
    id_returned_by = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='returned_guest_ids')
    visit_type = models.CharField(max_length=10, choices=VISIT_TYPE_CHOICES, default=TYPE_ADVANCE, db_index=True)
    vehicle_details = models.CharField(max_length=150, blank=True, default='')
    purpose_of_visit = models.ForeignKey(
        'core.PurposeOfVisit',
        on_delete=models.PROTECT,
        related_name='guest_visits',
    )
    visit_date = models.DateField()
    visit_time = models.TimeField(blank=True, null=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    unit_approval_status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    tenant_approval_status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    gate_pass_code = models.CharField(
        max_length=32,
        unique=True,
        blank=True,
        null=True,
    )
    approved_at = models.DateTimeField(blank=True, null=True)
    checked_in_at = models.DateTimeField(blank=True, null=True)
    checked_out_at = models.DateTimeField(blank=True, null=True)
    checked_in_by = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='checked_in_guest_visits')
    checked_out_by = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='checked_out_guest_visits')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='created_guest_visits',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-visit_date', '-created_at']

    def clean(self):
        if self.tenant_id and self.unit_id:
            if not TenantUnitAllocation.objects.filter(
                tenant_id=self.tenant_id,
                unit_id=self.unit_id,
                released_at__isnull=True,
            ).exists():
                raise ValidationError({
                    'unit': 'The selected unit is not currently allocated to this tenant.'
                })
        if self.checked_out_at and not self.checked_in_at:
            raise ValidationError({'checked_out_at': 'A guest must be checked in before check-out.'})

    def __str__(self):
        return f'{self.guest_name} visiting {self.tenant.full_name} ({self.status})'


class GuestVisitAccompanyingPerson(models.Model):
    guest_visit = models.ForeignKey(
        GuestVisit,
        on_delete=models.CASCADE,
        related_name='accompanying_people',
    )
    name = models.CharField(max_length=150)
    mobile_number = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'Guest Accompanying Person'
        verbose_name_plural = 'Guest Accompanying People'

    def __str__(self):
        return f'{self.name} accompanying {self.guest_visit.guest_name}'


# ============================================================
# HOLD DOCUMENTS / CUSTOMER ITEMS
# ============================================================

class HoldDocument(models.Model):
    STATUS_HELD = 'held'
    STATUS_COLLECTED = 'collected'
    STATUS_LOST = 'lost'
    STATUS_CHOICES = [
        (STATUS_HELD, 'Held'),
        (STATUS_COLLECTED, 'Collected'),
        (STATUS_LOST, 'Lost'),
    ]

    visit = models.ForeignKey(
        GuestVisit,
        on_delete=models.SET_NULL,
        related_name='held_documents',
        null=True,
        blank=True,
    )
    PERSON_GUEST = 'guest'
    PERSON_TENANT = 'tenant'
    PERSON_STAFF = 'staff'
    PERSON_OTHER = 'other'
    PERSON_TYPE_CHOICES = [
        (PERSON_GUEST, 'Guest'),
        (PERSON_TENANT, 'Tenant'),
        (PERSON_STAFF, 'Staff'),
        (PERSON_OTHER, 'Other'),
    ]
    person_type = models.CharField(max_length=20, choices=PERSON_TYPE_CHOICES, default=PERSON_GUEST)
    person_name = models.CharField(max_length=200, blank=True, default='')
    person_mobile = models.CharField(max_length=30, blank=True, default='')
    item_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    quantity = models.PositiveIntegerField(default=1)
    reference_number = models.CharField(max_length=100, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_HELD, db_index=True)
    received_at = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='held_documents_received')
    collected_at = models.DateTimeField(null=True, blank=True)
    collected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='held_documents_collected')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-received_at']

    def __str__(self):
        person = self.person_name or (self.visit.guest_name if self.visit_id else 'Unknown Person')
        return f'{self.item_name} - {person}'


# ============================================================
# ID / NFC TAG INVENTORY AND VISIT ISSUE TRACKING
# ============================================================
class IDTag(models.Model):
    TYPE_DYNAMIC = 'dynamic'
    TYPE_PREDEFINED = 'predefined'
    TYPE_CHOICES = [(TYPE_DYNAMIC, 'Dynamic ID Card'), (TYPE_PREDEFINED, 'Predefined NFC / ID Tag')]
    STATUS_AVAILABLE = 'available'
    STATUS_ISSUED = 'issued'
    STATUS_RETURNED = 'returned'
    STATUS_LOST = 'lost'
    STATUS_DAMAGED = 'damaged'
    STATUS_CHOICES = [(STATUS_AVAILABLE, 'Available'), (STATUS_ISSUED, 'Issued'), (STATUS_RETURNED, 'Returned'), (STATUS_LOST, 'Lost'), (STATUS_DAMAGED, 'Damaged')]
    tag_number = models.CharField(max_length=80, unique=True)
    nfc_number = models.CharField(max_length=100, blank=True, default='')
    tag_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_PREDEFINED)
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='id_tags', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_AVAILABLE, db_index=True)
    notes = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['tag_number']
    def __str__(self):
        return self.tag_number

class IDTagIssue(models.Model):
    STATUS_ISSUED = 'issued'
    STATUS_RETURNED = 'returned'
    STATUS_LOST = 'lost'
    STATUS_DAMAGED = 'damaged'
    STATUS_CHOICES = [(STATUS_ISSUED, 'Issued'), (STATUS_RETURNED, 'Returned'), (STATUS_LOST, 'Lost'), (STATUS_DAMAGED, 'Damaged')]
    visit = models.ForeignKey(GuestVisit, on_delete=models.CASCADE, related_name='tag_issues')
    tag = models.ForeignKey(IDTag, on_delete=models.PROTECT, related_name='issues')
    issued_at = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='issued_id_tags')
    returned_at = models.DateTimeField(null=True, blank=True)
    returned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='returned_id_tags')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ISSUED, db_index=True)
    class Meta:
        ordering = ['-issued_at']
        constraints = [
            models.UniqueConstraint(
                fields=['visit', 'tag'],
                name='unique_visit_id_tag_issue',
            ),
            models.UniqueConstraint(
                fields=['tag'],
                condition=Q(status='issued'),
                name='unique_active_id_tag_issue',
            ),
        ]
    def __str__(self):
        return f'{self.tag.tag_number} - {self.visit.guest_name}'


# ============================================================
# NOTIFICATION SYSTEM
# ============================================================
class Notification(models.Model):
    TYPE_ADVANCE_REQUEST = 'advance_request'
    TYPE_WALK_IN_REQUEST = 'walk_in_request'
    TYPE_UNIT_ACCEPTED = 'unit_accepted'
    TYPE_UNIT_REJECTED = 'unit_rejected'
    TYPE_TENANT_APPROVED = 'tenant_approved'
    TYPE_TENANT_REJECTED = 'tenant_rejected'
    TYPE_GATE_PASS_ISSUED = 'gate_pass_issued'
    TYPE_CHECKED_IN = 'checked_in'
    TYPE_CHECKED_OUT = 'checked_out'
    TYPE_GENERAL = 'general'

    TYPE_CHOICES = [
        (TYPE_ADVANCE_REQUEST, 'Advance Guest Request'),
        (TYPE_WALK_IN_REQUEST, 'Walk-in Guest Request'),
        (TYPE_UNIT_ACCEPTED, 'Unit Accepted Request'),
        (TYPE_UNIT_REJECTED, 'Unit Rejected Request'),
        (TYPE_TENANT_APPROVED, 'Tenant Approved Request'),
        (TYPE_TENANT_REJECTED, 'Tenant Rejected Request'),
        (TYPE_GATE_PASS_ISSUED, 'Gate Pass Issued'),
        (TYPE_CHECKED_IN, 'Guest Checked In'),
        (TYPE_CHECKED_OUT, 'Guest Checked Out'),
        (TYPE_GENERAL, 'General Notification'),
    ]

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications',
    )
    visit = models.ForeignKey(
        'GuestVisit',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=50,
        choices=TYPE_CHOICES,
        default=TYPE_GENERAL,
        db_index=True,
    )
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'

    def __str__(self):
        return f'{self.recipient.username}: {self.title}'

