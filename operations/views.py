from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from django.db.models import Q, Prefetch
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils import timezone
from datetime import timedelta
import base64
import binascii
import secrets

from core.models import Country, State, District, Area, Designation, EstablishmentType, PurposeOfVisit
from .models import (
    Company, CompanyStaff, CompanyDesignation, WorkSite, Building, BuildingTypeMaster,
    BuildingStaff, Floor, Unit, Tenant, TenantUnitAllocation, TenantFamilyMember, TenantStaffMember, GuestVisit, GuestVisitAccompanyingPerson, IDTag, IDTagIssue, HoldDocument,
)

User = get_user_model()


# ============================================================
# COMMON DIRECT-HTML HELPERS
# ============================================================

def _validation_errors(exc):
    if hasattr(exc, 'message_dict'):
        return ({key: list(value) for key, value in exc.message_dict.items() if key != '__all__'},
                list(exc.message_dict.get('__all__', [])))
    return {'__all__': list(exc.messages)}, []


def _related(model, raw, field_name, errors, required=True, queryset=None):
    if not str(raw or '').strip():
        if required:
            errors[field_name] = ['This field is required.']
        return None
    try:
        obj = (queryset if queryset is not None else model.objects.all()).filter(pk=raw).first()
    except (ValueError, TypeError, ValidationError):
        obj = None
    if obj is None:
        errors[field_name] = ['Please select a valid option.']
    return obj


def _field_values(request, instance, fields):
    result = {}
    for name in fields:
        field = instance._meta.get_field(name)
        if request.method == 'POST':
            raw = request.POST.get(name, '')
        elif field.is_relation and field.many_to_one:
            raw = getattr(instance, f'{name}_id', '') or ''
        else:
            raw = getattr(instance, name, '')
        if field.get_internal_type() == 'BooleanField':
            result[name] = (name in request.POST) if request.method == 'POST' else bool(raw)
        else:
            result[name] = str(raw) if raw is not None else ''
    return result


def get_building_staff(request):
    """Building Staff accounts are retired; no user receives this role."""
    return None


def is_building_staff(request):
    return False


def get_user_company(request):
    if request.user.is_superuser:
        return None
    staff = CompanyStaff.objects.select_related('company').filter(
        user=request.user, status=True, company__status=True,
    ).first()
    return staff.company if staff else None


def get_company_dial_code(company):
    """Return the dial code directly from Country Master through Company.country."""
    if not company:
        return ''
    country = getattr(company, 'country', None)
    return (getattr(country, 'dial_code', '') or '').strip()


def get_tenant_company_dial_code(tenant):
    """Resolve a tenant's company dial code from Country Master.

    Source of truth:
        Country Master -> Company.country -> Country.dial_code
    No dial code is hardcoded here.
    """
    if not tenant:
        return ''

    allocation = (
        tenant.unit_allocations
        .filter(released_at__isnull=True)
        .select_related('unit__company__country')
        .order_by('pk')
        .first()
    )
    if allocation and allocation.unit and allocation.unit.company:
        return get_company_dial_code(allocation.unit.company)

    # Legacy fallback for older tenant records that still use Tenant.unit.
    unit = getattr(tenant, 'unit', None)
    if unit and getattr(unit, 'company', None):
        return get_company_dial_code(unit.company)

    return ''


def _deny_building_staff(request):
    if is_building_staff(request):
        messages.error(request, 'This page is not available to Building Staff.')
        return redirect('dashboard')
    return None


def _company_context(request, company, errors=None, non_field_errors=None, is_edit=False):
    fields = [
        'name', 'address', 'tax_number', 'email', 'phone', 'country', 'state', 'district', 'area',
        'concerned_staff_name', 'concerned_staff_designation', 'concerned_staff_mobile',
        'applicable_tax', 'status',
    ]
    values = _field_values(request, company, fields)
    selected_designations = request.POST.getlist('enabled_designations') if request.method == 'POST' else list(
        company.enabled_designations.values_list('pk', flat=True) if company.pk else []
    )
    return {
        'company': company, 'values': values, 'errors': errors or {},
        'non_field_errors': non_field_errors or [], 'is_edit': is_edit,
        'countries': Country.objects.filter(status=True).order_by('name'),
        'states': State.objects.select_related('country').filter(status=True).order_by('name'),
        'districts': District.objects.select_related('state').filter(status=True).order_by('name'),
        'areas': Area.objects.select_related('district').filter(status=True).order_by('name'),
        'designations': Designation.objects.filter(status=True).order_by('name'),
        'all_designations': Designation.objects.all().order_by('name'),
        'selected_designations': [str(x) for x in selected_designations],
    }


def _save_company_post(request, company, creating=False):
    errors, non_field_errors = {}, []
    fields = [
        'name', 'address', 'tax_number', 'email', 'phone', 'country', 'state', 'district', 'area',
        'concerned_staff_name', 'concerned_staff_designation', 'concerned_staff_mobile',
        'applicable_tax', 'status',
    ]
    related_fields = {'country': Country, 'state': State, 'district': District, 'area': Area}
    for name in fields:
        if name in related_fields:
            obj = _related(related_fields[name], request.POST.get(name), name, errors, required=True)
            if obj is not None:
                setattr(company, name, obj)
            continue
        if name in ('applicable_tax', 'status'):
            setattr(company, name, name in request.POST)
            continue
        model_field = company._meta.get_field(name)
        value = request.POST.get(name, '').strip()
        if not value and not model_field.blank and not model_field.null:
            errors[name] = ['This field is required.']
        if model_field.max_length and len(value) > model_field.max_length:
            errors[name] = [f'Ensure this value has at most {model_field.max_length} characters.']
        setattr(company, name, value or (None if model_field.null else ''))

    if all(getattr(company, f'{key}_id', None) for key in ('country', 'state', 'district', 'area')):
        if company.state.country_id != company.country_id:
            errors['state'] = ['Selected state does not belong to the selected country.']
        if company.district.state_id != company.state_id:
            errors['district'] = ['Selected district does not belong to the selected state.']
        if company.area.district_id != company.district_id:
            errors['area'] = ['Selected area does not belong to the selected district.']

    active_designations = set(Designation.objects.filter(status=True).values_list('name', flat=True))
    current_designation = company.concerned_staff_designation or ''
    if current_designation and current_designation not in active_designations:
        # Keep an existing inactive master designation on an edit, but reject a new invalid value.
        if not company.pk or current_designation != getattr(company, '_original_staff_designation', None):
            errors['concerned_staff_designation'] = ['Select a valid active master designation.']

    selected_designations = []
    raw_ids = request.POST.getlist('enabled_designations')
    try:
        selected_designations = list(Designation.objects.filter(pk__in=raw_ids, status=True)) if raw_ids else []
        if len(selected_designations) != len(set(raw_ids)):
            errors['enabled_designations'] = ['Select valid master designations.']
    except (ValueError, TypeError, ValidationError):
        errors['enabled_designations'] = ['Select valid master designations.']

    if not errors:
        try:
            company.full_clean(exclude=['enabled_designations'])
        except ValidationError as exc:
            errors, non_field_errors = _validation_errors(exc)

    username = password = password_confirm = ''
    if creating:
        username = request.POST.get('staff_username', '').strip()
        password = request.POST.get('staff_password', '')
        password_confirm = request.POST.get('staff_password_confirm', '')
        if not username:
            errors['staff_username'] = ['Staff username is required.']
        elif len(username) > 150:
            errors['staff_username'] = ['Username cannot exceed 150 characters.']
        elif User.objects.filter(username__iexact=username).exists():
            errors['staff_username'] = ['This username is already taken.']
        if not password:
            errors['staff_password'] = ['Staff password is required.']
        if not password_confirm:
            errors['staff_password_confirm'] = ['Please confirm the password.']
        elif password != password_confirm:
            errors['staff_password_confirm'] = ['Passwords do not match.']
        if password and password == password_confirm:
            try:
                validate_password(password, user=User(username=username))
            except ValidationError as exc:
                errors['staff_password'] = list(exc.messages)

    if errors or non_field_errors:
        return False, errors, non_field_errors
    with transaction.atomic():
        company.save()
        company.enabled_designations.set(selected_designations)
        if creating:
            user = User.objects.create_user(username=username, email=company.email or '', password=password)
            CompanyStaff.objects.create(company=company, user=user, status=True)
    return True, {}, []


# ============================================================
# COMPANY CRUD
# ============================================================

@login_required
def company_list(request):

    denied = _deny_building_staff(request)
    if denied:
        return denied
    search = request.GET.get('search', '').strip()
    queryset = Company.objects.select_related('country', 'state', 'district', 'area')
    if not request.user.is_superuser:
        company = get_user_company(request)
        if not company:
            messages.error(request, 'You are not assigned to an active company.')
            return redirect('dashboard')
        queryset = queryset.filter(pk=company.pk)
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(address__icontains=search) | Q(tax_number__icontains=search) |
            Q(country__name__icontains=search) | Q(state__name__icontains=search) |
            Q(district__name__icontains=search) | Q(area__name__icontains=search)
        )
    page_obj = Paginator(queryset.order_by('name'), 10).get_page(request.GET.get('page'))
    return render(request, 'operations/company/list.html', {'page_obj': page_obj, 'search': search})


@login_required
def company_detail(request, pk):

    denied = _deny_building_staff(request)
    if denied:
        return denied
    if request.user.is_superuser:
        company = get_object_or_404(Company.objects.select_related('country', 'state', 'district', 'area'), pk=pk)
    else:
        company = get_user_company(request)
        if not company or company.pk != pk:
            messages.error(request, 'You are not authorized to view this company.')
            return redirect('dashboard')
    return render(request, 'operations/company/detail.html', {'company': company})


@login_required
def company_staff_details(request, pk):

    denied = _deny_building_staff(request)
    if denied:
        return denied
    company = get_object_or_404(Company.objects.select_related('country', 'state', 'district', 'area'), pk=pk)
    if not request.user.is_superuser:
        staff = CompanyStaff.objects.filter(user=request.user, status=True, company__status=True, company_id=company.pk).first()
        if not staff:
            return HttpResponseForbidden('You do not have permission to view these details.')
    staff = (
        CompanyStaff.objects
        .select_related('user')
        .filter(
            company=company,
            status=True,
        )
        .order_by('pk')
        .first()
    )

    return render(
        request,
        'operations/company/staff_details.html',
        {
            'company': company,
            'staff_account': staff,
        },
    )


@login_required
def company_create(request):

    denied = _deny_building_staff(request)
    if denied:
        return denied
    if not request.user.is_superuser:
        messages.error(request, 'Only Super Admin can create companies.')
        return redirect('dashboard')
    company = Company()
    errors, non_field_errors = {}, []
    if request.method == 'POST':
        valid, errors, non_field_errors = _save_company_post(request, company, creating=True)
        if valid:
            messages.success(request, 'Company and Company Admin login account created successfully.')
            return redirect('company_list')
    context = _company_context(request, company, errors, non_field_errors, is_edit=False)
    return render(request, 'operations/company/form.html', context)


@login_required
def company_edit(request, pk):

    denied = _deny_building_staff(request)
    if denied:
        return denied
    if not request.user.is_superuser:
        messages.error(request, 'Only Super Admin can edit companies.')
        return redirect('company_list')
    company = get_object_or_404(Company, pk=pk)
    company._original_staff_designation = company.concerned_staff_designation or ''
    errors, non_field_errors = {}, []
    if request.method == 'POST':
        valid, errors, non_field_errors = _save_company_post(request, company, creating=False)
        if valid:
            messages.success(request, 'Company / Client updated successfully.')
            return redirect('company_list')
    context = _company_context(request, company, errors, non_field_errors, is_edit=True)
    return render(request, 'operations/company/edit.html', context)


@login_required
def company_delete(request, pk):

    denied = _deny_building_staff(request)
    if denied:
        return denied
    if not request.user.is_superuser:
        messages.error(request, 'Only Super Admin can delete companies.')
        return redirect('dashboard')
    company = get_object_or_404(Company, pk=pk)
    if request.method == 'POST':
        if Tenant.objects.filter(unit__company=company).exists() or TenantUnitAllocation.objects.filter(unit__company=company).exists():
            messages.error(request, 'This company has tenants assigned to its units. Delete or reassign those tenant records before deleting the company.')
            return redirect('company_list')
        user_ids = list(CompanyStaff.objects.filter(company=company).values_list('user_id', flat=True))
        user_ids += list(BuildingStaff.objects.filter(building__company=company).values_list('user_id', flat=True))
        with transaction.atomic():
            company.delete()
            User.objects.filter(pk__in=user_ids).delete()
        messages.success(request, 'Company / Client and its staff login accounts deleted successfully.')
        return redirect('company_list')
    return render(request, 'operations/company/delete.html', {'company': company})


# ============================================================
# COMPANY DESIGNATION CRUD
# ============================================================

@login_required
def company_designation_list(request):

    denied = _deny_building_staff(request)
    if denied:
        return denied
    company = get_user_company(request)
    if request.user.is_superuser:
        global_items = Designation.objects.all()
        company_items = CompanyDesignation.objects.select_related('company').all()
    else:
        if not company:
            messages.error(request, 'Company access not found.')
            return redirect('dashboard')
        global_items = company.enabled_designations.filter(status=True).order_by('name')
        company_items = CompanyDesignation.objects.select_related('company').filter(company=company, status=True)
    items = [
        {
            'id': x.pk,
            'name': x.name,
            'type': 'Global Master',
            'source': 'global',
            'status': x.status,
            'company': None,
            'created_at': x.created_at,
        }
        for x in global_items
    ]
    items += [
        {
            'id': x.pk,
            'name': x.name,
            'type': 'Company',
            'source': 'company',
            'status': x.status,
            'company': x.company,
            'created_at': x.created_at,
        }
        for x in company_items
    ]
    search = request.GET.get('search', '').strip()
    if search:
        lowered = search.lower()
        items = [x for x in items if lowered in x['name'].lower() or (x['company'] and lowered in x['company'].name.lower())]
    items.sort(key=lambda x: x['name'].lower())
    return render(request, 'master/designation/list.html', {'page_obj': Paginator(items, 10).get_page(request.GET.get('page')), 'search': search, 'company': company})


def _save_company_designation(request, designation, company, superuser):
    errors, non_field_errors = {}, []
    name = request.POST.get('name', '').strip()
    if not name:
        errors['name'] = ['This field is required.']
    elif len(name) > 100:
        errors['name'] = ['Ensure this value has at most 100 characters.']
    designation.name = name
    designation.status = 'status' in request.POST
    if superuser:
        selected = _related(Company, request.POST.get('company'), 'company', errors)
        if selected:
            designation.company = selected
    else:
        designation.company = company
    if not errors:
        try:
            designation.full_clean()
        except ValidationError as exc:
            errors, non_field_errors = _validation_errors(exc)
    if errors or non_field_errors:
        return False, errors, non_field_errors
    designation.save()
    return True, {}, []


@login_required
def company_designation_create(request):

    denied = _deny_building_staff(request)
    if denied:
        return denied
    superuser = request.user.is_superuser
    company = None if superuser else get_user_company(request)
    if not superuser and not company:
        messages.error(request, 'You are not assigned to an active company.')
        return redirect('dashboard')
    designation = CompanyDesignation()
    errors, non_field_errors = {}, []
    if request.method == 'POST':
        valid, errors, non_field_errors = _save_company_designation(request, designation, company, superuser)
        if valid:
            messages.success(request, 'Company designation created successfully.' if superuser else 'Designation added successfully.')
            return redirect('company_designation_list')
    values = {'name': request.POST.get('name', '') if request.method == 'POST' else '', 'status': request.POST.get('status') == 'on' if request.method == 'POST' else True,
              'company': request.POST.get('company', '') if request.method == 'POST' else ''}
    return render(request, 'operations/company_designation/form.html', {
        'values': values, 'errors': errors, 'non_field_errors': non_field_errors,
        'is_edit': False, 'is_company_admin': not superuser, 'company': company,
        'companies': Company.objects.filter(status=True).order_by('name'),
    })


