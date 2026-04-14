"""
calendar_services.py

Load and store planning data (journées types, metatypes, calendar days,
real appointments) from OrthoAdvance via OrthoASession.get_calendar_records().
"""
import logging
import re
from datetime import date, datetime

from dashboard.models import (
    AppointmentRecord, CalendarDay,
    JourneeType, JourneeTypeEvent, Metatype,
)
from dashboard.models import UsersRecord
from orthoaget.session import OrthoASession

FRENCH_MONTHS = {
    'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12,
}

DEFAULT_APPT_COLOR = "#888888"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _metatype_id_from_url(url_str: str) -> int | None:
    m = re.search(r'/(\d+)$', str(url_str))
    return int(m.group(1)) if m else None


def _parse_french_date(label: str) -> date | None:
    parts = label.strip().split()
    if len(parts) < 4:
        return None
    try:
        day = int(parts[1])
        month = FRENCH_MONTHS.get(parts[2].lower())
        year = int(parts[3])
        return date(year, month, day) if month else None
    except (ValueError, IndexError):
        return None


def _parse_rdv_datetime(value: str) -> tuple[date, int] | None:
    """Parse ISO datetime string → (date, startminutes)."""
    try:
        dt = datetime.fromisoformat(str(value).strip("'\""))
        start = dt.hour * 60 + dt.minute
        return dt.date(), start
    except (ValueError, TypeError):
        return None


def _infer_duration_and_color(
    plage: str,
    metatype_by_value: dict,
) -> tuple[int, str]:
    """
    Infer appointment duration and color from plage_planning string.
    Tries an exact metatype value match first, then extracts trailing digits.
    """
    mt = metatype_by_value.get(plage)
    if mt:
        return mt.duree, mt.color
    m = re.search(r'(\d+)$', plage)
    duration = int(m.group(1)) if m else 0
    return duration, DEFAULT_APPT_COLOR


def _build_users_lookup() -> dict[str, str]:
    """Return {name.lower(): patient_id} for all UsersRecord rows."""
    return {u.name.lower(): u.patient_id for u in UsersRecord.objects.all()}


# ── Availability ──────────────────────────────────────────────────────────────

def is_data_available() -> bool:
    return CalendarDay.objects.exists()


# ── External refresh ──────────────────────────────────────────────────────────

def refresh_records_from_external(progress_cb=None) -> dict:
    """
    Fetch all planning data from OrthoAdvance and populate the DB.
    Clears all existing planning data before inserting.
    """
    def _progress(text: str, pct: int) -> None:
        if progress_cb:
            progress_cb(text, pct)

    _progress("Connexion à OrthoAdvance…", 5)
    with OrthoASession() as session:
        _progress("Téléchargement du planning…", 20)
        raw = session.get_calendar_records()

    return _save_from_raw(raw, _progress)


def _save_from_raw(raw: dict, _progress=None) -> dict:
    def _prog(text: str, pct: int) -> None:
        if _progress:
            _progress(text, pct)

    # ── Metatypes ─────────────────────────────────────────────────────────────
    _prog("Enregistrement des metatypes…", 35)
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
        for mt_id, mt in raw.get('metatypes', {}).items()
    ]
    Metatype.objects.bulk_create(metatype_objects)
    metatype_map_by_id    = {mt.metatype_id: mt for mt in Metatype.objects.all()}
    metatype_map_by_value = {mt.value: mt for mt in metatype_map_by_id.values()}

    # ── Journées types ────────────────────────────────────────────────────────
    _prog("Enregistrement des journées types…", 50)
    JourneeTypeEvent.objects.all().delete()
    JourneeType.objects.all().delete()

    jt_data = raw.get('jt', {})
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
                metatype=metatype_map_by_id.get(mt_id),
                praticien_id=str(evt.get('praticien_id', '')),
                day=str(evt.get('day', '')),
            ))
    JourneeTypeEvent.objects.bulk_create(events_to_create)

    # ── Calendar days ─────────────────────────────────────────────────────────
    _prog("Enregistrement du calendrier…", 65)
    CalendarDay.objects.all().delete()
    jt_by_name = {jt.name: jt for jt in JourneeType.objects.all()}

    days_to_create = []
    for entry in raw.get('alldays2026', []):
        label, jt_name, status = entry[0], entry[1], entry[2]
        parsed_date = _parse_french_date(label)
        if parsed_date is None:
            logging.warning(f"Skipping calendar day: {label!r}")
            continue
        days_to_create.append(CalendarDay(
            date=parsed_date,
            label=label,
            jt=jt_by_name.get(jt_name) if jt_name else None,
            status=status,
        ))
    CalendarDay.objects.bulk_create(days_to_create)

    # ── Real appointments (rdvs_history) ──────────────────────────────────────
    _prog("Enregistrement des rendez-vous réels…", 80)
    rdvs = raw.get('rdvs_history', [])
    n_appts = _save_appointments(rdvs, metatype_map_by_value)

    _prog("Chargement terminé", 100)
    logging.info(
        f"Planning refreshed: {len(metatype_objects)} metatypes, "
        f"{len(jt_data)} JTs, {len(days_to_create)} days, {n_appts} appointments."
    )
    return {
        "metatypes": len(metatype_objects),
        "jt": len(jt_data),
        "days": len(days_to_create),
        "appointments": n_appts,
    }


