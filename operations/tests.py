from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, Client, RequestFactory
from django.db import IntegrityError, transaction
from datetime import date

from core.models import Country, State, District, Area, EstablishmentType, PurposeOfVisit
from operations.models import Company, CompanyStaff, WorkSite, Building, BuildingTypeMaster, BuildingStaff, Floor, Unit, Tenant, TenantUnitAllocation, TenantFamilyMember, GuestVisit, GuestVisitAccompanyingPerson


class PropertyHierarchyTests(TestCase):
    def setUp(self):
        country = Country.objects.create(name='Test Country')
        state = State.objects.create(country=country, name='Test State')
        district = District.objects.create(state=state, name='Test District')
        area = Area.objects.create(district=district, name='Test Area')
        self.company = Company.objects.create(
            name='Test Company', address='Test address', country=country,
            state=state, district=district, area=area,
        )
        self.site = WorkSite.objects.create(company=self.company, name='Main Site', address='Site address', location='Kozhikode')
        self.building = Building.objects.create(
            company=self.company, work_site=self.site, name='Tower 1',
            building_type='apartment', number_of_floors=3, number_of_flats=5,
        )

    def test_company_can_have_multiple_work_sites(self):
        WorkSite.objects.create(company=self.company, name='Second Site', address='Second address', location='Palakkad')
        self.assertEqual(self.company.work_sites.count(), 2)

    def test_unit_hierarchy(self):
        floor = Floor.objects.create(building=self.building, name='Floor 1', floor_number=1)
        unit = Unit.objects.create(
            company=self.company, work_site=self.site, building=self.building,
            floor=floor, name='101', unit_type='flat',
            establishment_type=EstablishmentType.objects.create(name='Residential Test'),
        )
        self.assertEqual(unit.building, self.building)
        self.assertEqual(unit.floor, floor)

    def test_unit_must_match_building(self):
        villa_building = Building.objects.create(
            company=self.company, work_site=self.site, name='Villa Group',
            building_type='villa', number_of_villas=3, number_of_floors=0,
        )
        unit = Unit(
            company=self.company, work_site=self.site, building=villa_building,
            name='Villa 1', unit_type='flat',
            establishment_type=EstablishmentType.objects.create(name='Villa Test'),
        )
        with self.assertRaises(ValidationError):
            unit.full_clean()


class BuildingStaffAccessTests(TestCase):
    def setUp(self):
        country = Country.objects.create(name='Staff Test Country')
        state = State.objects.create(country=country, name='Staff Test State')
        district = District.objects.create(state=state, name='Staff Test District')
        area = Area.objects.create(district=district, name='Staff Test Area')
        self.company = Company.objects.create(
            name='Staff Test Company', address='Company address', country=country,
            state=state, district=district, area=area,
        )
        self.site = WorkSite.objects.create(
            company=self.company, name='Staff Site', address='Site address', location='Kozhikode'
        )
        self.building = Building.objects.create(
            company=self.company, work_site=self.site, name='Assigned Tower',
            building_type='apartment', number_of_floors=2, number_of_flats=4,
        )

    def test_building_staff_is_limited_to_assigned_building(self):
        other_site = WorkSite.objects.create(
            company=self.company, name='Other Site', address='Other address', location='Palakkad'
        )
        Building.objects.create(
            company=self.company, work_site=other_site, name='Other Tower',
            building_type='office', number_of_floors=2, number_of_office_units=2,
        )
        user = User.objects.create_user(username='tower_staff', password='StrongTestPassword!234')
        BuildingStaff.objects.create(building=self.building, user=user, staff_name='Tower Staff')
        self.assertTrue(user.check_password('StrongTestPassword!234'))
        client = Client()
        self.assertTrue(client.login(username='tower_staff', password='StrongTestPassword!234'))
        response = client.get('/buildings/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Assigned Tower')
        self.assertNotContains(response, 'Other Tower')
        self.assertEqual(client.get('/work-sites/').status_code, 302)
        self.assertEqual(client.get('/my-building/').status_code, 200)

    def test_building_type_master_is_separate_from_establishment_type(self):
        building_type = BuildingTypeMaster.objects.create(name='Commercial Test', code='other')
        establishment_type = EstablishmentType.objects.create(name='Shop Test')
        self.assertEqual(building_type.code, 'other')
        self.assertEqual(establishment_type.name, 'Shop Test')