@login_required
def company_designation_edit(request, pk):

    denied = _deny_building_staff(request)
    if denied:
        return denied
    superuser = request.user.is_superuser
    company = None if superuser else get_user_company(request)
    if not superuser and not company:
        messages.error(request, 'You are not assigned to an active company.')
        return redirect('dashboard')
    designation = get_object_or_404(CompanyDesignation, pk=pk) if superuser else get_object_or_404(CompanyDesignation, pk=pk, company=company)
    errors, non_field_errors = {}, []
    if request.method == 'POST':
        valid, errors, non_field_errors = _save_company_designation(request, designation, company, superuser)
        if valid:
            messages.success(request, 'Company designation updated successfully.' if superuser else 'Designation updated successfully.')
            return redirect('company_designation_list')
    values = {'name': request.POST.get('name', designation.name) if request.method == 'POST' else designation.name,
              'status': ('status' in request.POST) if request.method == 'POST' else designation.status,
              'company': request.POST.get('company', designation.company_id) if request.method == 'POST' else str(designation.company_id)}
    return render(request, 'operations/company_designation/form.html', {
        'values': values, 'errors': errors, 'non_field_errors': non_field_errors,
        'is_edit': True, 'is_company_admin': not superuser, 'company': company, 'designation': designation,
        'companies': Company.objects.filter(status=True).order_by('name'),
    })


@login_required
def company_designation_delete(request, pk):

    denied = _deny_building_staff(request)
    if denied:
        return denied
    if request.user.is_superuser:
        designation = get_object_or_404(CompanyDesignation, pk=pk)
    else:
        company = get_user_company(request)
        if not company:
            messages.error(request, 'You are not assigned to an active company.')
            return redirect('dashboard')
        designation = get_object_or_404(CompanyDesignation, pk=pk, company=company)
    if request.method == 'POST':
        designation.delete()
        messages.success(request, 'Company designation deleted successfully.')
    return redirect('company_designation_list')


# ============================================================
# WORK SITE / BUILDING / FLOOR / UNIT HELPERS
# ============================================================

def _accessible_companies(request):
    if request.user.is_superuser:
        return Company.objects.filter(status=True).order_by('name')
    if is_building_staff(request):
        return Company.objects.none()
    company = get_user_company(request)
    return Company.objects.filter(pk=company.pk) if company else Company.objects.none()


def _scope_queryset(request, queryset, company_field='company'):
    if request.user.is_superuser:
        return queryset
    building_staff = get_building_staff(request)
    if building_staff:
        model = queryset.model
        if model is Building:
            return queryset.filter(pk=building_staff.building_id)
        if model is Floor:
            return queryset.filter(building_id=building_staff.building_id)
        if model is Unit:
            return queryset.filter(building_id=building_staff.building_id)
        if model is Tenant:
            return queryset.filter(unit__building_id=building_staff.building_id)
        if model is Company:
            return queryset.filter(pk=building_staff.building.company_id)
        return queryset.none()
    company = get_user_company(request)
    if not company:
        return queryset.none()
    return queryset.filter(**{f'{company_field}_id': company.pk})


def _save_operation_instance(request, instance, field_config, fixed_company=None):
    errors, non_field_errors = {}, []
    for name, config in field_config.items():
        field = instance._meta.get_field(name)
        if name == 'company' and fixed_company is not None:
            setattr(instance, 'company', fixed_company)
            continue
        if field.get_internal_type() == 'BooleanField':
            setattr(instance, name, name in request.POST)
            continue
        raw = request.POST.get(name, '').strip()
        if field.is_relation and field.many_to_one:
            if not raw and not field.blank and not field.null:
                errors[name] = ['This field is required.']
                continue
            if not raw and (field.blank or field.null):
                setattr(instance, name, None)
                continue
            allowed = config.get('queryset')
            obj = _related(field.remote_field.model, raw, name, errors, required=not field.blank and not field.null, queryset=allowed)
            if obj is not None:
                setattr(instance, name, obj)
            continue
        if field.get_internal_type() in ('PositiveIntegerField', 'PositiveSmallIntegerField', 'SmallIntegerField', 'IntegerField'):
            if not raw:
                raw = '0' if not field.null else ''
            try:
                value = int(raw) if raw else None
                if value is not None and value < 0:
                    raise ValueError
            except (ValueError, TypeError):
                errors[name] = ['Enter a valid non-negative whole number.']
                continue
            setattr(instance, name, value)
            continue
        value = raw
        if not value and not field.blank and not field.null:
            errors[name] = ['This field is required.']
        if field.max_length and len(value) > field.max_length:
            errors[name] = [f'Ensure this value has at most {field.max_length} characters.']
        setattr(instance, name, value or (None if field.null else ''))
    if isinstance(instance, Building):
        if instance.building_type == 'apartment':
            instance.number_of_villas = 0
            instance.other_type_name = ''
        elif instance.building_type == 'villa':
            instance.number_of_floors = 0
            instance.number_of_flats = 0
            instance.number_of_office_units = 0
            instance.number_of_other_units = 0
            instance.other_type_name = ''
        elif instance.building_type == 'office':
            instance.number_of_flats = 0
            instance.number_of_villas = 0
            instance.number_of_other_units = 0
            instance.other_type_name = ''
        elif instance.building_type == 'other':
            instance.number_of_flats = 0
            instance.number_of_villas = 0
            instance.number_of_office_units = 0
        if instance.building_type != 'villa' and instance.number_of_floors is None:
            instance.number_of_floors = 0

    if not errors:
        try:
            instance.full_clean()
        except ValidationError as exc:
            errors, non_field_errors = _validation_errors(exc)
    return errors, non_field_errors


def _operation_values(request, instance, field_config):
    values = {}
    for name in field_config:
        field = instance._meta.get_field(name)
        if request.method == 'POST':
            raw = request.POST.get(name, '')
        elif field.is_relation and field.many_to_one:
            raw = getattr(instance, f'{name}_id', '') or ''
        else:
            raw = getattr(instance, name, '')
        values[name] = str(raw) if raw is not None else ''
    return values


def _operation_form(request, instance, field_config, title, template, list_url, fixed_company=None, extra_context=None):
    errors, non_field_errors = {}, []
    if request.method == 'POST':
        errors, non_field_errors = _save_operation_instance(request, instance, field_config, fixed_company)
        unit_email = (request.POST.get('email', '').strip().lower() if isinstance(instance, Unit) else '')
        unit_mobile = (request.POST.get('mobile_number', '').strip() if isinstance(instance, Unit) else '')
        if isinstance(instance, Unit) and not instance.pk:
            if not unit_email:
                errors['email'] = ['Email is required for the Unit login username.']
            if not unit_mobile:
                errors['mobile_number'] = ['Mobile number is required as the initial password.']
            if unit_email and User.objects.filter(username__iexact=unit_email).exists():
                errors['email'] = ['This email is already used by another login account.']
        if not errors and not non_field_errors:
            instance.save()
            if isinstance(instance, Unit) and not instance.user_id:
                account = User.objects.create_user(username=unit_email, email=unit_email, password=unit_mobile)
                instance.user = account
                instance.save(update_fields=['user'])
            messages.success(request, f'{title} successfully.')
            return redirect(list_url)
    context = {
        'title': title, 'is_edit': bool(instance.pk), 'values': _operation_values(request, instance, field_config),
        'errors': errors, 'non_field_errors': non_field_errors, 'instance': instance,
    }
    if extra_context:
        context.update(extra_context)
    return render(request, template, context)


def _company_and_site_config(request, instance=None):
    company = get_user_company(request)
    companies = _accessible_companies(request)
    sites = WorkSite.objects.select_related('company').filter(status=True)
    if not request.user.is_superuser:
        sites = sites.filter(company=company) if company else sites.none()
    return company, companies, sites


# ============================================================
# WORK SITE CRUD
# ============================================================

@login_required
def work_site_list(request):

    denied = _deny_building_staff(request)
    if denied:
        return denied
    queryset = WorkSite.objects.select_related('company').all()
    if not request.user.is_superuser:
        company = get_user_company(request)
        if not company:
            messages.error(request, 'Company access not found.')
            return redirect('dashboard')
        queryset = queryset.filter(company=company)
    search = request.GET.get('search', '').strip()
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(company__name__icontains=search) | Q(address__icontains=search) | Q(location__icontains=search))
    return render(request, 'operations/work_site/list.html', {'page_obj': Paginator(queryset, 10).get_page(request.GET.get('page')), 'search': search})


@login_required
def work_site_create(request):

    denied = _deny_building_staff(request)
    if denied:
        return denied
    company, companies, _ = _company_and_site_config(request)
    if not request.user.is_superuser and not company:
        messages.error(request, 'Company access not found.')
        return redirect('dashboard')
    instance = WorkSite()
    config = {'company': {'queryset': companies}, 'name': {}, 'address': {}, 'location': {}, 'status': {}}
    return _operation_form(request, instance, config, 'Work Site saved', 'operations/work_site/form.html', 'work_site_list',
                           fixed_company=company if not request.user.is_superuser else None,
                           extra_context={'companies': companies, 'is_company_admin': not request.user.is_superuser, 'company': company})


@login_required
def work_site_edit(request, pk):

    denied = _deny_building_staff(request)
    if denied:
        return denied
    company, companies, _ = _company_and_site_config(request)
    queryset = WorkSite.objects.all() if request.user.is_superuser else WorkSite.objects.filter(company=company)
    instance = get_object_or_404(queryset, pk=pk)
    config = {'company': {'queryset': companies}, 'name': {}, 'address': {}, 'location': {}, 'status': {}}
    return _operation_form(request, instance, config, 'Work Site updated', 'operations/work_site/form.html', 'work_site_list',
                           fixed_company=company if not request.user.is_superuser else None,
                           extra_context={'companies': companies, 'is_company_admin': not request.user.is_superuser, 'company': company})


@login_required
def work_site_delete(request, pk):

    denied = _deny_building_staff(request)
    if denied:
        return denied
    queryset = WorkSite.objects.all() if request.user.is_superuser else WorkSite.objects.filter(company=get_user_company(request))
    item = get_object_or_404(queryset, pk=pk)
    if request.method == 'POST':
        if Tenant.objects.filter(unit__work_site=item).exists() or TenantUnitAllocation.objects.filter(unit__work_site=item).exists():
            messages.error(request, 'This Work Site has tenants assigned to its units. Delete or reassign those tenant records before deleting the Work Site.')
            return redirect('work_site_list')
        user_ids = list(BuildingStaff.objects.filter(building__work_site=item).values_list('user_id', flat=True))
        with transaction.atomic():
            item.delete()
            User.objects.filter(pk__in=user_ids).delete()
        messages.success(request, 'Work Site and its building staff login accounts deleted successfully.')
    return redirect('work_site_list')


# ============================================================
# BUILDING CRUD
# ============================================================

@login_required
def building_list(request):
    queryset = _scope_queryset(
        request,
        Building.objects.select_related('company', 'work_site', 'building_type_master').all(),
    )
    search = request.GET.get('search', '').strip()
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(work_site__name__icontains=search) |
            Q(company__name__icontains=search) | Q(building_type__icontains=search) |
            Q(building_type_master__name__icontains=search) | Q(address__icontains=search) |
            Q(location__icontains=search)
        )
    page_obj = Paginator(queryset.order_by('company__name', 'name'), 10).get_page(request.GET.get('page'))
    return render(request, 'operations/building/list.html', {
        'page_obj': page_obj, 'search': search, 'is_building_staff': is_building_staff(request),
    })


def _building_form_config(request, instance=None):
    company = get_user_company(request)
    companies = _accessible_companies(request)
    sites = WorkSite.objects.select_related('company').filter(status=True)
    if not request.user.is_superuser:
        sites = sites.filter(company=company) if company and not is_building_staff(request) else sites.none()
    selected_company = request.POST.get('company') if request.method == 'POST' else (getattr(instance, 'company_id', '') or '')
    if not selected_company and company and not request.user.is_superuser:
        selected_company = company.pk
    if selected_company:
        sites = sites.filter(company_id=selected_company)
    building_types = BuildingTypeMaster.objects.filter(status=True).order_by('name')
    if instance.pk and instance.building_type_master_id:
        building_types = (BuildingTypeMaster.objects.filter(status=True) | BuildingTypeMaster.objects.filter(pk=instance.building_type_master_id)).distinct().order_by('name')
    config = {
        'company': {'queryset': companies}, 'work_site': {'queryset': sites},
        'building_type_master': {'queryset': building_types}, 'name': {}, 'address': {},
        'location': {}, 'number_of_floors': {}, 'number_of_flats': {}, 'number_of_villas': {},
        'number_of_office_units': {}, 'number_of_other_units': {}, 'other_type_name': {}, 'status': {},
    }
    return company, companies, sites, building_types, config


def _building_form(request, instance, is_edit=False):
    company, companies, sites, building_types, config = _building_form_config(request, instance)
    errors, non_field_errors = {}, []

    if request.method == 'POST':
        errors, non_field_errors = _save_operation_instance(
            request, instance, config,
            fixed_company=company if not request.user.is_superuser else None,
        )
        if not instance.building_type_master_id:
            errors['building_type_master'] = ['Select a Building Type.']
        if instance.work_site_id and instance.company_id and instance.work_site.company_id != instance.company_id:
            errors['work_site'] = ['Select a Work Site belonging to the selected Company.']

        if not errors and not non_field_errors:
            instance.save()
            messages.success(request, 'Building saved successfully.')
            return redirect('building_list')

    values = _operation_values(request, instance, config)
    context = {
        'title': 'Update Building' if is_edit else 'Create Building',
        'is_edit': is_edit, 'values': values, 'errors': errors,
        'non_field_errors': non_field_errors, 'instance': instance,
        'companies': companies, 'work_sites': sites, 'building_types': building_types,
        'company': company,
    }
    return render(request, 'operations/building/form.html', context)


@login_required
def building_create(request):
    denied = _deny_building_staff(request)
    if denied:
        return denied
    company = get_user_company(request)
    if not request.user.is_superuser and not company:
        messages.error(request, 'Company access not found.')
        return redirect('dashboard')
    return _building_form(request, Building(), is_edit=False)


@login_required
def building_edit(request, pk):
    denied = _deny_building_staff(request)
    if denied:
        return denied
    company = get_user_company(request)
    queryset = Building.objects.all() if request.user.is_superuser else Building.objects.filter(company=company)
    instance = get_object_or_404(queryset, pk=pk)
    return _building_form(request, instance, is_edit=True)


@login_required
def building_delete(request, pk):
    denied = _deny_building_staff(request)
    if denied:
        return denied
    queryset = Building.objects.all() if request.user.is_superuser else Building.objects.filter(company=get_user_company(request))
    item = get_object_or_404(queryset, pk=pk)
    if request.method == 'POST':
        if Tenant.objects.filter(unit__building=item).exists() or TenantUnitAllocation.objects.filter(unit__building=item).exists():
            messages.error(request, 'This building has tenants assigned to its units. Delete or reassign those tenant records before deleting the building.')
            return redirect('building_list')
        item.delete()
        messages.success(request, 'Building, its floors and units were deleted successfully.')
    return redirect('building_list')


@login_required
def my_building(request):
    staff = get_building_staff(request)
    if not staff:
        return redirect('building_list')
    return render(request, 'operations/building/detail.html', {'building': staff.building})


# ============================================================
# BUILDING TYPE MASTER
# ============================================================

@login_required
def building_type_list(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Only Super Admin can manage Building Types.')
    search = request.GET.get('search', '').strip()
    queryset = BuildingTypeMaster.objects.all()
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search) | Q(description__icontains=search))
    page_obj = Paginator(queryset.order_by('name'), 10).get_page(request.GET.get('page'))
    return render(request, 'operations/building_type/list.html', {'page_obj': page_obj, 'search': search})


