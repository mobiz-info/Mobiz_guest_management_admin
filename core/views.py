from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.serializers import python
from django.db.models.deletion import ProtectedError
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404

from operations.models import Company, CompanyStaff, WorkSite, Building, BuildingStaff, Floor, Unit, Tenant, GuestVisit
from .models import Country, State, District, Area, Designation, EstablishmentType, PurposeOfVisit

User = get_user_model()


# ============================================================
# AUTHENTICATION AND DASHBOARD
# ============================================================

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        # Email-based tenant usernames should work regardless of email casing.
        if '@' in username:
            matching_username = User.objects.filter(username__iexact=username).values_list('username', flat=True).first()
            if matching_username:
                username = matching_username
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_superuser:
                login(request, user)
                return redirect('dashboard')
            staff = CompanyStaff.objects.select_related('company').filter(
                user=user, status=True, company__status=True
            ).first()
            building_staff = None
            unit_profile = Unit.objects.select_related('building', 'company', 'work_site').filter(user=user, status=True, building__status=True, company__status=True, work_site__status=True).first()
            tenant = Tenant.objects.select_related(
                'unit', 'unit__building', 'unit__company', 'unit__work_site'
            ).filter(
                user=user, status=True,
                unit_allocations__released_at__isnull=True,
                unit_allocations__unit__status=True,
                unit_allocations__unit__building__status=True,
                unit_allocations__unit__company__status=True,
                unit_allocations__unit__work_site__status=True,
            ).distinct().first()

            if staff or tenant or unit_profile:
                login(request, user)
                if tenant and tenant.must_change_password and not staff:
                    return redirect('tenant_change_password')
                return redirect('dashboard')
            error = 'Your account is inactive or you are not authorized to access this system.'
        else:
            error = 'Invalid username or password.'
    return render(request, 'login.html', {'error': error})


@login_required
def dashboard_view(request):
    # Defense in depth: do not rely only on middleware for the first-login
    # password-change requirement. A tenant with an initial password must not
    # access the dashboard until the password has been changed.
    if not request.user.is_superuser:
        tenant_profile = Tenant.objects.filter(
            user=request.user,
            status=True,
        ).first()

        if tenant_profile and tenant_profile.must_change_password:
            has_active_company_role = CompanyStaff.objects.filter(
                user=request.user,
                status=True,
                company__status=True,
            ).exists()
            if not has_active_company_role:
                return redirect('tenant_change_password')

    if request.user.is_superuser:
        dashboard_data = {
            'role': 'superadmin', 'role_name': 'Super Admin',
            'title': 'Super Admin Dashboard', 'subtitle': 'Welcome to Guest Management System',
            'total_companies': Company.objects.count(),
            'total_work_sites': WorkSite.objects.count(),
            'total_buildings': Building.objects.count(),
            'total_floors': Floor.objects.count(), 'total_units': Unit.objects.count(),
            'total_tenants': Tenant.objects.count(), 'total_guests': 0,
        }
    else:
        staff = CompanyStaff.objects.select_related('company').filter(
            user=request.user, status=True, company__status=True
        ).first()
        building_staff = None
        unit_profile = Unit.objects.select_related('building', 'company', 'work_site').filter(user=request.user, status=True, building__status=True, company__status=True, work_site__status=True).first()
        tenant = Tenant.objects.select_related(
            'unit', 'unit__building', 'unit__company', 'unit__work_site'
        ).filter(
            user=request.user, status=True,
            unit_allocations__released_at__isnull=True,
            unit_allocations__unit__status=True,
            unit_allocations__unit__building__status=True,
            unit_allocations__unit__company__status=True,
            unit_allocations__unit__work_site__status=True,
        ).distinct().first()

        # Unit login must always resolve to its own Unit Dashboard, even if
        # the same account also has a staff relation from older data.
        if unit_profile:
            unit_visits = GuestVisit.objects.filter(unit=unit_profile)
            dashboard_data = {
                'role': 'unit', 'role_name': 'Unit User', 'title': 'Unit Dashboard',
                'subtitle': f'Welcome to {unit_profile.name}', 'company_name': unit_profile.company.name,
                'building_name': unit_profile.building.name, 'unit_name': unit_profile.name,
                'total_guests': unit_visits.count(),
                'pending_guest_requests': unit_visits.filter(visit_type='walk_in', unit_approval_status='pending').count(),
                'approved_guest_passes': unit_visits.filter(status='approved').count(),
                'unit_gate_passes': unit_visits.filter(status='approved').exclude(gate_pass_code__isnull=True).select_related('tenant').order_by('-approved_at')[:8],
            }
        elif staff:
            dashboard_data = {
                'role': 'company_staff', 'role_name': 'Company Admin',
                'title': 'Company Dashboard', 'subtitle': f'Welcome to {staff.company.name}',
                'company_name': staff.company.name, 'total_work_sites': staff.company.work_sites.count(),
                'total_buildings': staff.company.buildings.count(),
                'total_floors': sum(b.floors.count() for b in staff.company.buildings.all()),
                'total_units': staff.company.units.count(), 'total_tenants': Tenant.objects.filter(unit__company=staff.company).count(), 'total_guests': 0,
            }
        elif tenant:
            allocated_units = list(
                tenant.unit_allocations.filter(
                    released_at__isnull=True,
                    unit__status=True,
                    unit__building__status=True,
                    unit__company__status=True,
                    unit__work_site__status=True,
                ).select_related('unit', 'unit__building', 'unit__floor')
                .order_by('unit__building__name', 'unit__floor__floor_number', 'unit__name')
            )
            allocated_unit_labels = ', '.join(
                f'{allocation.unit.building.name} / {allocation.unit.name}'
                for allocation in allocated_units
            )
            dashboard_data = {
                'role': 'tenant',
                'role_name': 'Tenant',
                'title': 'Tenant Dashboard',
                'subtitle': f'Welcome, {tenant.full_name}',
                'tenant_name': tenant.full_name,
                'tenant_mobile_number': tenant.mobile_number,
                'tenant_dial_code': (tenant.unit.company.country.dial_code or '') if tenant.unit.company.country_id else '',
                'company_name': tenant.unit.company.name,
                'building_name': tenant.unit.building.name,
                'unit_name': tenant.unit.name,
                'allocated_unit_labels': allocated_unit_labels,
                'total_allocated_units': len(allocated_units),
                'tenant_type': tenant.get_tenant_type_display(),
                'total_family_members': tenant.family_members.count(),
                'total_staff_members': tenant.staff_members.filter(status=True).count(),
                'total_guests': 0,
            }
        else:
            logout(request)
            messages.error(request, 'Your account is inactive or access is not authorized.')
            return redirect('login')
    return render(request, 'dashboard.html', {'dashboard_data': dashboard_data})


