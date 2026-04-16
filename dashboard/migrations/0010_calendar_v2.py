"""
Migration 0010 — calendar v2

Adapt to the new get_calendar_records() format:
  - fauteuil: IntegerField → CharField in JourneeTypeEvent & AppointmentRecord
  - JourneeTypeEvent: embed metatype fields directly (drop FK + day field)
  - AppointmentRecord: remove patient_name, praticien_name, plage_planning, color
  - Drop CalendarDay and Metatype tables (no longer needed)
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0009_rename_dashboard_a_date_idx_dashboard_a_date_264dd9_idx'),
    ]

    operations = [
        # ── 1. JourneeTypeEvent: drop FK + day, add embedded metatype fields, change fauteuil ──
        migrations.RemoveField(model_name='journeetypeevent', name='metatype'),
        migrations.RemoveField(model_name='journeetypeevent', name='day'),
        migrations.AlterField(
            model_name='journeetypeevent',
            name='fauteuil',
            field=models.CharField(max_length=10, help_text='Chair label, e.g. F1, F2b'),
        ),
        migrations.AddField(
            model_name='journeetypeevent',
            name='mt_value',
            field=models.CharField(max_length=50, default=''),
        ),
        migrations.AddField(
            model_name='journeetypeevent',
            name='mt_color',
            field=models.CharField(max_length=20, default='#cccccc'),
        ),
        migrations.AddField(
            model_name='journeetypeevent',
            name='mt_as1',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='journeetypeevent',
            name='mt_as2',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='journeetypeevent',
            name='mt_dr',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='journeetypeevent',
            name='mt_duree',
            field=models.IntegerField(default=0),
        ),

        # ── 2. AppointmentRecord: change fauteuil, remove obsolete fields ──
        migrations.AlterField(
            model_name='appointmentrecord',
            name='fauteuil',
            field=models.CharField(max_length=10, blank=True, default=''),
        ),
        migrations.RemoveField(model_name='appointmentrecord', name='patient_name'),
        migrations.RemoveField(model_name='appointmentrecord', name='praticien_name'),
        migrations.RemoveField(model_name='appointmentrecord', name='plage_planning'),
        migrations.RemoveField(model_name='appointmentrecord', name='color'),

        # ── 3. Drop CalendarDay and Metatype ──
        migrations.DeleteModel(name='CalendarDay'),
        migrations.DeleteModel(name='Metatype'),
    ]
