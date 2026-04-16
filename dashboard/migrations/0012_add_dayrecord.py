from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0011_alter_appointmentrecord_patient_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='DayRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('jt_name', models.CharField(blank=True, max_length=255)),
            ],
            options={
                'indexes': [models.Index(fields=['date'], name='dashboard_d_date_idx')],
            },
        ),
    ]