def _save_appointments(rdvs: list, metatype_by_value: dict) -> int:
    """
    Parse rdvs_history, resolve patient/praticien IDs from UsersRecord,
    assign fauteils by matching JT events, then bulk-save AppointmentRecord.
    Returns the number of records saved.
    """
    AppointmentRecord.objects.all().delete()
    if not rdvs:
        return 0

    users_lookup = _build_users_lookup()

    # Build: {(jt_name, startminutes): [fauteuil_0, fauteuil_1, …]} from JT events
    jt_events_by_time: dict[tuple, list[int]] = {}
    for evt in JourneeTypeEvent.objects.select_related('jt').order_by('fauteuil'):
        key = (evt.jt.name, evt.startminutes)
        jt_events_by_time.setdefault(key, []).append(evt.fauteuil)

    # Build: {date: jt_name} from CalendarDays
    date_to_jt: dict[date, str | None] = {
        cd.date: (cd.jt.name if cd.jt else None)
        for cd in CalendarDay.objects.select_related('jt').all()
    }

    # Track how many appointments have already been assigned per (jt_name, startminutes) slot,
    # so successive appointments at the same time take successive fauteils.
    slot_usage: dict[tuple, int] = {}

    objects = []
    skipped = 0
    for row in rdvs:
        parsed = _parse_rdv_datetime(row.get('Date et heure du RDV', ''))
        if parsed is None:
            logging.warning(f"Skipping rdv — unparseable datetime: {row}")
            skipped += 1
            continue

        rdv_date, startminutes = parsed
        plage = str(row.get('Plage planning', ''))
        duration, color = _infer_duration_and_color(plage, metatype_by_value)

        patient_name   = str(row.get('Patient', ''))
        praticien_name = str(row.get('Praticien', ''))
        patient_id   = users_lookup.get(patient_name.lower(),   '')
        praticien_id = users_lookup.get(praticien_name.lower(), '')

        # Assign fauteuil: find the nth fauteuil at this JT + startminutes slot
        jt_name = date_to_jt.get(rdv_date)
        fauteuil = None
        if jt_name:
            slot_key = (jt_name, startminutes)
            available = jt_events_by_time.get(slot_key, [])
            idx = slot_usage.get(slot_key, 0)
            if idx < len(available):
                fauteuil = available[idx]
            slot_usage[slot_key] = idx + 1

        objects.append(AppointmentRecord(
            date=rdv_date,
            startminutes=startminutes,
            duration=duration,
            patient_name=patient_name,
            patient_id=patient_id,
            praticien_name=praticien_name,
            praticien_id=praticien_id,
            plage_planning=plage,
            fauteuil=fauteuil,
            color=color,
        ))

    AppointmentRecord.objects.bulk_create(objects)
    if skipped:
        logging.warning(f"Skipped {skipped} appointment row(s) during import.")
    return len(objects)


# ── Diff computation ──────────────────────────────────────────────────────────

