import secrets
from datetime import date
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q, Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.http import HttpResponse

from rest_framework import permissions, status, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

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
    CompanyStaff,
    Unit,
    Tenant,
    TenantUnitAllocation,
    GuestVisit,
    GuestVisitAccompanyingPerson,
    Notification,
    IDTag,
    IDTagIssue,
)

from api.serializers import (
    CountrySerializer,
    StateSerializer,
    DistrictSerializer,
    AreaSerializer,
    DesignationSerializer,
    EstablishmentTypeSerializer,
    PurposeOfVisitSerializer,
    LoginInputSerializer,
    UnitDetailSerializer,
    TenantProfileSerializer,
    TenantProfileUpdateSerializer,
    GuestVisitListSerializer,
    GuestVisitDetailSerializer,
    HouseholderAdvanceVisitCreateSerializer,
    TenantAdvanceVisitCreateSerializer,
    TenantWalkInVisitCreateSerializer,
    GatePassDetailSerializer,
    GatePassVerifyInputSerializer,
    CheckInInputSerializer,
    CheckOutInputSerializer,
    IDTagReturnInputSerializer,
    NotificationSerializer,
)
from api.permissions import (
    IsHouseholder,
    IsTenant,
    IsHouseholderOrTenant,
    IsTenantSecurityAuthorized,
    get_active_unit,
    get_active_tenant,
)
from api.utils import (
    api_response,
    generate_gate_pass_code,
    generate_qr_code_base64,
    mask_id_number,
    create_notification,
)


def _format_gate_pass_dict(visit, request=None):
    """Builds standard Gate Pass data dictionary."""
    accompanying = [
        {
            'id': p.id,
            'name': p.name,
            'mobile_number': p.mobile_number,
            'created_at': p.created_at,
        }
        for p in visit.accompanying_people.all()
    ]
    guest_photo_url = None
    if visit.guest_photo:
        guest_photo_url = request.build_absolute_uri(visit.guest_photo.url) if request else visit.guest_photo.url

    active_tags = list(
        visit.tag_issues.filter(status=IDTagIssue.STATUS_ISSUED).values_list('tag__tag_number', flat=True)
    )

    return {
        'id': visit.id,
        'gate_pass_code': visit.gate_pass_code or '',
        'status': visit.status,
        'visit_type': visit.visit_type,
        'guest_name': visit.guest_name,
        'guest_mobile_number': visit.guest_mobile_number,
        'guest_photo_url': guest_photo_url,
        'unit_id': visit.unit_id,
        'unit_name': visit.unit.name,
        'building_name': visit.unit.building.name,
        'tenant_id': visit.tenant_id,
        'tenant_name': visit.tenant.full_name,
        'purpose_name': visit.purpose_of_visit.name if visit.purpose_of_visit else '',
        'visit_date': visit.visit_date,
        'visit_time': visit.visit_time,
        'vehicle_details': visit.vehicle_details,
        'additional_visitors': visit.additional_visitors,
        'accompanying_people': accompanying,
        'masked_id_number': mask_id_number(visit.id_number),
        'qr_code_image': generate_qr_code_base64(visit.gate_pass_code) if (visit.gate_pass_code and visit.status == GuestVisit.STATUS_APPROVED) else '',
        'qr_data': visit.gate_pass_code or '',
        'is_checked_in': bool(visit.checked_in_at),
        'checked_in_at': visit.checked_in_at,
        'is_checked_out': bool(visit.checked_out_at),
        'checked_out_at': visit.checked_out_at,
        'active_id_tags': active_tags,
        'created_at': visit.created_at,
    }


# =========================================================
# AUTHENTICATION APIS
# =========================================================

def _authenticate_and_create_token(username, password, expected_role=None):
    """
    Common login helper supporting:
    - superadmin
    - householder (Unit account)
    - tenant
    - company_staff
    """
    if '@' in username:
        matching = User.objects.filter(username__iexact=username).values_list('username', flat=True).first()
        if matching:
            username = matching

    user = authenticate(username=username, password=password)
    if not user:
        return None, "Invalid username or password.", status.HTTP_401_UNAUTHORIZED

    if not user.is_active:
        return None, "User account is inactive.", status.HTTP_403_FORBIDDEN

    # Determine user role
    role = None
    role_name = ""
    unit = None
    tenant = None
    company_id = None
    building_id = None

    if user.is_superuser:
        role = 'superadmin'
        role_name = 'Super Admin'
    else:
        # Check Unit (Householder) profile
        unit = get_active_unit(user)
        if unit:
            role = 'householder'
            role_name = 'Householder'
            company_id = unit.company_id
            building_id = unit.building_id
        else:
            # Check Tenant profile
            tenant = get_active_tenant(user)
            if tenant:
                role = 'tenant'
                role_name = 'Tenant'
                company_id = tenant.unit.company_id
                building_id = tenant.unit.building_id
            else:
                # Check Company Staff
                staff = CompanyStaff.objects.select_related('company').filter(
                    user=user, status=True, company__status=True
                ).first()
                if staff:
                    role = 'company_staff'
                    role_name = 'Company Admin'
                    company_id = staff.company_id

    if not role:
        return None, "Your account is not authorized or has no active profile.", status.HTTP_403_FORBIDDEN

    if expected_role and role != expected_role and not user.is_superuser:
        return None, f"Login restricted to {expected_role} accounts.", status.HTTP_403_FORBIDDEN

    refresh = RefreshToken.for_user(user)
    refresh['role'] = role
    if unit:
        refresh['unit_id'] = unit.id
    if tenant:
        refresh['tenant_id'] = tenant.id
    if company_id:
        refresh['company_id'] = company_id
    if building_id:
        refresh['building_id'] = building_id

    user_data = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'role': role,
        'role_name': role_name,
        'company_id': company_id,
        'building_id': building_id,
    }

    if unit:
        user_data['unit'] = {
            'id': unit.id,
            'name': unit.name,
            'building_name': unit.building.name,
            'company_name': unit.company.name,
        }
    if tenant:
        user_data['tenant'] = {
            'id': tenant.id,
            'full_name': tenant.full_name,
            'mobile_number': tenant.mobile_number,
            'must_change_password': tenant.must_change_password,
        }

    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': user_data,
    }, None, status.HTTP_200_OK


class UnifiedLoginAPIView(APIView):
    """Unified login endpoint for Super Admin, Householder, Tenant, and Company Staff."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginInputSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid credentials format.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        data, err, err_code = _authenticate_and_create_token(
            serializer.validated_data['username'],
            serializer.validated_data['password'],
        )
        if err:
            return api_response(success=False, message=err, errors={"detail": [err]}, status_code=err_code)
        return api_response(success=True, message="Login successful.", data=data)


class HouseholderLoginAPIView(APIView):
    """Dedicated login endpoint for Householder Mobile Application."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginInputSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid credentials format.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        data, err, err_code = _authenticate_and_create_token(
            serializer.validated_data['username'],
            serializer.validated_data['password'],
            expected_role='householder',
        )
        if err:
            return api_response(success=False, message=err, errors={"detail": [err]}, status_code=err_code)
        return api_response(success=True, message="Householder login successful.", data=data)


class TenantLoginAPIView(APIView):
    """Dedicated login endpoint for Tenant Mobile Application."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginInputSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid credentials format.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        data, err, err_code = _authenticate_and_create_token(
            serializer.validated_data['username'],
            serializer.validated_data['password'],
            expected_role='tenant',
        )
        if err:
            return api_response(success=False, message=err, errors={"detail": [err]}, status_code=err_code)
        return api_response(success=True, message="Tenant login successful.", data=data)


class MeAPIView(APIView):
    """Generic current user profile API."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        role = 'superadmin' if user.is_superuser else 'user'
        unit = get_active_unit(user)
        tenant = get_active_tenant(user)
        if unit:
            role = 'householder'
        elif tenant:
            role = 'tenant'

        return api_response(
            success=True,
            message="User profile retrieved.",
            data={
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': role,
            }
        )


