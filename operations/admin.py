from django.contrib import admin
from .models import Company, CompanyStaff, CompanyDesignation, WorkSite, Building, BuildingTypeMaster, BuildingStaff, Floor, Unit, Tenant, TenantUnitAllocation, TenantFamilyMember, TenantStaffMember, GuestVisit, GuestVisitAccompanyingPerson, IDTag, IDTagIssue, HoldDocument, Notification


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'country', 'state', 'status')
    search_fields = ('name', 'tax_number', 'email')
    list_filter = ('status', 'country')


@admin.register(CompanyStaff)
class CompanyStaffAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'status')
    search_fields = ('user__username', 'company__name')
    list_filter = ('status', 'company')


@admin.register(CompanyDesignation)
class CompanyDesignationAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'status')
    search_fields = ('name', 'company__name')
    list_filter = ('status', 'company')


@admin.register(WorkSite)
class WorkSiteAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'location', 'status')
    search_fields = ('name', 'company__name', 'location')
    list_filter = ('status', 'company')


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ('name', 'building_type', 'company', 'work_site', 'status')
    search_fields = ('name', 'company__name', 'work_site__name')
    list_filter = ('status', 'building_type', 'company', 'work_site')


@admin.register(Floor)
class FloorAdmin(admin.ModelAdmin):
    list_display = ('name', 'building', 'floor_number', 'status')
    search_fields = ('name', 'building__name')
    list_filter = ('status', 'building')


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ('name', 'unit_type', 'company', 'work_site', 'building', 'floor', 'status')
    search_fields = ('name', 'company__name', 'work_site__name', 'building__name')
    list_filter = ('status', 'unit_type', 'company', 'work_site', 'building')


@admin.register(BuildingTypeMaster)
class BuildingTypeMasterAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'status')
    search_fields = ('name', 'description')
    list_filter = ('code', 'status')


@admin.register(BuildingStaff)
class BuildingStaffAdmin(admin.ModelAdmin):
    list_display = ('staff_name', 'user', 'building', 'status')
    search_fields = ('staff_name', 'user__username', 'building__name')
    list_filter = ('status',)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'tenant_type', 'user', 'mobile_number', 'unit', 'status', 'lease_start_date', 'lease_end_date')
    search_fields = ('full_name', 'mobile_number', 'email', 'identity_number', 'unit__name', 'unit__building__name')
    list_filter = ('status', 'unit__building')



@admin.register(TenantFamilyMember)
class TenantFamilyMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'mobile_number', 'email')
    search_fields = (
        'name',
        'mobile_number',
        'email',
        'tenant__full_name',
        'tenant__unit__name',
        'tenant__unit__building__name',
    )


@admin.register(TenantUnitAllocation)
class TenantUnitAllocationAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'unit', 'allocated_at')
    search_fields = ('tenant__full_name', 'unit__name', 'unit__building__name')
    list_select_related = ('tenant', 'unit', 'unit__building')


@admin.register(GuestVisit)
class GuestVisitAdmin(admin.ModelAdmin):
    list_display = ('guest_name', 'guest_mobile_number', 'tenant', 'visit_type', 'purpose_of_visit', 'visit_date', 'status', 'checked_in_at', 'checked_out_at', 'gate_pass_code')
    search_fields = ('guest_name', 'guest_mobile_number', 'tenant__full_name', 'gate_pass_code', 'vehicle_details')
    list_filter = ('visit_type', 'status', 'visit_date', 'purpose_of_visit')
    readonly_fields = ('gate_pass_code', 'approved_at', 'checked_in_at', 'checked_out_at', 'created_at', 'updated_at')


@admin.register(GuestVisitAccompanyingPerson)
class GuestVisitAccompanyingPersonAdmin(admin.ModelAdmin):
    list_display = ('name', 'mobile_number', 'guest_visit')
    search_fields = ('name', 'mobile_number', 'guest_visit__guest_name')


@admin.register(TenantStaffMember)
class TenantStaffMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'designation', 'mobile_number', 'tenant', 'status')
    list_filter = ('status',)
    search_fields = ('name', 'designation', 'mobile_number', 'tenant__full_name')


from .models import IDTag, IDTagIssue, HoldDocument

@admin.register(IDTag)
class IDTagAdmin(admin.ModelAdmin):
    list_display = ("tag_number", "nfc_number", "tag_type", "building", "status")
    list_filter = ("tag_type", "status", "building")
    search_fields = ("tag_number", "nfc_number", "building__name")

@admin.register(IDTagIssue)
class IDTagIssueAdmin(admin.ModelAdmin):
    list_display = ("tag", "visit", "issued_at", "issued_by", "returned_at", "status")
    list_filter = ("status", "issued_at")
    search_fields = ("tag__tag_number", "visit__guest_name", "visit__visitor_id_card_number")


@admin.register(HoldDocument)
class HoldDocumentAdmin(admin.ModelAdmin):
    list_display = ('item_name', 'visit', 'quantity', 'status', 'received_at', 'collected_at')
    list_filter = ('status', 'received_at')
    search_fields = ('item_name', 'reference_number', 'visit__guest_name', 'visit__tenant__full_name')
    readonly_fields = ('received_at', 'collected_at')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'recipient', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'recipient__username')
    readonly_fields = ('created_at',)

