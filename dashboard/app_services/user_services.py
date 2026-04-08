import logging

from dashboard.models import UsersRecord
from orthoaget.session import OrthoASession


def refresh_users_records_from_external(session: OrthoASession | None = None) -> dict:
    """
    Upsert UsersRecord from OrthoAdvance.
    Existing records are never deleted — only created or updated.
    Unique key: patient_id ("Nom").
    """
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

    logging.debug(f"Finished refreshing users records: {created} created, {updated} updated.")
    return {"created": created, "updated": updated, "total": len(external_users)}
