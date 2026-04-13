from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0006_rename_recetterecord_incomerecord'),
    ]

    operations = [
        migrations.CreateModel(
            name='Metatype',
            fields=[
                ('metatype_id', models.IntegerField(primary_key=True, serialize=False)),
                ('as1', models.IntegerField(default=0, help_text='Assistant time at start (minutes)')),
                ('as2', models.IntegerField(default=0, help_text='Assistant time at end (minutes)')),
                ('color', models.CharField(max_length=20)),
                ('dr', models.IntegerField(default=0, help_text='Doctor intervention time (minutes)')),
                ('duree', models.IntegerField(help_text='Total duration (minutes)')),
                ('value', models.CharField(help_text='Display name, e.g. P50', max_length=50)),
            ],
        ),
        migrations.CreateModel(
            name='JourneeType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='JourneeTypeEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fauteuil', models.IntegerField(help_text='Chair number (0-indexed)')),
                ('startminutes', models.IntegerField(help_text='Start time in minutes from midnight')),
                ('duration', models.IntegerField(help_text='Duration in minutes')),
                ('praticien_id', models.CharField(max_length=50)),
                ('day', models.CharField(help_text='Day ID from OrthoAdvance', max_length=10)),
                ('jt', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='events',
                    to='dashboard.journeetype',
                )),
                ('metatype', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='dashboard.metatype',
                )),
            ],
        ),
        migrations.CreateModel(
            name='CalendarDay',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('label', models.CharField(help_text='Full French label, e.g. Lundi 5 Janvier 2026', max_length=255)),
                ('status', models.CharField(max_length=100)),
                ('jt', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='dashboard.journeetype',
                )),
            ],
        ),
    ]
