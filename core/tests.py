from django.test import TestCase
from core.models import Country, State, District, Area, Designation


class MasterModelTests(TestCase):
    def setUp(self):
        self.country = Country.objects.create(name='Test Country', currency_code='TST', dial_code='+999')
        self.state = State.objects.create(country=self.country, name='Test State')
        self.district = District.objects.create(state=self.state, name='Test District')

    def test_location_hierarchy(self):
        area = Area.objects.create(district=self.district, name='Test Area')
        self.assertEqual(area.district.state.country, self.country)

    def test_designation_creation(self):
        designation = Designation.objects.create(name='Security Officer')
        self.assertTrue(designation.status)
