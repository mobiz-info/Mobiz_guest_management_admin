from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0016_unique_active_id_tag_issue'),
    ]

    operations = [
        migrations.CreateModel(
            name='HoldDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('item_name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('reference_number', models.CharField(blank=True, default='', max_length=100)),
                ('status', models.CharField(choices=[('held', 'Held'), ('collected', 'Collected'), ('lost', 'Lost')], db_index=True, default='held', max_length=20)),
                ('received_at', models.DateTimeField(auto_now_add=True)),
                ('collected_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('collected_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='held_documents_collected', to=settings.AUTH_USER_MODEL)),
                ('received_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='held_documents_received', to=settings.AUTH_USER_MODEL)),
                ('visit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='held_documents', to='operations.guestvisit')),
            ],
            options={'ordering': ['-received_at']},
        ),
    ]