@login_required
def building_type_create(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Only Super Admin can manage Building Types.')
    values = {'name': '', 'code': 'other', 'description': '', 'status': True}
    errors, non_field_errors = {}, []
    if request.method == 'POST':
        values = {'name': request.POST.get('name', '').strip(), 'code': request.POST.get('code', 'other'),
                  'description': request.POST.get('description', '').strip(), 'status': 'status' in request.POST}
        item = BuildingTypeMaster(**values)
        try:
            item.full_clean()
            item.save()
        except ValidationError as exc:
            errors, non_field_errors = _validation_errors(exc)
        if not errors and not non_field_errors:
            messages.success(request, 'Building Type created successfully.')
            return redirect('building_type_list')
    return render(request, 'operations/building_type/form.html', {
        'title': 'Create Building Type', 'values': values, 'errors': errors,
        'non_field_errors': non_field_errors, 'type_choices': BuildingTypeMaster.CATEGORY_CHOICES,
    })


@login_required
def building_type_edit(request, pk):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Only Super Admin can manage Building Types.')
    item = get_object_or_404(BuildingTypeMaster, pk=pk)
    values = {'name': item.name, 'code': item.code, 'description': item.description, 'status': item.status}
    errors, non_field_errors = {}, []
    if request.method == 'POST':
        values = {'name': request.POST.get('name', '').strip(), 'code': request.POST.get('code', 'other'),
                  'description': request.POST.get('description', '').strip(), 'status': 'status' in request.POST}
        for key, value in values.items():
            setattr(item, key, value)
        try:
            item.full_clean()
            item.save()
        except ValidationError as exc:
            errors, non_field_errors = _validation_errors(exc)
        if not errors and not non_field_errors:
            messages.success(request, 'Building Type updated successfully.')
            return redirect('building_type_list')
    return render(request, 'operations/building_type/form.html', {
        'title': 'Update Building Type', 'values': values, 'errors': errors,
        'non_field_errors': non_field_errors, 'type_choices': BuildingTypeMaster.CATEGORY_CHOICES,
    })


@login_required
def building_type_delete(request, pk):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Only Super Admin can manage Building Types.')
    item = get_object_or_404(BuildingTypeMaster, pk=pk)
    if request.method == 'POST':
        if item.buildings.exists():
            messages.error(request, 'This Building Type is in use and cannot be deleted. Deactivate it instead.')
        else:
            item.delete()
            messages.success(request, 'Building Type deleted successfully.')
    return redirect('building_type_list')


# ============================================================
# FLOOR CRUD
# ============================================================

@login_required
def floor_list(request):
    queryset = Floor.objects.select_related('building', 'building__company', 'building__work_site').all()
    if not request.user.is_superuser:
        company = get_user_company(request)
        if not company:
            messages.error(request, 'Company access not found.')
            return redirect('dashboard')
        building_staff = get_building_staff(request)
        queryset = queryset.filter(building_id=building_staff.building_id) if building_staff else queryset.filter(building__company=company)
    search = request.GET.get('search', '').strip()
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(building__name__icontains=search) | Q(building__work_site__name__icontains=search))
    return render(request, 'operations/floor/list.html', {'page_obj': Paginator(queryset, 10).get_page(request.GET.get('page')), 'search': search, 'is_building_staff': is_building_staff(request)})


def _floor_buildings(request):
    queryset = Building.objects.select_related('company', 'work_site', 'building_type_master').filter(status=True).exclude(building_type='villa')
    if not request.user.is_superuser:
        company = get_user_company(request)
        building_staff = get_building_staff(request)
        if building_staff:
            queryset = queryset.filter(pk=building_staff.building_id)
        else:
            queryset = queryset.filter(company=company) if company else queryset.none()
    return queryset


@login_required
def floor_create(request):
    if not request.user.is_superuser and not get_user_company(request):
        messages.error(request, 'Company access not found.')
        return redirect('dashboard')
    buildings = _floor_buildings(request)
    instance = Floor()
    config = {'building': {'queryset': buildings}, 'name': {}, 'floor_number': {}, 'status': {}}
    return _operation_form(request, instance, config, 'Floor saved', 'operations/floor/form.html', 'floor_list',
                           extra_context={'buildings': buildings})


@login_required
def floor_edit(request, pk):
    buildings = _floor_buildings(request)
    queryset = _scope_queryset(request, Floor.objects.all(), company_field='building__company')
    instance = get_object_or_404(queryset, pk=pk)
    config = {'building': {'queryset': buildings}, 'name': {}, 'floor_number': {}, 'status': {}}
    return _operation_form(request, instance, config, 'Floor updated', 'operations/floor/form.html', 'floor_list',
                           extra_context={'buildings': buildings})


@login_required
def floor_delete(request, pk):
    queryset = _scope_queryset(request, Floor.objects.all(), company_field='building__company')
    item = get_object_or_404(queryset, pk=pk)
    if request.method == 'POST':
        if item.units.exists():
            messages.error(request, 'This floor has units assigned. Move or delete those units before deleting the floor.')
        else:
            item.delete()
            messages.success(request, 'Floor deleted successfully.')
    return redirect('floor_list')


# ============================================================
# UNIT CRUD
# ============================================================

@login_required
def unit_list(request):
    queryset = _scope_queryset(request, Unit.objects.select_related('company', 'work_site', 'building', 'floor', 'establishment_type').prefetch_related('tenant_allocations__tenant').all())
    if not request.user.is_superuser and not get_user_company(request):
        messages.error(request, 'Company access not found.')
        return redirect('dashboard')
    search = request.GET.get('search', '').strip()
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(building__name__icontains=search) | Q(work_site__name__icontains=search) | Q(company__name__icontains=search))
    return render(request, 'operations/unit/list.html', {'page_obj': Paginator(queryset, 10).get_page(request.GET.get('page')), 'search': search, 'is_building_staff': is_building_staff(request)})


def _unit_form_data(request, instance=None):
    company, companies, sites = _company_and_site_config(request, instance)
    building_staff = get_building_staff(request)
    if building_staff:
        sites = sites.filter(pk=building_staff.building.work_site_id)
    selected_company = request.POST.get('company') if request.method == 'POST' else (getattr(instance, 'company_id', '') or (company.pk if company else ''))
    if selected_company:
        sites = sites.filter(company_id=selected_company)
    selected_site = request.POST.get('work_site') if request.method == 'POST' else (getattr(instance, 'work_site_id', '') or '')
    buildings = Building.objects.select_related('company', 'work_site', 'building_type_master').filter(status=True)
    if not request.user.is_superuser:
        building_staff = get_building_staff(request)
        if building_staff:
            buildings = buildings.filter(pk=building_staff.building_id)
        else:
            buildings = buildings.filter(company=company) if company else buildings.none()
    if selected_company:
        buildings = buildings.filter(company_id=selected_company)
    if selected_site:
        buildings = buildings.filter(work_site_id=selected_site)
    selected_building = request.POST.get('building') if request.method == 'POST' else (getattr(instance, 'building_id', '') or '')
    floors = Floor.objects.select_related('building').filter(status=True)
    if selected_building:
        floors = floors.filter(building_id=selected_building)
    else:
        floors = floors.none()
    establishment_types = EstablishmentType.objects.filter(status=True).order_by('name')
    if instance and instance.pk and instance.establishment_type_id:
        establishment_types = (EstablishmentType.objects.filter(status=True) | EstablishmentType.objects.filter(pk=instance.establishment_type_id)).distinct().order_by('name')
    config = {
        'company': {'queryset': companies}, 'work_site': {'queryset': sites}, 'building': {'queryset': buildings},
        'floor': {'queryset': floors}, 'establishment_type': {'queryset': establishment_types}, 'name': {}, 'email': {}, 'mobile_number': {}, 'unit_type': {}, 'status': {},
    }
    return company, companies, sites, buildings, floors, config

@login_required
def unit_create(request):
    (
        company,
        companies,
        sites,
        buildings,
        floors,
        config,
    ) = _unit_form_data(request)

    # Establishment Type queryset
    establishment_types = config['establishment_type']['queryset']

    if not request.user.is_superuser and not company:
        messages.error(
            request,
            'Company access not found.'
        )
        return redirect('dashboard')

    return _operation_form(
        request,
        Unit(),
        config,
        'Unit saved',
        'operations/unit/form.html',
        'unit_list',
        fixed_company=(
            company
            if not request.user.is_superuser
            else None
        ),
        extra_context={
            'companies': companies,
            'work_sites': sites,
            'buildings': buildings,
            'floors': floors,
            'unit_types': Unit.UNIT_TYPE_CHOICES,
            'establishment_types': establishment_types,
            'is_company_admin': not request.user.is_superuser,
            'company': company,
        },
    )

@login_required
def unit_edit(request, pk):
    queryset = _scope_queryset(
        request,
        Unit.objects.all()
    )

    instance = get_object_or_404(
        queryset,
        pk=pk
    )

    (
        company,
        companies,
        sites,
        buildings,
        floors,
        config,
    ) = _unit_form_data(
        request,
        instance
    )

    # Establishment Type queryset
    establishment_types = config['establishment_type']['queryset']

    return _operation_form(
        request,
        instance,
        config,
        'Unit updated',
        'operations/unit/form.html',
        'unit_list',
        fixed_company=(
            company
            if not request.user.is_superuser
            else None
        ),
        extra_context={
            'companies': companies,
            'work_sites': sites,
            'buildings': buildings,
            'floors': floors,
            'unit_types': Unit.UNIT_TYPE_CHOICES,
            'establishment_types': establishment_types,
            'is_company_admin': not request.user.is_superuser,
            'company': company,
        },
    )

@login_required
def unit_delete(request, pk):
    queryset = _scope_queryset(request, Unit.objects.all())
    item = get_object_or_404(queryset, pk=pk)
    if request.method == 'POST':
        if item.tenant_allocations.exists() or item.tenants.exists():
            messages.error(request, 'This unit is allocated to a tenant. Release or reassign it before deleting the unit.')
        else:
            item.delete()
            messages.success(request, 'Unit deleted successfully.')
    return redirect('unit_list')


# ============================================================
# TENANT CRUD
# Super Admin: all tenants; Company Staff: own company;
# Building Staff: assigned building only. Tenant accounts are
# restricted to their own family-member pages.
# ============================================================

def _tenant_available_units(request, instance=None):
    """Return active units that are unallocated or already allocated to this tenant.

    Allocation is unit-level: a building may contain units assigned to different
    tenants, and a tenant may select more than one available unit.
    """
    queryset = Unit.objects.select_related(
        'company', 'work_site', 'building', 'floor'
    ).filter(
        status=True,
        company__status=True,
        work_site__status=True,
        building__status=True,
    )

    building_staff = get_building_staff(request)
    if not request.user.is_superuser:
        if building_staff:
            queryset = queryset.filter(building_id=building_staff.building_id)
        else:
            company = get_user_company(request)
            queryset = queryset.filter(company=company) if company else queryset.none()

    occupied_query = TenantUnitAllocation.objects.filter(released_at__isnull=True)
    if instance and instance.pk:
        occupied_query = occupied_query.exclude(tenant_id=instance.pk)
    occupied_allocation_ids = occupied_query.values_list('unit_id', flat=True)

    # Protect older records whose legacy Tenant.unit FK exists but whose
    # allocation-history row has not been backfilled for some reason.
    legacy_tenant_query = Tenant.objects.filter(status=True)
    if instance and instance.pk:
        legacy_tenant_query = legacy_tenant_query.exclude(pk=instance.pk)
    legacy_unit_ids = legacy_tenant_query.values_list('unit_id', flat=True)

    return list(
        queryset.exclude(pk__in=occupied_allocation_ids)
        .exclude(pk__in=legacy_unit_ids).order_by(
            'company__name', 'work_site__name', 'building__name',
            'floor__floor_number', 'name'
        )
    )


def _tenant_values(request, instance):
    if request.method == 'POST':
        unit_ids = request.POST.getlist('units')
    elif instance.pk:
        unit_ids = list(
            instance.unit_allocations.filter(released_at__isnull=True)
            .values_list('unit_id', flat=True)
        )
        if not unit_ids and instance.unit_id and instance.status:
            unit_ids = [instance.unit_id]
    else:
        unit_ids = [instance.unit_id] if instance.unit_id else []

    return {
        'full_name': request.POST.get('full_name', '') if request.method == 'POST' else instance.full_name,
        'mobile_number': request.POST.get('mobile_number', '') if request.method == 'POST' else instance.mobile_number,
        'email': request.POST.get('email', '') if request.method == 'POST' else (instance.email or ''),
        'address': request.POST.get('address', '') if request.method == 'POST' else instance.address,
        'tenant_type': request.POST.get('tenant_type', '') if request.method == 'POST' else instance.tenant_type,
        'identity_number': request.POST.get('identity_number', '') if request.method == 'POST' else (instance.identity_number or ''),
        'lease_start_date': request.POST.get('lease_start_date', '') if request.method == 'POST' else (instance.lease_start_date or ''),
        'lease_end_date': request.POST.get('lease_end_date', '') if request.method == 'POST' else (instance.lease_end_date or ''),
        'notes': request.POST.get('notes', '') if request.method == 'POST' else instance.notes,
        'status': ('status' in request.POST) if request.method == 'POST' else instance.status,
        'unit_ids': [str(value) for value in unit_ids],
        'username': request.POST.get('username', '').strip() if request.method == 'POST' else (instance.user.username if instance.pk and instance.user_id else ''),
        'password': request.POST.get('password', '') if request.method == 'POST' else '',
        'password_confirm': request.POST.get('password_confirm', '') if request.method == 'POST' else '',
    }


def _tenant_form_context(request, instance, units, errors=None, non_field_errors=None):
    return {
        'title': 'Edit Tenant' if instance.pk else 'Add Tenant',
        'is_edit': bool(instance.pk),
        'tenant': instance,
        'units': units,
        'values': _tenant_values(request, instance),
        'errors': errors or {},
        'non_field_errors': non_field_errors or [],
        'is_building_staff': is_building_staff(request),
        'has_tenant_account': bool(instance.pk and instance.user_id),
        'must_change_password': bool(instance.pk and instance.must_change_password),
    }