class TenantAccessTests(TestCase):
    def setUp(self):
        country = Country.objects.create(name='Tenant Test Country')
        state = State.objects.create(country=country, name='Tenant Test State')
        district = District.objects.create(state=state, name='Tenant Test District')
        area = Area.objects.create(district=district, name='Tenant Test Area')
        self.company = Company.objects.create(
            name='Tenant Test Company', address='Company address', country=country,
            state=state, district=district, area=area,
        )
        self.site = WorkSite.objects.create(
            company=self.company, name='Tenant Site', address='Site address', location='Kozhikode'
        )
        self.building = Building.objects.create(
            company=self.company, work_site=self.site, name='Tenant Tower',
            building_type='apartment', number_of_floors=1, number_of_flats=3,
        )
        self.floor = Floor.objects.create(building=self.building, name='Floor 1', floor_number=1)
        self.unit = Unit.objects.create(
            company=self.company, work_site=self.site, building=self.building, floor=self.floor,
            name='101', unit_type='flat',
            establishment_type=EstablishmentType.objects.create(name='Tenant Residential'),
        )

    def test_tenant_is_linked_to_unit_and_dates_are_validated(self):
        from datetime import date
        tenant = Tenant(
            unit=self.unit, full_name='Test Tenant', mobile_number='9876543210',
            lease_start_date=date(2026, 1, 1), lease_end_date=date(2026, 12, 31),
        )
        tenant.full_clean()
        tenant.save()
        self.assertEqual(tenant.unit.building, self.building)
        self.assertEqual(Tenant.objects.filter(unit__building=self.building).count(), 1)

    def test_available_units_are_individual_not_building_wide(self):
        from operations.views import _tenant_available_units

        second_unit = Unit.objects.create(
            company=self.company, work_site=self.site, building=self.building,
            floor=self.floor, name='102', unit_type='flat',
            establishment_type=EstablishmentType.objects.create(name='Tenant Residential 2'),
        )
        first_tenant = Tenant.objects.create(
            unit=self.unit, full_name='First Tenant', mobile_number='1111111111',
            tenant_type='owner', status=True,
        )
        TenantUnitAllocation.objects.create(tenant=first_tenant, unit=self.unit)

        request = RequestFactory().get('/tenants/create/')
        request.user = User.objects.create_superuser(
            username='unit_selector_admin', email='admin@example.com', password='StrongTestPassword!234'
        )
        available = _tenant_available_units(request)
        available_ids = {unit.pk for unit in available}

        self.assertNotIn(self.unit.pk, available_ids)
        self.assertIn(second_unit.pk, available_ids)
        self.assertEqual(second_unit.building_id, self.unit.building_id)

    def test_unit_allocation_rejects_duplicate_active_assignment(self):
        second_tenant = Tenant.objects.create(
            unit=self.unit, full_name='Second Tenant', mobile_number='2222222222',
            tenant_type='owner', status=True,
        )
        first_tenant = Tenant.objects.create(
            unit=self.unit, full_name='First Tenant', mobile_number='1111111111',
            tenant_type='owner', status=True,
        )
        TenantUnitAllocation.objects.create(tenant=first_tenant, unit=self.unit)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TenantUnitAllocation.objects.create(tenant=second_tenant, unit=self.unit)

    def test_lease_end_cannot_precede_start(self):
        from datetime import date
        tenant = Tenant(
            unit=self.unit, full_name='Test Tenant', mobile_number='9876543210',
            lease_start_date=date(2026, 12, 31), lease_end_date=date(2026, 1, 1),
        )
        with self.assertRaises(ValidationError):
            tenant.full_clean()

    def test_building_staff_cannot_view_other_building_tenants(self):
        other_site = WorkSite.objects.create(
            company=self.company, name='Other Tenant Site', address='Other address', location='Palakkad'
        )
        other_building = Building.objects.create(
            company=self.company, work_site=other_site, name='Other Tenant Tower',
            building_type='apartment', number_of_floors=1, number_of_flats=2,
        )
        other_floor = Floor.objects.create(building=other_building, name='Floor 1', floor_number=1)
        other_unit = Unit.objects.create(
            company=self.company, work_site=other_site, building=other_building, floor=other_floor,
            name='201', unit_type='flat',
            establishment_type=EstablishmentType.objects.create(name='Other Tenant Residential'),
        )
        Tenant.objects.create(unit=self.unit, full_name='Assigned Tenant', mobile_number='1111111111')
        Tenant.objects.create(unit=other_unit, full_name='Other Building Tenant', mobile_number='2222222222')
        user = User.objects.create_user(username='tenant_building_staff', password='StrongTestPassword!234')
        BuildingStaff.objects.create(building=self.building, user=user, staff_name='Building Staff')
        client = Client()
        self.assertTrue(client.login(username='tenant_building_staff', password='StrongTestPassword!234'))
        response = client.get('/tenants/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Assigned Tenant')
        self.assertNotContains(response, 'Other Building Tenant')
        self.assertEqual(client.get(f'/tenants/{Tenant.objects.get(full_name="Other Building Tenant").pk}/edit/').status_code, 404)


