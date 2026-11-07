from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0010_tenant_family_staff_address_unit'),
    ]

    operations = [
        migrations.AddField(
            model_name='guestvisit',
            name='guest_mobile_number',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
    ]