class HouseholderMeAPIView(APIView):
    """Retrieve logged-in Householder profile."""
    permission_classes = [IsHouseholder]

    def get(self, request):
        unit = request.unit
        data = {
            'user_id': request.user.id,
            'username': request.user.username,
            'unit_id': unit.id,
            'unit_name': unit.name,
            'unit_type': unit.unit_type,
            'unit_type_display': unit.get_unit_type_display(),
            'email': unit.email or request.user.email,
            'mobile_number': unit.mobile_number,
            'building_name': unit.building.name,
            'company_name': unit.company.name,
        }
        return api_response(success=True, message="Householder profile retrieved.", data=data)


class TenantMeAPIView(APIView):
    """Retrieve logged-in Tenant profile."""
    permission_classes = [IsTenant]

    def get(self, request):
        serializer = TenantProfileSerializer(request.tenant)
        return api_response(success=True, message="Tenant profile retrieved.", data=serializer.data)


# =========================================================
# HOUSEHOLDER APPLICATION APIS
# =========================================================

class HouseholderUnitDetailAPIView(APIView):
    """Retrieve associated Unit details for the authenticated Householder."""
    permission_classes = [IsHouseholder]

    def get(self, request):
        serializer = UnitDetailSerializer(request.unit)
        return api_response(success=True, message="Unit details retrieved.", data=serializer.data)


class HouseholderDashboardAPIView(APIView):
    """Dashboard statistics for the authenticated Householder / Unit."""
    permission_classes = [IsHouseholder]

    def get(self, request):
        unit = request.unit
        visits = GuestVisit.objects.filter(unit=unit)

        total_guests = visits.count()
        pending_walk_in = visits.filter(visit_type=GuestVisit.TYPE_WALK_IN, unit_approval_status=GuestVisit.STATUS_PENDING).count()
        pending_advance = visits.filter(visit_type=GuestVisit.TYPE_ADVANCE, tenant_approval_status=GuestVisit.STATUS_PENDING).count()
        approved_gate_passes = visits.filter(status=GuestVisit.STATUS_APPROVED).exclude(gate_pass_code__isnull=True).count()
        active_visitors = visits.filter(status=GuestVisit.STATUS_APPROVED, checked_in_at__isnull=False, checked_out_at__isnull=True).count()

        recent_passes = visits.filter(
            status=GuestVisit.STATUS_APPROVED
        ).exclude(gate_pass_code__isnull=True).order_by('-approved_at', '-created_at')[:5]

        recent_passes_data = [_format_gate_pass_dict(v, request) for v in recent_passes]

        data = {
            'unit_name': unit.name,
            'building_name': unit.building.name,
            'company_name': unit.company.name,
            'total_guests': total_guests,
            'pending_walk_in_requests': pending_walk_in,
            'pending_advance_requests': pending_advance,
            'approved_gate_passes': approved_gate_passes,
            'active_visitors': active_visitors,
            'recent_gate_passes': recent_passes_data,
        }
        return api_response(success=True, message="Dashboard statistics retrieved.", data=data)