def _compute_diffs(events: list[dict], appointments: list[dict]) -> list[dict]:
    """
    Compare JT events with real appointments on the same fauteuil.
    Uses a ±5 min tolerance on startminutes.

    Returns list of {fauteuil, startminutes, duration, type} dicts.
    type: 'missing' (in JT but no real appt) or 'extra' (real appt but no JT event).
    """
    TOLERANCE = 5

    def _find_match(pool: list[dict], fauteuil: int, start: int) -> dict | None:
        for item in pool:
            if item.get('fauteuil') == fauteuil and abs(item['startminutes'] - start) <= TOLERANCE:
                return item
        return None

    diffs = []
    matched_appt_indices: set[int] = set()

    for evt in events:
        appt = _find_match(appointments, evt['fauteuil'], evt['startminutes'])
        if appt is None:
            diffs.append({
                'fauteuil': evt['fauteuil'],
                'startminutes': evt['startminutes'],
                'duration': evt['duration'],
                'type': 'missing',
            })
        else:
            matched_appt_indices.add(id(appt))

    for appt in appointments:
        if id(appt) not in matched_appt_indices and appt.get('fauteuil') is not None:
            diffs.append({
                'fauteuil': appt['fauteuil'],
                'startminutes': appt['startminutes'],
                'duration': appt['duration'] or 25,
                'type': 'extra',
            })

    return diffs


# ── Read queries ──────────────────────────────────────────────────────────────

def get_working_days() -> list[dict]:
    qs = (
        CalendarDay.objects
        .filter(status='Ouvert')
        .select_related('jt')
        .order_by('date')
    )
    return [
        {"date": d.date.isoformat(), "label": d.label, "jt_name": d.jt.name if d.jt else None}
        for d in qs
    ]


def get_day_planning(day_date: date) -> dict | None:
    """
    Return the full planning data for a given date (JT events + real appointments + diffs),
    ready for JSON serialisation. Returns None if the date is not in the DB.
    """
    try:
        cal_day = CalendarDay.objects.select_related('jt').get(date=day_date)
    except CalendarDay.DoesNotExist:
        return None

    result: dict = {
        "date":     day_date.isoformat(),
        "label":    cal_day.label,
        "status":   cal_day.status,
        "jt_name":  None,
        "events":   [],
        "appointments": [],
        "diffs":    [],
        "fauteils": [],
        "start_time": 0,
        "end_time":   0,
    }

    # ── JT events ─────────────────────────────────────────────────────────────
    if cal_day.jt:
        events_qs = (
            JourneeTypeEvent.objects
            .filter(jt=cal_day.jt)
            .select_related('metatype')
            .order_by('fauteuil', 'startminutes')
        )
        fauteils: set[int] = set()
        min_start: int | None = None
        max_end:   int | None = None
        events = []

        for evt in events_qs:
            fauteils.add(evt.fauteuil)
            end = evt.startminutes + evt.duration
            if min_start is None or evt.startminutes < min_start:
                min_start = evt.startminutes
            if max_end is None or end > max_end:
                max_end = end
            mt = evt.metatype
            events.append({
                "fauteuil":     evt.fauteuil,
                "startminutes": evt.startminutes,
                "duration":     evt.duration,
                "color":        mt.color if mt else "#cccccc",
                "value":        mt.value if mt else "",
                "as1":          mt.as1 if mt else 0,
                "as2":          mt.as2 if mt else 0,
                "dr":           mt.dr  if mt else 0,
                "praticien_id": evt.praticien_id,
            })

        result.update({
            "jt_name":    cal_day.jt.name,
            "events":     events,
            "fauteils":   sorted(fauteils),
            "start_time": min_start or 0,
            "end_time":   max_end   or 0,
        })

    # ── Real appointments ─────────────────────────────────────────────────────
    appointments = []
    for appt in AppointmentRecord.objects.filter(date=day_date).order_by('fauteuil', 'startminutes'):
        end = appt.startminutes + appt.duration
        if result["start_time"] == 0 or appt.startminutes < result["start_time"]:
            result["start_time"] = appt.startminutes
        if end > result["end_time"]:
            result["end_time"] = end
        if appt.fauteuil is not None and appt.fauteuil not in result["fauteils"]:
            result["fauteils"] = sorted(set(result["fauteils"]) | {appt.fauteuil})
        appointments.append({
            "fauteuil":      appt.fauteuil,
            "startminutes":  appt.startminutes,
            "duration":      appt.duration,
            "patient_name":  appt.patient_name,
            "patient_id":    appt.patient_id,
            "praticien_name": appt.praticien_name,
            "praticien_id":  appt.praticien_id,
            "plage_planning": appt.plage_planning,
            "color":         appt.color,
        })

    result["appointments"] = appointments
    result["diffs"] = _compute_diffs(result["events"], appointments)
    return result


def get_adjacent_dates(day_date: date) -> tuple[date | None, date | None]:
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
