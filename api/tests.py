from datetime import date, timedelta
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

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
    Company,
    WorkSite,
    Building,
    Floor,
    Unit,
    Tenant,
    TenantUnitAllocation,
    GuestVisit,
    GuestVisitAccompanyingPerson,
    Notification,
    IDTag,
    IDTagIssue,
)


class MobizAPIBaseTestCase(APITestCase):
    def setUp(self):
        # 1. Master Records
        self.country, _ = Country.objects.get_or_create(name="India", defaults={'currency_code': 'INR', 'dial_code': '+91', 'status': True})
        self.state, _ = State.objects.get_or_create(country=self.country, name="Kerala", defaults={'status': True})
        self.district, _ = District.objects.get_or_create(state=self.state, name="Kozhikode", defaults={'status': True})
        self.area, _ = Area.objects.get_or_create(district=self.district, name="City Center", defaults={'status': True})
        self.est_type, _ = EstablishmentType.objects.get_or_create(name="Residential", defaults={'status': True})
        self.purpose1, _ = PurposeOfVisit.objects.get_or_create(name="Family Visit", defaults={'status': True})
        self.purpose2, _ = PurposeOfVisit.objects.get_or_create(name="Maintenance", defaults={'status': True})

        # 2. Company & Site
        self.company = Company.objects.create(
            name="Alpha Properties",
            address="123 Alpha Way",
            country=self.country,
            state=self.state,
            district=self.district,
            area=self.area,
            status=True,
        )
        self.work_site = WorkSite.objects.create(
            company=self.company,
            name="Alpha Site",
            address="Site Address 1",
            location="Downtown",
            status=True,
        )
        self.building = Building.objects.create(
            company=self.company,
            work_site=self.work_site,
            name="Alpha Tower",
            building_type="apartment",
            address="Building Address 1",
            location="Downtown",
            number_of_floors=5,
            number_of_flats=10,
            status=True,
        )
        self.floor1 = Floor.objects.create(
            building=self.building,
            name="Floor 1",
            floor_number=1,
            status=True,
        )

        # 3. Unit 1 & Householder 1
        self.u1_user = User.objects.create_user(username="unit101", password="Password123!", email="unit101@alpha.com")
        self.unit1 = Unit.objects.create(
            company=self.company,
            work_site=self.work_site,
            building=self.building,
            floor=self.floor1,
            establishment_type=self.est_type,
            name="101",
            email="unit101@alpha.com",
            mobile_number="9876543210",
            user=self.u1_user,
            unit_type="flat",
            status=True,
        )

        # 4. Unit 2 & Householder 2 (for isolation testing)
        self.u2_user = User.objects.create_user(username="unit102", password="Password123!", email="unit102@alpha.com")
        self.unit2 = Unit.objects.create(
            company=self.company,
            work_site=self.work_site,
            building=self.building,
            floor=self.floor1,
            establishment_type=self.est_type,
            name="102",
            email="unit102@alpha.com",
            mobile_number="9876543211",
            user=self.u2_user,
            unit_type="flat",
            status=True,
        )

        # 5. Tenant 1 allocated to Unit 1
        self.t1_user = User.objects.create_user(username="tenant_john", password="Password123!", email="john@example.com")
        self.tenant1 = Tenant.objects.create(
            unit=self.unit1,
            user=self.t1_user,
            full_name="John Doe",
            mobile_number="9876500001",
            email="john@example.com",
            tenant_type="rental",
            status=True,
        )
        TenantUnitAllocation.objects.create(tenant=self.tenant1, unit=self.unit1)

        # 6. Tenant 2 allocated to Unit 2
        self.t2_user = User.objects.create_user(username="tenant_alice", password="Password123!", email="alice@example.com")
        self.tenant2 = Tenant.objects.create(
            unit=self.unit2,
            user=self.t2_user,
            full_name="Alice Smith",
            mobile_number="9876500002",
            email="alice@example.com",
            tenant_type="owner",
            status=True,
        )
        TenantUnitAllocation.objects.create(tenant=self.tenant2, unit=self.unit2)

        # 7. Pre-created ID Tag for Security
        self.id_tag1 = IDTag.objects.create(
            tag_number="TAG-101",
            building=self.building,
            tag_type=IDTag.TYPE_PREDEFINED,
            status=IDTag.STATUS_AVAILABLE,
        )

    def login_as_householder(self):
        resp = self.client.post('/api/householder/auth/login/', {'username': 'unit101', 'password': 'Password123!'})
        token = resp.data['data']['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return resp

    def login_as_tenant(self):
        resp = self.client.post('/api/tenant/auth/login/', {'username': 'tenant_john', 'password': 'Password123!'})
        token = resp.data['data']['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return resp


class MobizAPITests(MobizAPIBaseTestCase):

    # ---------------------------------------------------------
    # 1. AUTHENTICATION & LOGIN TESTS
    # ---------------------------------------------------------

    def test_householder_login_success(self):
        resp = self.client.post('/api/householder/auth/login/', {'username': 'unit101', 'password': 'Password123!'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['success'])
        self.assertIn('access', resp.data['data'])
        self.assertEqual(resp.data['data']['user']['role'], 'householder')
        self.assertEqual(resp.data['data']['user']['unit']['name'], '101')

    def test_tenant_login_success(self):
        resp = self.client.post('/api/tenant/auth/login/', {'username': 'tenant_john', 'password': 'Password123!'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['success'])
        self.assertIn('access', resp.data['data'])
        self.assertEqual(resp.data['data']['user']['role'], 'tenant')
        self.assertEqual(resp.data['data']['user']['tenant']['full_name'], 'John Doe')

    def test_unified_login(self):
        resp = self.client.post('/api/auth/login/', {'username': 'tenant_john', 'password': 'Password123!'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['success'])
        self.assertEqual(resp.data['data']['user']['role'], 'tenant')

    def test_login_invalid_password(self):
        resp = self.client.post('/api/householder/auth/login/', {'username': 'unit101', 'password': 'WrongPassword'})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(resp.data['success'])

    def test_householder_cannot_login_at_tenant_endpoint(self):
        resp = self.client.post('/api/tenant/auth/login/', {'username': 'unit101', 'password': 'Password123!'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(resp.data['success'])

    # ---------------------------------------------------------
    # 2. HOUSEHOLDER PROFILE, UNIT & DASHBOARD
    # ---------------------------------------------------------

    def test_householder_unit_and_profile_api(self):
        self.login_as_householder()
        resp_me = self.client.get('/api/householder/auth/me/')
        self.assertEqual(resp_me.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_me.data['data']['unit_name'], '101')

        resp_unit = self.client.get('/api/householder/unit/')
        self.assertEqual(resp_unit.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_unit.data['data']['name'], '101')
        self.assertEqual(resp_unit.data['data']['building_name'], 'Alpha Tower')
        self.assertEqual(resp_unit.data['data']['current_tenant']['full_name'], 'John Doe')

    def test_householder_dashboard_stats(self):
        self.login_as_householder()
        resp = self.client.get('/api/householder/dashboard/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('total_guests', resp.data['data'])
        self.assertIn('pending_walk_in_requests', resp.data['data'])
        self.assertIn('pending_advance_requests', resp.data['data'])
        self.assertIn('approved_gate_passes', resp.data['data'])
        self.assertIn('active_visitors', resp.data['data'])

    # ---------------------------------------------------------
    # 3. TENANT PROFILE, UNITS & DASHBOARD
    # ---------------------------------------------------------

    def test_tenant_profile_and_units_and_dashboard(self):
        self.login_as_tenant()
        resp_me = self.client.get('/api/tenant/auth/me/')
        self.assertEqual(resp_me.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_me.data['data']['full_name'], 'John Doe')
        self.assertEqual(len(resp_me.data['data']['allocated_units']), 1)

        resp_units = self.client.get('/api/tenant/units/')
        self.assertEqual(resp_units.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_units.data['data']), 1)
        self.assertEqual(resp_units.data['data'][0]['name'], '101')

        resp_dash = self.client.get('/api/tenant/dashboard/')
        self.assertEqual(resp_dash.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_dash.data['data']['tenant_name'], 'John Doe')
        self.assertEqual(resp_dash.data['data']['allocated_units_count'], 1)

    def test_tenant_profile_update(self):
        self.login_as_tenant()
        resp = self.client.patch('/api/tenant/profile/', {'address': 'Penthouse Suite 101', 'notes': 'VIP Tenant'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['data']['address'], 'Penthouse Suite 101')
        self.tenant1.refresh_from_db()
        self.assertEqual(self.tenant1.address, 'Penthouse Suite 101')

    # ---------------------------------------------------------
    # 4. WORKFLOW A: TENANT ADVANCE GUEST VISIT
    # (Auto-generates Gate Pass and QR code)
    # ---------------------------------------------------------

    def test_workflow_a_tenant_advance_visit_auto_approval_and_gate_pass(self):
        self.login_as_tenant()
        payload = {
            'unit': self.unit1.id,
            'guest_name': 'Robert Brown',
            'guest_mobile_number': '9876500099',
            'purpose_of_visit': str(self.purpose1.id),
            'visit_date': str(date.today()),
            'visit_time': '14:30:00',
            'additional_visitors': 2,
            'accompanying_people': [
                {'name': 'Sarah Brown', 'mobile_number': '9876500098'},
                {'name': 'Tommy Brown', 'mobile_number': '9876500097'},
            ],
            'vehicle_details': 'KL-11-AB-1234',
            'notes': 'Family dinner',
        }
        resp = self.client.post('/api/tenant/guest-visits/advance/', payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp.data['success'])
        gate_pass_data = resp.data['data']
        self.assertEqual(gate_pass_data['status'], 'approved')
        self.assertTrue(gate_pass_data['gate_pass_code'].startswith('ENT-'))
        self.assertTrue(gate_pass_data['qr_code_image'].startswith('data:image/png;base64,'))
        self.assertEqual(len(gate_pass_data['accompanying_people']), 2)

        # Verify notification created for Householder
        notif = Notification.objects.filter(recipient=self.u1_user).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.notification_type, Notification.TYPE_GATE_PASS_ISSUED)

    # ---------------------------------------------------------
    # 5. WORKFLOW B: HOUSEHOLDER ADVANCE GUEST VISIT
    # (Request sent to Tenant -> Tenant approves/rejects -> Gate pass only after approval)
    # ---------------------------------------------------------

    def test_workflow_b_householder_advance_visit_full_lifecycle(self):
        # 1. Householder creates advance request
        self.login_as_householder()
        payload = {
            'guest_name': 'David Miller',
            'guest_mobile_number': '9876543299',
            'purpose_of_visit': str(self.purpose2.id),
            'visit_date': str(date.today() + timedelta(days=1)),
            'visit_time': '10:00:00',
            'notes': 'Plumber service',
        }
        resp = self.client.post('/api/householder/guest-visits/advance/', payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        visit_id = resp.data['data']['id']
        self.assertEqual(resp.data['data']['status'], 'pending')
        self.assertEqual(resp.data['data']['unit_approval_status'], 'approved')
        self.assertEqual(resp.data['data']['tenant_approval_status'], 'pending')
        self.assertIsNone(resp.data['data']['gate_pass_code'])

        # Check tenant received notification
        notif = Notification.objects.filter(recipient=self.t1_user, visit_id=visit_id).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.notification_type, Notification.TYPE_ADVANCE_REQUEST)

        # 2. Tenant views pending approvals
        self.login_as_tenant()
        pending_resp = self.client.get('/api/tenant/guest-visits/pending-approvals/')
        self.assertEqual(pending_resp.status_code, status.HTTP_200_OK)
        pending_ids = [v['id'] for v in pending_resp.data['data']]
        self.assertIn(visit_id, pending_ids)

        # 3. Tenant approves request
        appr_resp = self.client.post(f'/api/tenant/guest-visits/{visit_id}/approve/')
        self.assertEqual(appr_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(appr_resp.data['success'])
        self.assertEqual(appr_resp.data['data']['status'], 'approved')
        self.assertTrue(appr_resp.data['data']['gate_pass_code'].startswith('ENT-'))

        # 4. Householder can now retrieve generated Gate Pass
        self.login_as_householder()
        gp_resp = self.client.get(f'/api/householder/gate-passes/{visit_id}/')
        self.assertEqual(gp_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(gp_resp.data['data']['id'], visit_id)
        self.assertTrue(gp_resp.data['data']['qr_code_image'].startswith('data:image/png;base64,'))

    def test_workflow_b_tenant_rejection(self):
        self.login_as_householder()
        payload = {
            'guest_name': 'Sales Person',
            'guest_mobile_number': '9876543200',
            'purpose_of_visit': str(self.purpose1.id),
            'visit_date': str(date.today()),
        }
        create_resp = self.client.post('/api/householder/guest-visits/advance/', payload, format='json')
        visit_id = create_resp.data['data']['id']

        # Tenant rejects
        self.login_as_tenant()
        rej_resp = self.client.post(f'/api/tenant/guest-visits/{visit_id}/reject/')
        self.assertEqual(rej_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(rej_resp.data['data']['status'], 'denied')

        # Visit in DB has no gate pass code
        visit = GuestVisit.objects.get(pk=visit_id)
        self.assertEqual(visit.status, 'denied')
        self.assertIsNone(visit.gate_pass_code)

    # ---------------------------------------------------------
    # 6. WORKFLOW C: TENANT WALK-IN GUEST VISIT
    # (Tenant creates -> Householder accepts/rejects -> Tenant approves -> Gate Pass generated)
    # ---------------------------------------------------------

    def test_workflow_c_tenant_walk_in_visit_full_lifecycle(self):
        # 1. Tenant creates walk-in request
        self.login_as_tenant()
        payload = {
            'unit': self.unit1.id,
            'guest_name': 'Courier Delivery',
            'guest_mobile_number': '9876511111',
            'purpose_of_visit': str(self.purpose1.id),
            'visit_date': str(date.today()),
            'notes': 'Parcel delivery at door',
        }
        create_resp = self.client.post('/api/tenant/guest-visits/walk-in/', payload, format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        visit_id = create_resp.data['data']['id']
        self.assertEqual(create_resp.data['data']['status'], 'pending')
        self.assertEqual(create_resp.data['data']['unit_approval_status'], 'pending')
        self.assertEqual(create_resp.data['data']['tenant_approval_status'], 'pending')

        # 2. Tenant cannot approve before Unit acceptance!
        premature_appr = self.client.post(f'/api/tenant/guest-visits/{visit_id}/approve/')
        self.assertEqual(premature_appr.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(premature_appr.data['success'])

        # 3. Householder accepts walk-in request
        self.login_as_householder()
        accept_resp = self.client.post(f'/api/householder/guest-visits/{visit_id}/accept/')
        self.assertEqual(accept_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(accept_resp.data['data']['unit_approval_status'], 'approved')

        # 4. Now Tenant approves
        self.login_as_tenant()
        appr_resp = self.client.post(f'/api/tenant/guest-visits/{visit_id}/approve/')
        self.assertEqual(appr_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(appr_resp.data['data']['status'], 'approved')
        self.assertTrue(appr_resp.data['data']['gate_pass_code'].startswith('ENT-'))

    def test_workflow_c_householder_rejects_walk_in(self):
        self.login_as_tenant()
        payload = {
            'unit': self.unit1.id,
            'guest_name': 'Uninvited Visitor',
            'guest_mobile_number': '9876522222',
            'purpose_of_visit': str(self.purpose1.id),
            'visit_date': str(date.today()),
        }
        create_resp = self.client.post('/api/tenant/guest-visits/walk-in/', payload, format='json')
        visit_id = create_resp.data['data']['id']

        # Householder rejects
        self.login_as_householder()
        rej_resp = self.client.post(f'/api/householder/guest-visits/{visit_id}/reject/')
        self.assertEqual(rej_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(rej_resp.data['data']['status'], 'denied')

        # Verify no gate pass can ever be generated
        self.login_as_tenant()
        appr_resp = self.client.post(f'/api/tenant/guest-visits/{visit_id}/approve/')
        self.assertEqual(appr_resp.status_code, status.HTTP_400_BAD_REQUEST)

    # ---------------------------------------------------------
    # 7. SECURITY SERVICES: VERIFY, CHECK-IN, RETURN, CHECKOUT
    # ---------------------------------------------------------

    def test_security_full_checkin_checkout_workflow(self):
        # Create an approved visit with gate pass
        self.login_as_tenant()
        payload = {
            'unit': self.unit1.id,
            'guest_name': 'Security Test Visitor',
            'guest_mobile_number': '9876533333',
            'purpose_of_visit': str(self.purpose1.id),
            'visit_date': str(date.today()),
        }
        res = self.client.post('/api/tenant/guest-visits/advance/', payload, format='json')
        gp_code = res.data['data']['gate_pass_code']
        visit_id = res.data['data']['id']

        # 1. Verify Gate Pass
        verify_resp = self.client.post('/api/security/verify/', {'code': gp_code})
        self.assertEqual(verify_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(verify_resp.data['data']['is_valid_for_entry'])
        self.assertEqual(verify_resp.data['data']['verification_status'], 'Valid for Entry')

        # 2. Check-in
        checkin_payload = {
            'gate_pass_code': gp_code,
            'id_type': 'national_id',
            'id_number': 'ID1234567890',
            'notes': 'Identity verified at gate',
        }
        checkin_resp = self.client.post('/api/security/check-in/', checkin_payload)
        self.assertEqual(checkin_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(checkin_resp.data['data']['is_checked_in'])
        assigned_tag = checkin_resp.data['data']['issued_tag_number']
        self.assertTrue(bool(assigned_tag))

        # Check Active Visitors list
        active_resp = self.client.get('/api/security/visitors/active/')
        self.assertEqual(active_resp.status_code, status.HTTP_200_OK)
        active_ids = [v['id'] for v in active_resp.data['data']]
        self.assertIn(visit_id, active_ids)

        # 3. Check-out without returning ID tag must fail!
        checkout_premature = self.client.post('/api/security/check-out/', {'gate_pass_code': gp_code})
        self.assertEqual(checkout_premature.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('outstanding_tags', checkout_premature.data['errors'])

        # 4. Return ID tag
        tag_return_resp = self.client.post('/api/security/return-id-tag/', {'tag_number': assigned_tag})
        self.assertEqual(tag_return_resp.status_code, status.HTTP_200_OK)

        # 5. Check-out succeeds now (with automatic return_id=True or explicit)
        checkout_resp = self.client.post('/api/security/check-out/', {'gate_pass_code': gp_code, 'return_id': True})
        self.assertEqual(checkout_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(checkout_resp.data['data']['is_checked_out'])

        # Verify not active anymore
        active_after = self.client.get('/api/security/visitors/active/')
        active_after_ids = [v['id'] for v in active_after.data['data']]
        self.assertNotIn(visit_id, active_after_ids)

    # ---------------------------------------------------------
    # 8. NOTIFICATIONS APIS
    # ---------------------------------------------------------

    def test_notification_apis(self):
        # Create test notification
        notif = Notification.objects.create(
            recipient=self.u1_user,
            title="System Alert",
            message="Maintenance tonight at 10 PM",
            notification_type=Notification.TYPE_GENERAL,
        )

        self.login_as_householder()
        # List
        list_resp = self.client.get('/api/householder/notifications/')
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_resp.data['data']), 1)

        # Unread count
        count_resp = self.client.get('/api/householder/notifications/unread-count/')
        self.assertEqual(count_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(count_resp.data['data']['unread_count'], 1)

        # Mark as read
        mark_resp = self.client.post(f'/api/householder/notifications/{notif.id}/read/')
        self.assertEqual(mark_resp.status_code, status.HTTP_200_OK)

        # Unread count should now be 0
        count_after = self.client.get('/api/householder/notifications/unread-count/')
        self.assertEqual(count_after.data['data']['unread_count'], 0)

    # ---------------------------------------------------------
    # 9. DATA ISOLATION & PERMISSION BOUNDARIES
    # ---------------------------------------------------------

    def test_householder_cannot_access_other_unit_data(self):
        # Create a visit belonging to Unit 2
        visit2 = GuestVisit.objects.create(
            tenant=self.tenant2,
            unit=self.unit2,
            guest_name="Private Guest for Unit 102",
            guest_mobile_number="9876543000",
            purpose_of_visit=self.purpose1,
            visit_date=date.today(),
            status=GuestVisit.STATUS_APPROVED,
            gate_pass_code="ENT-UNIT2-PASS",
        )

        # Log in as Unit 1
        self.login_as_householder()

        # Cannot view Unit 2 visit detail
        resp_detail = self.client.get(f'/api/householder/guest-visits/{visit2.id}/')
        self.assertEqual(resp_detail.status_code, status.HTTP_404_NOT_FOUND)

        # Cannot view Unit 2 gate pass
        resp_gp = self.client.get(f'/api/householder/gate-passes/{visit2.id}/')
        self.assertEqual(resp_gp.status_code, status.HTTP_404_NOT_FOUND)

        # Unit 1 gate pass list does not include Unit 2's pass
        resp_list = self.client.get('/api/householder/gate-passes/')
        codes = [gp['gate_pass_code'] for gp in resp_list.data['data']]
        self.assertNotIn("ENT-UNIT2-PASS", codes)

    def test_tenant_cannot_access_other_tenant_data(self):
        # Create a visit belonging to Tenant 2
        visit2 = GuestVisit.objects.create(
            tenant=self.tenant2,
            unit=self.unit2,
            guest_name="Private Guest for Tenant Alice",
            guest_mobile_number="9876543001",
            purpose_of_visit=self.purpose1,
            visit_date=date.today(),
            status=GuestVisit.STATUS_APPROVED,
            gate_pass_code="ENT-TENANT2-PASS",
        )

        # Log in as Tenant 1 (John)
        self.login_as_tenant()

        # Cannot view Tenant 2 visit detail
        resp_detail = self.client.get(f'/api/tenant/guest-visits/{visit2.id}/')
        self.assertEqual(resp_detail.status_code, status.HTTP_404_NOT_FOUND)

        # Cannot book a visit for a unit not allocated to Tenant 1
        resp_book = self.client.post('/api/tenant/guest-visits/advance/', {
            'unit': self.unit2.id,  # Belongs to Tenant 2, not Tenant 1
            'guest_name': 'Hacker Guest',
            'guest_mobile_number': '9876543002',
            'purpose_of_visit': str(self.purpose1.id),
            'visit_date': str(date.today()),
        })
        self.assertEqual(resp_book.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(resp_book.data['success'])

    # ---------------------------------------------------------
    # 10. DOCUMENTATION & SCHEMA
    # ---------------------------------------------------------

    def test_schema_and_docs_endpoints(self):
        schema_resp = self.client.get('/api/schema/')
        self.assertEqual(schema_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(schema_resp.data['openapi'], '3.0.3')

        docs_resp = self.client.get('/api/docs/')
        self.assertEqual(docs_resp.status_code, status.HTTP_200_OK)
        self.assertIn(b'swagger-ui', docs_resp.content)
