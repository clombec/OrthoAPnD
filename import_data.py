"""
import_data.py
Standalone script to manually import static records into the Django database.
Run with: python import_data.py
"""

import os
import django

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mon_nas_web.settings")
django.setup()

from dashboard.models import ProsthesisRecord  # noqa: E402

# ── Static records to import ───────────────────────────────────────────────────

RECORDS = [
    {
        "patient":          "Dupont Jean",
        "procedure":        "Couper Go de collage indirect",
        "prosthetist":      "Labo Dupont",
        "send_date":        "25/03/2026",
        "receive_date":     "02/04/2026",
        "impression_date":  "2026-04-09T09:30:00+02:00",
        "duration":         15,
        "comments":         "Teinte A2",
        "appointment_date": "2026-04-09T09:30:00+02:00",
        "url":              "",
    },
    {
        "patient":          "Martin Claire",
        "procedure":        "Acte 2",
        "prosthetist":      "Labo Martin",
        "send_date":        "05/04/2026",
        "receive_date":     "",
        "impression_date":  "2026-03-16T17:55:00+01:00",
        "duration":         10,
        "comments":         "",
        "appointment_date": "",
        "url":              "",
    },
    {
        "patient":          "Bernard Luc",
        "procedure":        "Acte A",
        "prosthetist":      "Labo Bernard",
        "send_date":        "07/04/2026",
        "receive_date":     "",
        "impression_date":  "2026-03-16T17:55:00+01:00",
        "duration":         20,
        "comments":         "Urgent",
        "appointment_date": "2026-04-20T09:00:00",
        "url":              "https://example.com/case/456",
    },
]


# ── Sync function ──────────────────────────────────────────────────────────────

def import_static_records() -> dict:
    """
    Upsert the static RECORDS list into the database.
    Uses patient + procedure as the unique key.
    Returns a summary dict with created/updated counts.
    """
    created = 0
    updated = 0

    for data in RECORDS:
        _, is_created = ProsthesisRecord.objects.update_or_create(
            patient=data["patient"],
            procedure=data["procedure"],
            defaults={
                "prosthetist":      data.get("prosthetist", ""),
                "send_date":        data.get("send_date"),
                "receive_date":     data.get("receive_date"),
                "impression_date":  data.get("impression_date"),
                "duration":         data.get("duration"),
                "comments":         data.get("comments", ""),
                "appointment_date": data.get("appointment_date"),
                "url":              data.get("url", ""),
            },
        )
        if is_created:
            created += 1
        else:
            updated += 1

    return {"created": created, "updated": updated, "total": len(RECORDS)}


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Clearing existing records...")
    ProsthesisRecord.objects.all().delete()

    print("Starting static data import...")
    try:
        result = import_static_records()
        print(
            f"SUCCESS: {result['created']} created, "
            f"{result['updated']} updated "
            f"({result['total']} total)"
        )
    except Exception as exc:
        print(f"FAILED: {exc}")

    for record in ProsthesisRecord.objects.all():
        print(record.patient, record.send_date, type(record.send_date), record.impression_date, type(record.impression_date), record.appointment_date, type(record.appointment_date))

    print(ProsthesisRecord.objects.all())