def logout_view(request):
    logout(request)
    return redirect('login')


def superuser_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, 'Only Super Admin can manage global master data.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


# ============================================================
# DIRECT HTML MASTER FORM HELPERS (NO forms.py / template_fields.py)
# ============================================================

def _master_field_names(model):
    if model is Country:
        return ['name', 'currency_code', 'emblem', 'dial_code']
    if model is State:
        return ['country', 'name']
    if model is District:
        return ['state', 'name']
    if model is Area:
        return ['district', 'name']
    return ['name']


def _master_values(request, instance, fields):
    values = {}
    for name in fields:
        field = instance._meta.get_field(name)
        if request.method == 'POST':
            value = request.POST.get(name, '')
        elif field.is_relation and field.many_to_one:
            value = getattr(instance, f'{name}_id', '') or ''
        else:
            value = getattr(instance, name, '')
        values[name] = str(value) if value is not None else ''
    return values


def _master_save(request, instance, fields):
    errors, non_field_errors = {}, []
    for name in fields:
        field = instance._meta.get_field(name)
        if field.get_internal_type() == 'BooleanField':
            setattr(instance, name, name in request.POST)
            continue
        raw = request.POST.get(name, '').strip()
        if field.is_relation and field.many_to_one:
            if not raw:
                errors[name] = ['This field is required.']
                continue
            try:
                related = field.remote_field.model.objects.filter(pk=raw).first()
            except (ValueError, TypeError, ValidationError):
                related = None
            if related is None:
                errors[name] = ['Please select a valid option.']
            else:
                setattr(instance, name, related)
            continue
        if not raw and not field.blank and not field.null:
            errors[name] = ['This field is required.']
        if field.max_length and len(raw) > field.max_length:
            errors[name] = [f'Ensure this value has at most {field.max_length} characters.']
        setattr(instance, name, raw or (None if field.null else ''))
    if not errors:
        try:
            instance.full_clean()
        except ValidationError as exc:
            if hasattr(exc, 'message_dict'):
                errors = {key: list(val) for key, val in exc.message_dict.items() if key != '__all__'}
                non_field_errors = list(exc.message_dict.get('__all__', []))
            else:
                non_field_errors = list(exc.messages)
    return errors, non_field_errors


