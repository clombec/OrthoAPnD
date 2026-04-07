import yaml
from pathlib import Path

from .models import ProsthesisRecord
from orthoaget.mainLoad import get_records

SORTABLE_FIELDS = {
    "prosthetist",
    "patient",
    "procedure",
    "send_date",
    "receive_date",
    "impression_date",
    "duration",
    "appointment_date",
}

CONFIG_PATH = Path(__file__).parent / "configuration.yaml"
DEFAULT_COLOR = "#ffffff"


# ── Color config ──────────────────────────────────────────────────────────────

def load_colors() -> dict:
    """Read the YAML config and return the colors dictionary."""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("colors", {})


def save_colors(colors: dict) -> None:
    """Write the colors dictionary back to the YAML config file."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    data["colors"] = colors
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def sync_procedures_to_config() -> dict:
    """
    Ensure every procedure value in the database has an entry in the
    color config. Missing entries are added with the default color.
    Returns the up-to-date colors dictionary.
    """
    colors = load_colors()
    procedures = (
        ProsthesisRecord.objects
        .values_list("procedure", flat=True)
        .distinct()
    )
    changed = False
    for proc in procedures:
        if proc and proc not in colors:
            colors[proc] = DEFAULT_COLOR
            changed = True
    if changed:
        save_colors(colors)
    return colors


# ── Record queries ─────────────────────────────────────────────────────────────

def get_sorted_records(sort_by: str = "patient", direction: str = "asc"):
    """
    Return all ProsthesisRecord objects sorted by the given field.

    :param sort_by:   Field name to sort on (must be in SORTABLE_FIELDS).
    :param direction: 'asc' or 'desc'.
    :return:          Ordered QuerySet.
    """
    if sort_by not in SORTABLE_FIELDS:
        sort_by = "patient"
        
    order_field = sort_by if direction == "asc" else f"-{sort_by}"
    return ProsthesisRecord.objects.order_by(order_field)

def refresh_records_from_external() -> dict:
    """
    Fetch records from the external project and insert them in the DB.
    The DB is fully refreshed --> existing records are deleted before inserting the new ones.
    Returns a summary dict with counts.
    """

    print("Clearing existing records...")
    ProsthesisRecord.objects.all().delete()

    external_records = get_records()  # retourne une liste de dicts
    created = 0
    updated = 0

    for data in external_records:
        # Use patient + procedure as unique key — adapt to your needs
        obj, is_created = ProsthesisRecord.objects.update_or_create(
            patient=data["Patient"],
            procedure=data["Acte prothésiste"],
            prosthetist=data["Prothésiste"],
            send_date=data["Date d'envoi au labo"],
            receive_date=data["Date de réception"],
            defaults={
                "duration":         data.get("Durée"),
                "comments":         data.get("Commentaires", ""),
                "appointment_date": data.get("Date du rdv"),
                "impression_date":  data.get("PE"),
                "url":              data.get("url", ""),
            },
        )
        if is_created:
            created += 1
        else:
            updated += 1

    return {"created": created, "updated": updated, "total": len(external_records)}
