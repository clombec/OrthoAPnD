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