class HouseholderAdvanceVisitAPIView(APIView):
    """
    Create and list Advance Guest Visit requests for the authenticated Householder.
    Workflow B: Unit creates request -> sent to active Tenant -> Tenant approves/rejects.
    """
    permission_classes = [IsHouseholder]

    def get(self, request):
        unit = request.unit
        visits = GuestVisit.objects.filter(
            unit=unit,
            visit_type=GuestVisit.TYPE_ADVANCE,
        ).select_related(
            'tenant', 'unit', 'unit__building', 'purpose_of_visit'
        ).prefetch_related('accompanying_people').order_by('-created_at')

        serializer = GuestVisitListSerializer(visits, many=True, context={'request': request})
        return api_response(success=True, message="Advance guest visit requests retrieved.", data=serializer.data)

    def post(self, request):
        unit = request.unit
        allocation = TenantUnitAllocation.objects.filter(
            unit=unit,
            released_at__isnull=True,
            tenant__status=True,
        ).select_related('tenant', 'tenant__user').first()

        if not allocation or not allocation.tenant:
            return api_response(
                success=False,
                message="No active tenant is currently allocated to this unit. Cannot create advance visit request.",
                errors={"tenant": ["No active tenant allocated to this unit."]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        tenant = allocation.tenant
        serializer = HouseholderAdvanceVisitCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid advance visit request data.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        validated = serializer.validated_data
        purpose = PurposeOfVisit.objects.get(pk=validated['purpose_of_visit'])

        with transaction.atomic():
            visit = GuestVisit.objects.create(
                tenant=tenant,
                unit=unit,
                guest_name=validated['guest_name'],
                guest_mobile_number=validated['guest_mobile_number'],
                additional_visitors=validated.get('additional_visitors', 0),
                visit_type=GuestVisit.TYPE_ADVANCE,
                vehicle_details=validated.get('vehicle_details', ''),
                purpose_of_visit=purpose,
                visit_date=validated['visit_date'],
                visit_time=validated.get('visit_time'),
                notes=validated.get('notes', ''),
                status=GuestVisit.STATUS_PENDING,
                unit_approval_status=GuestVisit.STATUS_APPROVED,
                tenant_approval_status=GuestVisit.STATUS_PENDING,
                created_by=request.user,
                guest_photo=validated.get('guest_photo'),
            )

            companions = validated.get('accompanying_people', [])
            if companions:
                GuestVisitAccompanyingPerson.objects.bulk_create([
                    GuestVisitAccompanyingPerson(
                        guest_visit=visit,
                        name=c['name'],
                        mobile_number=c['mobile_number'],
                    )
                    for c in companions
                ])

            # Notify Tenant
            if tenant.user:
                create_notification(
                    recipient=tenant.user,
                    sender=request.user,
                    visit=visit,
                    title="New Advance Guest Visit Request",
                    message=f"Householder {unit.name} requested an advance visit for {visit.guest_name} on {visit.visit_date}.",
                    notification_type=Notification.TYPE_ADVANCE_REQUEST,
                )

        detail_serializer = GuestVisitDetailSerializer(visit, context={'request': request})
        return api_response(
            success=True,
            message="Advance guest visit request submitted successfully. Awaiting Tenant approval.",
            data=detail_serializer.data,
            status_code=status.HTTP_201_CREATED,
        )


class HouseholderWalkInVisitListAPIView(APIView):
    """View Walk-in Guest Visit requests for the authenticated Householder."""
    permission_classes = [IsHouseholder]

    def get(self, request):
        unit = request.unit
        visits = GuestVisit.objects.filter(
            unit=unit,
            visit_type=GuestVisit.TYPE_WALK_IN,
        ).select_related(
            'tenant', 'unit', 'unit__building', 'purpose_of_visit'
        ).prefetch_related('accompanying_people').order_by('-created_at')

        serializer = GuestVisitListSerializer(visits, many=True, context={'request': request})
        return api_response(success=True, message="Walk-in guest visit requests retrieved.", data=serializer.data)


class HouseholderWalkInAcceptAPIView(APIView):
    """
    Accept a Walk-in Guest Visit request.
    Workflow C: Unit accepts -> proceeds to Tenant approval.
    """
    permission_classes = [IsHouseholder]

    def post(self, request, pk):
        unit = request.unit
        with transaction.atomic():
            visit = get_object_or_404(
                GuestVisit.objects.select_for_update().select_related('tenant', 'tenant__user', 'unit'),
                pk=pk,
                unit=unit,
            )

            if visit.visit_type != GuestVisit.TYPE_WALK_IN:
                return api_response(
                    success=False,
                    message="Only walk-in requests can be accepted by the Householder.",
                    errors={"detail": ["Invalid visit type for unit acceptance."]},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if visit.status != GuestVisit.STATUS_PENDING or visit.unit_approval_status != GuestVisit.STATUS_PENDING:
                return api_response(
                    success=False,
                    message="This visit request is not pending unit acceptance.",
                    errors={"detail": ["Visit already processed."]},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            visit.unit_approval_status = GuestVisit.STATUS_APPROVED
            visit.save(update_fields=['unit_approval_status', 'updated_at'])

            # Notify Tenant
            if visit.tenant.user:
                create_notification(
                    recipient=visit.tenant.user,
                    sender=request.user,
                    visit=visit,
                    title="Walk-in Request Accepted by Unit",
                    message=f"Unit {unit.name} has ACCEPTED the walk-in request for {visit.guest_name}. Please provide final Tenant approval to generate the Gate Pass.",
                    notification_type=Notification.TYPE_UNIT_ACCEPTED,
                )

        return api_response(
            success=True,
            message="Walk-in request accepted. It is now awaiting final Tenant approval.",
            data={'id': visit.id, 'unit_approval_status': visit.unit_approval_status, 'status': visit.status},
        )


class HouseholderWalkInRejectAPIView(APIView):
    """Reject a Walk-in Guest Visit request."""
    permission_classes = [IsHouseholder]

    def post(self, request, pk):
        unit = request.unit
        with transaction.atomic():
            visit = get_object_or_404(
                GuestVisit.objects.select_for_update().select_related('tenant', 'tenant__user', 'unit'),
                pk=pk,
                unit=unit,
            )

            if visit.status != GuestVisit.STATUS_PENDING:
                return api_response(
                    success=False,
                    message="This visit request has already been processed.",
                    errors={"detail": ["Visit not pending."]},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            visit.unit_approval_status = GuestVisit.STATUS_DENIED
            visit.status = GuestVisit.STATUS_DENIED
            visit.gate_pass_code = None
            visit.save(update_fields=['unit_approval_status', 'status', 'gate_pass_code', 'updated_at'])

            # Notify Tenant
            if visit.tenant.user:
                create_notification(
                    recipient=visit.tenant.user,
                    sender=request.user,
                    visit=visit,
                    title="Walk-in Request Rejected by Unit",
                    message=f"Unit {unit.name} has REJECTED the walk-in request for {visit.guest_name}.",
                    notification_type=Notification.TYPE_UNIT_REJECTED,
                )

        return api_response(
            success=True,
            message="Walk-in request rejected. No Gate Pass will be generated.",
            data={'id': visit.id, 'unit_approval_status': visit.unit_approval_status, 'status': visit.status},
        )


class HouseholderGatePassListAPIView(APIView):
    """View all generated Gate Passes for the authenticated Householder."""
    permission_classes = [IsHouseholder]

    def get(self, request):
        unit = request.unit
        passes = GuestVisit.objects.filter(
            unit=unit,
            status=GuestVisit.STATUS_APPROVED,
        ).exclude(
            gate_pass_code__isnull=True
        ).select_related(
            'tenant', 'unit', 'unit__building', 'purpose_of_visit'
        ).prefetch_related('accompanying_people', 'tag_issues').order_by('-approved_at', '-created_at')

        data = [_format_gate_pass_dict(p, request) for p in passes]
        return api_response(success=True, message="Gate Passes retrieved.", data=data)


class HouseholderGatePassDetailAPIView(APIView):
    """Retrieve Gate Pass details and QR Code information for the authenticated Householder."""
    permission_classes = [IsHouseholder]

    def get(self, request, pk=None, code=None):
        unit = request.unit
        qs = GuestVisit.objects.filter(
            unit=unit,
            status=GuestVisit.STATUS_APPROVED,
        ).select_related(
            'tenant', 'unit', 'unit__building', 'purpose_of_visit'
        ).prefetch_related('accompanying_people', 'tag_issues')

        if pk:
            visit = get_object_or_404(qs, pk=pk)
        elif code:
            visit = get_object_or_404(qs, gate_pass_code=code)
        else:
            return api_response(success=False, message="Gate Pass ID or code is required.", status_code=status.HTTP_400_BAD_REQUEST)

        if not visit.gate_pass_code:
            return api_response(
                success=False,
                message="No Gate Pass has been generated for this visit.",
                errors={"detail": ["Gate pass code missing."]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        data = _format_gate_pass_dict(visit, request)
        return api_response(success=True, message="Gate Pass details retrieved.", data=data)


class HouseholderVisitHistoryAPIView(APIView):
    """View Guest Visit History for the authenticated Householder."""
    permission_classes = [IsHouseholder]

    def get(self, request):
        unit = request.unit
        visits = GuestVisit.objects.filter(unit=unit).select_related(
            'tenant', 'unit', 'unit__building', 'purpose_of_visit'
        ).prefetch_related('accompanying_people').order_by('-visit_date', '-created_at')

        # Filter by search or status
        search = request.query_params.get('search', '').strip()
        if search:
            visits = visits.filter(
                Q(guest_name__icontains=search)
                | Q(guest_mobile_number__icontains=search)
                | Q(gate_pass_code__icontains=search)
                | Q(purpose_of_visit__name__icontains=search)
            )

        status_param = request.query_params.get('status', '').strip()
        if status_param:
            visits = visits.filter(status=status_param)

        serializer = GuestVisitListSerializer(visits, many=True, context={'request': request})
        return api_response(success=True, message="Guest visit history retrieved.", data=serializer.data)


class HouseholderActiveVisitorsAPIView(APIView):
    """Retrieve currently active visitors for the authenticated Householder (checked in and not checked out)."""
    permission_classes = [IsHouseholder]

    def get(self, request):
        unit = request.unit
        active_visits = GuestVisit.objects.filter(
            unit=unit,
            status=GuestVisit.STATUS_APPROVED,
            checked_in_at__isnull=False,
            checked_out_at__isnull=True,
        ).select_related(
            'tenant', 'unit', 'unit__building', 'purpose_of_visit'
        ).prefetch_related('accompanying_people', 'tag_issues').order_by('-checked_in_at')

        serializer = GuestVisitDetailSerializer(active_visits, many=True, context={'request': request})
        return api_response(success=True, message="Active visitors retrieved.", data=serializer.data)


class HouseholderVisitDetailAPIView(APIView):
    """Retrieve specific guest visit details for the authenticated Householder."""
    permission_classes = [IsHouseholder]

    def get(self, request, pk):
        unit = request.unit
        visit = get_object_or_404(
            GuestVisit.objects.select_related(
                'tenant', 'unit', 'unit__building', 'purpose_of_visit'
            ).prefetch_related('accompanying_people', 'tag_issues'),
            pk=pk,
            unit=unit,
        )
        serializer = GuestVisitDetailSerializer(visit, context={'request': request})
        return api_response(success=True, message="Guest visit details retrieved.", data=serializer.data)


# =========================================================
# TENANT APPLICATION APIS
# =========================================================

class TenantUnitsAPIView(APIView):
    """Retrieve associated Unit details for the authenticated Tenant."""
    permission_classes = [IsTenant]

    def get(self, request):
        tenant = request.tenant
        allocations = tenant.unit_allocations.filter(
            released_at__isnull=True,
            unit__status=True,
        ).select_related('unit', 'unit__building', 'unit__floor', 'unit__company', 'unit__work_site', 'unit__establishment_type')

        units_data = [UnitDetailSerializer(alloc.unit).data for alloc in allocations]
        return api_response(success=True, message="Associated unit details retrieved.", data=units_data)


class TenantDashboardAPIView(APIView):
    """Dashboard statistics for the authenticated Tenant."""
    permission_classes = [IsTenant]

    def get(self, request):
        tenant = request.tenant
        visits = GuestVisit.objects.filter(tenant=tenant)

        total_guests = visits.count()
        allocated_units_count = tenant.unit_allocations.filter(released_at__isnull=True, unit__status=True).count()
        pending_advance_requests = visits.filter(
            visit_type=GuestVisit.TYPE_ADVANCE,
            tenant_approval_status=GuestVisit.STATUS_PENDING,
        ).count()
        pending_walk_in_requests = visits.filter(
            visit_type=GuestVisit.TYPE_WALK_IN,
            status=GuestVisit.STATUS_PENDING,
        ).count()
        approved_gate_passes = visits.filter(status=GuestVisit.STATUS_APPROVED).exclude(gate_pass_code__isnull=True).count()
        active_visitors = visits.filter(status=GuestVisit.STATUS_APPROVED, checked_in_at__isnull=False, checked_out_at__isnull=True).count()
        family_members_count = tenant.family_members.count()
        staff_members_count = tenant.staff_members.filter(status=True).count()

        recent_passes = visits.filter(
            status=GuestVisit.STATUS_APPROVED
        ).exclude(gate_pass_code__isnull=True).order_by('-approved_at', '-created_at')[:5]

        recent_passes_data = [_format_gate_pass_dict(v, request) for v in recent_passes]

        data = {
            'tenant_name': tenant.full_name,
            'total_guests': total_guests,
            'allocated_units_count': allocated_units_count,
            'pending_advance_requests': pending_advance_requests,
            'pending_walk_in_requests': pending_walk_in_requests,
            'approved_gate_passes': approved_gate_passes,
            'active_visitors': active_visitors,
            'family_members_count': family_members_count,
            'staff_members_count': staff_members_count,
            'recent_gate_passes': recent_passes_data,
        }
        return api_response(success=True, message="Tenant dashboard statistics retrieved.", data=data)


class TenantAdvanceVisitCreateAPIView(APIView):
    """
    Create Advance Guest Visit booking.
    Workflow A: Tenant creates -> Auto approved -> Gate Pass and QR Code generated immediately.
    """
    permission_classes = [IsTenant]

    def post(self, request):
        tenant = request.tenant
        serializer = TenantAdvanceVisitCreateSerializer(data=request.data, context={'tenant': tenant})
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid booking data.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        validated = serializer.validated_data
        purpose = PurposeOfVisit.objects.get(pk=validated['purpose_of_visit'])
        unit = Unit.objects.get(pk=validated['unit'])

        with transaction.atomic():
            gate_pass_code = generate_gate_pass_code()
            now = timezone.now()

            visit = GuestVisit.objects.create(
                tenant=tenant,
                unit=unit,
                guest_name=validated['guest_name'],
                guest_mobile_number=validated['guest_mobile_number'],
                additional_visitors=validated.get('additional_visitors', 0),
                visit_type=GuestVisit.TYPE_ADVANCE,
                vehicle_details=validated.get('vehicle_details', ''),
                purpose_of_visit=purpose,
                visit_date=validated['visit_date'],
                visit_time=validated.get('visit_time'),
                notes=validated.get('notes', ''),
                status=GuestVisit.STATUS_APPROVED,
                unit_approval_status=GuestVisit.STATUS_APPROVED,
                tenant_approval_status=GuestVisit.STATUS_APPROVED,
                approved_at=now,
                gate_pass_code=gate_pass_code,
                created_by=request.user,
                guest_photo=validated.get('guest_photo'),
            )

            companions = validated.get('accompanying_people', [])
            if companions:
                GuestVisitAccompanyingPerson.objects.bulk_create([
                    GuestVisitAccompanyingPerson(
                        guest_visit=visit,
                        name=c['name'],
                        mobile_number=c['mobile_number'],
                    )
                    for c in companions
                ])

            # Notify Householder
            if unit.user:
                create_notification(
                    recipient=unit.user,
                    sender=request.user,
                    visit=visit,
                    title="Advance Guest Visit Scheduled",
                    message=f"Tenant {tenant.full_name} scheduled an advance visit for {visit.guest_name} on {visit.visit_date}. Gate Pass: {gate_pass_code}",
                    notification_type=Notification.TYPE_GATE_PASS_ISSUED,
                )

        pass_data = _format_gate_pass_dict(visit, request)
        return api_response(
            success=True,
            message="Advance guest visit booked successfully. Gate Pass generated.",
            data=pass_data,
            status_code=status.HTTP_201_CREATED,
        )


class TenantWalkInVisitCreateAPIView(APIView):
    """
    Create Walk-in Guest Visit request.
    Workflow C: Tenant creates -> sent to Householder/Unit for acceptance.
    """
    permission_classes = [IsTenant]

    def post(self, request):
        tenant = request.tenant
        serializer = TenantWalkInVisitCreateSerializer(data=request.data, context={'tenant': tenant})
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid walk-in visit request data.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        validated = serializer.validated_data
        purpose = PurposeOfVisit.objects.get(pk=validated['purpose_of_visit'])
        unit = Unit.objects.get(pk=validated['unit'])

        with transaction.atomic():
            visit = GuestVisit.objects.create(
                tenant=tenant,
                unit=unit,
                guest_name=validated['guest_name'],
                guest_mobile_number=validated['guest_mobile_number'],
                additional_visitors=validated.get('additional_visitors', 0),
                visit_type=GuestVisit.TYPE_WALK_IN,
                vehicle_details=validated.get('vehicle_details', ''),
                purpose_of_visit=purpose,
                visit_date=validated['visit_date'],
                visit_time=validated.get('visit_time'),
                notes=validated.get('notes', ''),
                status=GuestVisit.STATUS_PENDING,
                unit_approval_status=GuestVisit.STATUS_PENDING,
                tenant_approval_status=GuestVisit.STATUS_PENDING,
                created_by=request.user,
                guest_photo=validated.get('guest_photo'),
            )

            companions = validated.get('accompanying_people', [])
            if companions:
                GuestVisitAccompanyingPerson.objects.bulk_create([
                    GuestVisitAccompanyingPerson(
                        guest_visit=visit,
                        name=c['name'],
                        mobile_number=c['mobile_number'],
                    )
                    for c in companions
                ])

            # Notify Householder
            if unit.user:
                create_notification(
                    recipient=unit.user,
                    sender=request.user,
                    visit=visit,
                    title="New Walk-in Guest Visit Request",
                    message=f"Tenant {tenant.full_name} registered a walk-in request for {visit.guest_name}. Please accept or reject this request.",
                    notification_type=Notification.TYPE_WALK_IN_REQUEST,
                )

        detail_serializer = GuestVisitDetailSerializer(visit, context={'request': request})
        return api_response(
            success=True,
            message="Walk-in request created successfully and sent to Unit for acceptance.",
            data=detail_serializer.data,
            status_code=status.HTTP_201_CREATED,
        )


class TenantVisitListAPIView(APIView):
    """View all submitted Guest Visit requests for the authenticated Tenant."""
    permission_classes = [IsTenant]

    def get(self, request):
        tenant = request.tenant
        visits = GuestVisit.objects.filter(tenant=tenant).select_related(
            'tenant', 'unit', 'unit__building', 'purpose_of_visit'
        ).prefetch_related('accompanying_people').order_by('-created_at')

        serializer = GuestVisitListSerializer(visits, many=True, context={'request': request})
        return api_response(success=True, message="Guest visit requests retrieved.", data=serializer.data)


class TenantPendingApprovalsAPIView(APIView):
    """
    Retrieve requests awaiting Tenant action:
    1. Unit Advance requests awaiting Tenant approval (unit_approval='approved', tenant_approval='pending')
    2. Unit-accepted Walk-in requests awaiting final Tenant approval (visit_type='walk_in', unit_approval='approved', tenant_approval='pending')
    """
    permission_classes = [IsTenant]

    def get(self, request):
        tenant = request.tenant
        visits = GuestVisit.objects.filter(
            tenant=tenant,
            status=GuestVisit.STATUS_PENDING,
            unit_approval_status=GuestVisit.STATUS_APPROVED,
            tenant_approval_status=GuestVisit.STATUS_PENDING,
        ).select_related(
            'tenant', 'unit', 'unit__building', 'purpose_of_visit'
        ).prefetch_related('accompanying_people').order_by('-created_at')

        serializer = GuestVisitDetailSerializer(visits, many=True, context={'request': request})
        return api_response(success=True, message="Pending requests awaiting Tenant approval retrieved.", data=serializer.data)


class TenantApproveVisitAPIView(APIView):
    """
    Approve a Guest Visit request (Unit Advance or Unit-accepted Walk-in).
    Generates Gate Pass and QR Code upon successful approval.
    """
    permission_classes = [IsTenant]

    def post(self, request, pk):
        tenant = request.tenant
        with transaction.atomic():
            visit = get_object_or_404(
                GuestVisit.objects.select_for_update().select_related('tenant', 'unit', 'unit__user'),
                pk=pk,
                tenant=tenant,
            )

            if visit.status != GuestVisit.STATUS_PENDING:
                return api_response(
                    success=False,
                    message="This visit has already been processed.",
                    errors={"detail": ["Visit already processed."]},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # Enforce workflow rule: Walk-in requests require Unit acceptance before Tenant approval
            if visit.visit_type == GuestVisit.TYPE_WALK_IN and visit.unit_approval_status != GuestVisit.STATUS_APPROVED:
                return api_response(
                    success=False,
                    message="The Unit must accept this walk-in request before Tenant approval.",
                    errors={"unit_approval": ["Unit acceptance required first."]},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            gate_pass_code = generate_gate_pass_code()
            now = timezone.now()

            visit.tenant_approval_status = GuestVisit.STATUS_APPROVED
            visit.status = GuestVisit.STATUS_APPROVED
            visit.approved_at = now
            visit.gate_pass_code = gate_pass_code
            visit.save(update_fields=['status', 'tenant_approval_status', 'approved_at', 'gate_pass_code', 'updated_at'])

            # Notify Householder
            if visit.unit.user:
                create_notification(
                    recipient=visit.unit.user,
                    sender=request.user,
                    visit=visit,
                    title="Guest Visit Approved by Tenant",
                    message=f"Tenant {tenant.full_name} APPROVED the visit for {visit.guest_name}. Gate Pass: {gate_pass_code}",
                    notification_type=Notification.TYPE_TENANT_APPROVED,
                )

        pass_data = _format_gate_pass_dict(visit, request)
        return api_response(
            success=True,
            message="Guest visit approved and Gate Pass generated successfully.",
            data=pass_data,
        )


class TenantRejectVisitAPIView(APIView):
    """Reject a Guest Visit request."""
    permission_classes = [IsTenant]

    def post(self, request, pk):
        tenant = request.tenant
        with transaction.atomic():
            visit = get_object_or_404(
                GuestVisit.objects.select_for_update().select_related('tenant', 'unit', 'unit__user'),
                pk=pk,
                tenant=tenant,
            )

            if visit.status != GuestVisit.STATUS_PENDING:
                return api_response(
                    success=False,
                    message="This visit has already been processed.",
                    errors={"detail": ["Visit already processed."]},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            visit.status = GuestVisit.STATUS_DENIED
            visit.tenant_approval_status = GuestVisit.STATUS_DENIED
            visit.gate_pass_code = None
            visit.approved_at = None
            visit.save(update_fields=['status', 'tenant_approval_status', 'gate_pass_code', 'approved_at', 'updated_at'])

            # Notify Householder
            if visit.unit.user:
                create_notification(
                    recipient=visit.unit.user,
                    sender=request.user,
                    visit=visit,
                    title="Guest Visit Rejected by Tenant",
                    message=f"Tenant {tenant.full_name} REJECTED the visit request for {visit.guest_name}.",
                    notification_type=Notification.TYPE_TENANT_REJECTED,
                )

        return api_response(
            success=True,
            message="Guest visit rejected.",
            data={'id': visit.id, 'status': visit.status, 'tenant_approval_status': visit.tenant_approval_status},
        )


class TenantGatePassListAPIView(APIView):
    """View all generated Gate Passes for the authenticated Tenant."""
    permission_classes = [IsTenant]

    def get(self, request):
        tenant = request.tenant
        passes = GuestVisit.objects.filter(
            tenant=tenant,
            status=GuestVisit.STATUS_APPROVED,
        ).exclude(
            gate_pass_code__isnull=True
        ).select_related(
            'tenant', 'unit', 'unit__building', 'purpose_of_visit'
        ).prefetch_related('accompanying_people', 'tag_issues').order_by('-approved_at', '-created_at')

        data = [_format_gate_pass_dict(p, request) for p in passes]
        return api_response(success=True, message="Tenant Gate Passes retrieved.", data=data)


class TenantGatePassDetailAPIView(APIView):
    """Retrieve Gate Pass details and QR Code information for the authenticated Tenant."""
    permission_classes = [IsTenant]

    def get(self, request, pk=None, code=None):
        tenant = request.tenant
        qs = GuestVisit.objects.filter(
            tenant=tenant,
            status=GuestVisit.STATUS_APPROVED,
        ).select_related(
            'tenant', 'unit', 'unit__building', 'purpose_of_visit'
        ).prefetch_related('accompanying_people', 'tag_issues')

        if pk:
            visit = get_object_or_404(qs, pk=pk)
        elif code:
            visit = get_object_or_404(qs, gate_pass_code=code)
        else:
            return api_response(success=False, message="Gate Pass ID or code is required.", status_code=status.HTTP_400_BAD_REQUEST)

        if not visit.gate_pass_code:
            return api_response(
                success=False,
                message="No Gate Pass has been generated for this visit.",
                errors={"detail": ["Gate pass code missing."]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        data = _format_gate_pass_dict(visit, request)
        return api_response(success=True, message="Gate Pass details retrieved.", data=data)


class TenantVisitHistoryAPIView(APIView):
    """View Guest Visit History for the authenticated Tenant."""
    permission_classes = [IsTenant]

    def get(self, request):
        tenant = request.tenant
        visits = GuestVisit.objects.filter(tenant=tenant).select_related(
            'tenant', 'unit', 'unit__building', 'purpose_of_visit'
        ).prefetch_related('accompanying_people').order_by('-visit_date', '-created_at')

        search = request.query_params.get('search', '').strip()
        if search:
            visits = visits.filter(
                Q(guest_name__icontains=search)
                | Q(guest_mobile_number__icontains=search)
                | Q(gate_pass_code__icontains=search)
                | Q(purpose_of_visit__name__icontains=search)
            )

        status_param = request.query_params.get('status', '').strip()
        if status_param:
            visits = visits.filter(status=status_param)

        serializer = GuestVisitListSerializer(visits, many=True, context={'request': request})
        return api_response(success=True, message="Tenant guest visit history retrieved.", data=serializer.data)


class TenantActiveVisitorsAPIView(APIView):
    """View active visitors for the authenticated Tenant (checked in and not checked out)."""
    permission_classes = [IsTenant]

    def get(self, request):
        tenant = request.tenant
        active_visits = GuestVisit.objects.filter(
            tenant=tenant,
            status=GuestVisit.STATUS_APPROVED,
            checked_in_at__isnull=False,
            checked_out_at__isnull=True,
        ).select_related(
            'tenant', 'unit', 'unit__building', 'purpose_of_visit'
        ).prefetch_related('accompanying_people', 'tag_issues').order_by('-checked_in_at')

        serializer = GuestVisitDetailSerializer(active_visits, many=True, context={'request': request})
        return api_response(success=True, message="Active visitors retrieved.", data=serializer.data)


class TenantVisitDetailAPIView(APIView):
    """Retrieve specific guest visit details for the authenticated Tenant."""
    permission_classes = [IsTenant]

    def get(self, request, pk):
        tenant = request.tenant
        visit = get_object_or_404(
            GuestVisit.objects.select_related(
                'tenant', 'unit', 'unit__building', 'purpose_of_visit'
            ).prefetch_related('accompanying_people', 'tag_issues'),
            pk=pk,
            tenant=tenant,
        )
        serializer = GuestVisitDetailSerializer(visit, context={'request': request})
        return api_response(success=True, message="Guest visit details retrieved.", data=serializer.data)


class TenantProfileUpdateAPIView(APIView):
    """View and update profile for the authenticated Tenant."""
    permission_classes = [IsTenant]

    def get(self, request):
        serializer = TenantProfileSerializer(request.tenant)
        return api_response(success=True, message="Profile retrieved.", data=serializer.data)

    def put(self, request):
        return self._update(request, partial=False)

    def patch(self, request):
        return self._update(request, partial=True)

    def _update(self, request, partial):
        tenant = request.tenant
        serializer = TenantProfileUpdateSerializer(tenant, data=request.data, partial=partial)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Profile update failed.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        serializer.save()
        return api_response(
            success=True,
            message="Profile updated successfully.",
            data=TenantProfileSerializer(tenant).data,
        )


# =========================================================
# SECURITY SERVICES (REUSING TENANT ACCOUNT)
# =========================================================

def _get_security_authorized_visit(request, lookup_field, lookup_value):
    """
    Scopes security operations:
    Tenant can perform security operations only for currently allocated units.
    Superuser can access all.
    """
    kwargs = {lookup_field: lookup_value}
    visit = GuestVisit.objects.select_related(
        'tenant', 'unit', 'unit__building', 'unit__company', 'purpose_of_visit'
    ).prefetch_related('accompanying_people', 'tag_issues').filter(**kwargs).first()

    if not visit:
        return None, "Guest visit not found."

    if request.user.is_superuser:
        return visit, None

    tenant = getattr(request, 'tenant', None) or get_active_tenant(request.user)
    if not tenant:
        return None, "Not authorized for security operations."

    # Tenant security access is unit-scoped, not building-scoped. A Tenant
    # allocated to one unit must not gain access to other units in that building.
    if not tenant.unit_allocations.filter(
        released_at__isnull=True,
        unit_id=visit.unit_id,
        unit__status=True,
        unit__building__status=True,
        unit__company__status=True,
        unit__work_site__status=True,
    ).exists():
        return None, "You do not have security authority for this property / unit."

    return visit, None


class SecurityVerifyGatePassAPIView(APIView):
    """
    Verify Gate Pass number or QR Code reference.
    Returns guest details, entry validity, and gate pass status.
    """
    permission_classes = [IsTenantSecurityAuthorized]

    def post(self, request):
        serializer = GatePassVerifyInputSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Gate Pass code required.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        code = serializer.validated_data['code']
        visit, err = _get_security_authorized_visit(request, 'gate_pass_code', code)
        if err:
            return api_response(success=False, message=err, errors={"code": [err]}, status_code=status.HTTP_404_NOT_FOUND)

        is_valid_for_entry = (
            visit.status == GuestVisit.STATUS_APPROVED
            and not visit.checked_in_at
        )

        pass_data = _format_gate_pass_dict(visit, request)
        pass_data['is_valid_for_entry'] = is_valid_for_entry
        pass_data['verification_status'] = 'Valid for Entry' if is_valid_for_entry else (
            'Already Checked In' if (visit.checked_in_at and not visit.checked_out_at) else (
                'Already Checked Out' if visit.checked_out_at else 'Not Approved'
            )
        )

        return api_response(
            success=True,
            message="Gate Pass verified successfully.",
            data=pass_data,
        )


class SecurityCheckInAPIView(APIView):
    """
    Perform Guest Check-in:
    - Validates gate pass status (must be approved, not already checked in).
    - Collects ID type and ID number.
    - Allocates security ID Tag.
    - Records check-in timestamp and staff/tenant user.
    """
    permission_classes = [IsTenantSecurityAuthorized]

    def post(self, request):
        code = request.data.get('gate_pass_code') or request.data.get('code')
        visit_id = request.data.get('visit_id')

        if not code and not visit_id:
            return api_response(
                success=False,
                message="Provide gate_pass_code or visit_id for check-in.",
                errors={"gate_pass_code": ["Gate Pass code or visit ID is required."]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if code:
            visit, err = _get_security_authorized_visit(request, 'gate_pass_code', code.strip())
        else:
            visit, err = _get_security_authorized_visit(request, 'pk', visit_id)

        if err:
            return api_response(success=False, message=err, errors={"detail": [err]}, status_code=status.HTTP_404_NOT_FOUND)

        serializer = CheckInInputSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid check-in details.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        validated = serializer.validated_data

        if visit.status != GuestVisit.STATUS_APPROVED:
            return api_response(
                success=False,
                message="Only approved visits can be checked in.",
                errors={"status": ["Visit is not approved."]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if visit.checked_in_at:
            return api_response(
                success=False,
                message="This guest has already been checked in.",
                errors={"checked_in_at": [f"Already checked in at {visit.checked_in_at}."]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            locked_visit = GuestVisit.objects.select_for_update().select_related(
                'unit', 'unit__building', 'tenant', 'tenant__user'
            ).get(pk=visit.pk)

            if locked_visit.checked_in_at:
                return api_response(
                    success=False,
                    message="This guest has already been checked in.",
                    errors={"detail": ["Already checked in."]},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            now = timezone.now()
            locked_visit.checked_in_at = now
            locked_visit.checked_in_by = request.user
            locked_visit.id_type = validated['id_type']
            locked_visit.id_number = validated['id_number']
            locked_visit.id_received_at = now
            locked_visit.id_received_by = request.user
            if validated.get('notes'):
                locked_visit.notes = f"{locked_visit.notes}\nCheck-in notes: {validated['notes']}".strip()
            locked_visit.save()

            # Business rule: exactly ONE security ID tag per Guest Visit
            tag = (
                IDTag.objects.select_for_update()
                .filter(
                    building=locked_visit.unit.building,
                    status__in=[IDTag.STATUS_AVAILABLE, IDTag.STATUS_RETURNED],
                )
                .order_by('tag_number')
                .first()
            )

            # Generate dynamic tag if none available
            if tag is None:
                for _ in range(20):
                    candidate = f"DYN-{secrets.token_hex(4).upper()}"
                    if not IDTag.objects.filter(tag_number=candidate).exists():
                        tag = IDTag.objects.create(
                            tag_number=candidate,
                            tag_type=IDTag.TYPE_DYNAMIC,
                            building=locked_visit.unit.building,
                            status=IDTag.STATUS_AVAILABLE,
                        )
                        break

            issued_tag_number = None
            if tag:
                tag.status = IDTag.STATUS_ISSUED
                tag.save(update_fields=['status', 'updated_at'])
                issue = IDTagIssue.objects.create(
                    visit=locked_visit,
                    tag=tag,
                    issued_by=request.user,
                )
                issued_tag_number = tag.tag_number

            # Send notifications
            if locked_visit.tenant and locked_visit.tenant.user:
                create_notification(
                    recipient=locked_visit.tenant.user,
                    sender=request.user,
                    visit=locked_visit,
                    title="Guest Checked In",
                    message=f"Guest {locked_visit.guest_name} has checked in. ID Tag: {issued_tag_number or 'None'}.",
                    notification_type=Notification.TYPE_CHECKED_IN,
                )
            if locked_visit.unit and locked_visit.unit.user:
                create_notification(
                    recipient=locked_visit.unit.user,
                    sender=request.user,
                    visit=locked_visit,
                    title="Guest Checked In",
                    message=f"Guest {locked_visit.guest_name} has checked in for Unit {locked_visit.unit.name}.",
                    notification_type=Notification.TYPE_CHECKED_IN,
                )

        pass_data = _format_gate_pass_dict(locked_visit, request)
        pass_data['issued_tag_number'] = issued_tag_number
        return api_response(
            success=True,
            message=f"Guest checked in successfully. Assigned ID Tag: {issued_tag_number or 'None'}.",
            data=pass_data,
        )


class SecurityCheckOutAPIView(APIView):
    """
    Perform Guest Check-out:
    - Validates visit is checked in and not already checked out.
    - Validates return of guest original ID and all issued ID tags.
    """
    permission_classes = [IsTenantSecurityAuthorized]

    def post(self, request):
        code = request.data.get('gate_pass_code') or request.data.get('code')
        visit_id = request.data.get('visit_id')

        if not code and not visit_id:
            return api_response(
                success=False,
                message="Provide gate_pass_code or visit_id for checkout.",
                errors={"gate_pass_code": ["Gate Pass code or visit ID is required."]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if code:
            visit, err = _get_security_authorized_visit(request, 'gate_pass_code', code.strip())
        else:
            visit, err = _get_security_authorized_visit(request, 'pk', visit_id)

        if err:
            return api_response(success=False, message=err, errors={"detail": [err]}, status_code=status.HTTP_404_NOT_FOUND)

        serializer = CheckOutInputSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid checkout data.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        validated = serializer.validated_data

        if not visit.checked_in_at:
            return api_response(
                success=False,
                message="Guest has not checked in yet.",
                errors={"checked_in_at": ["Check-in must be recorded before checkout."]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if visit.checked_out_at:
            return api_response(
                success=False,
                message="Guest has already checked out.",
                errors={"checked_out_at": [f"Already checked out at {visit.checked_out_at}."]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            locked_visit = GuestVisit.objects.select_for_update().select_related(
                'unit', 'tenant', 'tenant__user'
            ).get(pk=visit.pk)

            if locked_visit.checked_out_at:
                return api_response(
                    success=False,
                    message="Guest has already checked out.",
                    errors={"detail": ["Already checked out."]},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # Check if outstanding issued tags exist
            outstanding = list(
                locked_visit.tag_issues.filter(status=IDTagIssue.STATUS_ISSUED).select_related('tag')
            )
            if outstanding:
                tag_numbers = [x.tag.tag_number for x in outstanding]
                return api_response(
                    success=False,
                    message=f"Return all issued ID tags before checkout: {', '.join(tag_numbers)}.",
                    errors={"outstanding_tags": tag_numbers},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            now = timezone.now()

            # Process original ID card return if held
            if locked_visit.id_received_at and not locked_visit.id_returned_at:
                if validated.get('return_id', True):
                    locked_visit.id_returned_at = now
                    locked_visit.id_returned_by = request.user
                else:
                    return api_response(
                        success=False,
                        message="Guest's original ID must be returned before checkout.",
                        errors={"id_return": ["Return original ID card first."]},
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )

            locked_visit.checked_out_at = now
            locked_visit.checked_out_by = request.user
            if validated.get('notes'):
                locked_visit.notes = f"{locked_visit.notes}\nCheckout notes: {validated['notes']}".strip()
            locked_visit.save()

            # Notifications
            if locked_visit.tenant and locked_visit.tenant.user:
                create_notification(
                    recipient=locked_visit.tenant.user,
                    sender=request.user,
                    visit=locked_visit,
                    title="Guest Checked Out",
                    message=f"Guest {locked_visit.guest_name} has checked out.",
                    notification_type=Notification.TYPE_CHECKED_OUT,
                )
            if locked_visit.unit and locked_visit.unit.user:
                create_notification(
                    recipient=locked_visit.unit.user,
                    sender=request.user,
                    visit=locked_visit,
                    title="Guest Checked Out",
                    message=f"Guest {locked_visit.guest_name} has checked out for Unit {locked_visit.unit.name}.",
                    notification_type=Notification.TYPE_CHECKED_OUT,
                )

        pass_data = _format_gate_pass_dict(locked_visit, request)
        return api_response(
            success=True,
            message="Guest checked out successfully.",
            data=pass_data,
        )


class SecurityReturnIdCardAPIView(APIView):
    """Record physical return of guest's original ID card."""
    permission_classes = [IsTenantSecurityAuthorized]

    def post(self, request):
        code = request.data.get('gate_pass_code')
        visit_id = request.data.get('visit_id')

        if not code and not visit_id:
            return api_response(
                success=False,
                message="Provide gate_pass_code or visit_id.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if code:
            visit, err = _get_security_authorized_visit(request, 'gate_pass_code', code.strip())
        else:
            visit, err = _get_security_authorized_visit(request, 'pk', visit_id)

        if err:
            return api_response(success=False, message=err, status_code=status.HTTP_404_NOT_FOUND)

        if not visit.id_received_at:
            return api_response(
                success=False,
                message="No original ID was recorded as received for this guest.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if visit.id_returned_at:
            return api_response(
                success=False,
                message="Original ID has already been returned.",
                data={'id_returned_at': visit.id_returned_at},
            )

        now = timezone.now()
        visit.id_returned_at = now
        visit.id_returned_by = request.user
        visit.save(update_fields=['id_returned_at', 'id_returned_by', 'updated_at'])

        return api_response(
            success=True,
            message=f"Original ID {mask_id_number(visit.id_number)} return recorded successfully.",
            data={'id_returned_at': now},
        )


class SecurityReturnIdTagAPIView(APIView):
    """Record return of an issued security ID tag."""
    permission_classes = [IsTenantSecurityAuthorized]

    def post(self, request):
        serializer = IDTagReturnInputSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Tag number or issue ID required.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        tag_number = serializer.validated_data.get('tag_number')
        issue_id = serializer.validated_data.get('issue_id')

        with transaction.atomic():
            if issue_id:
                issue = IDTagIssue.objects.select_for_update().select_related('tag', 'visit', 'visit__unit').filter(pk=issue_id).first()
            else:
                issue = IDTagIssue.objects.select_for_update().select_related('tag', 'visit', 'visit__unit').filter(
                    tag__tag_number=tag_number.strip(),
                    status=IDTagIssue.STATUS_ISSUED,
                ).first()

            if not issue:
                return api_response(
                    success=False,
                    message="Active ID tag issue not found.",
                    errors={"tag": ["No active issue found for this tag."]},
                    status_code=status.HTTP_404_NOT_FOUND,
                )

            # Security authorization check for this visit
            visit, err = _get_security_authorized_visit(request, 'pk', issue.visit_id)
            if err:
                return api_response(success=False, message=err, status_code=status.HTTP_403_FORBIDDEN)

            now = timezone.now()
            issue.status = IDTagIssue.STATUS_RETURNED
            issue.returned_at = now
            issue.returned_by = request.user
            issue.save(update_fields=['status', 'returned_at', 'returned_by'])

            issue.tag.status = IDTag.STATUS_RETURNED
            issue.tag.save(update_fields=['status', 'updated_at'])

        return api_response(
            success=True,
            message=f"ID tag {issue.tag.tag_number} returned successfully.",
            data={
                'tag_number': issue.tag.tag_number,
                'issue_id': issue.id,
                'returned_at': now,
            },
        )


class SecurityActiveVisitorsAPIView(APIView):
    """Retrieve all active visitors across authorized properties."""
    permission_classes = [IsTenantSecurityAuthorized]

    def get(self, request):
        tenant = getattr(request, 'tenant', None) or get_active_tenant(request.user)

        qs = GuestVisit.objects.filter(
            status=GuestVisit.STATUS_APPROVED,
            checked_in_at__isnull=False,
            checked_out_at__isnull=True,
        ).select_related(
            'tenant', 'unit', 'unit__building', 'purpose_of_visit'
        ).prefetch_related('accompanying_people', 'tag_issues').order_by('-checked_in_at')

        if not request.user.is_superuser and tenant:
            allocated_building_ids = tenant.unit_allocations.filter(
                released_at__isnull=True, unit__status=True
            ).values_list('unit__building_id', flat=True).distinct()

            qs = qs.filter(
                Q(unit__building_id__in=allocated_building_ids) | Q(tenant=tenant)
            ).distinct()

        serializer = GuestVisitDetailSerializer(qs, many=True, context={'request': request})
        return api_response(success=True, message="Active visitors retrieved.", data=serializer.data)


class SecurityVisitorHistoryAPIView(APIView):
    """Retrieve visitor history across authorized properties."""
    permission_classes = [IsTenantSecurityAuthorized]

    def get(self, request):
        tenant = getattr(request, 'tenant', None) or get_active_tenant(request.user)

        qs = GuestVisit.objects.select_related(
            'tenant', 'unit', 'unit__building', 'purpose_of_visit'
        ).prefetch_related('accompanying_people').order_by('-visit_date', '-created_at')

        if not request.user.is_superuser and tenant:
            allocated_building_ids = tenant.unit_allocations.filter(
                released_at__isnull=True, unit__status=True
            ).values_list('unit__building_id', flat=True).distinct()

            qs = qs.filter(
                Q(unit__building_id__in=allocated_building_ids) | Q(tenant=tenant)
            ).distinct()

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(guest_name__icontains=search)
                | Q(guest_mobile_number__icontains=search)
                | Q(gate_pass_code__icontains=search)
                | Q(unit__name__icontains=search)
                | Q(tenant__full_name__icontains=search)
            )

        serializer = GuestVisitListSerializer(qs, many=True, context={'request': request})
        return api_response(success=True, message="Visitor history retrieved.", data=serializer.data)


# =========================================================
# NOTIFICATION APIS
# =========================================================

class NotificationListAPIView(APIView):
    """List notifications for the logged-in user."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')
        serializer = NotificationSerializer(notifications, many=True)
        return api_response(success=True, message="Notifications retrieved.", data=serializer.data)


class NotificationUnreadCountAPIView(APIView):
    """Retrieve unread notification count for the logged-in user."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return api_response(success=True, message="Unread count retrieved.", data={'unread_count': count})


class NotificationMarkReadAPIView(APIView):
    """Mark a specific notification as read."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
        if not notif.is_read:
            notif.is_read = True
            notif.read_at = timezone.now()
            notif.save(update_fields=['is_read', 'read_at'])
        return api_response(success=True, message="Notification marked as read.", data={'id': notif.id, 'is_read': True})


class NotificationMarkAllReadAPIView(APIView):
    """Mark all notifications as read for the logged-in user."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        now = timezone.now()
        count = Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True, read_at=now)
        return api_response(success=True, message=f"{count} notifications marked as read.", data={'marked_count': count})


# =========================================================
# OPENAPI SCHEMA & SWAGGER UI VIEWS
# =========================================================

class OpenAPISchemaAPIView(APIView):
    """Serves OpenAPI 3.0 specification for Mobiz Mobile APIs."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        schema = {
            "openapi": "3.0.3",
            "info": {
                "title": "Mobiz Guest Management Mobile APIs",
                "version": "1.0.0",
                "description": "REST APIs for Householder Mobile Application and Tenant Mobile Application with Security Services.",
            },
            "servers": [
                {"url": request.build_absolute_uri('/api/'), "description": "Current Server"}
            ],
            "components": {
                "securitySchemes": {
                    "BearerAuth": {
                        "type": "http",
                        "scheme": "bearer",
                        "bearerFormat": "JWT"
                    }
                }
            },
            "security": [{"BearerAuth": []}],
            "paths": {
                "/auth/login/": {
                    "post": {
                        "tags": ["Authentication"],
                        "summary": "Unified Login for all user types",
                        "security": [],
                        "responses": {"200": {"description": "JWT tokens and user profile"}}
                    }
                },
                "/householder/auth/login/": {
                    "post": {
                        "tags": ["Householder Auth"],
                        "summary": "Householder (Unit) Login",
                        "security": [],
                        "responses": {"200": {"description": "Householder JWT and Unit details"}}
                    }
                },
                "/householder/unit/": {
                    "get": {
                        "tags": ["Householder Application"],
                        "summary": "Retrieve Householder Unit Details",
                        "responses": {"200": {"description": "Unit details"}}
                    }
                },
                "/householder/dashboard/": {
                    "get": {
                        "tags": ["Householder Application"],
                        "summary": "Retrieve Householder Dashboard Statistics",
                        "responses": {"200": {"description": "Dashboard statistics"}}
                    }
                },
                "/householder/guest-visits/advance/": {
                    "get": {"tags": ["Householder Application"], "summary": "View Householder Advance Requests"},
                    "post": {"tags": ["Householder Application"], "summary": "Create Householder Advance Visit Request"}
                },
                "/householder/guest-visits/walk-in/": {
                    "get": {"tags": ["Householder Application"], "summary": "View Walk-in Requests"}
                },
                "/householder/guest-visits/{id}/accept/": {
                    "post": {"tags": ["Householder Application"], "summary": "Accept Walk-in Visit Request"}
                },
                "/householder/guest-visits/{id}/reject/": {
                    "post": {"tags": ["Householder Application"], "summary": "Reject Walk-in Visit Request"}
                },
                "/householder/gate-passes/": {
                    "get": {"tags": ["Householder Application"], "summary": "View Householder Gate Passes"}
                },
                "/householder/gate-passes/{id}/": {
                    "get": {"tags": ["Householder Application"], "summary": "Retrieve Gate Pass Details & QR Code"}
                },
                "/householder/visitors/active/": {
                    "get": {"tags": ["Householder Application"], "summary": "Retrieve Active Visitors for Unit"}
                },
                "/tenant/auth/login/": {
                    "post": {
                        "tags": ["Tenant Auth"],
                        "summary": "Tenant Login",
                        "security": [],
                        "responses": {"200": {"description": "Tenant JWT and Profile"}}
                    }
                },
                "/tenant/dashboard/": {
                    "get": {"tags": ["Tenant Application"], "summary": "Retrieve Tenant Dashboard Statistics"}
                },
                "/tenant/guest-visits/advance/": {
                    "post": {"tags": ["Tenant Application"], "summary": "Create Advance Guest Booking (Auto Gate Pass)"}
                },
                "/tenant/guest-visits/walk-in/": {
                    "post": {"tags": ["Tenant Application"], "summary": "Create Walk-in Guest Visit Request"}
                },
                "/tenant/guest-visits/pending-approvals/": {
                    "get": {"tags": ["Tenant Application"], "summary": "View Requests Awaiting Tenant Approval"}
                },
                "/tenant/guest-visits/{id}/approve/": {
                    "post": {"tags": ["Tenant Application"], "summary": "Approve Visit Request (Generates Gate Pass)"}
                },
                "/tenant/guest-visits/{id}/reject/": {
                    "post": {"tags": ["Tenant Application"], "summary": "Reject Visit Request"}
                },
                "/tenant/gate-passes/": {
                    "get": {"tags": ["Tenant Application"], "summary": "View Tenant Gate Passes"}
                },
                "/security/verify/": {
                    "post": {"tags": ["Security Services"], "summary": "Verify Gate Pass Number or QR Code"}
                },
                "/security/check-in/": {
                    "post": {"tags": ["Security Services"], "summary": "Perform Guest Check-in with ID Tag"}
                },
                "/security/check-out/": {
                    "post": {"tags": ["Security Services"], "summary": "Perform Guest Check-out with Tag Validation"}
                },
                "/security/return-id-card/": {
                    "post": {"tags": ["Security Services"], "summary": "Record Return of Original ID Card"}
                },
                "/security/return-id-tag/": {
                    "post": {"tags": ["Security Services"], "summary": "Record Return of Security ID Tag"}
                },
                "/security/visitors/active/": {
                    "get": {"tags": ["Security Services"], "summary": "Retrieve All Active Visitors"}
                }
            }
        }
        return Response(schema)


class SwaggerUIView(APIView):
    """Interactive Swagger UI documentation page."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Mobiz Guest Management API Documentation</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui.css" />
    <style>
        body { margin: 0; padding: 0; }
        .topbar { display: none !important; }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui-bundle.js"></script>
    <script>
        window.onload = function() {
            window.ui = SwaggerUIBundle({
                url: "/api/schema/",
                dom_id: '#swagger-ui',
                deepLinking: true,
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIBundle.SwaggerUIStandalonePreset
                ],
                layout: "BaseLayout"
            });
        };
    </script>
</body>
</html>"""
        return HttpResponse(html, content_type="text/html")


# =========================================================
# EXISTING MASTER VIEWSETS (PRESERVED)
# =========================================================

class IsSuperUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class CountryViewSet(viewsets.ModelViewSet):
    queryset = Country.objects.all()
    serializer_class = CountrySerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsSuperUser()]


class StateViewSet(viewsets.ModelViewSet):
    queryset = State.objects.all()
    serializer_class = StateSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsSuperUser()]


class DistrictViewSet(viewsets.ModelViewSet):
    queryset = District.objects.all()
    serializer_class = DistrictSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsSuperUser()]


class AreaViewSet(viewsets.ModelViewSet):
    queryset = Area.objects.all()
    serializer_class = AreaSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsSuperUser()]


class DesignationViewSet(viewsets.ModelViewSet):
    queryset = Designation.objects.all()
    serializer_class = DesignationSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsSuperUser()]


class EstablishmentTypeViewSet(viewsets.ModelViewSet):
    queryset = EstablishmentType.objects.all()
    serializer_class = EstablishmentTypeSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsSuperUser()]


class PurposeOfVisitViewSet(viewsets.ModelViewSet):
    queryset = PurposeOfVisit.objects.all()
    serializer_class = PurposeOfVisitSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsSuperUser()]
