from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0017_hold_documents'),
    ]

    operations = [
        migrations.AlterField(
            model_name='holddocument',
            name='visit',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name='held_documents',
                to='operations.guestvisit',
            ),
        ),
        migrations.AddField(
            model_name='holddocument',
            name='person_type',
            field=models.CharField(
                choices=[('guest', 'Guest'), ('tenant', 'Tenant'), ('staff', 'Staff'), ('other', 'Other')],
                default='guest',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='holddocument',
            name='person_name',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='holddocument',
            name='person_mobile',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
    ]
