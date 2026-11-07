from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0015_guestvisit_visitors_and_id_tags'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='idtagissue',
            constraint=models.UniqueConstraint(
                fields=('tag',),
                condition=Q(status='issued'),
                name='unique_active_id_tag_issue',
            ),
        ),
    ]
