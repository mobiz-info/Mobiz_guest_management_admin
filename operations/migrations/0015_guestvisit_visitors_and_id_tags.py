from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0014_guest_id_tracking_and_photo'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(model_name='guestvisit', name='additional_visitors', field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name='guestvisit', name='visitor_id_card_number', field=models.CharField(blank=True, db_index=True, default='', max_length=80)),
        migrations.CreateModel(name='IDTag', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('tag_number', models.CharField(max_length=80, unique=True)),
            ('nfc_number', models.CharField(blank=True, default='', max_length=100)),
            ('tag_type', models.CharField(choices=[('dynamic', 'Dynamic ID Card'), ('predefined', 'Predefined NFC / ID Tag')], default='predefined', max_length=20)),
            ('status', models.CharField(choices=[('available', 'Available'), ('issued', 'Issued'), ('returned', 'Returned'), ('lost', 'Lost'), ('damaged', 'Damaged')], db_index=True, default='available', max_length=20)),
            ('notes', models.CharField(blank=True, default='', max_length=255)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('building', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='id_tags', to='operations.building')),
        ], options={'ordering': ['tag_number']}),
        migrations.CreateModel(name='IDTagIssue', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('issued_at', models.DateTimeField(auto_now_add=True)),
            ('returned_at', models.DateTimeField(blank=True, null=True)),
            ('status', models.CharField(choices=[('issued', 'Issued'), ('returned', 'Returned'), ('lost', 'Lost'), ('damaged', 'Damaged')], db_index=True, default='issued', max_length=20)),
            ('issued_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='issued_id_tags', to=settings.AUTH_USER_MODEL)),
            ('returned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='returned_id_tags', to=settings.AUTH_USER_MODEL)),
            ('tag', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='issues', to='operations.idtag')),
            ('visit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tag_issues', to='operations.guestvisit')),
        ], options={'ordering': ['-issued_at']}),
        migrations.AddConstraint(model_name='idtagissue', constraint=models.UniqueConstraint(fields=('visit', 'tag'), name='unique_visit_id_tag_issue')),
    ]
