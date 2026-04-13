"""
calendar_services.py

Load and store planning data (journées types, metatypes, calendar days)
from OrthoAdvance via OrthoASession.get_jt_records().
"""
import logging
import re
from datetime import date

from dashboard.models import CalendarDay, JourneeType, JourneeTypeEvent, Metatype
from orthoaget.session import OrthoASession

FRENCH_MONTHS = {
    'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12,
}


def _metatype_id_from_url(url_str: str) -> int | None:
    """Extract the integer ID from a metatype URL like /listes/rdvs-metatypes/123."""
    m = re.search(r'/(\d+)$', str(url_str))
    return int(m.group(1)) if m else None


def _parse_french_date(label: str) -> date | None:
    """Parse a French date label like 'Lundi 5 Janvier 2026' into a date object."""
    parts = label.strip().split()
    if len(parts) < 4:
        return None
    try:
        day = int(parts[1])
        month = FRENCH_MONTHS.get(parts[2].lower())
        year = int(parts[3])
        if month is None:
            return None
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


def is_data_available() -> bool:
    """Return True if planning data exists in the DB."""
    return CalendarDay.objects.exists()


def refresh_records_from_external(progress_cb=None) -> dict:
    """
    Fetch JT planning data from OrthoAdvance and populate the DB.
    Clears all existing planning data before inserting.

    progress_cb: optional callable(text: str, percent: int).
    Returns a summary dict with counts.
    """
    def _progress(text: str, pct: int) -> None:
        if progress_cb:
            progress_cb(text, pct)

    _progress("Connexion à OrthoAdvance…", 5)
    with OrthoASession() as session:
        _progress("Téléchargement du planning…", 20)
        raw = session.get_jt_records()

    return _save_from_raw(raw, _progress)


def _save_from_raw(raw: dict, _progress=None) -> dict:
    def _prog(text: str, pct: int) -> None:
        if _progress:
            _progress(text, pct)

    # ── Metatypes ─────────────────────────────────────────────────────────────
    _prog("Enregistrement des metatypes…", 40)
    metatypes_data = raw.get('metatypes', {})
    Metatype.objects.all().delete()
    metatype_objects = [
        Metatype(
            metatype_id=int(mt_id),
            as1=mt.get('as1', 0),
            as2=mt.get('as2', 0),
            color=mt.get('color', '#ffffff'),
            dr=mt.get('dr', 0),
            duree=mt.get('duree', 0),
            value=mt.get('value', ''),
        )
        for mt_id, mt in metatypes_data.items()
    ]
    Metatype.objects.bulk_create(metatype_objects)
    metatype_map = {mt.metatype_id: mt for mt in Metatype.objects.all()}

    # ── Journées types ────────────────────────────────────────────────────────
    _prog("Enregistrement des journées types…", 55)
    jt_data = raw.get('jt', {})
    JourneeTypeEvent.objects.all().delete()
    JourneeType.objects.all().delete()

    events_to_create = []
    for jt_name, jt_content in jt_data.items():
        jt_obj = JourneeType.objects.create(name=jt_name)
        for evt in jt_content.get('events', []):
            mt_id = _metatype_id_from_url(evt.get('metatype', ''))
            events_to_create.append(JourneeTypeEvent(
                jt=jt_obj,
                fauteuil=int(evt.get('fauteuil', 0)),
                startminutes=int(evt.get('startminutes', 0)),
                duration=int(evt.get('duration', 0)),
                metatype=metatype_map.get(mt_id),
                praticien_id=str(evt.get('praticien_id', '')),
                day=str(evt.get('day', '')),
            ))
    JourneeTypeEvent.objects.bulk_create(events_to_create)

    # ── Calendar days ─────────────────────────────────────────────────────────
    _prog("Enregistrement du calendrier…", 75)
    alldays = raw.get('alldays2026', [])
    CalendarDay.objects.all().delete()
    jt_by_name = {jt.name: jt for jt in JourneeType.objects.all()}

    days_to_create = []
    for entry in alldays:
        label, jt_name, status = entry[0], entry[1], entry[2]
        parsed_date = _parse_french_date(label)
        if parsed_date is None:
            logging.warning(f"Skipping calendar day with unparseable label: {label!r}")
            continue
        days_to_create.append(CalendarDay(
            date=parsed_date,
            label=label,
            jt=jt_by_name.get(jt_name) if jt_name else None,
            status=status,
        ))
    CalendarDay.objects.bulk_create(days_to_create)

    _prog("Chargement terminé", 100)
    logging.info(
        f"Planning refreshed: {len(metatype_objects)} metatypes, "
        f"{len(jt_data)} JTs, {len(days_to_create)} days."
    )
    return {
        "metatypes": len(metatype_objects),
        "jt": len(jt_data),
        "days": len(days_to_create),
    }


