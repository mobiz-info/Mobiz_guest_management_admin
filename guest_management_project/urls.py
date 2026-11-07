from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from reports.views import reports_home, report_detail
from operations.views import id_tag_return

from core.views import (
    # Authentication and Dashboard
    login_view,
    logout_view,
    dashboard_view,

    # Country Master
    country_list,
    country_create,
    country_edit,
    country_delete,

    # State Master
    state_list,
    state_create,
    state_edit,
    state_delete,

    # District Master
    district_list,
    district_create,
    district_edit,
    district_delete,

    # Area Master
    area_list,
    area_create,
    area_edit,
    area_delete,

    # Global designation records (managed from the unified Designation master)
    designation_create,
    designation_edit,
    designation_delete,

    # Establishment Type Master
    establishment_type_list,
    establishment_type_create,
    establishment_type_edit,
    establishment_type_delete,

    # Purpose of Visit Master
    purpose_of_visit_list,
    purpose_of_visit_create,
    purpose_of_visit_edit,
    purpose_of_visit_delete,
)

from operations.views import (
    # Company / Client
    company_list,
    company_create,
    company_detail,
    company_edit,
    company_delete,
    company_staff_details,

    # Company-Specific Designation
    company_designation_list,
    company_designation_create,
    company_designation_edit,
    company_designation_delete,

    # Work Site
    work_site_list,
    work_site_create,
    work_site_edit,
    work_site_delete,

    # Building
    building_list,
    building_create,
    building_edit,
    building_delete,
    my_building,

    # Building Type Master
    building_type_list,
    building_type_create,
    building_type_edit,
    building_type_delete,
    id_tag_master_list,
    id_tag_master_create,
    id_tag_master_edit,
    id_tag_master_delete,

    # Floor
    floor_list,
    floor_create,
    floor_edit,
    floor_delete,

    # Unit
    unit_list,
    unit_create,
    unit_edit,
    unit_delete,

    # Dependent Dropdown Options
    work_site_options,
    building_options,
    floor_options,

    # Tenant
    tenant_list,
    tenant_lease_list,
    tenant_create,
    tenant_edit,
    tenant_delete,
    tenant_change_password,
    tenant_family_member_list,
    tenant_family_member_create,
    tenant_family_member_edit,
    tenant_family_member_delete,
    tenant_staff_member_list,
    tenant_staff_member_create,
    tenant_staff_member_edit,
    tenant_staff_member_delete,

    # Guest / Visitor and Gate Pass
    guest_visit_list,
    guest_visit_camera,
    guest_visit_create,
    guest_visit_approve,
    guest_visit_unit_accept,
    guest_visit_deny,
    guest_visit_gate_pass,
    guest_visit_check_in,
    guest_visit_check_out,
    guest_visit_id_return,
    gate_pass_scan,
    hold_document_list,
    hold_document_create,
    hold_document_collect,
)


