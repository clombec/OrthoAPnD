"""
income_services.py

Fetch and store payment records from OrthoAdvance reglements/history.
"""
import logging
from datetime import date, datetime

from django.db.models import Sum

from dashboard.models import RecetteRecord
from orthoaget.session import OrthoASession

# Column names as returned by OrthoABase after CSV cleanup
AMOUNT_KEY = "amount"
DATE_KEY = "date"

# Date formats to try when parsing the date field
DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"]


def _parse_date(value: str) -> date | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def refresh_income_from_external(progress_cb=None) -> dict:
    """
    Fetch payment records from OrthoAdvance, clear the table and re-insert.
    Returns a summary dict with the total record count.
    """
    def _progress(text: str, pct: int) -> None:
        if progress_cb:
            progress_cb(text, pct)

    _progress("Connexion à OrthoAdvance…", 5)
    with OrthoASession() as session:
        _progress("Téléchargement des encaissements…", 30)
        rows = session.get_income_records(all=True)

    _progress("Traitement des données…", 70)
    objects = []
    skipped = 0
    for row in rows:
        parsed_date = _parse_date(str(row.get(DATE_KEY, "")))
        amount = row.get(AMOUNT_KEY)
        if parsed_date is None or amount is None:
            logging.warning(f"Skipping income row — unparseable date or amount: {row}")
            skipped += 1
            continue
        objects.append(RecetteRecord(date=parsed_date, amount=amount))

    _progress("Enregistrement en base de données…", 90)
    RecetteRecord.objects.all().delete()
    RecetteRecord.objects.bulk_create(objects)

    logging.debug(f"Income refreshed: {len(objects)} saved, {skipped} skipped.")
    _progress("Chargement terminé", 100)
    return {"total": len(objects), "skipped": skipped}


def get_income_by_month(year: int, month: int) -> list[dict]:
    """
    Return daily totals for the given calendar month, sorted by date ascending.
    Each entry: {"date": "YYYY-MM-DD", "total": float}.
    """
    qs = (
        RecetteRecord.objects
        .filter(date__year=year, date__month=month)
        .values("date")
        .annotate(total=Sum("amount"))
        .order_by("date")
    )
    return [{"date": r["date"].isoformat(), "total": round(r["total"], 2)} for r in qs]


def get_available_month_range() -> tuple[str, str] | None:
    """
    Return (first_month, last_month) as "YYYY-MM" strings based on DB content,
    or None if the table is empty.
    """
    from django.db.models import Min, Max
    agg = RecetteRecord.objects.aggregate(min_date=Min("date"), max_date=Max("date"))
    if agg["min_date"] is None:
        return None
    first = agg["min_date"].strftime("%Y-%m")
    last  = agg["max_date"].strftime("%Y-%m")
    return first, last