def _save_tenant_post(request, instance, units):
    errors, non_field_errors = {}, []

    selected_unit_raw = request.POST.getlist('units')
    if not selected_unit_raw:
        errors['units'] = ['Select at least one available unit.']

    allowed_units = {str(unit.pk): unit for unit in units}
    selected_units = []
    for raw_id in selected_unit_raw:
        unit = allowed_units.get(str(raw_id).strip())
        if unit is None:
            errors['units'] = ['One or more selected units are unavailable or already allocated to another tenant.']
            continue
        if unit.pk not in [item.pk for item in selected_units]:
            selected_units.append(unit)

    selected_ids = [unit.pk for unit in selected_units]

    full_name = request.POST.get('full_name', '').strip()
    mobile_number = request.POST.get('mobile_number', '').strip()
    email = request.POST.get('email', '').strip()
    address = request.POST.get('address', '').strip()
    tenant_type = request.POST.get('tenant_type', 'rental').strip()
    identity_number = request.POST.get('identity_number', '').strip()
    lease_start_raw = request.POST.get('lease_start_date', '').strip()
    lease_end_raw = request.POST.get('lease_end_date', '').strip()
    notes = request.POST.get('notes', '').strip()
    status = 'status' in request.POST

    if not full_name:
        errors['full_name'] = ['Tenant name is required.']
    elif len(full_name) > 150:
        errors['full_name'] = ['Tenant name must be 150 characters or fewer.']

    if not mobile_number:
        errors['mobile_number'] = ['Mobile number is required.']
    elif len(mobile_number) > 30:
        errors['mobile_number'] = ['Mobile number must be 30 characters or fewer.']

    if not address:
        errors['address'] = ['Tenant address is required.']

    if not email:
        errors['email'] = ['Tenant email is required.']
    elif len(email) > 254:
        errors['email'] = ['Email must be 254 characters or fewer.']
    else:
        from django.core.validators import validate_email
        try:
            validate_email(email)
        except ValidationError:
            errors['email'] = ['Enter a valid email address.']

    if tenant_type not in dict(Tenant.TENANT_TYPE_CHOICES):
        errors['tenant_type'] = ['Select Rental Tenant or Owner.']

    if selected_units:
        company_ids = {unit.company_id for unit in selected_units}
        if len(company_ids) > 1:
            errors['units'] = ['All units assigned to one tenant must belong to the same company.']

    def read_date(raw, field_name):
        if not raw:
            return None
        parsed = parse_date(raw)
        if parsed is None:
            errors[field_name] = ['Enter a valid date.']
        return parsed

    lease_start_date = read_date(lease_start_raw, 'lease_start_date')
    lease_end_date = read_date(lease_end_raw, 'lease_end_date')

    if tenant_type == 'rental':
        if not lease_start_date:
            errors['lease_start_date'] = ['Lease start date is required for rental tenants.']
        elif not lease_end_date:
            # A one-year lease is the default. Staff can enter a different end date.
            try:
                lease_end_date = lease_start_date.replace(year=lease_start_date.year + 1)
            except ValueError:
                # Leap-day start date: use the final day of February next year.
                lease_end_date = lease_start_date.replace(
                    year=lease_start_date.year + 1, day=28
                )
    elif tenant_type == 'owner':
        lease_start_date = None
        lease_end_date = None

    account = instance.user if instance.pk and instance.user_id else None
    # Tenant login credentials are derived from the registered contact details.
    # The existing template is intentionally unchanged: its password input is
    # ignored for a new account, where the mobile number is the initial password.
    username = email.strip().lower()
    password = mobile_number if account is None else request.POST.get('password', '')

    if not username:
        errors['email'] = ['Tenant email is required for login.']
    elif len(username) > 150:
        errors['email'] = ['Email must be 150 characters or fewer to be used as the login username.']
    else:
        duplicate_username = User.objects.filter(username__iexact=username)
        if account is not None:
            duplicate_username = duplicate_username.exclude(pk=account.pk)
        if duplicate_username.exists():
            errors['email'] = ['This email is already used as a login username. Enter a different email.']

    # Existing accounts keep their current password unless an administrator
    # explicitly enters a new one in the existing optional password field.
    if account is not None and password and password != mobile_number:
        try:
            validate_password(password, user=account)
        except ValidationError as exc:
            errors['password'] = list(exc.messages)

    instance.full_name = full_name
    instance.mobile_number = mobile_number
    instance.email = email or None
    instance.address = address
    instance.tenant_type = tenant_type
    instance.identity_number = identity_number or None
    instance.lease_start_date = lease_start_date
    instance.lease_end_date = lease_end_date
    instance.notes = notes
    instance.status = status

    # The old FK remains for compatibility; the first selected unit is the primary unit.
    if selected_units:
        instance.unit = selected_units[0]

    if not errors:
        try:
            instance.full_clean()
        except ValidationError as exc:
            field_errors, general_errors = _validation_errors(exc)
            for field_name, field_messages in field_errors.items():
                errors.setdefault(field_name, []).extend(field_messages)
            non_field_errors.extend(general_errors)

    if errors or non_field_errors:
        return errors, non_field_errors

    try:
        with transaction.atomic():
            # Save tenant first; allocation rows have a tenant FK.
            instance.save()

            # Preserve allocation history. Only rows with released_at=NULL reserve a unit.
            existing_active_ids = set(
                instance.unit_allocations.filter(released_at__isnull=True)
                .values_list('unit_id', flat=True)
            )
            allowed_ids = set(
                Unit.objects.filter(
                    pk__in=[unit.pk for unit in units],
                    status=True,
                ).values_list('pk', flat=True)
            )
            selected_set = set(selected_ids)
            if instance.pk and is_building_staff(request) and status:
                # Building Staff must not remove allocations in another building.
                selected_set |= (existing_active_ids - allowed_ids)

            # Lock selected units and check only active allocations.
            locked_units = list(
                Unit.objects.select_for_update().filter(pk__in=selected_set).order_by('pk')
            )
            if len(locked_units) != len(selected_set):
                raise ValidationError('One or more selected units no longer exist.')

            occupied = TenantUnitAllocation.objects.select_for_update().filter(
                released_at__isnull=True, unit_id__in=selected_set
            ).exclude(tenant_id=instance.pk)
            if occupied.exists():
                raise ValidationError('One or more selected units have already been allocated to another tenant.')

            released_at = timezone.now()
            active_allocations = instance.unit_allocations.filter(released_at__isnull=True)
            if not status:
                # Deactivation releases every allocation but keeps its history row.
                active_allocations.update(released_at=released_at)
            else:
                ids_to_release = existing_active_ids - selected_set
                if ids_to_release:
                    active_allocations.filter(unit_id__in=ids_to_release).update(
                        released_at=released_at
                    )
                allocations_to_add = selected_set - existing_active_ids
                for unit_id in sorted(allocations_to_add):
                    TenantUnitAllocation.objects.create(tenant=instance, unit_id=unit_id)

            # Keep the legacy FK pointed at the first currently active allocation.
            first_allocation = instance.unit_allocations.filter(
                released_at__isnull=True
            ).select_related('unit').order_by('unit__building__name', 'unit__name').first()
            if first_allocation and instance.unit_id != first_allocation.unit_id:
                instance.unit = first_allocation.unit
                instance.save(update_fields=['unit', 'updated_at'])

            if account is None:
                account = User(
                    username=username,
                    email=email,
                    first_name=full_name[:150],
                    is_active=status,
                )
                account.set_password(mobile_number)
                account.save()
                instance.must_change_password = True
            else:
                # Keep the tenant's login username synchronized with their email.
                account.username = username
                account.email = email
                account.first_name = full_name[:150]
                if password:
                    account.set_password(password)
                    instance.must_change_password = True
                account.save()

            instance.user = account
            instance.save(update_fields=['user', 'must_change_password', 'updated_at'])

            # Do not disable an account that still has another active staff role.
            has_other_role = (
                CompanyStaff.objects.filter(user=account, status=True, company__status=True).exists()
                or BuildingStaff.objects.filter(
                    user=account, status=True, building__status=True,
                    building__company__status=True, building__work_site__status=True
                ).exists()
            )
            if not account.is_superuser and not has_other_role and account.is_active != status:
                account.is_active = status
                account.save(update_fields=['is_active'])

    except ValidationError as exc:
        if hasattr(exc, 'messages'):
            non_field_errors.extend(exc.messages)
        else:
            non_field_errors.append(str(exc))
        return errors, non_field_errors
    except Exception as exc:
        # Unique DB constraint is the final protection against concurrent duplicate allocation.
        from django.db import IntegrityError
        if isinstance(exc, IntegrityError):
            non_field_errors.append('A selected unit was just allocated to another tenant. Refresh the form and select available units.')
            return errors, non_field_errors
        raise

    return {}, []

@login_required
def tenant_list(request):
    tenant_profile = getattr(request.user, 'tenant_profile', None)
    if tenant_profile and not request.user.is_superuser and not get_building_staff(request) and not get_user_company(request):
        return redirect('guest_visit_list')

    active_allocation_queryset = TenantUnitAllocation.objects.filter(
        released_at__isnull=True
    ).select_related('unit', 'unit__building', 'unit__floor', 'unit__company')
    queryset = Tenant.objects.select_related(
        'user', 'unit', 'unit__company', 'unit__work_site', 'unit__building', 'unit__floor'
    ).prefetch_related(
        Prefetch('unit_allocations', queryset=active_allocation_queryset, to_attr='active_unit_allocations')
    ).all()

    if not request.user.is_superuser:
        building_staff = get_building_staff(request)
        if building_staff:
            queryset = queryset.filter(
                Q(unit__building_id=building_staff.building_id)
                | Q(unit_allocations__released_at__isnull=True, unit_allocations__unit__building_id=building_staff.building_id)
            )
        else:
            company = get_user_company(request)
            queryset = queryset.filter(
                Q(unit__company=company) | Q(unit_allocations__released_at__isnull=True, unit_allocations__unit__company=company)
            )
    search = request.GET.get('search', '').strip()
    if search:
        queryset = queryset.filter(
            Q(full_name__icontains=search)
            | Q(mobile_number__icontains=search)
            | Q(email__icontains=search)
            | Q(address__icontains=search)
            | Q(identity_number__icontains=search)
            | Q(unit__name__icontains=search)
            | Q(unit__building__name__icontains=search)
            | Q(unit__company__name__icontains=search)
            | Q(unit__work_site__name__icontains=search)
            | Q(unit_allocations__released_at__isnull=True, unit_allocations__unit__name__icontains=search)
            | Q(unit_allocations__released_at__isnull=True, unit_allocations__unit__building__name__icontains=search)
            | Q(user__username__icontains=search)
        ).distinct()

    page_obj = Paginator(queryset.distinct().order_by(
        'unit__building__name', 'unit__name', 'full_name'
    ), 10).get_page(request.GET.get('page'))

    return render(request, 'operations/tenant/list.html', {
        'page_obj': page_obj,
        'search': search,
        'is_building_staff': is_building_staff(request),
        'is_superuser': request.user.is_superuser,
        'today': timezone.localdate(),
        'lease_soon_date': timezone.localdate() + timedelta(days=30),
    })


@login_required
def tenant_lease_list(request):
    """Show active rental tenants with expired or soon-to-expire leases."""
    tenant_profile = getattr(request.user, 'tenant_profile', None)
    if tenant_profile and not request.user.is_superuser and not get_building_staff(request) and not get_user_company(request):
        return redirect('guest_visit_list')

    today = timezone.localdate()
    soon_date = today + timedelta(days=30)
    active_allocation_queryset = TenantUnitAllocation.objects.filter(
        released_at__isnull=True
    ).select_related('unit', 'unit__building', 'unit__floor', 'unit__company')

    queryset = Tenant.objects.select_related(
        'user', 'unit', 'unit__company', 'unit__work_site', 'unit__building', 'unit__floor'
    ).prefetch_related(
        Prefetch('unit_allocations', queryset=active_allocation_queryset, to_attr='active_unit_allocations')
    ).filter(
        status=True, tenant_type='rental', lease_end_date__isnull=False,
        lease_end_date__lte=soon_date,
    )

    if not request.user.is_superuser:
        building_staff = get_building_staff(request)
        if building_staff:
            queryset = queryset.filter(
                Q(unit__building_id=building_staff.building_id)
                | Q(unit_allocations__released_at__isnull=True, unit_allocations__unit__building_id=building_staff.building_id)
            )
        else:
            company = get_user_company(request)
            queryset = queryset.filter(
                Q(unit__company=company)
                | Q(unit_allocations__released_at__isnull=True, unit_allocations__unit__company=company)
            )

    search = request.GET.get('search', '').strip()
    if search:
        queryset = queryset.filter(
            Q(full_name__icontains=search)
            | Q(mobile_number__icontains=search)
            | Q(email__icontains=search)
            | Q(unit__name__icontains=search)
            | Q(unit__building__name__icontains=search)
            | Q(unit_allocations__released_at__isnull=True, unit_allocations__unit__name__icontains=search)
            | Q(unit_allocations__released_at__isnull=True, unit_allocations__unit__building__name__icontains=search)
        )

    page_obj = Paginator(queryset.distinct().order_by('lease_end_date', 'full_name'), 10).get_page(
        request.GET.get('page')
    )
    return render(request, 'operations/tenant/list.html', {
        'page_obj': page_obj,
        'search': search,
        'is_building_staff': is_building_staff(request),
        'is_superuser': request.user.is_superuser,
        'today': today,
        'lease_soon_date': soon_date,
        'lease_list': True,
    })


@login_required
def tenant_create(request):
    # Working assumption: only the common Super Admin creates tenant accounts.
    if not request.user.is_superuser:
        messages.error(request, 'Only Super Admin can create tenant accounts.')
        return redirect('dashboard')

    company = get_user_company(request)

    instance = Tenant()
    units = _tenant_available_units(request)
    errors, non_field_errors = {}, []

    if request.method == 'POST':
        errors, non_field_errors = _save_tenant_post(request, instance, units)
        if not errors and not non_field_errors:
            messages.success(request, 'Tenant and login account created successfully.')
            return redirect('tenant_list')

    return render(
        request,
        'operations/tenant/form.html',
        _tenant_form_context(request, instance, units, errors, non_field_errors),
    )


@login_required
def tenant_edit(request, pk):
    if (
        not request.user.is_superuser
        and not get_building_staff(request)
        and not get_user_company(request)
    ):
        messages.error(request, 'You do not have permission to edit tenant records.')
        return redirect('dashboard')

    queryset = Tenant.objects.select_related('user', 'unit', 'unit__building', 'unit__company').prefetch_related(
        'unit_allocations__unit'
    )
    if not request.user.is_superuser:
        building_staff = get_building_staff(request)
        if building_staff:
            queryset = queryset.filter(
                Q(unit__building_id=building_staff.building_id)
                | Q(unit_allocations__unit__building_id=building_staff.building_id)
            ).distinct()
        else:
            company = get_user_company(request)
            queryset = queryset.filter(
                Q(unit__company=company) | Q(unit_allocations__unit__company=company)
            ).distinct()

    instance = get_object_or_404(queryset, pk=pk)
    units = _tenant_available_units(request, instance)
    errors, non_field_errors = {}, []

    if request.method == 'POST':
        errors, non_field_errors = _save_tenant_post(request, instance, units)
        if not errors and not non_field_errors:
            messages.success(request, 'Tenant details updated successfully.')
            return redirect('tenant_list')

    return render(
        request,
        'operations/tenant/form.html',
        _tenant_form_context(request, instance, units, errors, non_field_errors),
    )


@login_required
def tenant_delete(request, pk):
    if (
        not request.user.is_superuser
        and not get_building_staff(request)
        and not get_user_company(request)
    ):
        messages.error(request, 'You do not have permission to deactivate tenant records.')
        return redirect('dashboard')

    queryset = Tenant.objects.select_related('user', 'unit', 'unit__building', 'unit__company').prefetch_related(
        'unit_allocations__unit'
    )
    if not request.user.is_superuser:
        building_staff = get_building_staff(request)
        if building_staff:
            queryset = queryset.filter(
                Q(unit__building_id=building_staff.building_id)
                | Q(unit_allocations__unit__building_id=building_staff.building_id)
            ).distinct()
        else:
            queryset = queryset.filter(
                Q(unit__company=get_user_company(request))
                | Q(unit_allocations__unit__company=get_user_company(request))
            ).distinct()

    item = get_object_or_404(queryset, pk=pk)
    if request.method == 'POST':
        # Tenant deletion is intentionally a HARD DELETE.
        # All data that belongs to this tenant is removed, while master
        # data such as Company / Building / Unit / Country is preserved.
        with transaction.atomic():
            linked_user = item.user if item.user_id else None

            # HoldDocument uses SET_NULL when its GuestVisit is deleted.
            # Delete tenant-linked held documents explicitly so no orphaned
            # tenant guest documents remain.
            tenant_visits = GuestVisit.objects.filter(tenant=item)

            # Remove uploaded guest photos as well as their database rows.
            for photo_name in tenant_visits.exclude(
                guest_photo=''
            ).values_list('guest_photo', flat=True):
                if photo_name:
                    default_storage.delete(photo_name)

            HoldDocument.objects.filter(visit__in=tenant_visits).delete()

            # These related records use CASCADE and will be deleted with
            # the tenant, including:
            # - family members
            # - tenant staff members
            # - unit allocation records
            # - guest visits
            # - accompanying visitors
            # - ID tag issue records belonging to those visits
            item.delete()

            # Tenant.user is SET_NULL by model design, so remove the
            # dedicated tenant login explicitly after deleting the profile.
            # Do not delete a superuser account.
            if linked_user and not linked_user.is_superuser:
                has_other_role = (
                    CompanyStaff.objects.filter(user=linked_user).exists()
                    or BuildingStaff.objects.filter(user=linked_user).exists()
                )
                if not has_other_role:
                    linked_user.delete()

        messages.success(
            request,
            'Tenant and all data connected to this tenant were permanently deleted. Company, building, unit and master data were preserved.'
        )
    return redirect('tenant_list')


