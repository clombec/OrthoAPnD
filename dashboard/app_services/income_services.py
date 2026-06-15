"""
income_services.py

Fetch and store payment records from OrthoAdvance reglements/history.
"""
import logging
from datetime import date, datetime

from django.db.models import Sum

from dashboard.models import IncomeRecord, EcheanceRecord, PrevisionRecord
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


def _fetch_echeances_for_recettes(session: OrthoASession) -> list:
    """Fetch echeances for the recettes view: Jan 1st (2 years ago) → today."""
    today = date.today()
    dayin = date(today.year - 2, 1, 1)
    return session.get_echeances_records(
        dayin=dayin.strftime("%Y-%m-%d"),
        dayout=today.strftime("%Y-%m-%d"),
    )


def refresh_income_from_external(progress_cb=None) -> dict:
    """
    Fetch payment records from OrthoAdvance for the range [last DB date → today],
    replace only that slice, and leave older records untouched.
    Returns a summary dict with the count of records saved/skipped.
    """
    def _progress(text: str, pct: int) -> None:
        if progress_cb:
            progress_cb(text, pct)

    from django.db.models import Max
    today = date.today()
    agg = IncomeRecord.objects.aggregate(last=Max("date"))
    dayin = agg["last"] or date(2020, 1, 1)

    _progress("Connexion à OrthoAdvance…", 5)
    with OrthoASession() as session:
        _progress("Téléchargement des encaissements…", 25)
        rows = session.get_income_records(dayin=dayin.strftime("%Y-%m-%d"))
        _progress("Téléchargement des échéances…", 50)
        echeances = _fetch_echeances_for_recettes(session)

    _progress("Traitement des données…", 65)
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

    _progress("Enregistrement en base de données…", 85)
    IncomeRecord.objects.filter(date__gte=dayin, date__lte=today).delete()
    IncomeRecord.objects.bulk_create(objects)

    total_echeances = sum(item.get("Dû", 0.0) for item in echeances)
    EcheanceRecord.objects.update_or_create(date=today, defaults={"amount": total_echeances})

    logging.debug(f"Income refreshed: {len(objects)} saved, {skipped} skipped. Echeances: {total_echeances:.2f} €")
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


def get_echeances_by_month(year: int, month: int) -> list[dict]:
    """
    Return daily echeance snapshots for the given calendar month, sorted by date.
    Each entry: {"date": "YYYY-MM-DD", "amount": float}.
    """
    qs = (
        EcheanceRecord.objects
        .filter(date__year=year, date__month=month)
        .order_by("date")
    )
    return [{"date": r.date.isoformat(), "amount": round(r.amount, 2)} for r in qs]


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


# ── Prévisions (echeances futures par date d'échéance) ────────────────────────