def _master_form(request, model, title, instance=None):
    instance = instance or model()
    fields = _master_field_names(model)
    errors, non_field_errors = {}, []
    if request.method == 'POST':
        errors, non_field_errors = _master_save(request, instance, fields)
        if not errors and not non_field_errors:
            instance.save()
            return None
    values = _master_values(request, instance, fields)
    context = {
        'title': title, 'is_edit': bool(instance.pk), 'values': values,
        'errors': errors, 'non_field_errors': non_field_errors,
        'countries': Country.objects.filter(status=True).order_by('name'),
        'states': State.objects.select_related('country').filter(status=True).order_by('country__name', 'name'),
        'districts': District.objects.select_related('state', 'state__country').filter(status=True).order_by('state__name', 'name'),
        'instance': instance,
    }
    templates = {
        Country: 'master/country/form.html', State: 'master/state/form.html',
        District: 'master/district/form.html', Area: 'master/area/form.html',
        Designation: 'master/designation/form.html', EstablishmentType: 'master/establishment_type/form.html',
        PurposeOfVisit: 'master/purpose_of_visit/form.html',
    }
    return render(request, templates[model], context)


# ============================================================
# COUNTRY MASTER
# ============================================================

@superuser_required
def country_list(request):
    search = request.GET.get('search', '').strip()
    queryset = Country.objects.all()
    if search:
        queryset = queryset.filter(name__icontains=search)
    return render(request, 'master/country/list.html', {'page_obj': Paginator(queryset.order_by('name'), 10).get_page(request.GET.get('page')), 'search': search})


@superuser_required
def country_create(request):
    response = _master_form(request, Country, 'Create Country')
    if response is None:
        messages.success(request, 'Country created successfully.')
        return redirect('country_list')
    return response


@superuser_required
def country_edit(request, pk):
    response = _master_form(request, Country, 'Edit Country', get_object_or_404(Country, pk=pk))
    if response is None:
        messages.success(request, 'Country updated successfully.')
        return redirect('country_list')
    return response


@superuser_required
def country_delete(request, pk):
    if request.method == 'POST':
        try:
            get_object_or_404(Country, pk=pk).delete()
            messages.success(request, 'Country deleted successfully.')
        except Exception:
            messages.error(request, 'This country cannot be deleted because it is being used by other records.')
    return redirect('country_list')


# ============================================================
# STATE MASTER
# ============================================================

@superuser_required
def state_list(request):
    search = request.GET.get('search', '').strip()
    queryset = State.objects.select_related('country').all()
    if search:
        queryset = queryset.filter(name__icontains=search) | queryset.filter(country__name__icontains=search)
    return render(request, 'master/state/list.html', {'page_obj': Paginator(queryset.order_by('name'), 10).get_page(request.GET.get('page')), 'search': search})


@superuser_required
def state_create(request):
    response = _master_form(request, State, 'Create State')
    if response is None:
        messages.success(request, 'State / Province created successfully.')
        return redirect('state_list')
    return response


@superuser_required
def state_edit(request, pk):
    response = _master_form(request, State, 'Edit State', get_object_or_404(State, pk=pk))
    if response is None:
        messages.success(request, 'State / Province updated successfully.')
        return redirect('state_list')
    return response


@superuser_required
def state_delete(request, pk):
    if request.method == 'POST':
        try:
            get_object_or_404(State, pk=pk).delete()
            messages.success(request, 'State / Province deleted successfully.')
        except Exception:
            messages.error(request, 'This state cannot be deleted because it is being used by other records.')
    return redirect('state_list')


# ============================================================
# DISTRICT MASTER
# ============================================================

@superuser_required
def district_list(request):
    search = request.GET.get('search', '').strip()
    queryset = District.objects.select_related('state', 'state__country').all()
    if search:
        from django.db.models import Q
        queryset = queryset.filter(Q(name__icontains=search) | Q(state__name__icontains=search) | Q(state__country__name__icontains=search))
    return render(request, 'master/district/list.html', {'page_obj': Paginator(queryset.order_by('name'), 10).get_page(request.GET.get('page')), 'search': search})


@superuser_required
def district_create(request):
    response = _master_form(request, District, 'Create District')
    if response is None:
        messages.success(request, 'District created successfully.')
        return redirect('district_list')
    return response


@superuser_required
def district_edit(request, pk):
    response = _master_form(request, District, 'Edit District', get_object_or_404(District, pk=pk))
    if response is None:
        messages.success(request, 'District updated successfully.')
        return redirect('district_list')
    return response


@superuser_required
def district_delete(request, pk):
    if request.method == 'POST':
        try:
            get_object_or_404(District, pk=pk).delete()
            messages.success(request, 'District deleted successfully.')
        except Exception:
            messages.error(request, 'This district cannot be deleted because it is being used by other records.')
    return redirect('district_list')


# ============================================================
# AREA MASTER
# ============================================================

@superuser_required
def area_list(request):
    search = request.GET.get('search', '').strip()
    queryset = Area.objects.select_related('district', 'district__state', 'district__state__country').all()
    if search:
        from django.db.models import Q
        queryset = queryset.filter(Q(name__icontains=search) | Q(district__name__icontains=search) | Q(district__state__name__icontains=search))
    return render(request, 'master/area/list.html', {'page_obj': Paginator(queryset.order_by('name'), 10).get_page(request.GET.get('page')), 'search': search})