@login_required
def tenant_change_password(request):
    """Force newly created tenants to change their initial password."""
    tenant = getattr(request.user, 'tenant_profile', None)
    if tenant is None or not tenant.status:
        messages.error(request, 'An active tenant account is required to change this password.')
        return redirect('dashboard')

    if not tenant.must_change_password:
        return redirect('dashboard')

    errors = {}
    if request.method == 'POST':
        password = request.POST.get('new_password', '')
        confirmation = request.POST.get('confirm_password', '')
        if not password:
            errors['new_password'] = ['Enter a new password.']
        if not confirmation:
            errors['confirm_password'] = ['Confirm the new password.']
        elif password != confirmation:
            errors['confirm_password'] = ['Passwords do not match.']

        if password and password == confirmation:
            try:
                validate_password(password, user=request.user)
            except ValidationError as exc:
                errors['new_password'] = list(exc.messages)

        if not errors:
            request.user.set_password(password)
            request.user.save(update_fields=['password'])
            tenant.must_change_password = False
            tenant.save(update_fields=['must_change_password', 'updated_at'])
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Password changed successfully.')
            return redirect('dashboard')

    return render(request, 'operations/tenant/change_password.html', {'errors': errors})


# ============================================================
# TENANT FAMILY MEMBERS
# Tenant accounts can manage only their own family members.
# Super Admin, Company Staff and Building Staff can manage
# family members only for tenants within their authorized scope.
# ============================================================

def _family_tenant_for_request(request, tenant_pk=None):
    tenant_profile = getattr(request.user, 'tenant_profile', None)
    is_admin_role = (
        request.user.is_superuser
        or get_building_staff(request) is not None
        or CompanyStaff.objects.filter(
            user=request.user, status=True, company__status=True
        ).exists()
    )

    if tenant_profile and not is_admin_role:
        if tenant_pk is not None and tenant_pk != tenant_profile.pk:
            from django.http import Http404
            raise Http404
        if (
            not tenant_profile.status
            or not tenant_profile.unit_allocations.filter(
                released_at__isnull=True, unit__status=True, unit__building__status=True,
                unit__company__status=True, unit__work_site__status=True
            ).exists()
        ):
            from django.http import Http404
            raise Http404
        return tenant_profile, True

    if tenant_pk is None:
        return None, False

    tenants = Tenant.objects.select_related(
        'user', 'unit', 'unit__company', 'unit__building', 'unit__work_site'
    )
    tenants = _scope_queryset(request, tenants, company_field='unit__company')
    return get_object_or_404(tenants, pk=tenant_pk), False


def _tenant_member_units(tenant, member=None):
    """Only units currently allocated to this tenant may be selected."""
    unit_ids = tenant.unit_allocations.filter(
        released_at__isnull=True,
        unit__status=True,
        unit__building__status=True,
        unit__company__status=True,
        unit__work_site__status=True,
    ).values_list('unit_id', flat=True)
    return Unit.objects.select_related('building', 'floor', 'company').filter(
        pk__in=unit_ids
    ).order_by('building__name', 'floor__floor_number', 'name')


def _family_member_context(request, tenant, member, errors=None, non_field_errors=None, self_service=False):
    if request.method == 'POST':
        values = {
            'name': request.POST.get('name', ''),
            'mobile_number': request.POST.get('mobile_number', ''),
            'email': request.POST.get('email', ''),
            'address': request.POST.get('address', ''),
            'unit_id': request.POST.get('unit', ''),
        }
    else:
        values = {
            'name': member.name if member.pk else '',
            'mobile_number': member.mobile_number if member.pk else '',
            'email': member.email if member.pk and member.email else '',
            'address': member.address if member.pk else '',
            'unit_id': str(member.unit_id) if member.pk and member.unit_id else '',
        }

    units = _tenant_member_units(tenant, member)
    dial_code = get_tenant_company_dial_code(tenant)
    return {
        'tenant': tenant,
        'member': member,
        'values': values,
        'units': units,
        'dial_code': dial_code,
        'tenant_dial_code': dial_code,
        'errors': errors or {},
        'non_field_errors': non_field_errors or [],
        'self_service': self_service,
        'title': 'Edit Family Member' if member.pk else 'Add Family Member',
    }


def _save_family_member_post(request, tenant, member):
    errors, non_field_errors = {}, []
    name = request.POST.get('name', '').strip()
    mobile_number = request.POST.get('mobile_number', '').strip()
    email = request.POST.get('email', '').strip()
    address = request.POST.get('address', '').strip()
    unit = _related(Unit, request.POST.get('unit'), 'unit', errors, queryset=_tenant_member_units(tenant, member))

    if not name:
        errors['name'] = ['Family member name is required.']
    elif len(name) > 150:
        errors['name'] = ['Name must be 150 characters or fewer.']
    if not mobile_number:
        errors['mobile_number'] = ['Mobile number is required.']
    elif len(mobile_number) > 30:
        errors['mobile_number'] = ['Mobile number must be 30 characters or fewer.']
    if email and len(email) > 254:
        errors['email'] = ['Email must be 254 characters or fewer.']
    elif email:
        from django.core.validators import validate_email
        try:
            validate_email(email)
        except ValidationError:
            errors['email'] = ['Enter a valid email address.']
    if not address:
        errors['address'] = ['Address is required.']

    member.tenant = tenant
    member.name = name
    member.mobile_number = mobile_number
    member.email = email or None
    member.address = address
    member.unit = unit

    if not errors:
        try:
            member.full_clean()
        except ValidationError as exc:
            field_errors, non_field_errors = _validation_errors(exc)
            for field_name, field_messages in field_errors.items():
                errors.setdefault(field_name, []).extend(field_messages)

    if not errors and not non_field_errors:
        member.save()
        return {}, []
    return errors, non_field_errors


@login_required
def tenant_family_member_list(request, tenant_pk=None):
    tenant, self_service = _family_tenant_for_request(request, tenant_pk)
    if tenant is None:
        messages.error(request, 'Select a tenant to manage family members.')
        return redirect('tenant_list')

    queryset = tenant.family_members.all()
    search = request.GET.get('search', '').strip()
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(mobile_number__icontains=search)
            | Q(email__icontains=search)
            | Q(address__icontains=search)
        )

    # Group all family members by their assigned unit so members of the same
    # household/unit are displayed together (instead of splitting groups across pages).
    ordered_members = list(queryset.select_related(
        'unit', 'unit__building', 'unit__floor'
    ).order_by('unit__building__name', 'unit__floor__floor_number', 'unit__name', 'name'))
    grouped = {}
    for family_member in ordered_members:
        unit = family_member.unit
        if unit:
            unit_key = f'unit-{unit.pk}'
            unit_label = f"{unit.building.name}" + (f" · {unit.floor.name}" if unit.floor else '') + f" · {unit.name}"
        else:
            unit_key = 'unit-unassigned'
            unit_label = 'Unit not assigned'
        if unit_key not in grouped:
            grouped[unit_key] = {'key': unit_key, 'label': unit_label, 'unit': unit, 'members': []}
        grouped[unit_key]['members'].append(family_member)

    return render(request, 'operations/tenant/family_list.html', {
        'tenant': tenant,
        'unit_groups': list(grouped.values()),
        'family_member_count': len(ordered_members),
        'search': search,
        'self_service': self_service,
    })


@login_required
def tenant_family_member_create(request, tenant_pk=None):
    tenant, self_service = _family_tenant_for_request(request, tenant_pk)
    if tenant is None:
        messages.error(request, 'Select a tenant to add family members.')
        return redirect('tenant_list')

    member = TenantFamilyMember(tenant=tenant)
    errors, non_field_errors = {}, []
    if request.method == 'POST':
        errors, non_field_errors = _save_family_member_post(request, tenant, member)
        if not errors and not non_field_errors:
            messages.success(request, 'Family member added successfully.')
            return redirect('my_family_members' if self_service else 'tenant_family_member_list', **({} if self_service else {'tenant_pk': tenant.pk}))

    return render(request, 'operations/tenant/family_form.html', _family_member_context(
        request, tenant, member, errors, non_field_errors, self_service
    ))


@login_required
def tenant_family_member_edit(request, pk, tenant_pk=None):
    tenant, self_service = _family_tenant_for_request(request, tenant_pk)
    if tenant is None:
        messages.error(request, 'Select a tenant to edit family members.')
        return redirect('tenant_list')

    member = get_object_or_404(tenant.family_members.all(), pk=pk)
    errors, non_field_errors = {}, []
    if request.method == 'POST':
        errors, non_field_errors = _save_family_member_post(request, tenant, member)
        if not errors and not non_field_errors:
            messages.success(request, 'Family member updated successfully.')
            return redirect('my_family_members' if self_service else 'tenant_family_member_list', **({} if self_service else {'tenant_pk': tenant.pk}))

    return render(request, 'operations/tenant/family_form.html', _family_member_context(
        request, tenant, member, errors, non_field_errors, self_service
    ))


@login_required
def tenant_family_member_delete(request, pk, tenant_pk=None):
    tenant, self_service = _family_tenant_for_request(request, tenant_pk)
    if tenant is None:
        messages.error(request, 'Select a tenant to delete family members.')
        return redirect('tenant_list')

    member = get_object_or_404(tenant.family_members.all(), pk=pk)
    if request.method == 'POST':
        member.delete()
        messages.success(request, 'Family member deleted successfully.')

    return redirect('my_family_members' if self_service else 'tenant_family_member_list', **({} if self_service else {'tenant_pk': tenant.pk}))


# ============================================================
# TENANT STAFF MEMBERS
# Household/domestic staff details are managed from the tenant dashboard.
# ============================================================

def _tenant_staff_designation_names(tenant, member=None):
    """Return active admin-managed designation names available to this tenant.

    Global Designation records can be enabled for a company from the Company
    form. CompanyDesignation records are company-specific designation masters.
    """
    unit_queryset = _tenant_member_units(tenant, member)
    company_ids = list(unit_queryset.values_list('company_id', flat=True).distinct())
    names = set()

    global_designations = Designation.objects.filter(status=True)
    if company_ids:
        global_designations = global_designations.filter(
            Q(enabled_companies__id__in=company_ids) | Q(enabled_companies__isnull=True)
        )
    for name in global_designations.values_list('name', flat=True).distinct():
        names.add(name)

    if company_ids:
        for name in CompanyDesignation.objects.filter(
            company_id__in=company_ids, status=True, company__status=True
        ).values_list('name', flat=True).distinct():
            names.add(name)

    # Keep a previously saved designation visible on edit even if an admin has
    # since deactivated it; it cannot be newly selected for another record.
    if member and member.pk and member.designation:
        names.add(member.designation)
    return sorted(names, key=str.casefold)


def _staff_member_context(request, tenant, member, errors=None, non_field_errors=None, self_service=False):
    if request.method == 'POST':
        values = {
            'name': request.POST.get('name', ''),
            'designation': request.POST.get('designation', ''),
            'mobile_number': request.POST.get('mobile_number', ''),
            'email': request.POST.get('email', ''),
            'address': request.POST.get('address', ''),
            'unit_id': request.POST.get('unit', ''),
            'status': 'status' in request.POST,
        }
    else:
        values = {
            'name': member.name if member.pk else '',
            'designation': member.designation if member.pk else '',
            'mobile_number': member.mobile_number if member.pk else '',
            'email': member.email if member.pk and member.email else '',
            'address': member.address if member.pk else '',
            'unit_id': str(member.unit_id) if member.pk and member.unit_id else '',
            'status': member.status if member.pk else True,
        }
    units = _tenant_member_units(tenant, member)
    dial_code = get_tenant_company_dial_code(tenant)
    return {
        'tenant': tenant,
        'member': member,
        'values': values,
        'units': units,
        'dial_code': dial_code,
        'tenant_dial_code': dial_code,
        'designations': _tenant_staff_designation_names(tenant, member),
        'errors': errors or {},
        'non_field_errors': non_field_errors or [],
        'self_service': self_service,
        'title': 'Edit Staff Member' if member.pk else 'Add Staff Member',
    }


def _save_staff_member_post(request, tenant, member):
    errors, non_field_errors = {}, []
    name = request.POST.get('name', '').strip()
    designation = request.POST.get('designation', '').strip()
    mobile_number = request.POST.get('mobile_number', '').strip()
    email = request.POST.get('email', '').strip()
    address = request.POST.get('address', '').strip()
    status = 'status' in request.POST
    unit = _related(Unit, request.POST.get('unit'), 'unit', errors, queryset=_tenant_member_units(tenant, member))

    if not name:
        errors['name'] = ['Staff member name is required.']
    elif len(name) > 150:
        errors['name'] = ['Name must be 150 characters or fewer.']
    if len(designation) > 100:
        errors['designation'] = ['Designation must be 100 characters or fewer.']
    elif designation:
        allowed_designations = set(_tenant_staff_designation_names(tenant, member))
        if designation not in allowed_designations:
            errors['designation'] = ['Select a designation created and enabled by the administrator.']
    if not mobile_number:
        errors['mobile_number'] = ['Mobile number is required.']
    elif len(mobile_number) > 30:
        errors['mobile_number'] = ['Mobile number must be 30 characters or fewer.']
    if not address:
        errors['address'] = ['Address is required.']
    if email:
        from django.core.validators import validate_email
        try:
            validate_email(email)
        except ValidationError:
            errors['email'] = ['Enter a valid email address.']

    member.tenant = tenant
    member.name = name
    member.designation = designation
    member.mobile_number = mobile_number
    member.email = email or None
    member.address = address
    member.unit = unit
    member.status = status

    if not errors:
        try:
            member.full_clean()
        except ValidationError as exc:
            field_errors, non_field_errors = _validation_errors(exc)
            for field_name, field_messages in field_errors.items():
                errors.setdefault(field_name, []).extend(field_messages)

    if not errors and not non_field_errors:
        member.save()
        return {}, []
    return errors, non_field_errors


@login_required
def tenant_staff_member_list(request, tenant_pk=None):
    tenant, self_service = _family_tenant_for_request(request, tenant_pk)
    if tenant is None:
        messages.error(request, 'Select a tenant to manage staff members.')
        return redirect('tenant_list')

    queryset = tenant.staff_members.all()
    search = request.GET.get('search', '').strip()
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(designation__icontains=search)
            | Q(mobile_number__icontains=search)
            | Q(email__icontains=search)
            | Q(address__icontains=search)
        )
    page_obj = Paginator(queryset.order_by('name'), 10).get_page(request.GET.get('page'))
    return render(request, 'operations/tenant/staff_list.html', {
        'tenant': tenant, 'page_obj': page_obj, 'search': search, 'self_service': self_service,
    })


@login_required
def tenant_staff_member_create(request, tenant_pk=None):
    tenant, self_service = _family_tenant_for_request(request, tenant_pk)
    if tenant is None:
        messages.error(request, 'Select a tenant to add staff members.')
        return redirect('tenant_list')
    member = TenantStaffMember(tenant=tenant)
    errors, non_field_errors = {}, []
    if request.method == 'POST':
        errors, non_field_errors = _save_staff_member_post(request, tenant, member)
        if not errors and not non_field_errors:
            messages.success(request, 'Staff member added successfully.')
            return redirect('my_staff_members' if self_service else 'tenant_staff_member_list', **({} if self_service else {'tenant_pk': tenant.pk}))
    return render(request, 'operations/tenant/staff_form.html', _staff_member_context(
        request, tenant, member, errors, non_field_errors, self_service
    ))


@login_required
def tenant_staff_member_edit(request, pk, tenant_pk=None):
    tenant, self_service = _family_tenant_for_request(request, tenant_pk)
    if tenant is None:
        messages.error(request, 'Select a tenant to edit staff members.')
        return redirect('tenant_list')
    member = get_object_or_404(tenant.staff_members.all(), pk=pk)
    errors, non_field_errors = {}, []
    if request.method == 'POST':
        errors, non_field_errors = _save_staff_member_post(request, tenant, member)
        if not errors and not non_field_errors:
            messages.success(request, 'Staff member updated successfully.')
            return redirect('my_staff_members' if self_service else 'tenant_staff_member_list', **({} if self_service else {'tenant_pk': tenant.pk}))
    return render(request, 'operations/tenant/staff_form.html', _staff_member_context(
        request, tenant, member, errors, non_field_errors, self_service
    ))


