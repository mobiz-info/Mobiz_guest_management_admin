from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from api.views import (
    # Master viewsets
    CountryViewSet,
    StateViewSet,
    DistrictViewSet,
    AreaViewSet,
    DesignationViewSet,
    EstablishmentTypeViewSet,
    PurposeOfVisitViewSet,

    # Auth
    UnifiedLoginAPIView,
    HouseholderLoginAPIView,
    TenantLoginAPIView,
    MeAPIView,
    HouseholderMeAPIView,
    TenantMeAPIView,

    # Householder Application
    HouseholderUnitDetailAPIView,
    HouseholderDashboardAPIView,
    HouseholderAdvanceVisitAPIView,
    HouseholderWalkInVisitListAPIView,
    HouseholderWalkInAcceptAPIView,
    HouseholderWalkInRejectAPIView,
    HouseholderGatePassListAPIView,
    HouseholderGatePassDetailAPIView,
    HouseholderVisitHistoryAPIView,
    HouseholderActiveVisitorsAPIView,
    HouseholderVisitDetailAPIView,

    # Tenant Application
    TenantProfileUpdateAPIView,
    TenantUnitsAPIView,
    TenantDashboardAPIView,
    TenantAdvanceVisitCreateAPIView,
    TenantWalkInVisitCreateAPIView,
    TenantVisitListAPIView,
    TenantPendingApprovalsAPIView,
    TenantApproveVisitAPIView,
    TenantRejectVisitAPIView,
    TenantGatePassListAPIView,
    TenantGatePassDetailAPIView,
    TenantVisitHistoryAPIView,
    TenantActiveVisitorsAPIView,
    TenantVisitDetailAPIView,

    # Security Services
    SecurityVerifyGatePassAPIView,
    SecurityCheckInAPIView,
    SecurityCheckOutAPIView,
    SecurityReturnIdCardAPIView,
    SecurityReturnIdTagAPIView,
    SecurityActiveVisitorsAPIView,
    SecurityVisitorHistoryAPIView,

    # Notifications
    NotificationListAPIView,
    NotificationUnreadCountAPIView,
    NotificationMarkReadAPIView,
    NotificationMarkAllReadAPIView,

    # Docs & Schema
    OpenAPISchemaAPIView,
    SwaggerUIView,
)

router = DefaultRouter()
router.register(r'countries', CountryViewSet, basename='country')
router.register(r'states', StateViewSet, basename='state')
router.register(r'districts', DistrictViewSet, basename='district')
router.register(r'areas', AreaViewSet, basename='area')
router.register(r'designations', DesignationViewSet, basename='designation')
router.register(r'establishment-types', EstablishmentTypeViewSet, basename='establishment-type')
router.register(r'purposes-of-visit', PurposeOfVisitViewSet, basename='purpose-of-visit')

