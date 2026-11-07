from datetime import timedelta
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Area,
    Country,
    District,
    EstablishmentType,
    PurposeOfVisit,
    State,
)
from operations.models import (
    Building,
    Company,
    CompanyStaff,
    GuestVisit,
    IDTag,
    IDTagIssue,
    HoldDocument,
    Tenant,
    TenantUnitAllocation,
    Unit,
    WorkSite,
)


class TenantReportsWorkflowTests(TestCase):
    def setUp(self):
        self.country = Country.objects.create(name='Test Country')
        self.state = State.objects.create(country=self.country, name='Test State')
        self.district = District.objects.create(state=self.state, name='Test District')
        self.area = Area.objects.create(district=self.district, name='Test Area')
        self.establishment = EstablishmentType.objects.create(name='Reports Test Residential')
        self.purpose = PurposeOfVisit.objects.create(name='Testing')

        self.company = Company.objects.create(
            name='Test Company',
            address='Test Address',
            country=self.country,
            state=self.state,
            district=self.district,
            area=self.area,
        )
        self.site = WorkSite.objects.create(
            company=self.company,
            name='Test Site',
            address='Test Address',
            location='Test Location',
        )
        self.building = Building.objects.create(
            company=self.company,
            work_site=self.site,
            name='Test Building',
            building_type='apartment',
            address='Test Address',
            location='Test Location',
        )
        self.unit = Unit.objects.create(
            company=self.company,
            work_site=self.site,
            building=self.building,
            establishment_type=self.establishment,
            name='101',
            unit_type='flat',
        )

        self.user = User.objects.create_user(
            username='tenant1',
            password='test-password',
        )
        self.tenant = Tenant.objects.create(
            unit=self.unit,
            user=self.user,
            full_name='Tenant One',
            mobile_number='9999999999',
        )
        TenantUnitAllocation.objects.create(
            tenant=self.tenant,
            unit=self.unit,
        )

        self.tag = IDTag.objects.create(
            tag_number='TAG-001',
            nfc_number='NFC-001',
            building=self.building,
            tag_type=IDTag.TYPE_PREDEFINED,
            status=IDTag.STATUS_AVAILABLE,
        )

    def _create_visit(self, name='Rahul', additional_visitors=0, checked_in=False):
        visit = GuestVisit.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            guest_name=name,
            guest_mobile_number='8888888888',
            additional_visitors=additional_visitors,
            visitor_id_card_number='VIS-001',
            purpose_of_visit=self.purpose,
            visit_date=timezone.localdate(),
            status=GuestVisit.STATUS_APPROVED,
            approved_at=timezone.now(),
        )
        if checked_in:
            visit.checked_in_at = timezone.now() - timedelta(hours=1)
            visit.save(update_fields=['checked_in_at'])
        return visit

    def test_guest_visit_can_be_created_without_photo_and_total_visitors_is_correct(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('guest_visit_create'),
            {
                'visit_type': GuestVisit.TYPE_WALK_IN,
                'building': self.building.pk,
                'unit': self.unit.pk,
                'guest_name': 'Rahul',
                'guest_mobile_number': '8888888888',
                'additional_visitors': '4',
                'visitor_id_card_number': 'VIS-100',
                'purpose_of_visit': self.purpose.pk,
                'visit_date': timezone.localdate().isoformat(),
                'visit_time': '',
                'vehicle_details': '',
                'notes': '',
                'tenant': self.tenant.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        visit = GuestVisit.objects.get(guest_name='Rahul')
        self.assertFalse(bool(visit.guest_photo))
        self.assertEqual(1 + visit.additional_visitors, 5)

    def test_check_in_issues_exactly_one_tag_for_multiple_visitors(self):
        visit = self._create_visit(additional_visitors=4)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('guest_visit_check_in', args=[visit.pk]),
            {'id_type': 'passport', 'id_number': 'P-123'},
        )

        self.assertEqual(response.status_code, 302)
        visit.refresh_from_db()
        issues = list(visit.tag_issues.all())
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].tag_id, self.tag.pk)
        self.assertEqual(self.tag.__class__.objects.get(pk=self.tag.pk).status, IDTag.STATUS_ISSUED)

    def test_active_tag_cannot_be_issued_to_two_visits(self):
        visit1 = self._create_visit(name='Guest One')
        visit2 = self._create_visit(name='Guest Two')

        IDTagIssue.objects.create(visit=visit1, tag=self.tag)
        self.tag.status = IDTag.STATUS_ISSUED
        self.tag.save(update_fields=['status'])

        with self.assertRaises(IntegrityError):
            IDTagIssue.objects.create(visit=visit2, tag=self.tag)

    def test_return_updates_issue_and_tag_status(self):
        visit = self._create_visit()
        issue = IDTagIssue.objects.create(visit=visit, tag=self.tag)
        self.tag.status = IDTag.STATUS_ISSUED
        self.tag.save(update_fields=['status'])

        staff_user = User.objects.create_user(
            username='company-staff',
            password='test-password',
        )
        CompanyStaff.objects.create(user=staff_user, company=self.company)
        self.client.force_login(staff_user)

        response = self.client.post(reverse('id_tag_return', args=[issue.pk]))

        self.assertEqual(response.status_code, 302)
        issue.refresh_from_db()
        self.tag.refresh_from_db()
        self.assertEqual(issue.status, IDTagIssue.STATUS_RETURNED)
        self.assertIsNotNone(issue.returned_at)
        self.assertEqual(self.tag.status, IDTag.STATUS_RETURNED)

    def test_return_report_keeps_unreturned_cards_visible(self):
        visit = self._create_visit()
        IDTagIssue.objects.create(visit=visit, tag=self.tag)
        self.tag.status = IDTag.STATUS_ISSUED
        self.tag.save(update_fields=['status'])

        self.client.force_login(self.user)
        response = self.client.get(reverse('report_detail', args=['id-card-return']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Not Returned')
        self.assertContains(response, 'TAG-001')

    def test_report_can_be_downloaded_as_pdf_and_excel(self):
        self._create_visit(name='Export Guest')
        self.client.force_login(self.user)

        pdf_response = self.client.get(
            reverse('report_detail', args=['guest-visit']),
            {'download': 'pdf'},
        )
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response['Content-Type'], 'application/pdf')
        self.assertIn('attachment; filename="guest-visit.pdf"', pdf_response['Content-Disposition'])
        self.assertTrue(pdf_response.content.startswith(b'%PDF'))

        excel_response = self.client.get(
            reverse('report_detail', args=['guest-visit']),
            {'download': 'excel'},
        )
        self.assertEqual(excel_response.status_code, 200)
        self.assertIn(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            excel_response['Content-Type'],
        )
        self.assertIn('attachment; filename="guest-visit.xlsx"', excel_response['Content-Disposition'])
        self.assertTrue(excel_response.content.startswith(b'PK'))

    def test_tenant_report_is_scoped_to_own_visits(self):
        other_unit = Unit.objects.create(
            company=self.company,
            work_site=self.site,
            building=self.building,
            establishment_type=self.establishment,
            name='102',
            unit_type='flat',
        )
        other_user = User.objects.create_user(
            username='tenant2',
            password='test-password',
        )
        other_tenant = Tenant.objects.create(
            unit=other_unit,
            user=other_user,
            full_name='Tenant Two',
            mobile_number='7777777777',
        )
        TenantUnitAllocation.objects.create(
            tenant=other_tenant,
            unit=other_unit,
        )

        self._create_visit(name='Own Guest')
        GuestVisit.objects.create(
            tenant=other_tenant,
            unit=other_unit,
            guest_name='Other Guest',
            guest_mobile_number='7777777777',
            visitor_id_card_number='VIS-002',
            purpose_of_visit=self.purpose,
            visit_date=timezone.localdate(),
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('report_detail', args=['guest-visit']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Own Guest')
        self.assertNotContains(response, 'Other Guest')

    def test_hold_document_can_be_recorded_and_collected(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('hold_document_create'), {
            'visit': self._create_visit().pk,
            'item_name': 'Passport',
            'description': 'Original passport held at security',
            'quantity': '1',
            'reference_number': 'HOLD-001',
            'notes': 'Keep in locker',
        })
        self.assertEqual(response.status_code, 302)
        document = HoldDocument.objects.get(reference_number='HOLD-001')
        self.assertEqual(document.status, HoldDocument.STATUS_HELD)
        response = self.client.post(reverse('hold_document_collect', args=[document.pk]))
        self.assertEqual(response.status_code, 302)
        document.refresh_from_db()
        self.assertEqual(document.status, HoldDocument.STATUS_COLLECTED)
        self.assertIsNotNone(document.collected_at)

    def test_gate_pass_scan_requires_valid_approved_code(self):
        visit = self._create_visit()
        visit.gate_pass_code = 'TESTPASS123'
        visit.save(update_fields=['gate_pass_code'])
        self.client.force_login(self.user)
        response = self.client.get(reverse('gate_pass_scan', args=[visit.gate_pass_code]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rahul')

    def test_all_five_reports_open_for_tenant(self):
        self.client.force_login(self.user)
        for slug in (
            'guest-visit',
            'visit-duration',
            'id-card-issue',
            'id-card-return',
            'active-id-tags',
        ):
            with self.subTest(report=slug):
                response = self.client.get(reverse('report_detail', args=[slug]))
                self.assertEqual(response.status_code, 200)
