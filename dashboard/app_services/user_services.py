import logging

from dashboard.models import UsersRecord
from orthoaget.session import OrthoASession


def refresh_users_records_from_external(session: OrthoASession | None = None, progress_cb=None) -> dict:
    """
    Upsert UsersRecord from OrthoAdvance.
    Existing records are never deleted — only created or updated.
    Unique key: patient_id ("Nom").
    """
    def _progress(text: str, percent: int) -> None:
        if progress_cb:
            progress_cb(text, percent)
        
    logging.debug("Start refreshing users records from external source...")

    if session is None:
        with OrthoASession() as session:
            external_users = session.get_users_records()
    else:
        external_users = session.get_users_records()

    created = 0
    updated = 0
    for user in external_users:
        _, is_created = UsersRecord.objects.update_or_create(
            patient_id=user["id"],
            defaults={
                "name":  user["name"],
            },
        )
        if is_created:
            created += 1
        else:
            updated += 1
        _progress(f"Chargement de la liste des patients...", int(20 + 0.7 * (created + updated) / len(external_users) * 100)) # Progress from 20% to 90% as records are processed

    logging.debug(f"Finished refreshing users records: {created} created, {updated} updated.")
    return {"created": created, "updated": updated, "total": len(external_users)}