@superuser_required
def area_create(request):
    response = _master_form(request, Area, 'Create Area')
    if response is None:
        messages.success(request, 'Area created successfully.')
        return redirect('area_list')
    return response


@superuser_required
def area_edit(request, pk):
    response = _master_form(request, Area, 'Edit Area', get_object_or_404(Area, pk=pk))
    if response is None:
        messages.success(request, 'Area updated successfully.')
        return redirect('area_list')
    return response


@superuser_required
def area_delete(request, pk):
    if request.method == 'POST':
        try:
            get_object_or_404(Area, pk=pk).delete()
            messages.success(request, 'Area deleted successfully.')
        except Exception:
            messages.error(request, 'This area cannot be deleted because it is being used by other records.')
    return redirect('area_list')


# Global designation create/edit/delete actions are linked from the unified master list.


@superuser_required
def designation_create(request):

    response = _master_form(
        request,
        Designation,
        'Add Global Designation'
    )

    if response is None:
        messages.success(
            request,
            'Global Designation created successfully.'
        )

        return redirect('company_designation_list')

    return response


@superuser_required
def designation_edit(request, pk):

    designation = get_object_or_404(
        Designation,
        pk=pk
    )

    response = _master_form(
        request,
        Designation,
        'Edit Global Designation',
        designation
    )

    if response is None:
        messages.success(
            request,
            'Global Designation updated successfully.'
        )

        return redirect('company_designation_list')

    return response


@superuser_required
def designation_delete(request, pk):

    if request.method == 'POST':

        designation = get_object_or_404(
            Designation,
            pk=pk
        )

        try:
            designation.delete()

            messages.success(
                request,
                'Global Designation deleted successfully.'
            )

        except Exception:
            messages.error(
                request,
                'This designation cannot be deleted because '
                'it is enabled for one or more companies.'
            )

    return redirect('company_designation_list')
# ============================================================
# ESTABLISHMENT TYPE MASTER
# ============================================================

@superuser_required
def establishment_type_list(request):
    search = request.GET.get('search', '').strip()
    queryset = EstablishmentType.objects.all()
    if search:
        queryset = queryset.filter(name__icontains=search)
    return render(request, 'master/establishment_type/list.html', {'page_obj': Paginator(queryset.order_by('name'), 10).get_page(request.GET.get('page')), 'search': search})


@superuser_required
def establishment_type_create(request):
    response = _master_form(request, EstablishmentType, 'Add Establishment Type')
    if response is None:
        messages.success(request, 'Establishment Type created successfully.')
        return redirect('establishment_type_list')
    return response


@superuser_required
def establishment_type_edit(request, pk):
    response = _master_form(request, EstablishmentType, 'Edit Establishment Type', get_object_or_404(EstablishmentType, pk=pk))
    if response is None:
        messages.success(request, 'Establishment Type updated successfully.')
        return redirect('establishment_type_list')
    return response


@superuser_required
def establishment_type_delete(request, pk):
    if request.method == 'POST':
        item = get_object_or_404(EstablishmentType, pk=pk)
        try:
            item.delete()
            messages.success(request, 'Establishment Type deleted successfully.')
        except ProtectedError:
            messages.error(request, 'This Establishment Type is assigned to one or more units. Deactivate it instead.')
    return redirect('establishment_type_list')


# ============================================================
# PURPOSE OF VISIT MASTER
# ============================================================

@superuser_required
def purpose_of_visit_list(request):
    search = request.GET.get('search', '').strip()
    queryset = PurposeOfVisit.objects.all()
    if search:
        queryset = queryset.filter(name__icontains=search)
    return render(request, 'master/purpose_of_visit/list.html', {'page_obj': Paginator(queryset.order_by('name'), 10).get_page(request.GET.get('page')), 'search': search})


@superuser_required
def purpose_of_visit_create(request):
    response = _master_form(request, PurposeOfVisit, 'Add Purpose of Visit')
    if response is None:
        messages.success(request, 'Purpose of Visit created successfully.')
        return redirect('purpose_of_visit_list')
    return response


@superuser_required
def purpose_of_visit_edit(request, pk):
    response = _master_form(request, PurposeOfVisit, 'Edit Purpose of Visit', get_object_or_404(PurposeOfVisit, pk=pk))
    if response is None:
        messages.success(request, 'Purpose of Visit updated successfully.')
        return redirect('purpose_of_visit_list')
    return response


@superuser_required
def purpose_of_visit_delete(request, pk):
    if request.method == 'POST':
        get_object_or_404(PurposeOfVisit, pk=pk).delete()
        messages.success(request, 'Purpose of Visit deleted successfully.')
    return redirect('purpose_of_visit_list')
