from django.db import models

class ProsthesisRecord(models.Model):
    """
    Model representing a prosthesis follow-up record.
    """
    prosthetist = models.CharField(max_length=255)
    patient = models.CharField(max_length=255)
    procedure = models.CharField(max_length=255)  # Acte Prothésiste
    send_date = models.DateField(null=True, blank=True)
    receive_date = models.DateField(null=True, blank=True)
    impression_date = models.DateTimeField(null=True, blank=True) # Prise d'empreintes
    duration = models.IntegerField(help_text="Duration in days", null=True)
    comments = models.TextField(blank=True)
    appointment_date = models.DateTimeField(null=True, blank=True)
    url = models.URLField(max_length=500, blank=True)

    def __str__(self):
        return f"{self.patient} - {self.procedure}"


class UsersRecord(models.Model):
    """
    Patient identity record, never deleted — only upserted.
    Unique key: patient_id ("Nom" field from OrthoAdvance).
    """
    patient_id = models.CharField(max_length=100, unique=True)  # "ID"
    name  = models.CharField(max_length=255)                    # "Prénom Nom"

    def __str__(self):
        return f"{self.name} ({self.patient_id})"


class IncomeRecord(models.Model):
    """
    Daily payment record from OrthoAdvance reglements/history.
    Fully replaced on each refresh.
    """
    date    = models.DateField()
    amount  = models.FloatField()

    def __str__(self):
        return f"{self.date} — {self.amount} €"


# ── Planning / Journées types ─────────────────────────────────────────────────

class Metatype(models.Model):
    """
    Appointment metatype definition from OrthoAdvance.
    The integer ID matches the numeric suffix of /listes/rdvs-metatypes/<id>.
    """
    metatype_id = models.IntegerField(primary_key=True)
    as1   = models.IntegerField(default=0, help_text="Assistant time at start (minutes)")
    as2   = models.IntegerField(default=0, help_text="Assistant time at end (minutes)")
    color = models.CharField(max_length=20)
    dr    = models.IntegerField(default=0, help_text="Doctor intervention time (minutes)")
    duree = models.IntegerField(help_text="Total duration (minutes)")
    value = models.CharField(max_length=50, help_text="Display name, e.g. P50")

    def __str__(self):
        return f"{self.value} ({self.duree} min)"


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
    """
    jt          = models.ForeignKey(JourneeType, on_delete=models.CASCADE, related_name="events")
    fauteuil    = models.IntegerField(help_text="Chair number (0-indexed)")
    startminutes = models.IntegerField(help_text="Start time in minutes from midnight")
    duration    = models.IntegerField(help_text="Duration in minutes")
    metatype    = models.ForeignKey(Metatype, on_delete=models.SET_NULL, null=True, blank=True)
    praticien_id = models.CharField(max_length=50)
    day         = models.CharField(max_length=10, help_text="Day ID from OrthoAdvance")

    def __str__(self):
        return f"{self.jt.name} — fauteuil {self.fauteuil} @ {self.startminutes} min"


class CalendarDay(models.Model):
    """
    One day of the year with its assigned JourneeType and open/closed status.
    """
    date   = models.DateField(unique=True)
    label  = models.CharField(max_length=255, help_text="Full French label, e.g. Lundi 5 Janvier 2026")
    jt     = models.ForeignKey(JourneeType, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.label} — {self.status}"


class AppointmentRecord(models.Model):
    """
    Real appointment from OrthoAdvance rdvs_history.
    Fully replaced on each planning refresh.
    """
    date          = models.DateField()
    startminutes  = models.IntegerField(help_text="Start time in minutes from midnight")
    duration      = models.IntegerField(default=0, help_text="Duration in minutes")
    patient_name  = models.CharField(max_length=255)
    patient_id    = models.CharField(max_length=100, blank=True)
    praticien_name = models.CharField(max_length=255)
    praticien_id  = models.CharField(max_length=100, blank=True)
    plage_planning = models.CharField(max_length=100)
    fauteuil      = models.IntegerField(null=True, blank=True)
    color         = models.CharField(max_length=20, default="#888888")

    class Meta:
        indexes = [models.Index(fields=["date"])]

    def __str__(self):
        return f"{self.date} {self.startminutes}min — {self.patient_name}"