urlpatterns = [
    # OpenAPI & Swagger UI Documentation
    path('schema/', OpenAPISchemaAPIView.as_view(), name='api_schema'),
    path('docs/', SwaggerUIView.as_view(), name='api_docs'),

    # Authentication & JWT
    path('auth/login/', UnifiedLoginAPIView.as_view(), name='api_login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='api_token_refresh'),
    path('auth/me/', MeAPIView.as_view(), name='api_me'),

    # Householder Mobile Application APIs
    path('householder/auth/login/', HouseholderLoginAPIView.as_view(), name='api_householder_login'),
    path('householder/auth/me/', HouseholderMeAPIView.as_view(), name='api_householder_me'),
    path('householder/unit/', HouseholderUnitDetailAPIView.as_view(), name='api_householder_unit'),
    path('householder/dashboard/', HouseholderDashboardAPIView.as_view(), name='api_householder_dashboard'),
    path('householder/guest-visits/advance/', HouseholderAdvanceVisitAPIView.as_view(), name='api_householder_advance_visits'),
    path('householder/guest-visits/walk-in/', HouseholderWalkInVisitListAPIView.as_view(), name='api_householder_walk_in_visits'),
    path('householder/guest-visits/<int:pk>/accept/', HouseholderWalkInAcceptAPIView.as_view(), name='api_householder_walk_in_accept'),
    path('householder/guest-visits/<int:pk>/reject/', HouseholderWalkInRejectAPIView.as_view(), name='api_householder_walk_in_reject'),
    path('householder/guest-visits/<int:pk>/', HouseholderVisitDetailAPIView.as_view(), name='api_householder_visit_detail'),
    path('householder/guest-visits/history/', HouseholderVisitHistoryAPIView.as_view(), name='api_householder_visit_history'),
    path('householder/gate-passes/', HouseholderGatePassListAPIView.as_view(), name='api_householder_gate_passes'),
    path('householder/gate-passes/<int:pk>/', HouseholderGatePassDetailAPIView.as_view(), name='api_householder_gate_pass_detail'),
    path('householder/gate-passes/by-code/<str:code>/', HouseholderGatePassDetailAPIView.as_view(), name='api_householder_gate_pass_by_code'),
    path('householder/visitors/active/', HouseholderActiveVisitorsAPIView.as_view(), name='api_householder_active_visitors'),
    path('householder/notifications/', NotificationListAPIView.as_view(), name='api_householder_notifications'),
    path('householder/notifications/unread-count/', NotificationUnreadCountAPIView.as_view(), name='api_householder_notifications_unread_count'),
    path('householder/notifications/<int:pk>/read/', NotificationMarkReadAPIView.as_view(), name='api_householder_notification_mark_read'),
    path('householder/notifications/mark-all-read/', NotificationMarkAllReadAPIView.as_view(), name='api_householder_notifications_mark_all_read'),

    # Tenant Mobile Application APIs
    path('tenant/auth/login/', TenantLoginAPIView.as_view(), name='api_tenant_login'),
    path('tenant/auth/me/', TenantMeAPIView.as_view(), name='api_tenant_me'),
    path('tenant/profile/', TenantProfileUpdateAPIView.as_view(), name='api_tenant_profile'),
    path('tenant/units/', TenantUnitsAPIView.as_view(), name='api_tenant_units'),
    path('tenant/dashboard/', TenantDashboardAPIView.as_view(), name='api_tenant_dashboard'),
    path('tenant/guest-visits/advance/', TenantAdvanceVisitCreateAPIView.as_view(), name='api_tenant_advance_visit_create'),
    path('tenant/guest-visits/walk-in/', TenantWalkInVisitCreateAPIView.as_view(), name='api_tenant_walk_in_visit_create'),
    path('tenant/guest-visits/', TenantVisitListAPIView.as_view(), name='api_tenant_visit_list'),
    path('tenant/guest-visits/pending-approvals/', TenantPendingApprovalsAPIView.as_view(), name='api_tenant_pending_approvals'),
    path('tenant/guest-visits/<int:pk>/approve/', TenantApproveVisitAPIView.as_view(), name='api_tenant_visit_approve'),
    path('tenant/guest-visits/<int:pk>/reject/', TenantRejectVisitAPIView.as_view(), name='api_tenant_visit_reject'),
    path('tenant/guest-visits/<int:pk>/', TenantVisitDetailAPIView.as_view(), name='api_tenant_visit_detail'),
    path('tenant/guest-visits/history/', TenantVisitHistoryAPIView.as_view(), name='api_tenant_visit_history'),
    path('tenant/gate-passes/', TenantGatePassListAPIView.as_view(), name='api_tenant_gate_passes'),
    path('tenant/gate-passes/<int:pk>/', TenantGatePassDetailAPIView.as_view(), name='api_tenant_gate_pass_detail'),
    path('tenant/gate-passes/by-code/<str:code>/', TenantGatePassDetailAPIView.as_view(), name='api_tenant_gate_pass_by_code'),
    path('tenant/visitors/active/', TenantActiveVisitorsAPIView.as_view(), name='api_tenant_active_visitors'),
    path('tenant/notifications/', NotificationListAPIView.as_view(), name='api_tenant_notifications'),
    path('tenant/notifications/unread-count/', NotificationUnreadCountAPIView.as_view(), name='api_tenant_notifications_unread_count'),
    path('tenant/notifications/<int:pk>/read/', NotificationMarkReadAPIView.as_view(), name='api_tenant_notification_mark_read'),
    path('tenant/notifications/mark-all-read/', NotificationMarkAllReadAPIView.as_view(), name='api_tenant_notifications_mark_all_read'),

    # Security Services (Reusing Tenant Account)
    path('security/verify/', SecurityVerifyGatePassAPIView.as_view(), name='api_security_verify'),
    path('security/check-in/', SecurityCheckInAPIView.as_view(), name='api_security_check_in'),
    path('security/check-out/', SecurityCheckOutAPIView.as_view(), name='api_security_check_out'),
    path('security/return-id-card/', SecurityReturnIdCardAPIView.as_view(), name='api_security_return_id_card'),
    path('security/return-id-tag/', SecurityReturnIdTagAPIView.as_view(), name='api_security_return_id_tag'),
    path('security/visitors/active/', SecurityActiveVisitorsAPIView.as_view(), name='api_security_active_visitors'),
    path('security/visitors/history/', SecurityVisitorHistoryAPIView.as_view(), name='api_security_visitor_history'),

    # Master routes
    path('', include(router.urls)),
]
