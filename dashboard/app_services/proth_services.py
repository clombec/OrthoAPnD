import yaml
from pathlib import Path

import logging

from dashboard.models import ProsthesisRecord
from dashboard.models import UsersRecord
from orthoaget import PROJECT_ROOT
from orthoaget.session import OrthoASession
from dashboard.app_services.user_services import refresh_users_records_from_external

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

# ── Color config ──────────────────────────────────────────────────────────────
DEFAULT_COLOR = "#ffffff"

def load_colors(config_path: Path) -> dict:
    """Read the YAML config and return the colors dictionary."""
    if not config_path.exists():
        return {}
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("colors", {})


def save_colors(config_path: Path, colors: dict) -> None:
    """Write the colors dictionary back to the YAML config file."""
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    data["colors"] = colors
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def sync_procedures_to_config(config_path: Path) -> dict:
    """
    Ensure every procedure value in the database has an entry in the
    color config. Missing entries are added with the default color.
    Returns the up-to-date colors dictionary.
    """
    colors = load_colors(config_path)
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
        save_colors(config_path, colors)
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

def refresh_records_from_external(progress_cb=None) -> dict:
    """
    Fetch records from the external project and insert them in the DB.
    The DB is fully refreshed --> existing records are deleted before inserting the new ones.
    For each patient, the URL is built by replacing <ID> with the patient_id from UsersRecord.
    If a patient is not found, UsersRecord is refreshed once. If still not found, url is set
    to an error message.

    progress_cb: optional callable(text: str, percent: int) called at key stages.
    Returns a summary dict with counts.
    """
    def _progress(text: str, percent: int) -> None:
        if progress_cb:
            progress_cb(text, percent)

    def build_users_lookup() -> dict:
        """Returns {  "prénom nom": patient_id  } (lowercase keys)."""
        return {
            f"{u.name}".lower(): u.patient_id
            for u in UsersRecord.objects.all()
        }

    logging.debug("Start refreshing records from external source...")
    _progress("Connexion à OrthoAdvance…", 5)

    with OrthoASession() as session:
        _progress("Téléchargement des actes prothésistes…", 10)
        external_records = session.get_proth_records()

        _progress("Vérification des patients…", 20)
        users_lookup = build_users_lookup()
        users_refreshed = False

        objects = []
        for data in external_records:
            patient_name = data["Patient"].lower()
            patient_id = users_lookup.get(patient_name)

            if patient_id is None:
                if not users_refreshed:
                    _progress("Mise à jour de la liste des patients…", 20)
                    refresh_users_records_from_external(session=session, progress_cb=progress_cb)
                    users_refreshed = True
                    users_lookup = build_users_lookup()
                    patient_id = users_lookup.get(patient_name)
                else:
                    logging.warning(f"Patient '{data['Patient']}' not found in UsersRecord after refresh.")

            if patient_id is not None:
                url = session.user_url(patient_id)
            else:
                url = "Utilisateur non trouvé dans OrthoAdvance"

            objects.append(ProsthesisRecord(
                patient=data["Patient"],
                procedure=data["Acte prothésiste"],
                prosthetist=data["Prothésiste"],
                send_date=data["Date d'envoi au labo"],
                receive_date=data["Date de réception"],
                duration=data.get("Durée"),
                comments=data.get("Commentaires", ""),
                appointment_date=data.get("Date du rdv"),
                impression_date=data.get("PE"),
                url=url,
            ))

        _progress("Enregistrement en base de données…", 90)
        ProsthesisRecord.objects.all().delete()
        ProsthesisRecord.objects.bulk_create(objects)

    logging.debug("Finished refreshing records from external source.")
    _progress("Chargement terminé", 100)

    return {"created": len(objects), "total": len(objects)}