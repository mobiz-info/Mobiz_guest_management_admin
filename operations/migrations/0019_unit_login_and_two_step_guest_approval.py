from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('operations', '0018_hold_document_person_details'), ('auth', '0012_alter_user_first_name_max_length')]
    operations = [
        migrations.AddField(model_name='unit', name='email', field=models.EmailField(blank=True, default='', max_length=254)),
        migrations.AddField(model_name='unit', name='mobile_number', field=models.CharField(blank=True, default='', max_length=30)),
        migrations.AddField(model_name='unit', name='user', field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='unit_profile', to='auth.user')),
        migrations.AddField(model_name='guestvisit', name='unit_approval_status', field=models.CharField(choices=[('pending', 'Pending Approval'), ('approved', 'Approved'), ('denied', 'Rejected')], db_index=True, default='pending', max_length=10)),
        migrations.AddField(model_name='guestvisit', name='tenant_approval_status', field=models.CharField(choices=[('pending', 'Pending Approval'), ('approved', 'Approved'), ('denied', 'Rejected')], db_index=True, default='pending', max_length=10)),
    ]
