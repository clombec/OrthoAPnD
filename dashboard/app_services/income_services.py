"""
income_services.py

Fetch and store payment records from OrthoAdvance reglements/history.
"""
import logging
from datetime import date, datetime

from django.db.models import Sum

from dashboard.models import IncomeRecord
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
        rows = session.get_income_records(5)

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
        objects.append(IncomeRecord(date=parsed_date, amount=amount))

    _progress("Enregistrement en base de données…", 90)
    IncomeRecord.objects.all().delete()
    IncomeRecord.objects.bulk_create(objects)

    logging.debug(f"Income refreshed: {len(objects)} saved, {skipped} skipped.")
    _progress("Chargement terminé", 100)
    return {"total": len(objects), "skipped": skipped}


def get_income_by_month(year: int, month: int) -> list[dict]:
    """
    Return daily totals for the given calendar month, sorted by date ascending.
    Each entry: {"date": "YYYY-MM-DD", "total": float}.
    """
    qs = (
        IncomeRecord.objects
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
    agg = IncomeRecord.objects.aggregate(min_date=Min("date"), max_date=Max("date"))
    if agg["min_date"] is None:
        return None
    first = agg["min_date"].strftime("%Y-%m")
    last  = agg["max_date"].strftime("%Y-%m")
    return first, last


def get_income_by_year(year: int) -> list[dict]:
    """
    Return monthly totals for the given calendar year, sorted by month ascending.
    Each entry: {"month": int, "label": str, "total": float}.
    """
    MONTH_SHORT = ["", "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
                   "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]
    qs = (
        IncomeRecord.objects
        .filter(date__year=year)
        .values("date__month")
        .annotate(total=Sum("amount"))
        .order_by("date__month")
    )
    return [
        {"month": r["date__month"], "label": MONTH_SHORT[r["date__month"]], "total": round(r["total"], 2)}
        for r in qs
    ]


def get_income_all_years() -> list[dict]:
    """
    Return yearly totals for all years in the DB, sorted ascending.
    Each entry: {"year": int, "total": float}.
    """
    qs = (
        IncomeRecord.objects
        .values("date__year")
        .annotate(total=Sum("amount"))
        .order_by("date__year")
    )
    return [{"year": r["date__year"], "total": round(r["total"], 2)} for r in qs]


def get_available_year_range() -> tuple[int, int] | None:
    """
    Return (first_year, last_year) as ints based on DB content, or None if empty.
    """
    from django.db.models import Min, Max
    agg = IncomeRecord.objects.aggregate(min_date=Min("date"), max_date=Max("date"))
    if agg["min_date"] is None:
        return None
    return agg["min_date"].year, agg["max_date"].year


def get_income_comparison(year1: int, year2: int) -> list[dict]:
    """
    Return monthly comparison data for two years (always 12 months).
    Each entry: {"month": int, "label": str, "y1": float, "y2": float, "pct_diff": float|None}.
    pct_diff = (y2 - y1) / y1 * 100, or None when y1 == 0.
    """
    MONTH_SHORT = ["", "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
                   "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]

    def monthly_totals(year: int) -> dict[int, float]:
        qs = (
            IncomeRecord.objects
            .filter(date__year=year)
            .values("date__month")
            .annotate(total=Sum("amount"))
        )
        return {r["date__month"]: round(r["total"], 2) for r in qs}

    t1 = monthly_totals(year1)
    t2 = monthly_totals(year2)

    result = []
    for m in range(1, 13):
        v1 = t1.get(m, 0.0)
        v2 = t2.get(m, 0.0)
        pct_diff = round((v2 - v1) / v1 * 100, 1) if v1 > 0 else None
        result.append({"month": m, "label": MONTH_SHORT[m], "y1": v1, "y2": v2, "pct_diff": pct_diff})
    return result
