from django.db import models


class ProsthesisRecord(models.Model):
    """
    Model representing a prosthesis follow-up record.
    """
    prosthetist = models.CharField(max_length=255)
    patient = models.CharField(max_length=255)
    procedure = models.CharField(max_length=255)
    send_date = models.DateField(null=True, blank=True)
    receive_date = models.DateField(null=True, blank=True)
    impression_date = models.DateTimeField(null=True, blank=True)
    duration = models.IntegerField(help_text="Duration in days", null=True)
    comments = models.TextField(blank=True)
    appointment_date = models.DateTimeField(null=True, blank=True)
    url = models.URLField(max_length=500, blank=True)

    def __str__(self):
        return f"{self.patient} - {self.procedure}"


class UsersRecord(models.Model):
    """
    Patient identity record, never deleted — only upserted.
    Unique key: patient_id.
    """
    patient_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.name} ({self.patient_id})"


class IncomeRecord(models.Model):
    """
    Daily payment record from OrthoAdvance reglements/history.
    Fully replaced on each refresh.
    """
    date   = models.DateField()
    amount = models.FloatField()

    def __str__(self):
        return f"{self.date} — {self.amount} €"


# ── Planning / Journées types ─────────────────────────────────────────────────

class JourneeType(models.Model):
    """
    Named day template: describes the recurring appointment schedule for a day type.
    """
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class JourneeTypeEvent(models.Model):
    """
    A single appointment slot within a JourneeType.
    Metatype fields are embedded directly (no separate Metatype table).
    """
    jt           = models.ForeignKey(JourneeType, on_delete=models.CASCADE, related_name="events")
    fauteuil     = models.CharField(max_length=10, help_text="Chair label, e.g. F1, F2b")
    startminutes = models.IntegerField(help_text="Start time in minutes from midnight")
    duration     = models.IntegerField(help_text="Duration in minutes")
    praticien_id = models.CharField(max_length=50)
    mt_value     = models.CharField(max_length=50, default="")
    mt_color     = models.CharField(max_length=20, default="#cccccc")
    mt_as1       = models.IntegerField(default=0)
    mt_as2       = models.IntegerField(default=0)
    mt_dr        = models.IntegerField(default=0)
    mt_duree     = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.jt.name} — {self.fauteuil} @ {self.startminutes} min"


class DayRecord(models.Model):
    """
    Per-day metadata: the journée type name associated with that day.
    Populated from the new get_calendar_records() format (days[].jt_name).
    """
    date    = models.DateField(unique=True)
    jt_name = models.CharField(max_length=255, blank=True)

    class Meta:
        indexes = [models.Index(fields=["date"])]

    def __str__(self):
        return f"{self.date} — {self.jt_name}"


class AppointmentRecord(models.Model):
    """
    Real appointment from OrthoAdvance events.
    Fully replaced on each calendar refresh.
    """
    date         = models.DateField()
    startminutes = models.IntegerField(help_text="Start time in minutes from midnight")
    duration     = models.IntegerField(default=0, help_text="Duration in minutes")
    fauteuil     = models.CharField(max_length=10, blank=True, default="")
    praticien_id = models.CharField(max_length=100, blank=True)
    patient_id   = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["date"])]

    def __str__(self):
        return f"{self.date} {self.startminutes}min — {self.fauteuil}"
