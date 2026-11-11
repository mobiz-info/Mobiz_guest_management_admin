from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0020_notification'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenantfamilymember',
            name='relationship',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
    ]
