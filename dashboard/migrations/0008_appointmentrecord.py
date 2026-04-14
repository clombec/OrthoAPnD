from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0007_calendar_models'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppointmentRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('startminutes', models.IntegerField(help_text='Start time in minutes from midnight')),
                ('duration', models.IntegerField(default=0, help_text='Duration in minutes')),
                ('patient_name', models.CharField(max_length=255)),
                ('patient_id', models.CharField(blank=True, max_length=100)),
                ('praticien_name', models.CharField(max_length=255)),
                ('praticien_id', models.CharField(blank=True, max_length=100)),
                ('plage_planning', models.CharField(max_length=100)),
                ('fauteuil', models.IntegerField(blank=True, null=True)),
                ('color', models.CharField(default='#888888', max_length=20)),
            ],
            options={
                'indexes': [models.Index(fields=['date'], name='dashboard_a_date_idx')],
            },
        ),
    ]
