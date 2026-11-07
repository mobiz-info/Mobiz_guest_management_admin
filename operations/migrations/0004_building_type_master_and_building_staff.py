from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_type_masters(apps, schema_editor):
    BuildingTypeMaster = apps.get_model('operations', 'BuildingTypeMaster')
    EstablishmentType = apps.get_model('core', 'EstablishmentType')
    Building = apps.get_model('operations', 'Building')
    Unit = apps.get_model('operations', 'Unit')

    building_types = [
        ('Apartment', 'apartment'),
        ('Villa', 'villa'),
        ('Office', 'office'),
        ('Other', 'other'),
        ('Residential', 'apartment'),
        ('Commercial', 'other'),
        ('Office Building', 'office'),
    ]
    type_map = {}
    for name, code in building_types:
        item, _ = BuildingTypeMaster.objects.get_or_create(
            name=name,
            defaults={'code': code, 'status': True},
        )
        type_map[name] = item

    by_code = {}
    for item in BuildingTypeMaster.objects.all().order_by('id'):
        by_code.setdefault(item.code, item)
    for building in Building.objects.filter(building_type_master__isnull=True):
        building.building_type_master = by_code.get(building.building_type) or type_map.get('Other')
        building.save(update_fields=['building_type_master'])

    defaults = [
        ('Shop', 'other'),
        ('Office', 'office'),
        ('Residential', 'apartment'),
        ('Godown', 'other'),
        ('Restaurant', 'other'),
        ('Clinic', 'office'),
    ]
    establishment_map = {}
    for name, _ in defaults:
        item, _ = EstablishmentType.objects.get_or_create(name=name, defaults={'status': True})
        establishment_map[name] = item

    for unit in Unit.objects.filter(establishment_type__isnull=True):
        if unit.unit_type == 'office':
            chosen = establishment_map['Office']
        elif unit.unit_type == 'other':
            chosen = establishment_map['Godown']
        else:
            chosen = establishment_map['Residential']
        unit.establishment_type = chosen
        unit.save(update_fields=['establishment_type'])


def reverse_seed(apps, schema_editor):
    # Seeded rows are safe to keep on reverse; user data must not be deleted.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
        ('operations', '0003_require_worksite_building_address_location'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BuildingTypeMaster',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('code', models.CharField(choices=[('apartment', 'Apartment / Residential'), ('villa', 'Villa'), ('office', 'Office / Office Building'), ('other', 'Commercial / Other')], default='other', max_length=20)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('status', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'verbose_name': 'Building Type', 'verbose_name_plural': 'Building Types', 'ordering': ['name']},
        ),
        migrations.AddField(
            model_name='building',
            name='building_type_master',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='buildings', to='operations.buildingtypemaster'),
        ),
        migrations.AddField(
            model_name='unit',
            name='establishment_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='units', to='core.establishmenttype'),
        ),
        migrations.CreateModel(
            name='BuildingStaff',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('staff_name', models.CharField(max_length=150)),
                ('designation', models.CharField(blank=True, max_length=100)),
                ('mobile', models.CharField(blank=True, max_length=30)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('status', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('building', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='staff_account', to='operations.building')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='building_staff', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Building Staff', 'verbose_name_plural': 'Building Staff', 'ordering': ['building__name']},
        ),
        migrations.RunPython(seed_type_masters, reverse_seed),
    ]
