from rest_framework import serializers
from django.utils import timezone
from django.db import transaction

from core.models import (
    Country,
    State,
    District,
    Area,
    Designation,
    EstablishmentType,
    PurposeOfVisit,
)
from operations.models import (
    Unit,
    Tenant,
    TenantUnitAllocation,
    GuestVisit,
    GuestVisitAccompanyingPerson,
    Notification,
    IDTag,
    IDTagIssue,
)
from api.utils import generate_qr_code_base64, mask_id_number


# =========================================================
# EXISTING CORE MASTER SERIALIZERS
# =========================================================

class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = [
            'id', 'name', 'currency_code', 'emblem', 'dial_code',
            'status', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Country name is required.")
        return value


class StateSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source='country.name', read_only=True)

    class Meta:
        model = State
        fields = [
            'id', 'country', 'country_name', 'name',
            'status', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'country_name', 'created_at', 'updated_at']

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("State name is required.")
        return value


class DistrictSerializer(serializers.ModelSerializer):
    state_name = serializers.CharField(source='state.name', read_only=True)
    country_name = serializers.CharField(source='state.country.name', read_only=True)

    class Meta:
        model = District
        fields = [
            'id', 'state', 'state_name', 'country_name', 'name',
            'status', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'state_name', 'country_name', 'created_at', 'updated_at']

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("District name is required.")
        return value


class AreaSerializer(serializers.ModelSerializer):
    district_name = serializers.CharField(source='district.name', read_only=True)
    state_name = serializers.CharField(source='district.state.name', read_only=True)
    country_name = serializers.CharField(source='district.state.country.name', read_only=True)

    class Meta:
        model = Area
        fields = [
            'id', 'district', 'district_name', 'state_name', 'country_name',
            'name', 'status', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'district_name', 'state_name', 'country_name', 'created_at', 'updated_at']

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Area name is required.")
        return value


class DesignationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Designation
        fields = ['id', 'name', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Designation name is required.")
        return value


class EstablishmentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EstablishmentType
        fields = ['id', 'name', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Establishment Type name is required.")
        return value


class PurposeOfVisitSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurposeOfVisit
        fields = ['id', 'name', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Purpose of Visit name is required.")
        return value


# =========================================================
# AUTH & PROFILE SERIALIZERS
# =========================================================

class LoginInputSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)


class AccompanyingPersonInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=True)
    mobile_number = serializers.CharField(max_length=30, required=True)

    def validate_name(self, val):
        val = val.strip()
        if not val:
            raise serializers.ValidationError("Name cannot be blank.")
        return val

    def validate_mobile_number(self, val):
        val = val.strip()
        if not val:
            raise serializers.ValidationError("Mobile number cannot be blank.")
        return val


class AccompanyingPersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestVisitAccompanyingPerson
        fields = ['id', 'name', 'mobile_number', 'created_at']


# =========================================================
# UNIT SERIALIZERS
# =========================================================

class UnitDetailSerializer(serializers.ModelSerializer):
    building_name = serializers.CharField(source='building.name', read_only=True)
    floor_name = serializers.CharField(source='floor.name', read_only=True, default='')
    floor_number = serializers.IntegerField(source='floor.floor_number', read_only=True, default=None)
    company_name = serializers.CharField(source='company.name', read_only=True)
    work_site_name = serializers.CharField(source='work_site.name', read_only=True)
    establishment_type_name = serializers.CharField(source='establishment_type.name', read_only=True, default='')
    unit_type_display = serializers.CharField(source='get_unit_type_display', read_only=True)
    current_tenant = serializers.SerializerMethodField()

    class Meta:
        model = Unit
        fields = [
            'id', 'name', 'email', 'mobile_number', 'unit_type', 'unit_type_display',
            'building_id', 'building_name',
            'floor_id', 'floor_name', 'floor_number',
            'company_id', 'company_name',
            'work_site_id', 'work_site_name',
            'establishment_type_id', 'establishment_type_name',
            'status', 'current_tenant',
        ]

    def get_current_tenant(self, obj):
        allocation = obj.tenant_allocations.filter(released_at__isnull=True).select_related('tenant').first()
        if allocation and allocation.tenant:
            t = allocation.tenant
            return {
                'id': t.id,
                'full_name': t.full_name,
                'mobile_number': t.mobile_number,
                'email': t.email,
                'tenant_type': t.tenant_type,
                'tenant_type_display': t.get_tenant_type_display(),
            }
        return None


# =========================================================
# TENANT SERIALIZERS
# =========================================================

class TenantAllocatedUnitSerializer(serializers.Serializer):
    unit_id = serializers.IntegerField()
    unit_name = serializers.CharField()
    building_id = serializers.IntegerField()
    building_name = serializers.CharField()
    floor_name = serializers.CharField(default='')
    company_name = serializers.CharField()
    allocated_at = serializers.DateTimeField()


class TenantProfileSerializer(serializers.ModelSerializer):
    tenant_type_display = serializers.CharField(source='get_tenant_type_display', read_only=True)
    allocated_units = serializers.SerializerMethodField()
    username = serializers.CharField(source='user.username', read_only=True, default='')
    family_members_count = serializers.SerializerMethodField()
    staff_members_count = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = [
            'id', 'username', 'full_name', 'mobile_number', 'email', 'address',
            'tenant_type', 'tenant_type_display', 'identity_number',
            'lease_start_date', 'lease_end_date', 'status', 'notes',
            'must_change_password', 'allocated_units',
            'family_members_count', 'staff_members_count',
            'created_at', 'updated_at',
        ]

    def get_allocated_units(self, obj):
        allocations = obj.unit_allocations.filter(
            released_at__isnull=True,
            unit__status=True,
        ).select_related('unit', 'unit__building', 'unit__floor', 'unit__company')
        result = []
        for alloc in allocations:
            result.append({
                'unit_id': alloc.unit.id,
                'unit_name': alloc.unit.name,
                'building_id': alloc.unit.building.id,
                'building_name': alloc.unit.building.name,
                'floor_name': alloc.unit.floor.name if alloc.unit.floor else '',
                'company_name': alloc.unit.company.name,
                'allocated_at': alloc.allocated_at,
            })
        return result

    def get_family_members_count(self, obj):
        return obj.family_members.count()

    def get_staff_members_count(self, obj):
        return obj.staff_members.filter(status=True).count()


class TenantProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ['full_name', 'mobile_number', 'email', 'address', 'notes']

    def validate_full_name(self, value):
        val = value.strip()
        if not val:
            raise serializers.ValidationError("Full name cannot be blank.")
        return val

    def validate_mobile_number(self, value):
        val = value.strip()
        if not val:
            raise serializers.ValidationError("Mobile number cannot be blank.")
        return val


# =========================================================
# GUEST VISIT SERIALIZERS
# =========================================================

class GuestVisitListSerializer(serializers.ModelSerializer):
    visit_type_display = serializers.CharField(source='get_visit_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    purpose_name = serializers.CharField(source='purpose_of_visit.name', read_only=True)
    unit_name = serializers.CharField(source='unit.name', read_only=True)
    building_name = serializers.CharField(source='unit.building.name', read_only=True)
    tenant_name = serializers.CharField(source='tenant.full_name', read_only=True)
    accompanying_count = serializers.SerializerMethodField()
    is_checked_in = serializers.SerializerMethodField()
    is_checked_out = serializers.SerializerMethodField()
    guest_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = GuestVisit
        fields = [
            'id', 'guest_name', 'guest_mobile_number', 'guest_photo_url',
            'visit_type', 'visit_type_display',
            'purpose_of_visit', 'purpose_name',
            'unit_id', 'unit_name', 'building_name',
            'tenant_id', 'tenant_name',
            'visit_date', 'visit_time',
            'status', 'status_display',
            'unit_approval_status', 'tenant_approval_status',
            'gate_pass_code', 'additional_visitors', 'accompanying_count',
            'is_checked_in', 'checked_in_at',
            'is_checked_out', 'checked_out_at',
            'created_at',
        ]

    def get_accompanying_count(self, obj):
        return obj.accompanying_people.count()

    def get_is_checked_in(self, obj):
        return bool(obj.checked_in_at)

    def get_is_checked_out(self, obj):
        return bool(obj.checked_out_at)

    def get_guest_photo_url(self, obj):
        if obj.guest_photo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.guest_photo.url)
            return obj.guest_photo.url
        return None


class GuestVisitDetailSerializer(GuestVisitListSerializer):
    accompanying_people = AccompanyingPersonSerializer(many=True, read_only=True)
    masked_id_number = serializers.SerializerMethodField()
    qr_code_image = serializers.SerializerMethodField()
    qr_data = serializers.SerializerMethodField()
    active_tag_numbers = serializers.SerializerMethodField()

    class Meta:
        model = GuestVisit
        fields = GuestVisitListSerializer.Meta.fields + [
            'vehicle_details', 'notes', 'visitor_id_card_number',
            'id_type', 'id_number', 'masked_id_number',
            'id_received_at', 'id_returned_at',
            'accompanying_people',
            'qr_code_image', 'qr_data',
            'active_tag_numbers',
        ]

    def get_masked_id_number(self, obj):
        return mask_id_number(obj.id_number)

    def get_qr_code_image(self, obj):
        if obj.gate_pass_code and obj.status == GuestVisit.STATUS_APPROVED:
            return generate_qr_code_base64(obj.gate_pass_code)
        return ""

    def get_qr_data(self, obj):
        return obj.gate_pass_code if (obj.gate_pass_code and obj.status == GuestVisit.STATUS_APPROVED) else ""

    def get_active_tag_numbers(self, obj):
        return list(
            obj.tag_issues.filter(status=IDTagIssue.STATUS_ISSUED).values_list('tag__tag_number', flat=True)
        )


class HouseholderAdvanceVisitCreateSerializer(serializers.Serializer):
    guest_name = serializers.CharField(max_length=150, required=True)
    guest_mobile_number = serializers.CharField(max_length=30, required=True)
    purpose_of_visit = serializers.CharField(required=True)
    visit_date = serializers.DateField(required=True)
    visit_time = serializers.TimeField(required=False, allow_null=True)
    vehicle_details = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    additional_visitors = serializers.IntegerField(required=False, default=0, min_value=0, max_value=100)
    accompanying_people = AccompanyingPersonInputSerializer(many=True, required=False, default=list)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    guest_photo = serializers.ImageField(required=False, allow_null=True)

    def validate_guest_name(self, value):
        val = value.strip()
        if not val:
            raise serializers.ValidationError("Guest name is required.")
        return val

    def validate_guest_mobile_number(self, value):
        val = value.strip()
        if not val:
            raise serializers.ValidationError("Guest mobile number is required.")
        return val

    def validate_purpose_of_visit(self, value):
        try:
            purpose = PurposeOfVisit.objects.filter(pk=value, status=True).first()
        except Exception:
            purpose = None
        if not purpose:
            raise serializers.ValidationError("Select a valid active purpose of visit.")
        return purpose.pk


class TenantAdvanceVisitCreateSerializer(HouseholderAdvanceVisitCreateSerializer):
    unit = serializers.IntegerField(required=True)

    def validate_unit(self, value):
        tenant = self.context.get('tenant')
        if not tenant:
            raise serializers.ValidationError("Tenant context required.")
        has_allocation = TenantUnitAllocation.objects.filter(
            tenant=tenant,
            unit_id=value,
            released_at__isnull=True,
            unit__status=True,
        ).exists()
        if not has_allocation:
            raise serializers.ValidationError("The selected unit is not currently allocated to your account.")
        return value


class TenantWalkInVisitCreateSerializer(TenantAdvanceVisitCreateSerializer):
    pass


class GatePassDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    gate_pass_code = serializers.CharField()
    status = serializers.CharField()
    visit_type = serializers.CharField()
    guest_name = serializers.CharField()
    guest_mobile_number = serializers.CharField()
    guest_photo_url = serializers.CharField(allow_null=True)
    unit_id = serializers.IntegerField()
    unit_name = serializers.CharField()
    building_name = serializers.CharField()
    tenant_id = serializers.IntegerField()
    tenant_name = serializers.CharField()
    purpose_name = serializers.CharField()
    visit_date = serializers.DateField()
    visit_time = serializers.TimeField(allow_null=True)
    vehicle_details = serializers.CharField(allow_blank=True)
    additional_visitors = serializers.IntegerField()
    accompanying_people = AccompanyingPersonSerializer(many=True)
    masked_id_number = serializers.CharField(allow_blank=True)
    qr_code_image = serializers.CharField()
    qr_data = serializers.CharField()
    is_checked_in = serializers.BooleanField()
    checked_in_at = serializers.DateTimeField(allow_null=True)
    is_checked_out = serializers.BooleanField()
    checked_out_at = serializers.DateTimeField(allow_null=True)
    active_id_tags = serializers.ListField(child=serializers.CharField())
    created_at = serializers.DateTimeField()


# =========================================================
# SECURITY OPERATIONS SERIALIZERS
# =========================================================

class GatePassVerifyInputSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)

    def validate_code(self, val):
        val = val.strip()
        if not val:
            raise serializers.ValidationError("Gate Pass number or QR code reference is required.")
        return val


class CheckInInputSerializer(serializers.Serializer):
    id_type = serializers.ChoiceField(choices=GuestVisit.ID_TYPE_CHOICES, required=True)
    id_number = serializers.CharField(max_length=100, required=True)
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_id_number(self, val):
        val = val.strip()
        if not val:
            raise serializers.ValidationError("ID number is required for check-in.")
        return val


class CheckOutInputSerializer(serializers.Serializer):
    return_id = serializers.BooleanField(required=False, default=True)
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class IDTagReturnInputSerializer(serializers.Serializer):
    tag_number = serializers.CharField(required=False, allow_blank=True)
    issue_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if not attrs.get('tag_number') and not attrs.get('issue_id'):
            raise serializers.ValidationError("Provide either tag_number or issue_id to return.")
        return attrs


# =========================================================
# NOTIFICATION SERIALIZERS
# =========================================================

class NotificationSerializer(serializers.ModelSerializer):
    created_at_formatted = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id', 'title', 'message', 'notification_type',
            'visit_id', 'is_read', 'read_at', 'created_at', 'created_at_formatted',
        ]

    def get_created_at_formatted(self, obj):
        return timezone.localtime(obj.created_at).strftime('%d-%m-%Y %I:%M %p')