@login_required
def tenant_staff_member_delete(request, pk, tenant_pk=None):
    tenant, self_service = _family_tenant_for_request(request, tenant_pk)
    if tenant is None:
        messages.error(request, 'Select a tenant to delete staff members.')
        return redirect('tenant_list')
    member = get_object_or_404(tenant.staff_members.all(), pk=pk)
    if request.method == 'POST':
        member.delete()
        messages.success(request, 'Staff member record deleted successfully.')
    return redirect('my_staff_members' if self_service else 'tenant_staff_member_list', **({} if self_service else {'tenant_pk': tenant.pk}))



# ============================================================
# GUEST / VISITOR VISITS AND GATE PASSES
# ============================================================

def _guest_visit_tenant_queryset(request):
    queryset = Tenant.objects.select_related(
        'user', 'unit', 'unit__company', 'unit__building', 'unit__work_site'
    ).prefetch_related(Prefetch(
        'unit_allocations',
        queryset=TenantUnitAllocation.objects.filter(released_at__isnull=True).select_related('unit', 'unit__building'),
        to_attr='active_unit_allocations',
    ))

    tenant_profile = getattr(request.user, 'tenant_profile', None)
    unit_profile = Unit.objects.filter(user=request.user, status=True).first()
    is_staff_role = (
        request.user.is_superuser
        or get_building_staff(request) is not None
        or CompanyStaff.objects.filter(
            user=request.user, status=True, company__status=True
        ).exists()
    )

    if tenant_profile and not is_staff_role:
        return queryset.filter(pk=tenant_profile.pk, status=True)

    unit_profile = Unit.objects.filter(user=request.user, status=True).first()
    if unit_profile and not is_staff_role:
        return queryset.filter(status=True, unit_allocations__unit=unit_profile, unit_allocations__released_at__isnull=True).distinct()

    if request.user.is_superuser:
        return queryset.filter(status=True)

    building_staff = get_building_staff(request)
    if building_staff:
        return queryset.filter(
            status=True
        ).filter(
            Q(unit__building_id=building_staff.building_id)
            | Q(unit_allocations__released_at__isnull=True, unit_allocations__unit__building_id=building_staff.building_id)
        ).distinct()

    company = get_user_company(request)
    if company:
        return queryset.filter(
            status=True
        ).filter(
            Q(unit__company=company)
            | Q(unit_allocations__released_at__isnull=True, unit_allocations__unit__company=company)
        ).distinct()

    return queryset.none()



@login_required
def guest_visit_list(request):
    tenant_profile = getattr(request.user, 'tenant_profile', None)
    is_staff_role = (
        request.user.is_superuser
        or get_building_staff(request) is not None
        or CompanyStaff.objects.filter(
            user=request.user, status=True, company__status=True
        ).exists()
    )
    unit_profile = Unit.objects.filter(user=request.user, status=True).first()
    is_tenant_self_service = bool(tenant_profile and not is_staff_role)
    is_unit_self_service = bool(unit_profile and not is_staff_role)
    visits = GuestVisit.objects.select_related(
        'tenant', 'tenant__user', 'unit', 'unit__building', 'unit__company',
        'purpose_of_visit', 'created_by', 'checked_in_by', 'checked_out_by',
    ).prefetch_related(
        'accompanying_people',
        Prefetch('tag_issues', queryset=IDTagIssue.objects.filter(status=IDTagIssue.STATUS_ISSUED).select_related('tag'), to_attr='active_tag_issues'),
    )

    if is_tenant_self_service:
        if not tenant_profile.status:
            return HttpResponseForbidden('Your tenant account is inactive.')
        visits = visits.filter(tenant=tenant_profile)
    elif is_unit_self_service:
        visits = visits.filter(unit=unit_profile)
    else:
        scoped_tenants = _guest_visit_tenant_queryset(request).values_list('pk', flat=True)
        visits = visits.filter(tenant_id__in=scoped_tenants)

    search = request.GET.get('search', '').strip()
    if search:
        visits = visits.filter(
            Q(guest_name__icontains=search)
            | Q(guest_mobile_number__icontains=search)
            | Q(tenant__full_name__icontains=search)
            | Q(purpose_of_visit__name__icontains=search)
            | Q(gate_pass_code__icontains=search)
            | Q(vehicle_details__icontains=search)
            | Q(accompanying_people__name__icontains=search)
            | Q(accompanying_people__mobile_number__icontains=search)
        ).distinct()

    page_obj = Paginator(visits.order_by('-visit_date', '-created_at'), 10).get_page(
        request.GET.get('page')
    )
    return render(request, 'operations/guest_visit/list.html', {
        'page_obj': page_obj,
        'search': search,
        'is_tenant_self_service': is_tenant_self_service,
        'is_unit_self_service': is_unit_self_service,
        'is_staff_role': is_staff_role,
        'can_manage_checkin': bool(is_staff_role or is_tenant_self_service),
        'can_create_visit': bool(is_staff_role or is_tenant_self_service or is_unit_self_service),
        'can_approve_visits': bool(is_tenant_self_service or request.user.is_superuser),
        'can_accept_unit_requests': bool(is_unit_self_service or request.user.is_superuser),
        'today': timezone.localdate(),
    })


@login_required
def guest_visit_camera(request):
    """Standalone same-origin camera page used by the Guest Visit form."""
    return render(request, 'operations/guest_visit/camera.html')


@login_required
def guest_visit_create(request):
    tenant_profile = getattr(request.user, 'tenant_profile', None)
    is_staff_role = (
        request.user.is_superuser
        or get_building_staff(request) is not None
        or CompanyStaff.objects.filter(user=request.user, status=True, company__status=True).exists()
    )
    unit_profile = Unit.objects.filter(user=request.user, status=True).first()
    is_tenant_self_service = bool(tenant_profile and not is_staff_role)
    is_unit_self_service = bool(unit_profile and not is_staff_role)
    if is_tenant_self_service and not tenant_profile.status:
        return HttpResponseForbidden('Your tenant account is inactive.')
    if not is_staff_role and not is_tenant_self_service and not is_unit_self_service:
        messages.error(request, 'You do not have permission to register a guest visit.')
        return redirect('guest_visit_list')

    tenants = _guest_visit_tenant_queryset(request).order_by('full_name')
    purposes = PurposeOfVisit.objects.filter(status=True).order_by('name')
    errors, non_field_errors = {}, []
    accompanying_names = request.POST.getlist('accompanying_name') if request.method == 'POST' else ['']
    accompanying_mobiles = request.POST.getlist('accompanying_mobile') if request.method == 'POST' else ['']
    count = max(len(accompanying_names), len(accompanying_mobiles), 1)
    accompanying_rows = [
        {'name': accompanying_names[i] if i < len(accompanying_names) else '',
         'mobile': accompanying_mobiles[i] if i < len(accompanying_mobiles) else ''}
        for i in range(count)
    ]
    values = {
        'tenant': request.POST.get('tenant', ''),
        'guest_name': request.POST.get('guest_name', ''),
        'guest_mobile_number': request.POST.get('guest_mobile_number', ''),
        'additional_visitors': request.POST.get('additional_visitors', '0'),
        'visitor_id_card_number': request.POST.get('visitor_id_card_number', '').strip(),
        'purpose_of_visit': request.POST.get('purpose_of_visit', ''),
        'unit': request.POST.get('unit', ''),
        'building': request.POST.get('building', ''),
        'visit_type': request.POST.get('visit_type', GuestVisit.TYPE_ADVANCE),
        'vehicle_details': request.POST.get('vehicle_details', ''),
        'visit_date': request.POST.get('visit_date', timezone.localdate().isoformat()),
        'visit_time': request.POST.get('visit_time', ''),
        'notes': request.POST.get('notes', ''),
    }

    if request.method == 'POST':
        if is_tenant_self_service:
            tenant = tenant_profile
            values['tenant'] = str(tenant.pk)
        else:
            tenant = _related(Tenant, values['tenant'], 'tenant', errors, queryset=tenants)

        if values['visit_type'] not in {GuestVisit.TYPE_ADVANCE, GuestVisit.TYPE_WALK_IN}:
            errors['visit_type'] = ['Select a valid visit type.']
        if is_unit_self_service and values['visit_type'] != GuestVisit.TYPE_ADVANCE:
            errors['visit_type'] = ['Unit accounts can create Advance Guest Visit requests only.']
        if is_tenant_self_service and values['visit_type'] != GuestVisit.TYPE_WALK_IN:
            errors['visit_type'] = ['Tenant accounts can create Walk-in requests from this screen.']

        purpose = _related(PurposeOfVisit, values['purpose_of_visit'], 'purpose_of_visit', errors, queryset=purposes)
        unit = None
        building = None
        if tenant:
            tenant_units = Unit.objects.filter(
                tenant_allocations__tenant=tenant,
                tenant_allocations__released_at__isnull=True,
                status=True,
            ).distinct()
            if is_unit_self_service:
                tenant_units = tenant_units.filter(pk=unit_profile.pk)
            building_staff = get_building_staff(request)
            if building_staff:
                tenant_units = tenant_units.filter(building_id=building_staff.building_id)
            elif not request.user.is_superuser:
                company = get_user_company(request)
                if company:
                    tenant_units = tenant_units.filter(company=company)
            allowed_buildings = Building.objects.filter(pk__in=tenant_units.values_list('building_id', flat=True), status=True)
            building = _related(Building, values['building'], 'building', errors, queryset=allowed_buildings)
            unit = _related(Unit, values['unit'], 'unit', errors, queryset=tenant_units)
            if unit and building and unit.building_id != building.pk:
                errors['unit'] = ['Select a unit within the selected building.']
        elif values['unit'] or values['building']:
            errors['unit'] = ['Select a valid tenant before selecting a building or unit.']

        guest_name = values['guest_name'].strip()
        if not guest_name:
            errors['guest_name'] = ['Guest name is required.']
        elif len(guest_name) > 150:
            errors['guest_name'] = ['Guest name must be 150 characters or fewer.']
        # Verification ID details are collected by security at check-in,
        # not when the guest visit is first registered. Keep this legacy
        # field optional at creation time.
        visitor_card_number = values['visitor_id_card_number'].strip()
        if len(visitor_card_number) > 80:
            errors['visitor_id_card_number'] = ['Visitor ID Card Number must be 80 characters or fewer.']
        guest_mobile_number = values['guest_mobile_number'].strip()
        if not guest_mobile_number:
            errors['guest_mobile_number'] = ['Guest mobile number is required.']
        elif len(guest_mobile_number) > 30:
            errors['guest_mobile_number'] = ['Guest mobile number must be 30 characters or fewer.']
        try:
            additional_visitors = int(values['additional_visitors'] or 0)
            if additional_visitors < 0 or additional_visitors > 100:
                raise ValueError
        except (TypeError, ValueError):
            additional_visitors = 0
            errors['additional_visitors'] = ['Enter a number from 0 to 100.']

        visit_date = parse_date(values['visit_date']) if values['visit_date'] else None
        if not visit_date:
            errors['visit_date'] = ['Enter a valid visit date.']
        visit_time = None
        if values['visit_time']:
            from django.utils.dateparse import parse_time
            visit_time = parse_time(values['visit_time'])
            if visit_time is None:
                errors['visit_time'] = ['Enter a valid visit time.']

        valid_companions = []
        for index, row in enumerate(accompanying_rows, start=1):
            name, mobile = row['name'].strip(), row['mobile'].strip()
            if not name and not mobile:
                continue
            if not name or not mobile:
                errors.setdefault('accompanying_people', []).append(
                    f'Accompanying person {index}: enter both name and mobile number.'
                )
                continue
            if len(name) > 150 or len(mobile) > 30:
                errors.setdefault('accompanying_people', []).append(
                    f'Accompanying person {index}: name must be 150 characters or fewer and mobile 30 characters or fewer.'
                )
                continue
            valid_companions.append((name, mobile))

        if len(values['vehicle_details'].strip()) > 150:
            errors['vehicle_details'] = ['Vehicle details must be 150 characters or fewer.']

        if not errors and tenant and purpose and unit:
            # Advance requests originate from the Unit and await Tenant approval.
            # Walk-in requests originate from the Tenant and await Unit acceptance,
            # followed by Tenant approval before a Gate Pass can be generated.
            auto_approve_walk_in = False
            gate_pass_code = None
            approved_at = None
            status = GuestVisit.STATUS_PENDING

            if not non_field_errors:
                guest_photo = request.FILES.get('guest_photo')
                webcam_photo = request.POST.get('webcam_photo', '').strip()
                if webcam_photo:
                    try:
                        header, encoded = webcam_photo.split(',', 1)
                        raw_photo = base64.b64decode(encoded, validate=True)
                        if not raw_photo:
                            raise ValueError('empty image')
                        guest_photo = ContentFile(raw_photo, name=f'webcam_{secrets.token_hex(8)}.jpg')
                    except (ValueError, binascii.Error):
                        errors['guest_photo'] = ['The webcam photo could not be read. Please capture it again.']

                visit = GuestVisit(
                    tenant=tenant,
                    unit=unit,
                    guest_name=guest_name,
                    guest_photo=guest_photo,
                    guest_mobile_number=guest_mobile_number,
                    additional_visitors=additional_visitors,
                    visitor_id_card_number=values['visitor_id_card_number'],
                    visit_type=values['visit_type'],
                    vehicle_details=values['vehicle_details'].strip(),
                    purpose_of_visit=purpose,
                    visit_date=visit_date,
                    visit_time=visit_time,
                    notes=values['notes'].strip(),
                    status=status,
                    unit_approval_status=(GuestVisit.STATUS_APPROVED if is_unit_self_service and values['visit_type'] == GuestVisit.TYPE_ADVANCE else GuestVisit.STATUS_PENDING),
                    tenant_approval_status=(GuestVisit.STATUS_PENDING),
                    approved_at=approved_at,
                    gate_pass_code=gate_pass_code,
                    created_by=request.user,
                )
                try:
                    visit.full_clean()
                    visit.save()
                    GuestVisitAccompanyingPerson.objects.bulk_create([
                        GuestVisitAccompanyingPerson(guest_visit=visit, name=name, mobile_number=mobile)
                        for name, mobile in valid_companions
                    ])
                    if is_unit_self_service:
                        messages.success(request, 'Advance guest request sent to the Tenant for approval. Gate Pass will be created only after Tenant approval.')
                    else:
                        messages.success(request, 'Walk-in request sent to the Unit. The Unit must accept it before Tenant approval and Gate Pass generation.')
                    return redirect('guest_visit_list')
                except ValidationError as exc:
                    field_errors, general_errors = _validation_errors(exc)
                    errors.update(field_errors)
                    non_field_errors.extend(general_errors)

    allocated_buildings = []
    seen_building_ids = set()
    building_staff_for_form = get_building_staff(request)
    company_for_form = get_user_company(request) if not request.user.is_superuser and not building_staff_for_form else None
    for tenant_item in tenants:
        for allocation in tenant_item.active_unit_allocations:
            building = allocation.unit.building
            if building_staff_for_form and building.pk != building_staff_for_form.building_id:
                continue
            if company_for_form and allocation.unit.company_id != company_for_form.pk:
                continue
            if not building.status or not allocation.unit.status:
                continue
            key = (tenant_item.pk, building.pk)
            if key not in seen_building_ids:
                allocated_buildings.append({'id': building.pk, 'name': building.name, 'tenant_id': tenant_item.pk})
                seen_building_ids.add(key)

    return render(request, 'operations/guest_visit/form.html', {
        'title': 'Plan Guest Visit' if is_tenant_self_service else 'Register Guest Visit',
        'tenants': tenants,
        'allocated_buildings': allocated_buildings,
        'is_tenant_self_service': is_tenant_self_service,
        'is_staff_role': is_staff_role,
        'self_service_tenant': tenant_profile if is_tenant_self_service else None,
        'purposes': purposes,
        'values': values,
        'errors': errors,
        'non_field_errors': non_field_errors,
        'accompanying_rows': accompanying_rows,
    })