MONTH_SHORT = ["", "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
               "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]


def _fetch_echeances_for_previsions(session: OrthoASession) -> list:
    """Fetch echeances for the previsions view: today → 2 years from now."""
    today = date.today()
    dayout = today.replace(year=today.year + 2)
    return session.get_echeances_records(
        dayin=today.strftime("%Y-%m-%d"),
        dayout=dayout.strftime("%Y-%m-%d"),
    )


def refresh_previsions_from_external(progress_cb=None) -> dict:
    """
    Fetch future echeances from OrthoAdvance, aggregate by due date, and
    replace the entire PrevisionRecord table.
    Returns {"total": int} (number of distinct due dates stored).
    """
    def _progress(text: str, pct: int) -> None:
        if progress_cb:
            progress_cb(text, pct)

    _progress("Connexion à OrthoAdvance…", 5)
    with OrthoASession() as session:
        _progress("Téléchargement des prévisions…", 40)
        echeances = _fetch_echeances_for_previsions(session)

    _progress("Traitement des données…", 70)
    daily_totals: dict[str, float] = {}
    for item in echeances:
        date_str = item.get("Date")
        amount = item.get("Dû", 0.0)
        if date_str:
            daily_totals[date_str] = daily_totals.get(date_str, 0.0) + amount

    _progress("Enregistrement en base de données…", 85)
    PrevisionRecord.objects.all().delete()
    PrevisionRecord.objects.bulk_create([
        PrevisionRecord(date=d, amount=round(v, 2))
        for d, v in daily_totals.items()
    ])

    logging.debug(f"Previsions refreshed: {len(daily_totals)} due dates stored.")
    _progress("Chargement terminé", 100)
    return {"total": len(daily_totals)}


def get_available_prevision_month_range() -> tuple[str, str] | None:
    """
    Return (first_month, last_month) as "YYYY-MM" strings from the union of
    IncomeRecord and PrevisionRecord, or None if both tables are empty.
    """
    from django.db.models import Min, Max
    inc = IncomeRecord.objects.aggregate(mn=Min("date"), mx=Max("date"))
    prv = PrevisionRecord.objects.aggregate(mn=Min("date"), mx=Max("date"))
    candidates_min = [r for r in (inc["mn"], prv["mn"]) if r is not None]
    candidates_max = [r for r in (inc["mx"], prv["mx"]) if r is not None]
    if not candidates_min:
        return None
    return min(candidates_min).strftime("%Y-%m"), max(candidates_max).strftime("%Y-%m")


def get_available_prevision_year_range() -> tuple[int, int] | None:
    """
    Return (first_year, last_year) from the union of IncomeRecord and
    PrevisionRecord, or None if both tables are empty.
    """
    from django.db.models import Min, Max
    inc = IncomeRecord.objects.aggregate(mn=Min("date"), mx=Max("date"))
    prv = PrevisionRecord.objects.aggregate(mn=Min("date"), mx=Max("date"))
    candidates_min = [r.year for r in (inc["mn"], prv["mn"]) if r is not None]
    candidates_max = [r.year for r in (inc["mx"], prv["mx"]) if r is not None]
    if not candidates_min:
        return None
    return min(candidates_min), max(candidates_max)


def get_income_and_previsions_by_month(year: int, month: int) -> list[dict]:
    """
    Daily income + previsions for the given month (union of both sources).
    Each entry: {"date": "YYYY-MM-DD", "total": float, "prevision": float}.
    """
    income_map = {
        r["date"].isoformat(): round(r["total"], 2)
        for r in (
            IncomeRecord.objects
            .filter(date__year=year, date__month=month)
            .values("date")
            .annotate(total=Sum("amount"))
        )
    }
    prev_map = {
        r.date.isoformat(): round(r.amount, 2)
        for r in PrevisionRecord.objects.filter(date__year=year, date__month=month)
    }
    all_dates = sorted(set(income_map) | set(prev_map))
    return [
        {"date": d, "total": income_map.get(d, 0.0), "prevision": prev_map.get(d, 0.0)}
        for d in all_dates
    ]


def get_income_and_previsions_by_year(year: int) -> list[dict]:
    """
    Monthly income + previsions for the given year (union of both sources).
    Each entry: {"month": int, "label": str, "total": float, "prevision": float}.
    """
    income_map = {
        r["date__month"]: round(r["total"], 2)
        for r in (
            IncomeRecord.objects
            .filter(date__year=year)
            .values("date__month")
            .annotate(total=Sum("amount"))
        )
    }
    prev_map = {
        r["date__month"]: round(r["prevision"], 2)
        for r in (
            PrevisionRecord.objects
            .filter(date__year=year)
            .values("date__month")
            .annotate(prevision=Sum("amount"))
        )
    }
    all_months = sorted(set(income_map) | set(prev_map))
    return [
        {"month": m, "label": MONTH_SHORT[m],
         "total": income_map.get(m, 0.0), "prevision": prev_map.get(m, 0.0)}
        for m in all_months
    ]


def get_income_and_previsions_all_years() -> list[dict]:
    """
    Yearly income + previsions for all years in either table.
    Each entry: {"year": int, "total": float, "prevision": float}.
    """
    income_map = {
        r["date__year"]: round(r["total"], 2)
        for r in (
            IncomeRecord.objects
            .values("date__year")
            .annotate(total=Sum("amount"))
        )
    }
    prev_map = {
        r["date__year"]: round(r["prevision"], 2)
        for r in (
            PrevisionRecord.objects
            .values("date__year")
            .annotate(prevision=Sum("amount"))
        )
    }
    all_years = sorted(set(income_map) | set(prev_map))
    return [
        {"year": y, "total": income_map.get(y, 0.0), "prevision": prev_map.get(y, 0.0)}
        for y in all_years
    ]


# ── Comparaison annuelle ──────────────────────────────────────────────────────

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