urlpatterns = [

    # ========================================================
    # API
    # ========================================================

    path(
        'api/',
        include('api.urls')
    ),


    # ========================================================
    # AUTHENTICATION
    # ========================================================

    path(
        'login/',
        login_view,
        name='login'
    ),

    path(
        'logout/',
        logout_view,
        name='logout'
    ),


    # ========================================================
    # DASHBOARD
    # ========================================================

    path(
        '',
        dashboard_view,
        name='dashboard'
    ),


    # ========================================================
    # COUNTRY MASTER
    # ========================================================

    path(
        'master/country/',
        country_list,
        name='country_list'
    ),

    path(
        'master/country/create/',
        country_create,
        name='country_create'
    ),

    path(
        'master/country/<int:pk>/edit/',
        country_edit,
        name='country_edit'
    ),

    path(
        'master/country/<int:pk>/delete/',
        country_delete,
        name='country_delete'
    ),


    # ========================================================
    # STATE / PROVINCE / EMIRATE MASTER
    # ========================================================

    path(
        'master/state/',
        state_list,
        name='state_list'
    ),

    path(
        'master/state/create/',
        state_create,
        name='state_create'
    ),

    path(
        'master/state/<int:pk>/edit/',
        state_edit,
        name='state_edit'
    ),

    path(
        'master/state/<int:pk>/delete/',
        state_delete,
        name='state_delete'
    ),


    # ========================================================
    # DISTRICT MASTER
    # ========================================================

    path(
        'master/district/',
        district_list,
        name='district_list'
    ),

    path(
        'master/district/create/',
        district_create,
        name='district_create'
    ),

    path(
        'master/district/<int:pk>/edit/',
        district_edit,
        name='district_edit'
    ),

    path(
        'master/district/<int:pk>/delete/',
        district_delete,
        name='district_delete'
    ),


    # ========================================================
    # AREA MASTER
    # ========================================================

    path(
        'master/area/',
        area_list,
        name='area_list'
    ),

    path(
        'master/area/create/',
        area_create,
        name='area_create'
    ),

    path(
        'master/area/<int:pk>/edit/',
        area_edit,
        name='area_edit'
    ),

    path(
        'master/area/<int:pk>/delete/',
        area_delete,
        name='area_delete'
    ),



    # ========================================================
    # DESIGNATION MASTER (GLOBAL + COMPANY DESIGNATIONS)
    # ========================================================

    path('master/designation/', company_designation_list, name='company_designation_list'),
    path('master/designation/create/', company_designation_create, name='company_designation_create'),
    path('master/designation/<int:pk>/edit/', company_designation_edit, name='company_designation_edit'),
    path('master/designation/<int:pk>/delete/', company_designation_delete, name='company_designation_delete'),

    # Global designation records remain available for existing company mappings.
    path('master/designation/global/create/', designation_create, name='designation_create'),
    path('master/designation/global/<uuid:pk>/edit/', designation_edit, name='designation_edit'),
    path('master/designation/global/<uuid:pk>/delete/', designation_delete, name='designation_delete'),

    # ========================================================
    # ESTABLISHMENT TYPE MASTER
    # ========================================================

    path(
        'master/establishment-type/',
        establishment_type_list,
        name='establishment_type_list'
    ),

    path(
        'master/establishment-type/create/',
        establishment_type_create,
        name='establishment_type_create'
    ),

    path(
        'master/establishment-type/<uuid:pk>/edit/',
        establishment_type_edit,
        name='establishment_type_edit'
    ),

    path(
        'master/establishment-type/<uuid:pk>/delete/',
        establishment_type_delete,
        name='establishment_type_delete'
    ),


    # ========================================================
    # PURPOSE OF VISIT MASTER
    # ========================================================

    path(
        'master/purpose-of-visit/',
        purpose_of_visit_list,
        name='purpose_of_visit_list'
    ),

    path(
        'master/purpose-of-visit/create/',
        purpose_of_visit_create,
        name='purpose_of_visit_create'
    ),

    path(
        'master/purpose-of-visit/<uuid:pk>/edit/',
        purpose_of_visit_edit,
        name='purpose_of_visit_edit'
    ),

    path(
        'master/purpose-of-visit/<uuid:pk>/delete/',
        purpose_of_visit_delete,
        name='purpose_of_visit_delete'
    ),


    # ========================================================
    # BUILDING TYPE MASTER
    # ========================================================

    path(
        'master/building-type/',
        building_type_list,
        name='building_type_list'
    ),

    path(
        'master/building-type/create/',
        building_type_create,
        name='building_type_create'
    ),

    path(
        'master/building-type/<int:pk>/edit/',
        building_type_edit,
        name='building_type_edit'
    ),

    path(
        'master/building-type/<int:pk>/delete/',
        building_type_delete,
        name='building_type_delete'
    ),


    # ========================================================
    # ID CARD / NFC TAG MASTER
    # ========================================================

    path(
        'master/id-card-tags/',
        id_tag_master_list,
        name='id_tag_master_list'
    ),

    path(
        'master/id-card-tags/create/',
        id_tag_master_create,
        name='id_tag_master_create'
    ),

    path(
        'master/id-card-tags/<int:pk>/edit/',
        id_tag_master_edit,
        name='id_tag_master_edit'
    ),

    path(
        'master/id-card-tags/<int:pk>/delete/',
        id_tag_master_delete,
        name='id_tag_master_delete'
    ),


    # ========================================================
    # COMPANY / CLIENT
    # ========================================================

    path(
        'company/',
        company_list,
        name='company_list'
    ),

    path(
        'company/create/',
        company_create,
        name='company_create'
    ),

    path(
        'company/<int:pk>/',
        company_detail,
        name='company_detail'
    ),

    path(
        'company/<int:pk>/edit/',
        company_edit,
        name='company_edit'
    ),

    path(
        'company/<int:pk>/delete/',
        company_delete,
        name='company_delete'
    ),

    path(
        'company/<int:pk>/staff-details/',
        company_staff_details,
        name='company_staff_details'
    ),



    # ========================================================
    # WORK SITE CRUD
    # ========================================================

    path(
        'work-sites/',
        work_site_list,
        name='work_site_list'
    ),

    path(
        'work-sites/create/',
        work_site_create,
        name='work_site_create'
    ),

    path(
        'work-sites/<int:pk>/edit/',
        work_site_edit,
        name='work_site_edit'
    ),

    path(
        'work-sites/<int:pk>/delete/',
        work_site_delete,
        name='work_site_delete'
    ),


    # ========================================================
    # BUILDING / PROPERTY CRUD
    # ========================================================

    path(
        'buildings/',
        building_list,
        name='building_list'
    ),

    path(
        'my-building/',
        my_building,
        name='my_building'
    ),

    path(
        'buildings/create/',
        building_create,
        name='building_create'
    ),

    path(
        'buildings/<int:pk>/edit/',
        building_edit,
        name='building_edit'
    ),

    path(
        'buildings/<int:pk>/delete/',
        building_delete,
        name='building_delete'
    ),


    # ========================================================
    # FLOOR CRUD
    # ========================================================

    path(
        'floors/',
        floor_list,
        name='floor_list'
    ),

    path(
        'floors/create/',
        floor_create,
        name='floor_create'
    ),

    path(
        'floors/<int:pk>/edit/',
        floor_edit,
        name='floor_edit'
    ),

    path(
        'floors/<int:pk>/delete/',
        floor_delete,
        name='floor_delete'
    ),


    # ========================================================
    # UNIT CRUD
    # ========================================================

    path(
        'units/',
        unit_list,
        name='unit_list'
    ),

    path(
        'units/create/',
        unit_create,
        name='unit_create'
    ),

    path(
        'units/<int:pk>/edit/',
        unit_edit,
        name='unit_edit'
    ),

    path(
        'units/<int:pk>/delete/',
        unit_delete,
        name='unit_delete'
    ),


    # ========================================================
    # TENANT CRUD
    # ========================================================

    path(
        'tenants/',
        tenant_list,
        name='tenant_list'
    ),

    path(
        'tenants/lease-alerts/',
        tenant_lease_list,
        name='tenant_lease_list'
    ),

    path(
        'tenants/create/',
        tenant_create,
        name='tenant_create'
    ),

    path(
        'tenants/<int:pk>/edit/',
        tenant_edit,
        name='tenant_edit'
    ),

    path(
        'tenants/<int:pk>/delete/',
        tenant_delete,
        name='tenant_delete'
    ),

    path(
        'tenant/change-password/',
        tenant_change_password,
        name='tenant_change_password'
    ),

    # Tenant Family Members (admin/staff manages a selected tenant)
    path(
        'tenants/<int:tenant_pk>/family-members/',
        tenant_family_member_list,
        name='tenant_family_member_list'
    ),
    path(
        'tenants/<int:tenant_pk>/family-members/create/',
        tenant_family_member_create,
        name='tenant_family_member_create'
    ),
    path(
        'tenants/<int:tenant_pk>/family-members/<int:pk>/edit/',
        tenant_family_member_edit,
        name='tenant_family_member_edit'
    ),
    path(
        'tenants/<int:tenant_pk>/family-members/<int:pk>/delete/',
        tenant_family_member_delete,
        name='tenant_family_member_delete'
    ),

    # Tenant self-service family members
    path('my-family/', tenant_family_member_list, name='my_family_members'),
    path('my-family/create/', tenant_family_member_create, name='my_family_member_create'),
    path('my-family/<int:pk>/edit/', tenant_family_member_edit, name='my_family_member_edit'),
    path('my-family/<int:pk>/delete/', tenant_family_member_delete, name='my_family_member_delete'),

    # Tenant staff / household worker records
    path('tenants/<int:tenant_pk>/staff-members/', tenant_staff_member_list, name='tenant_staff_member_list'),
    path('tenants/<int:tenant_pk>/staff-members/create/', tenant_staff_member_create, name='tenant_staff_member_create'),
    path('tenants/<int:tenant_pk>/staff-members/<int:pk>/edit/', tenant_staff_member_edit, name='tenant_staff_member_edit'),
    path('tenants/<int:tenant_pk>/staff-members/<int:pk>/delete/', tenant_staff_member_delete, name='tenant_staff_member_delete'),
    path('my-staff/', tenant_staff_member_list, name='my_staff_members'),
    path('my-staff/create/', tenant_staff_member_create, name='my_staff_member_create'),
    path('my-staff/<int:pk>/edit/', tenant_staff_member_edit, name='my_staff_member_edit'),
    path('my-staff/<int:pk>/delete/', tenant_staff_member_delete, name='my_staff_member_delete'),

    # ========================================================
    # GUEST VISITS AND GATE PASS
    # ========================================================

    path('guest-visits/', guest_visit_list, name='guest_visit_list'),
    path('guest-visits/camera/', guest_visit_camera, name='guest_visit_camera'),
    path('guest-visits/create/', guest_visit_create, name='guest_visit_create'),
    path('guest-visits/<int:pk>/approve/', guest_visit_approve, name='guest_visit_approve'),
    path('guest-visits/<int:pk>/unit-accept/', guest_visit_unit_accept, name='guest_visit_unit_accept'),
    path('guest-visits/<int:pk>/deny/', guest_visit_deny, name='guest_visit_deny'),
    path('guest-visits/<int:pk>/gate-pass/', guest_visit_gate_pass, name='guest_visit_gate_pass'),
    path('guest-visits/<int:pk>/check-in/', guest_visit_check_in, name='guest_visit_check_in'),
    path('guest-visits/<int:pk>/check-out/', guest_visit_check_out, name='guest_visit_check_out'),
    path('guest-visits/<int:pk>/return-id/', guest_visit_id_return, name='guest_visit_id_return'),
    path('gate-pass/scan/<str:code>/', gate_pass_scan, name='gate_pass_scan'),
    path('hold-documents/', hold_document_list, name='hold_document_list'),
    path('hold-documents/create/', hold_document_create, name='hold_document_create'),
    path('hold-documents/<int:pk>/collect/', hold_document_collect, name='hold_document_collect'),

    # ========================================================
    # DEPENDENT DROPDOWN JSON OPTIONS
    # ========================================================

    path(
        'work-site-options/',
        work_site_options,
        name='work_site_options'
    ),

    path(
        'building-options/',
        building_options,
        name='building_options'
    ),

    path(
        'floor-options/',
        floor_options,
        name='floor_options'
    ),

    path('reports/', reports_home, name='reports_home'),
    path('reports/<slug:report_type>/', report_detail, name='report_detail'),
    path('id-tags/issues/<int:issue_pk>/return/', id_tag_return, name='id_tag_return'),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
