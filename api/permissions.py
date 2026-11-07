from rest_framework import permissions
from operations.models import Unit, Tenant, CompanyStaff


def get_active_unit(user):
    """
    Returns the active Unit associated with the user, or None.
    """
    if not user or not user.is_authenticated:
        return None
    return Unit.objects.select_related(
        'building', 'company', 'work_site', 'floor', 'establishment_type'
    ).filter(
        user=user,
        status=True,
        building__status=True,
        company__status=True,
        work_site__status=True,
    ).first()


def get_active_tenant(user):
    """
    Returns the active Tenant associated with the user, or None.
    """
    if not user or not user.is_authenticated:
        return None
    return Tenant.objects.select_related(
        'unit', 'unit__building', 'unit__company', 'unit__work_site'
    ).filter(
        user=user,
        status=True,
        unit_allocations__released_at__isnull=True,
        unit_allocations__unit__status=True,
        unit_allocations__unit__building__status=True,
        unit_allocations__unit__company__status=True,
        unit_allocations__unit__work_site__status=True,
    ).distinct().first()


class IsHouseholder(permissions.BasePermission):
    """
    Allows access only to authenticated Householder / Unit accounts.
    """
    message = "Access restricted to authorized Householder accounts."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        unit = get_active_unit(request.user)
        if unit:
            request.unit = unit
            return True
        return False


class IsTenant(permissions.BasePermission):
    """
    Allows access only to authenticated Tenant accounts.
    """
    message = "Access restricted to authorized Tenant accounts."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        tenant = get_active_tenant(request.user)
        if tenant:
            request.tenant = tenant
            return True
        return False


class IsHouseholderOrTenant(permissions.BasePermission):
    """
    Allows access to either an active Householder or an active Tenant account.
    """
    message = "Access restricted to authorized Householders or Tenants."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser:
            return True
        unit = get_active_unit(request.user)
        if unit:
            request.unit = unit
            return True
        tenant = get_active_tenant(request.user)
        if tenant:
            request.tenant = tenant
            return True
        return False


class IsTenantSecurityAuthorized(permissions.BasePermission):
    """
    Security operations reuse the Tenant account for authorized operations.
    Superuser is also allowed.
    """
    message = "Access restricted to authorized Tenant accounts for security operations."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser:
            return True
        tenant = get_active_tenant(request.user)
        if tenant:
            request.tenant = tenant
            return True
        return False
