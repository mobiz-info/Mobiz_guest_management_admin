# Generated manually for required Work Site and Building address fields.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0002_worksite_building_floor_unit'),
    ]

    operations = [
        migrations.AlterField(
            model_name='worksite',
            name='address',
            field=models.TextField(),
        ),
        migrations.AlterField(
            model_name='worksite',
            name='location',
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name='building',
            name='address',
            field=models.TextField(),
        ),
        migrations.AlterField(
            model_name='building',
            name='location',
            field=models.CharField(max_length=255),
        ),
    ]