class TenantFamilyMemberTests(TestCase):
    def setUp(self):
        country = Country.objects.create(name='Family Test Country')
        state = State.objects.create(country=country, name='Family Test State')
        district = District.objects.create(state=state, name='Family Test District')
        area = Area.objects.create(district=district, name='Family Test Area')
        company = Company.objects.create(
            name='Family Test Company',
            address='Company address',
            country=country,
            state=state,
            district=district,
            area=area,
        )
        site = WorkSite.objects.create(
            company=company,
            name='Family Test Site',
            address='Site address',
            location='Kozhikode',
        )
        building = Building.objects.create(
            company=company,
            work_site=site,
            name='Family Test Building',
            building_type='apartment',
            number_of_floors=1,
            number_of_flats=2,
        )
        floor = Floor.objects.create(
            building=building,
            name='Floor 1',
            floor_number=1,
        )
        unit = Unit.objects.create(
            company=company,
            work_site=site,
            building=building,
            floor=floor,
            name='101',
            unit_type='flat',
            establishment_type=EstablishmentType.objects.create(
                name='Family Test Residential'
            ),
        )
        self.tenant = Tenant.objects.create(
            unit=unit,
            full_name='Family Test Tenant',
            mobile_number='9876543210',
            tenant_type='rental',
        )

    def test_tenant_can_have_multiple_family_members_with_optional_email(self):
        first = TenantFamilyMember.objects.create(
            tenant=self.tenant,
            name='Family Member One',
            mobile_number='9000000001',
        )
        second = TenantFamilyMember.objects.create(
            tenant=self.tenant,
            name='Family Member Two',
            mobile_number='9000000002',
            email='family@example.com',
        )
        self.assertEqual(self.tenant.family_members.count(), 2)
        self.assertIsNone(first.email)
        self.assertEqual(second.email, 'family@example.com')
        self.assertEqual(first.tenant.unit_id, self.tenant.unit_id)

    def test_tenant_type_defaults_to_rental(self):
        self.assertEqual(self.tenant.tenant_type, 'rental')

    def test_tenant_can_have_multiple_units_and_unit_is_exclusive(self):
        second_unit = Unit.objects.create(
            company=self.tenant.unit.company,
            work_site=self.tenant.unit.work_site,
            building=self.tenant.unit.building,
            floor=self.tenant.unit.floor,
            name='102',
            unit_type='flat',
            establishment_type=self.tenant.unit.establishment_type,
        )
        TenantUnitAllocation.objects.create(tenant=self.tenant, unit=self.tenant.unit)
        TenantUnitAllocation.objects.create(tenant=self.tenant, unit=second_unit)
        self.assertEqual(self.tenant.allocated_units.count(), 2)

        another_tenant = Tenant.objects.create(
            unit=self.tenant.unit,
            full_name='Another Tenant',
            mobile_number='9876500000',
            tenant_type='rental',
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TenantUnitAllocation.objects.create(
                    tenant=another_tenant,
                    unit=second_unit,
                )

    def test_guest_visit_starts_pending_without_gate_pass(self):
        TenantUnitAllocation.objects.create(
            tenant=self.tenant,
            unit=self.tenant.unit,
        )
        purpose = PurposeOfVisit.objects.create(name='Test Visit Purpose')
        visit = GuestVisit.objects.create(
            tenant=self.tenant,
            unit=self.tenant.unit,
            guest_name='Test Visitor',
            purpose_of_visit=purpose,
            visit_date=date.today(),
        )
        self.assertEqual(visit.status, GuestVisit.STATUS_PENDING)
        self.assertIsNone(visit.gate_pass_code)
        visit.visit_type = GuestVisit.TYPE_WALK_IN
        visit.vehicle_details = 'KL-11-AB-1234'
        visit.save(update_fields=['visit_type', 'vehicle_details', 'updated_at'])
        companion = GuestVisitAccompanyingPerson.objects.create(
            guest_visit=visit, name='Accompanying Person', mobile_number='9000000001'
        )
        self.assertEqual(visit.accompanying_people.count(), 1)
        self.assertEqual(companion.mobile_number, '9000000001')



class TenantWorkingAssumptionTests(TestCase):
    def setUp(self):
        country = Country.objects.create(name='Assumption Country')
        state = State.objects.create(country=country, name='Assumption State')
        district = District.objects.create(state=state, name='Assumption District')
        area = Area.objects.create(district=district, name='Assumption Area')
        self.company = Company.objects.create(
            name='Assumption Company', address='Address', country=country,
            state=state, district=district, area=area,
        )
        self.site = WorkSite.objects.create(
            company=self.company, name='Assumption Site', address='Site address', location='Kozhikode'
        )
        self.building = Building.objects.create(
            company=self.company, work_site=self.site, name='Assumption Tower',
            building_type='apartment', number_of_floors=1, number_of_flats=2,
        )
        self.floor = Floor.objects.create(building=self.building, name='Floor 1', floor_number=1)
        self.unit = Unit.objects.create(
            company=self.company, work_site=self.site, building=self.building, floor=self.floor,
            name='A-101', unit_type='flat',
            establishment_type=EstablishmentType.objects.create(name='Assumption Residential'),
        )
        self.admin_user = User.objects.create_superuser(
            username='assumption_admin', email='admin@example.com', password='AdminPass!23456'
        )

    def test_deactivation_releases_unit_and_preserves_history(self):
        tenant_user = User.objects.create_user(
            username='manual_tenant_user', password='TemporaryPass!23456'
        )
        tenant = Tenant.objects.create(
            unit=self.unit, user=tenant_user, full_name='History Tenant',
            mobile_number='9876543210', address='Tenant address', status=True,
        )
        allocation = TenantUnitAllocation.objects.create(tenant=tenant, unit=self.unit)
        family = TenantFamilyMember.objects.create(
            tenant=tenant, name='Family Member', mobile_number='9876500000'
        )

        client = Client()
        client.force_login(self.admin_user)
        response = client.post(f'/tenants/{tenant.pk}/delete/')

        self.assertEqual(response.status_code, 302)
        tenant.refresh_from_db()
        allocation.refresh_from_db()
        tenant_user.refresh_from_db()
        self.assertFalse(tenant.status)
        self.assertIsNotNone(allocation.released_at)
        self.assertFalse(tenant_user.is_active)
        self.assertTrue(TenantFamilyMember.objects.filter(pk=family.pk).exists())
        self.assertTrue(Tenant.objects.filter(pk=tenant.pk).exists())

        # The same unit can be assigned to a new active tenant, while the old row remains.
        replacement_user = User.objects.create_user(
            username='replacement_tenant', password='TemporaryPass!23456'
        )
        replacement = Tenant.objects.create(
            unit=self.unit, user=replacement_user, full_name='Replacement Tenant',
            mobile_number='9876501234', address='Another address', status=True,
        )
        new_allocation = TenantUnitAllocation.objects.create(tenant=replacement, unit=self.unit)
        self.assertIsNone(new_allocation.released_at)
        self.assertTrue(TenantUnitAllocation.objects.filter(pk=allocation.pk).exists())

    def test_only_one_active_allocation_can_use_a_unit(self):
        first = Tenant.objects.create(
            unit=self.unit, full_name='First Tenant', mobile_number='9876543210', status=True,
        )
        second = Tenant.objects.create(
            unit=self.unit, full_name='Second Tenant', mobile_number='9876543211', status=True,
        )
        TenantUnitAllocation.objects.create(tenant=first, unit=self.unit)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TenantUnitAllocation.objects.create(tenant=second, unit=self.unit)

    def test_new_tenant_must_change_initial_password_flag_can_be_set(self):
        tenant = Tenant.objects.create(
            unit=self.unit, full_name='Initial Password Tenant',
            mobile_number='9876543210', must_change_password=True,
        )
        self.assertTrue(tenant.must_change_password)

    def test_tenant_must_change_initial_password_before_dashboard_access(self):
        tenant_user = User.objects.create_user(
            username='first_login_tenant', password='InitialMobilePass!234'
        )
        tenant = Tenant.objects.create(
            unit=self.unit, user=tenant_user, full_name='First Login Tenant',
            mobile_number='9876543210', address='Tenant address', status=True,
            must_change_password=True,
        )
        TenantUnitAllocation.objects.create(tenant=tenant, unit=self.unit)

        client = Client()
        response = client.post('/login/', {
            'username': 'first_login_tenant',
            'password': 'InitialMobilePass!234',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/tenant/change-password/')
        dashboard_response = client.get('/')
        self.assertEqual(
            dashboard_response.status_code,
            302,
            (
                'Tenant with must_change_password=True should be redirected '
                'before accessing the dashboard. '
                f'Got status={dashboard_response.status_code}, '
                f'location={dashboard_response.get("Location")}.'
            ),
        )
        self.assertEqual(
            dashboard_response.get('Location'),
            '/tenant/change-password/',
        )

        response = client.post('/tenant/change-password/', {
            'new_password': 'X9!pQ2#vR7@kLm4$zT8',
            'confirm_password': 'X9!pQ2#vR7@kLm4$zT8',
        })
        self.assertEqual(response.status_code, 302)
        tenant.refresh_from_db()
        tenant_user.refresh_from_db()
        self.assertFalse(tenant.must_change_password)
        self.assertTrue(tenant_user.check_password('X9!pQ2#vR7@kLm4$zT8'))
        self.assertEqual(client.get('/').status_code, 200)

    def test_new_tenant_uses_email_as_username_and_mobile_as_initial_password(self):
        client = Client()
        client.force_login(self.admin_user)
        response = client.post('/tenants/create/', {
            'units': [str(self.unit.pk)],
            'full_name': 'Manually Created Tenant',
            'mobile_number': '9876543210',
            'email': 'manual.tenant@example.com',
            'address': 'Tenant address',
            'tenant_type': 'owner',
            'username': 'manual_tenant_login',
            'password': '9876543210',
            'password_confirm': '9876543210',
            'status': 'on',
        })
        self.assertEqual(response.status_code, 302)
        tenant = Tenant.objects.get(full_name='Manually Created Tenant')
        self.assertEqual(tenant.user.username, 'manual.tenant@example.com')
        self.assertTrue(tenant.user.check_password('9876543210'))
        self.assertTrue(tenant.must_change_password)

        tenant_client = Client()
        login_response = tenant_client.post('/login/', {
            'username': 'MANUAL.TENANT@EXAMPLE.COM',
            'password': '9876543210',
        })
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(login_response.url, '/tenant/change-password/')

        self.assertTrue(TenantUnitAllocation.objects.filter(
            tenant=tenant, unit=self.unit, released_at__isnull=True
        ).exists())