# ── Read queries ──────────────────────────────────────────────────────────────

def get_working_days() -> list[dict]:
    """Return all open working days sorted by date."""
    qs = (
        CalendarDay.objects
        .filter(status='Ouvert')
        .select_related('jt')
        .order_by('date')
    )
    return [
        {
            "date": d.date.isoformat(),
            "label": d.label,
            "jt_name": d.jt.name if d.jt else None,
        }
        for d in qs
    ]


def get_day_planning(day_date: date) -> dict | None:
    """
    Return the full planning data for a given date, ready for JSON serialisation.
    Returns None if the date is not in the DB.
    """
    try:
        cal_day = CalendarDay.objects.select_related('jt').get(date=day_date)
    except CalendarDay.DoesNotExist:
        return None

    if cal_day.jt is None:
        return {
            "date": day_date.isoformat(),
            "label": cal_day.label,
            "status": cal_day.status,
            "jt_name": None,
            "events": [],
            "fauteils": [],
            "start_time": 0,
            "end_time": 0,
        }

    events_qs = (
        JourneeTypeEvent.objects
        .filter(jt=cal_day.jt)
        .select_related('metatype')
        .order_by('fauteuil', 'startminutes')
    )

    events = []
    fauteils: set[int] = set()
    min_start: int | None = None
    max_end: int | None = None

    for evt in events_qs:
        fauteils.add(evt.fauteuil)
        end = evt.startminutes + evt.duration
        if min_start is None or evt.startminutes < min_start:
            min_start = evt.startminutes
        if max_end is None or end > max_end:
            max_end = end
        mt = evt.metatype
        events.append({
            "fauteuil": evt.fauteuil,
            "startminutes": evt.startminutes,
            "duration": evt.duration,
            "color": mt.color if mt else "#cccccc",
            "value": mt.value if mt else "",
            "as1": mt.as1 if mt else 0,
            "as2": mt.as2 if mt else 0,
            "dr": mt.dr if mt else 0,
            "praticien_id": evt.praticien_id,
        })

    return {
        "date": day_date.isoformat(),
        "label": cal_day.label,
        "status": cal_day.status,
        "jt_name": cal_day.jt.name,
        "events": events,
        "fauteils": sorted(fauteils),
        "start_time": min_start or 0,
        "end_time": max_end or 0,
    }


def get_adjacent_dates(day_date: date) -> tuple[date | None, date | None]:
    """Return (prev_working_date, next_working_date) around day_date."""
    prev = (
        CalendarDay.objects
        .filter(status='Ouvert', date__lt=day_date)
        .order_by('-date')
        .values_list('date', flat=True)
        .first()
    )
    nxt = (
        CalendarDay.objects
        .filter(status='Ouvert', date__gt=day_date)
        .order_by('date')
        .values_list('date', flat=True)
        .first()
    )
    return prev, nxt


def get_nearest_working_day(ref: date) -> date | None:
    """Return the nearest working day >= ref, or the last one if none found ahead."""
    day = (
        CalendarDay.objects
        .filter(status='Ouvert', date__gte=ref)
        .order_by('date')
        .values_list('date', flat=True)
        .first()
    )
    if day:
        return day
    return (
        CalendarDay.objects
        .filter(status='Ouvert')
        .order_by('-date')
        .values_list('date', flat=True)
        .first()
    )
