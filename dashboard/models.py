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


class RecetteRecord(models.Model):
    """
    Daily payment record from OrthoAdvance reglements/history.
    Fully replaced on each refresh.
    """
    date    = models.DateField()
    amount  = models.FloatField()

    def __str__(self):
        return f"{self.date} — {self.amount} €"