def _get_authorized_guest_visit(request, pk):
    visit = get_object_or_404(
        GuestVisit.objects.select_related('tenant', 'tenant__user', 'tenant__unit__company', 'unit', 'unit__building', 'unit__company'),
        pk=pk,
    )
    tenant_profile = getattr(request.user, 'tenant_profile', None)
    unit_profile = Unit.objects.filter(user=request.user, status=True).first()
    is_staff_role = (
        request.user.is_superuser
        or get_building_staff(request) is not None
        or CompanyStaff.objects.filter(
            user=request.user, status=True, company__status=True
        ).exists()
    )

    if tenant_profile and not is_staff_role:
        if not tenant_profile.status:
            raise PermissionDenied('Your tenant account is inactive.')
        if visit.tenant_id != tenant_profile.pk:
            from django.http import Http404
            raise Http404
        return visit, True

    if unit_profile and not is_staff_role:
        if visit.unit_id != unit_profile.pk:
            from django.http import Http404
            raise Http404
        return visit, False

    if request.user.is_superuser:
        return visit, False

    building_staff = get_building_staff(request)
    if building_staff and visit.unit.building_id != building_staff.building_id:
        from django.http import Http404
        raise Http404
    company = get_user_company(request)
    if not request.user.is_superuser and not building_staff and company and visit.unit.company_id != company.pk:
        from django.http import Http404
        raise Http404
    if not _guest_visit_tenant_queryset(request).filter(pk=visit.tenant_id).exists():
        from django.http import Http404
        raise Http404
    return visit, False


@login_required
def guest_visit_approve(request, pk):
    visit, self_service = _get_authorized_guest_visit(request, pk)
    if request.method != 'POST':
        return redirect('guest_visit_list')

    tenant_profile = getattr(request.user, 'tenant_profile', None)
    if not self_service and not request.user.is_superuser:
        messages.error(request, 'Only the assigned tenant or Super Admin can approve this visit.')
        return redirect('guest_visit_list')
    if self_service and (not tenant_profile or visit.tenant_id != tenant_profile.pk):
        return HttpResponseForbidden('You cannot approve this visit.')

    if visit.status != GuestVisit.STATUS_PENDING:
        messages.warning(request, 'This visit has already been processed.')
        return redirect('guest_visit_list')
    if visit.unit_approval_status != GuestVisit.STATUS_APPROVED:
        messages.error(request, 'The Unit must accept this walk-in request before Tenant approval.')
        return redirect('guest_visit_list')

    with transaction.atomic():
        visit = GuestVisit.objects.select_for_update().get(pk=visit.pk)
        if visit.status != GuestVisit.STATUS_PENDING:
            messages.warning(request, 'This visit has already been processed.')
            return redirect('guest_visit_list')
        visit.tenant_approval_status = GuestVisit.STATUS_APPROVED
        visit.status = GuestVisit.STATUS_APPROVED
        visit.approved_at = timezone.now()
        # The Gate Pass code is also the unique Entry / Visitor Number.
        # The printed QR must contain this exact value (not a URL).
        # Format: ENT-YYYYMMDD-XXXXXX
        for _ in range(10):
            suffix = secrets.token_hex(3).upper()
            code = f"ENT-{timezone.localdate():%Y%m%d}-{suffix}"
            if not GuestVisit.objects.filter(gate_pass_code=code).exists():
                visit.gate_pass_code = code
                break
        if not visit.gate_pass_code:
            messages.error(request, 'Could not generate a Gate Pass. Please retry.')
            return redirect('guest_visit_list')
        visit.save(update_fields=['status', 'tenant_approval_status', 'approved_at', 'gate_pass_code', 'updated_at'])

    messages.success(request, 'Guest visit approved and Gate Pass generated.')
    return redirect('guest_visit_gate_pass', pk=visit.pk)


@login_required
def guest_visit_unit_accept(request, pk):
    visit, _ = _get_authorized_guest_visit(request, pk)
    unit_profile = Unit.objects.filter(user=request.user, status=True).first()
    if request.method != 'POST':
        return redirect('guest_visit_list')
    if not (request.user.is_superuser or (unit_profile and unit_profile.pk == visit.unit_id)):
        return HttpResponseForbidden('Only the requested Unit can accept this walk-in request.')
    if visit.visit_type != GuestVisit.TYPE_WALK_IN or visit.status != GuestVisit.STATUS_PENDING:
        messages.error(request, 'Only pending walk-in requests can be accepted by the Unit.')
        return redirect('guest_visit_list')
    visit.unit_approval_status = GuestVisit.STATUS_APPROVED
    visit.save(update_fields=['unit_approval_status', 'updated_at'])
    messages.success(request, 'Walk-in request accepted. It is now waiting for Tenant approval.')
    return redirect('guest_visit_list')


@login_required
def guest_visit_deny(request, pk):
    visit, self_service = _get_authorized_guest_visit(request, pk)
    if request.method != 'POST':
        return redirect('guest_visit_list')

    tenant_profile = getattr(request.user, 'tenant_profile', None)
    if not self_service and not request.user.is_superuser:
        messages.error(request, 'Only the assigned tenant or Super Admin can deny this visit.')
        return redirect('guest_visit_list')
    if self_service and (not tenant_profile or visit.tenant_id != tenant_profile.pk):
        return HttpResponseForbidden('You cannot deny this visit.')

    if visit.status != GuestVisit.STATUS_PENDING:
        messages.warning(request, 'This visit has already been processed.')
        return redirect('guest_visit_list')

    visit.status = GuestVisit.STATUS_DENIED
    visit.tenant_approval_status = GuestVisit.STATUS_DENIED
    visit.gate_pass_code = None
    visit.approved_at = None
    visit.save(update_fields=['status', 'tenant_approval_status', 'gate_pass_code', 'approved_at', 'updated_at'])
    messages.success(request, 'Guest visit denied.')
    return redirect('guest_visit_list')


@login_required
def guest_visit_gate_pass(request, pk):
    visit, self_service = _get_authorized_guest_visit(request, pk)
    if visit.status != GuestVisit.STATUS_APPROVED or not visit.gate_pass_code:
        messages.error(request, 'A Gate Pass is available only after the visit is approved.')
        return redirect('guest_visit_list')
    # QR opens the verification page directly. The Entry / Visitor Number
    # remains the lookup key used by the verification endpoint.
    qr_data = request.build_absolute_uri(
        reverse('gate_pass_scan', kwargs={'code': visit.gate_pass_code})
    )
    qr_code_data = ''
    try:
        import qrcode
        import io
        qr = qrcode.QRCode(version=1, box_size=6, border=3)
        qr.add_data(qr_data)
        qr.make(fit=True)
        image = qr.make_image()
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        qr_code_data = base64.b64encode(buffer.getvalue()).decode('ascii')
    except Exception:
        pass
    # Gate passes must not expose the full verification document number.
    # Keep the full number available in authorized reports, but show only the
    # last four characters on the printable/shareable gate pass.
    raw_id_number = (visit.id_number or '').strip()
    masked_id_number = (
        ('*' * max(len(raw_id_number) - 4, 0)) + raw_id_number[-4:]
        if raw_id_number else ''
    )
    return render(request, 'operations/guest_visit/gate_pass.html', {
        'visit': visit,
        'qr_code_data': qr_code_data,
        'qr_scan_url': qr_data,
        'masked_id_number': masked_id_number,
    })


def gate_pass_scan(request, code):
    visit = get_object_or_404(
        GuestVisit.objects.select_related(
            'tenant', 'unit', 'unit__building', 'unit__company', 'purpose_of_visit'
        ),
        gate_pass_code=code, status=GuestVisit.STATUS_APPROVED,
    )
    return render(request, 'operations/guest_visit/gate_pass_scan.html', {'visit': visit})

@login_required
def guest_visit_check_in(request, pk):
    if request.method != 'POST':
        return redirect('guest_visit_list')

    visit, self_service = _get_authorized_guest_visit(request, pk)
    is_staff_role = (
        request.user.is_superuser
        or get_building_staff(request) is not None
        or CompanyStaff.objects.filter(
            user=request.user, status=True, company__status=True
        ).exists()
    )
    if not (is_staff_role or self_service):
        return HttpResponseForbidden('You do not have permission to check this guest in.')

    id_type = request.POST.get('id_type', '').strip()
    id_number = request.POST.get('id_number', '').strip()
    valid_id_types = {choice[0] for choice in GuestVisit.ID_TYPE_CHOICES}

    if visit.status != GuestVisit.STATUS_APPROVED:
        messages.error(request, 'Only an approved visit can be checked in.')
        return redirect('guest_visit_list')

    if visit.checked_in_at:
        messages.warning(request, 'This guest has already been checked in.')
        return redirect('guest_visit_list')

    if id_type not in valid_id_types or not id_number:
        messages.error(request, 'Select the guest ID type and enter the ID number before check-in.')
        return redirect('guest_visit_list')

    with transaction.atomic():
        # Lock the visit while allocating its single security tag. This also
        # prevents repeated/concurrent submissions from creating multiple issues.
        locked_visit = GuestVisit.objects.select_for_update().select_related(
            'unit', 'unit__building'
        ).get(pk=visit.pk)

        existing_issue = locked_visit.tag_issues.filter(
            status=IDTagIssue.STATUS_ISSUED
        ).select_related('tag').first()
        if existing_issue:
            messages.warning(
                request,
                f'This visit already has active ID tag {existing_issue.tag.tag_number}.'
            )
            return redirect('guest_visit_list')

        now = timezone.now()
        locked_visit.checked_in_at = now
        locked_visit.checked_in_by = request.user
        locked_visit.id_type = id_type
        locked_visit.id_number = id_number
        locked_visit.id_received_at = now
        locked_visit.id_received_by = request.user
        locked_visit.save(update_fields=[
            'checked_in_at', 'checked_in_by', 'id_type', 'id_number',
            'id_received_at', 'id_received_by', 'updated_at',
        ])

        # Business rule: exactly ONE security ID tag per Guest Visit,
        # regardless of additional visitors.
        tag = (
            IDTag.objects.select_for_update()
            .filter(
                building=locked_visit.unit.building,
                status__in=[IDTag.STATUS_AVAILABLE, IDTag.STATUS_RETURNED],
            )
            .order_by('tag_number')
            .first()
        )

        # Dynamic cards can be generated when no registered tag is available.
        if tag is None:
            for _ in range(20):
                candidate = f'DYN-{secrets.token_hex(4).upper()}'
                if not IDTag.objects.filter(tag_number=candidate).exists():
                    tag = IDTag.objects.create(
                        tag_number=candidate,
                        tag_type=IDTag.TYPE_DYNAMIC,
                        building=locked_visit.unit.building,
                        status=IDTag.STATUS_AVAILABLE,
                    )
                    break

        if tag is None:
            # Keep the check-in record, but make the operational failure clear.
            messages.warning(
                request,
                'Check-in recorded, but no ID tag could be allocated. Please assign a tag before checkout.'
            )
        else:
            tag.status = IDTag.STATUS_ISSUED
            tag.save(update_fields=['status', 'updated_at'])
            IDTagIssue.objects.create(
                visit=locked_visit,
                tag=tag,
                issued_by=request.user,
            )
            messages.success(
                request,
                f'Guest check-in recorded. One ID tag issued: {tag.tag_number}.'
            )

    return redirect('guest_visit_list')


@login_required
def guest_visit_check_out(request, pk):
    if request.method != 'POST':
        return redirect('guest_visit_list')
    visit, self_service = _get_authorized_guest_visit(request, pk)
    is_staff_role = (
        request.user.is_superuser
        or get_building_staff(request) is not None
        or CompanyStaff.objects.filter(user=request.user, status=True, company__status=True).exists()
    )
    # Tenant users may record check-out for their own guest visits; staff remain scoped by _get_authorized_guest_visit.
    if not (is_staff_role or self_service):
        return HttpResponseForbidden('You do not have permission to check this guest out.')
    if not visit.checked_in_at:
        messages.error(request, 'Check-in must be recorded before check-out.')
    elif visit.checked_out_at:
        messages.warning(request, 'This guest has already been checked out.')
    elif visit.id_received_at and not visit.id_returned_at:
        messages.error(request, 'Return the original ID first, then return all issued ID tags before checkout.')
    else:
        # Lock the visit for the final checkout write. This prevents a stale
        # browser/report page or a repeated click from leaving the visit in an
        # apparently active state. Re-check all checkout prerequisites against
        # the locked database row.
        with transaction.atomic():
            locked_visit = (
                GuestVisit.objects
                .select_for_update()
                .get(pk=visit.pk)
            )

            if locked_visit.checked_out_at:
                messages.warning(request, 'This guest has already been checked out.')
                return redirect('guest_visit_list')

            outstanding = list(
                locked_visit.tag_issues
                .filter(status=IDTagIssue.STATUS_ISSUED)
                .select_related('tag')
            )
            if outstanding:
                messages.error(
                    request,
                    'Return all issued ID tags before checking out: '
                    + ', '.join(x.tag.tag_number for x in outstanding)
                )
                return redirect('guest_visit_list')

            now = timezone.now()

            # Persist checkout with a direct queryset UPDATE on the locked row.
            # This is intentionally used instead of model.save(): the report reads
            # GuestVisit.checked_out_at directly, so the timestamp must be written
            # to the database row that was just locked.
            updated_count = GuestVisit.objects.filter(pk=locked_visit.pk).update(
                checked_out_at=now,
                checked_out_by=request.user,
                updated_at=now,
            )

            # Re-read the row from the database before confirming success.  If the
            # database did not actually contain the timestamp, do not claim that
            # checkout succeeded.
            saved_checkout = (
                GuestVisit.objects
                .filter(pk=locked_visit.pk)
                .values_list('checked_out_at', flat=True)
                .first()
            )
            if updated_count != 1 or not saved_checkout:
                messages.error(
                    request,
                    'Checkout could not be recorded. Please try again.'
                )
                return redirect('guest_visit_list')

        messages.success(
            request,
            f'Guest checked out successfully at {timezone.localtime(now).strftime("%d-%m-%Y %I:%M %p")}.'
        )
    return redirect('guest_visit_list')


@login_required
def guest_visit_id_return(request, pk):
    """Record the physical return of the guest's original ID before checkout."""
    if request.method != 'POST':
        return redirect('guest_visit_list')

    visit, self_service = _get_authorized_guest_visit(request, pk)
    tenant_profile = getattr(request.user, 'tenant_profile', None)
    # Only the assigned Tenant can record the physical return from the Guest Visit page.
    # Super Admin / Company Staff / Building Staff do not get a return action here.
    if not tenant_profile or not tenant_profile.status or visit.tenant_id != tenant_profile.pk:
        return HttpResponseForbidden('Only the assigned tenant can record the original ID return.')

    if not visit.id_received_at:
        messages.error(request, 'The guest original ID has not been received by Security.')
        return redirect('guest_visit_list')
    if visit.id_returned_at:
        messages.warning(request, 'The guest original ID has already been returned.')
        return redirect('guest_visit_list')

    now = timezone.now()
    visit.id_returned_at = now
    visit.id_returned_by = request.user
    visit.save(update_fields=['id_returned_at', 'id_returned_by', 'updated_at'])
    messages.success(request, f'Original ID {visit.id_number} return recorded.')
    return redirect('guest_visit_list')


# ============================================================
# ID CARD / NFC TAG MASTER
# ============================================================

