# Generated for guest photo, original ID collection and return tracking.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0013_alter_tenantunitallocation_options'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='guestvisit', name='guest_photo',
            field=models.ImageField(blank=True, null=True, upload_to='guest_photos/'),
        ),
        migrations.AddField(
            model_name='guestvisit', name='id_type',
            field=models.CharField(blank=True, choices=[('national_id', 'National ID'), ('passport', 'Passport'), ('driving_license', 'Driving Licence'), ('other', 'Other ID')], default='', max_length=20),
        ),
        migrations.AddField(
            model_name='guestvisit', name='id_number',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='guestvisit', name='id_received_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='guestvisit', name='id_received_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='received_guest_ids', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='guestvisit', name='id_returned_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='guestvisit', name='id_returned_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='returned_guest_ids', to=settings.AUTH_USER_MODEL),
        ),
    ]
