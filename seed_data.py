"""Optional idempotent seed data for Guest Management master records.

Run with: python seed_data.py
This script intentionally does not create users or sample company/property records.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'guest_management_project.settings')
django.setup()

from core.models import Country, State, District, Area, Designation, EstablishmentType, PurposeOfVisit
from operations.models import BuildingTypeMaster


def seed_master_data():
    country, _ = Country.objects.get_or_create(
        name='India', defaults={'currency_code': 'INR', 'emblem': '🇮🇳', 'dial_code': '+91', 'status': True}
    )
    state, _ = State.objects.get_or_create(country=country, name='Kerala', defaults={'status': True})
    district, _ = District.objects.get_or_create(state=state, name='Kozhikode', defaults={'status': True})
    Area.objects.get_or_create(district=district, name='Kozhikode City', defaults={'status': True})

    for name in ('Security Officer', 'Supervisor', 'Manager', 'Receptionist'):
        Designation.objects.get_or_create(name=name, defaults={'status': True})
    for name in ('Shop', 'Office', 'Residential', 'Godown', 'Restaurant', 'Clinic'):
        EstablishmentType.objects.get_or_create(name=name, defaults={'status': True})

    for name, code in (
        ('Apartment', 'apartment'), ('Villa', 'villa'), ('Office', 'office'),
        ('Other', 'other'), ('Residential', 'apartment'), ('Commercial', 'other'),
        ('Office Building', 'office'),
    ):
        BuildingTypeMaster.objects.get_or_create(name=name, defaults={'code': code, 'status': True})
    # Purpose of Visit defaults were not finalized; create them from the Master screen.
    print('Guest Management master seed data is ready.')


if __name__ == '__main__':
    seed_master_data()
