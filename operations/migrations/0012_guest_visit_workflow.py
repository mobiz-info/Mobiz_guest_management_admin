from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0011_guest_mobile_number'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='guestvisit', name='visit_type',
            field=models.CharField(choices=[('advance', 'Advance Visit'), ('walk_in', 'Walk-in Visit')], db_index=True, default='advance', max_length=10),
        ),
        migrations.AddField(
            model_name='guestvisit', name='vehicle_details',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.AddField(
            model_name='guestvisit', name='checked_in_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='guestvisit', name='checked_out_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='guestvisit', name='checked_in_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='checked_in_guest_visits', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='guestvisit', name='checked_out_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='checked_out_guest_visits', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='guestvisit', name='status',
            field=models.CharField(choices=[('pending', 'Pending Approval'), ('approved', 'Approved'), ('denied', 'Rejected')], db_index=True, default='pending', max_length=10),
        ),
        migrations.CreateModel(
            name='GuestVisitAccompanyingPerson',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150)),
                ('mobile_number', models.CharField(max_length=30)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('guest_visit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='accompanying_people', to='operations.guestvisit')),
            ],
            options={'ordering': ['id'], 'verbose_name': 'Guest Accompanying Person', 'verbose_name_plural': 'Guest Accompanying People'},
        ),
    ]