@login_required
def id_tag_master_list(request):
    """Super Admin master for Dynamic ID Cards and predefined NFC/ID tags."""
    if not request.user.is_superuser:
        return HttpResponseForbidden('Only Super Admin can manage ID Card / NFC Tag master data.')

    tags = IDTag.objects.select_related('building', 'building__company').all()
    query = request.GET.get('q', '').strip()
    tag_type = request.GET.get('tag_type', '').strip()
    status = request.GET.get('status', '').strip()

    if query:
        tags = tags.filter(
            Q(tag_number__icontains=query)
            | Q(nfc_number__icontains=query)
            | Q(building__name__icontains=query)
        )
    if tag_type in {IDTag.TYPE_DYNAMIC, IDTag.TYPE_PREDEFINED}:
        tags = tags.filter(tag_type=tag_type)
    if status in dict(IDTag.STATUS_CHOICES):
        tags = tags.filter(status=status)

    return render(request, 'master/id_tag/list.html', {
        'tags': tags,
        'query': query,
        'tag_type': tag_type,
        'status': status,
        'type_choices': IDTag.TYPE_CHOICES,
        'status_choices': IDTag.STATUS_CHOICES,
    })


def _next_dynamic_tag_number():
    """Generate the next human-friendly Dynamic ID Card number (DYN-1001...)."""
    used = set(
        IDTag.objects.filter(tag_type=IDTag.TYPE_DYNAMIC, tag_number__startswith='DYN-')
        .values_list('tag_number', flat=True)
    )
    number = 1001
    while f'DYN-{number}' in used:
        number += 1
    return f'DYN-{number}'


@login_required
def id_tag_master_create(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Only Super Admin can manage ID Card / NFC Tag master data.')

    buildings = Building.objects.filter(status=True).select_related('company', 'work_site').order_by(
        'company__name', 'work_site__name', 'name'
    )
    errors = {}
    values = {
        'tag_type': request.POST.get('tag_type', IDTag.TYPE_PREDEFINED).strip(),
        'tag_number': request.POST.get('tag_number', '').strip(),
        'nfc_number': request.POST.get('nfc_number', '').strip(),
        'building': request.POST.get('building', '').strip(),
        'status': request.POST.get('status', IDTag.STATUS_AVAILABLE).strip(),
        'notes': request.POST.get('notes', '').strip(),
    }

    if request.method == 'POST':
        if values['tag_type'] not in {IDTag.TYPE_DYNAMIC, IDTag.TYPE_PREDEFINED}:
            errors['tag_type'] = 'Select a valid card type.'

        if values['tag_type'] == IDTag.TYPE_DYNAMIC:
            values['tag_number'] = _next_dynamic_tag_number()
        elif not values['tag_number']:
            errors['tag_number'] = 'Tag / Card Number is required for a predefined tag.'

        if values['tag_number'] and IDTag.objects.filter(tag_number=values['tag_number']).exists():
            errors['tag_number'] = 'This Tag / Card Number already exists.'

        building = _related(Building, values['building'], 'building', errors, required=True,
                            queryset=buildings)

        if values['status'] not in dict(IDTag.STATUS_CHOICES):
            errors['status'] = 'Select a valid status.'

        # A new master item must not start as Issued; issuance happens from Guest Visit.
        if values['status'] == IDTag.STATUS_ISSUED:
            errors['status'] = 'New tags/cards must start as Available or Returned.'

        if not errors:
            IDTag.objects.create(
                tag_number=values['tag_number'],
                nfc_number=values['nfc_number'],
                tag_type=values['tag_type'],
                building=building,
                status=values['status'],
                notes=values['notes'],
            )
            messages.success(request, f'ID card/tag {values["tag_number"]} created successfully.')
            return redirect('id_tag_master_list')

    return render(request, 'master/id_tag/form.html', {
        'title': 'Add ID Card / NFC Tag',
        'values': values,
        'errors': errors,
        'buildings': buildings,
        'type_choices': IDTag.TYPE_CHOICES,
        'status_choices': IDTag.STATUS_CHOICES,
        'is_edit': False,
    })


@login_required
def id_tag_master_edit(request, pk):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Only Super Admin can manage ID Card / NFC Tag master data.')

    tag = get_object_or_404(IDTag, pk=pk)
    buildings = Building.objects.filter(status=True).select_related('company', 'work_site').order_by(
        'company__name', 'work_site__name', 'name'
    )
    errors = {}
    values = {
        'tag_type': request.POST.get('tag_type', tag.tag_type).strip(),
        'tag_number': request.POST.get('tag_number', tag.tag_number).strip(),
        'nfc_number': request.POST.get('nfc_number', tag.nfc_number).strip(),
        'building': request.POST.get('building', str(tag.building_id or '')).strip(),
        'status': request.POST.get('status', tag.status).strip(),
        'notes': request.POST.get('notes', tag.notes).strip(),
    }

    if request.method == 'POST':
        if values['tag_type'] not in {IDTag.TYPE_DYNAMIC, IDTag.TYPE_PREDEFINED}:
            errors['tag_type'] = 'Select a valid card type.'

        if not values['tag_number']:
            errors['tag_number'] = 'Tag / Card Number is required.'
        elif IDTag.objects.filter(tag_number=values['tag_number']).exclude(pk=tag.pk).exists():
            errors['tag_number'] = 'This Tag / Card Number already exists.'

        building = _related(Building, values['building'], 'building', errors, required=True,
                            queryset=buildings)

        if values['status'] not in dict(IDTag.STATUS_CHOICES):
            errors['status'] = 'Select a valid status.'

        has_active_issue = tag.issues.filter(status=IDTagIssue.STATUS_ISSUED).exists()
        if has_active_issue and values['status'] != IDTag.STATUS_ISSUED:
            errors['status'] = 'An issued tag cannot be changed to another status until it is returned.'
        if has_active_issue and building is not None and building.pk != tag.building_id:
            errors['building'] = 'Building allocation cannot be changed while the tag is issued.'

        if not errors:
            tag.tag_type = values['tag_type']
            tag.tag_number = values['tag_number']
            tag.nfc_number = values['nfc_number']
            tag.building = building
            tag.status = values['status']
            tag.notes = values['notes']
            tag.save()
            messages.success(request, f'{tag.tag_number} updated successfully.')
            return redirect('id_tag_master_list')

    return render(request, 'master/id_tag/form.html', {
        'title': 'Edit ID Card / NFC Tag',
        'values': values,
        'errors': errors,
        'buildings': buildings,
        'type_choices': IDTag.TYPE_CHOICES,
        'status_choices': IDTag.STATUS_CHOICES,
        'is_edit': True,
        'tag': tag,
    })


@login_required
def id_tag_master_delete(request, pk):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Only Super Admin can manage ID Card / NFC Tag master data.')

    tag = get_object_or_404(IDTag, pk=pk)
    if request.method != 'POST':
        return redirect('id_tag_master_list')

    if tag.issues.exists():
        messages.error(request, 'This ID card/tag has issue history and cannot be deleted. Keep it for audit history.')
    else:
        number = tag.tag_number
        tag.delete()
        messages.success(request, f'{number} deleted successfully.')
    return redirect('id_tag_master_list')


# ============================================================
# HOLD DOCUMENTS / CUSTOMER ITEMS
# ============================================================

@login_required
def hold_document_list(request):
    documents = HoldDocument.objects.select_related(
        'visit', 'visit__tenant', 'visit__unit', 'visit__unit__building',
        'received_by', 'collected_by'
    )
    # Keep visibility scoped where a linked Guest Visit exists. Standalone
    # hold records are visible to the user who recorded them.
    scope = getattr(request.user, 'tenant_profile', None)
    if scope and not request.user.is_superuser and not get_building_staff(request) and not CompanyStaff.objects.filter(
        user=request.user, status=True, company__status=True
    ).exists():
        documents = documents.filter(Q(visit__tenant=scope) | Q(visit__isnull=True, received_by=request.user))
    elif not request.user.is_superuser:
        company = get_user_company(request)
        building_staff = get_building_staff(request)
        if building_staff:
            documents = documents.filter(
                Q(visit__unit__building_id=building_staff.building_id)
                | Q(visit__isnull=True, received_by=request.user)
            )
        elif company:
            documents = documents.filter(
                Q(visit__unit__company=company)
                | Q(visit__isnull=True, received_by=request.user)
            )
        else:
            documents = documents.filter(received_by=request.user)

    status = request.GET.get('status', '').strip()
    if status in {value for value, _ in HoldDocument.STATUS_CHOICES}:
        documents = documents.filter(status=status)
    search = request.GET.get('search', '').strip()
    if search:
        documents = documents.filter(
            Q(item_name__icontains=search)
            | Q(reference_number__icontains=search)
            | Q(person_name__icontains=search)
            | Q(person_mobile__icontains=search)
            | Q(visit__guest_name__icontains=search)
        )
    page_obj = Paginator(documents.order_by('-received_at'), 15).get_page(request.GET.get('page'))
    return render(request, 'operations/hold_document/list.html', {
        'page_obj': page_obj, 'status': status, 'search': search,
        'status_choices': HoldDocument.STATUS_CHOICES,
    })


@login_required
def hold_document_create(request):
    scoped_tenants = _guest_visit_tenant_queryset(request).values_list('pk', flat=True)
    visits = (
        GuestVisit.objects
        .select_related('tenant', 'unit', 'unit__building', 'unit__company', 'unit__company__country', 'purpose_of_visit')
        .filter(
            tenant_id__in=scoped_tenants,
            visitor_id_card_number__isnull=False,
        )
        .exclude(visitor_id_card_number='')
        .order_by('-visit_date', '-created_at')
    )
    errors = {}
    values = {
        'visit': request.POST.get('visit', ''),
        'person_type': request.POST.get('person_type', HoldDocument.PERSON_GUEST),
        'person_name': request.POST.get('person_name', '').strip(),
        'person_mobile': request.POST.get('person_mobile', '').strip(),
        'item_name': request.POST.get('item_name', '').strip(),
        'description': request.POST.get('description', '').strip(),
        'quantity': request.POST.get('quantity', '1'),
        'reference_number': request.POST.get('reference_number', '').strip(),
        'notes': request.POST.get('notes', '').strip(),
    }
    valid_person_types = {value for value, _ in HoldDocument.PERSON_TYPE_CHOICES}
    if values['person_type'] not in valid_person_types:
        values['person_type'] = HoldDocument.PERSON_OTHER

    if request.method == 'POST':
        visit = None
        if not values['visit']:
            errors['visit'] = ['Visitor ID / Guest Visit is required for a Hold Document.']
        else:
            visit = _related(
                GuestVisit, values['visit'], 'visit', errors,
                queryset=GuestVisit.objects.filter(pk__in=visits.values_list('pk', flat=True))
            )
            if visit and not visit.visitor_id_card_number:
                errors['visit'] = ['The selected visitor does not have a Visitor ID.']
        if not values['person_name'] and visit:
            values['person_name'] = visit.guest_name
        if not values['person_name']:
            errors['person_name'] = ['Person name is required.']
        if not values['item_name']:
            errors['item_name'] = ['Item/document name is required.']
        try:
            quantity = int(values['quantity'] or 1)
            if quantity < 1 or quantity > 10000:
                raise ValueError
        except (TypeError, ValueError):
            quantity = 1
            errors['quantity'] = ['Enter a quantity from 1 to 10000.']
        if not errors:
            HoldDocument.objects.create(
                visit=visit,
                person_type=values['person_type'],
                person_name=values['person_name'],
                person_mobile=values['person_mobile'],
                item_name=values['item_name'], description=values['description'],
                quantity=quantity, reference_number=values['reference_number'],
                notes=values['notes'], received_by=request.user,
            )
            messages.success(request, 'Document/item has been recorded under Hold Documents.')
            return redirect('hold_document_list')
    return render(request, 'operations/hold_document/form.html', {
        'visits': visits, 'values': values, 'errors': errors,
        'person_type_choices': HoldDocument.PERSON_TYPE_CHOICES,
        'title': 'Hold Document / Customer Item',
    })


@login_required
def hold_document_collect(request, pk):
    if request.method != 'POST':
        return redirect('hold_document_list')
    document = get_object_or_404(HoldDocument.objects.select_related('visit'), pk=pk)
    # Reuse the list visibility rule for safe collection access.
    allowed = request.user.is_superuser
    if not allowed:
        tenant = getattr(request.user, 'tenant_profile', None)
        building_staff = get_building_staff(request)
        company = get_user_company(request)
        if document.visit_id:
            allowed = bool(
                (tenant and document.visit.tenant_id == tenant.pk)
                or (building_staff and document.visit.unit.building_id == building_staff.building_id)
                or (company and document.visit.unit.company_id == company.pk)
            )
        else:
            allowed = document.received_by_id == request.user.pk
    if not allowed:
        return HttpResponseForbidden('You are not authorized to collect this held item.')
    if document.status != HoldDocument.STATUS_HELD:
        messages.warning(request, 'This held item has already been processed.')
        return redirect('hold_document_list')
    document.status = HoldDocument.STATUS_COLLECTED
    document.collected_at = timezone.now()
    document.collected_by = request.user
    document.save(update_fields=['status', 'collected_at', 'collected_by'])
    messages.success(request, 'Held document/item marked as collected.')
    return redirect('hold_document_list')


# ============================================================
# SIMPLE JSON OPTIONS FOR DEPENDENT DROPDOWNS
# ============================================================

@login_required
def work_site_options(request):
    if is_building_staff(request):
        return JsonResponse([], safe=False)
    queryset = WorkSite.objects.filter(status=True)
    company_id = request.GET.get('company')
    if company_id:
        queryset = queryset.filter(company_id=company_id)
    if not request.user.is_superuser:
        queryset = queryset.filter(company=get_user_company(request))
    return JsonResponse([{'id': item.pk, 'name': item.name} for item in queryset.order_by('name')], safe=False)


@login_required
def building_options(request):
    queryset = Building.objects.filter(status=True)
    building_staff = get_building_staff(request)
    if building_staff:
        queryset = queryset.filter(pk=building_staff.building_id)
    company_id, site_id = request.GET.get('company'), request.GET.get('work_site')
    if company_id:
        queryset = queryset.filter(company_id=company_id)
    if site_id:
        queryset = queryset.filter(work_site_id=site_id)
    if not request.user.is_superuser:
        queryset = queryset.filter(company=get_user_company(request))
    return JsonResponse([{'id': item.pk, 'name': item.name, 'type': item.building_type, 'number_of_floors': item.number_of_floors} for item in queryset.order_by('name')], safe=False)


@login_required
def floor_options(request):
    queryset = Floor.objects.filter(status=True)
    building_staff = get_building_staff(request)
    if building_staff:
        queryset = queryset.filter(building_id=building_staff.building_id)
    building_id = request.GET.get('building')
    if building_id:
        queryset = queryset.filter(building_id=building_id)
    if not request.user.is_superuser:
        queryset = queryset.filter(building__company=get_user_company(request))
    return JsonResponse([{'id': item.pk, 'name': item.name} for item in queryset.order_by('floor_number', 'name')], safe=False)


@login_required
def id_tag_return(request, issue_pk):
    if request.method != 'POST':
        return redirect('reports_home')

    tenant_profile = getattr(request.user, 'tenant_profile', None)
    if not tenant_profile or not tenant_profile.status:
        return HttpResponseForbidden('Only the assigned tenant can record ID tag returns.')

    with transaction.atomic():
        issue = get_object_or_404(
            IDTagIssue.objects.select_for_update().select_related(
                'tag', 'visit', 'visit__unit', 'visit__unit__building'
            ),
            pk=issue_pk,
        )

        if issue.visit.tenant_id != tenant_profile.pk:
            return HttpResponseForbidden('You can return tags only for your own guest visits.')

        if issue.status == IDTagIssue.STATUS_ISSUED:
            now = timezone.now()
            issue.status = IDTagIssue.STATUS_RETURNED
            issue.returned_at = now
            issue.returned_by = request.user
            issue.save(update_fields=['status', 'returned_at', 'returned_by'])

            issue.tag.status = IDTag.STATUS_RETURNED
            issue.tag.save(update_fields=['status', 'updated_at'])
            messages.success(
                request,
                f'ID tag {issue.tag.tag_number} return recorded.'
            )
        else:
            messages.warning(request, 'This ID tag issue is already closed.')

    return redirect('report_detail', report_type='id-card-report')

