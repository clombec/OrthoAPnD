from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0013_rename_dashboard_d_date_idx_dashboard_d_date_6c562d_idx'),
    ]

    operations = [
        migrations.CreateModel(
            name='EcheanceRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('amount', models.FloatField()),
            ],
        ),
    ]
