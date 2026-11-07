from django.shortcuts import redirect
from django.contrib.auth import logout
from operations.models import CompanyStaff, BuildingStaff
from django.urls import resolve, Resolver404
from django.conf import settings


class TenantFirstLoginPasswordChangeMiddleware:
    """Prevent tenant access until the initial password is changed.

    Existing tenant accounts are unaffected unless their must_change_password
    flag is explicitly set. Logout and static/media requests remain accessible.
    """

    allowed_url_names = {'tenant_change_password', 'logout'}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            tenant = getattr(user, 'tenant_profile', None)
            if tenant is not None and not user.is_superuser:
                has_active_staff_role = (
                    CompanyStaff.objects.filter(
                        user=user, status=True, company__status=True
                    ).exists()
                    or BuildingStaff.objects.filter(
                        user=user, status=True, building__status=True,
                        building__company__status=True, building__work_site__status=True
                    ).exists()
                )
                static_url = getattr(settings, 'STATIC_URL', '/static/') or '/static/'
                media_url = getattr(settings, 'MEDIA_URL', '/media/') or '/media/'
                is_asset_request = (
                    request.path_info.startswith(static_url)
                    or request.path_info.startswith(media_url)
                )

                if not tenant.status and not has_active_staff_role:
                    logout(request)
                    if not is_asset_request:
                        return redirect('login')

                if (
                    tenant.status
                    and tenant.must_change_password
                    and not has_active_staff_role
                    and not is_asset_request
                ):
                    try:
                        url_name = resolve(request.path_info).url_name
                    except Resolver404:
                        url_name = None
                    if url_name not in self.allowed_url_names:
                        return redirect('tenant_change_password')
        return self.get_response(request)
