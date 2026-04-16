"""
calendar_services.py

Load and store planning data from OrthoAdvance via OrthoASession.get_calendar_records().

Supported raw formats:

  New format (days list, jt_name known per day):
    {
      "jt": { "JT Name": [...] },   # optional: JT templates
      "days": [
        {
          "date": "2026-04-15",
          "jt_name": "Mercredi petites vacances / reprise (avec collab)",
          "events": [
            {"date": "2026-04-15T11:45:00+02:00", "startminutes": 705,
             "duration": 10, "praticien_id": "7", "fauteuil": "F3", "patient_id": null},
            ...
          ]
        },
        ...
      ]
    }

  Legacy format (flat events, auto-matching needed):
    {
      "jt": { "JT Name": [...] },
      "events": [
        {"date": "2026-04-15T11:45:00+02:00", "startminutes": 705, ...},
        ...
      ]
    }
"""
import logging
from datetime import date, datetime

from dashboard.models import AppointmentRecord, DayRecord, JourneeType, JourneeTypeEvent
from orthoaget.session import OrthoASession

# ── Availability ──────────────────────────────────────────────────────────────

def is_data_available() -> bool:
    return AppointmentRecord.objects.exists()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_event_date(value: str) -> date | None:
    """Parse ISO datetime string (with or without timezone) → date."""
    try:
        return datetime.fromisoformat(str(value).strip()).date()
    except (ValueError, TypeError):
        return None


# ── External refresh ──────────────────────────────────────────────────────────

def refresh_records_from_external(progress_cb=None) -> dict:
    """
    Fetch all planning data from OrthoAdvance and populate the DB.
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

    # ── Journées types ────────────────────────────────────────────────────────
    _prog("Enregistrement des journées types…", 40)
    JourneeTypeEvent.objects.all().delete()
    JourneeType.objects.all().delete()

    jt_data = raw.get("jt", {})
    events_to_create = []
    for jt_name, jt_events in jt_data.items():
        jt_obj = JourneeType.objects.create(name=jt_name)
        for evt in jt_events:
            mt = evt.get("metatype") or {}
            events_to_create.append(JourneeTypeEvent(
                jt=jt_obj,
                fauteuil=str(evt.get("fauteuil", "")),
                startminutes=int(evt.get("startminutes", 0)),
                duration=int(evt.get("duration", 0)),
                praticien_id=str(evt.get("praticien_id", "")),
                mt_value=str(mt.get("value", "")),
                mt_color=str(mt.get("color", "#cccccc")),
                mt_as1=int(mt.get("as1", 0)),
                mt_as2=int(mt.get("as2", 0)),
                mt_dr=int(mt.get("dr", 0)),
                mt_duree=int(mt.get("duree", 0)),
            ))
    JourneeTypeEvent.objects.bulk_create(events_to_create)

    # ── Real appointments ─────────────────────────────────────────────────────
    _prog("Enregistrement des rendez-vous…", 70)
    AppointmentRecord.objects.all().delete()
    DayRecord.objects.all().delete()

    days_data = raw.get("days")
    appt_objects: list = []
    skipped = 0

    if days_data is not None:
        # ── New format: events grouped by day, jt_name known per day ─────────
        day_records: list = []
        for day in days_data:
            parsed_date = _parse_event_date(day.get("date", ""))
            if parsed_date is None:
                logging.warning(f"Skipping day — unparseable date: {day.get('date')}")
                skipped += 1
                continue
            jt_name = day.get("jt_name") or ""
            if jt_name:
                day_records.append(DayRecord(date=parsed_date, jt_name=jt_name))
            for evt in day.get("events", []):
                patient_id = evt.get("patient_id")
                appt_objects.append(AppointmentRecord(
                    date=parsed_date,
                    startminutes=int(evt.get("startminutes", 0)),
                    duration=int(evt.get("duration", 0)),
                    fauteuil=str(evt.get("fauteuil", "")),
                    praticien_id=str(evt.get("praticien_id", "")),
                    patient_id=str(patient_id) if patient_id is not None else None,
                ))
        DayRecord.objects.bulk_create(day_records)
        AppointmentRecord.objects.bulk_create(appt_objects)
    else:
        # ── Legacy format: flat events list ───────────────────────────────────
        for evt in raw.get("events", []):
            parsed_date = _parse_event_date(evt.get("date", ""))
            if parsed_date is None:
                logging.warning(f"Skipping event — unparseable date: {evt}")
                skipped += 1
                continue
            patient_id = evt.get("patient_id")
            appt_objects.append(AppointmentRecord(
                date=parsed_date,
                startminutes=int(evt.get("startminutes", 0)),
                duration=int(evt.get("duration", 0)),
                fauteuil=str(evt.get("fauteuil", "")),
                praticien_id=str(evt.get("praticien_id", "")),
                patient_id=str(patient_id) if patient_id is not None else None,
            ))
        AppointmentRecord.objects.bulk_create(appt_objects)

    _prog("Chargement terminé", 100)
    logging.info(
        f"Calendar refreshed: {len(jt_data)} JTs, "
        f"{len(events_to_create)} JT events, "
        f"{len(appt_objects)} appointments ({skipped} skipped)."
    )
    return {
        "jt": len(jt_data),
        "jt_events": len(events_to_create),
        "appointments": len(appt_objects),
    }


# ── Diff computation ──────────────────────────────────────────────────────────

DIFF_TOLERANCE = 5  # minutes

def _compute_diffs(jt_events: list[dict], real_events: list[dict]) -> dict:
    """
    Compare JT template events with real appointments on the same fauteuil.
    Returns {"missing": [...], "extra": [...]} where:
      - missing = in JT but no matching real event (±DIFF_TOLERANCE min)
      - extra   = in real but no matching JT event
    Each entry keeps the source dict + a "fauteuil" key.
    """
    matched_real: set[int] = set()
    missing = []

    for jt_evt in jt_events:
        match = next(
            (i for i, r in enumerate(real_events)
             if r["fauteuil"] == jt_evt["fauteuil"]
             and abs(r["startminutes"] - jt_evt["startminutes"]) <= DIFF_TOLERANCE),
            None,
        )
        if match is None:
            missing.append(jt_evt)
        else:
            matched_real.add(match)

    extra = [r for i, r in enumerate(real_events) if i not in matched_real]
    return {"missing": missing, "extra": extra}


# ── JT auto-match ─────────────────────────────────────────────────────────────

def auto_match_jt(day_date: date) -> str | None:
    """
    Find the JT whose template best matches the real appointments of day_date.
    Scoring: fauteuil overlap (×10) + startminutes overlap.
    Returns the JT name or None if no JTs or no appointments.
    """
    real_qs = AppointmentRecord.objects.filter(date=day_date)
    if not real_qs.exists():
        return None

    real_fauteils = set(real_qs.values_list("fauteuil", flat=True))
    real_starts   = set(real_qs.values_list("startminutes", flat=True))

    best_name  = None
    best_score = -1

    for jt in JourneeType.objects.prefetch_related("events").all():
        jt_fauteils = set(jt.events.values_list("fauteuil", flat=True))
        jt_starts   = set(jt.events.values_list("startminutes", flat=True))
        score = len(real_fauteils & jt_fauteils) * 10 + len(real_starts & jt_starts)
        if score > best_score:
            best_score = score
            best_name  = jt.name

    return best_name


# ── Read queries ──────────────────────────────────────────────────────────────

def get_available_dates() -> list[str]:
    """Return sorted list of 'YYYY-MM-DD' strings that have at least one appointment."""
    return list(
        AppointmentRecord.objects
        .values_list("date", flat=True)
        .distinct()
        .order_by("date")
        .values_list("date", flat=True)
    )


def get_day_planning(day_date: date) -> dict:
    """
    Return all appointments for a given date, ready for JSON serialisation.
    """
    qs = (
        AppointmentRecord.objects
        .filter(date=day_date)
        .order_by("fauteuil", "startminutes")
    )

    appointments = []
    fauteils_seen: set[str] = set()
    min_start: int | None = None
    max_end:   int | None = None

    for appt in qs:
        fauteils_seen.add(appt.fauteuil)
        end = appt.startminutes + appt.duration
        if min_start is None or appt.startminutes < min_start:
            min_start = appt.startminutes
        if max_end is None or end > max_end:
            max_end = end
        appointments.append({
            "fauteuil":    appt.fauteuil,
            "startminutes": appt.startminutes,
            "duration":    appt.duration,
            "praticien_id": appt.praticien_id,
            "patient_id":  appt.patient_id,
        })

    # Natural sort for fauteuil labels (F1 < F1b < F2 < F2b < F3)
    def _fauteuil_key(f: str):
        import re
        parts = re.split(r'(\d+)', f)
        return [int(p) if p.isdigit() else p for p in parts]

    return {
        "date":         day_date.isoformat(),
        "fauteils":     sorted(fauteils_seen, key=_fauteuil_key),
        "start_time":   min_start or 570,
        "end_time":     max_end   or 1080,
        "appointments": appointments,
    }


def get_day_planning_with_jt(day_date: date, jt_name: str | None = None) -> dict:
    """
    Return real appointments for day_date combined with the JT template
    (from DayRecord, auto-matched, or explicitly named) and computed diffs.
    """
    day = get_day_planning(day_date)

    if jt_name is None:
        # New format: jt_name stored per day in DayRecord
        try:
            day_record = DayRecord.objects.get(date=day_date)
            jt_name = day_record.jt_name or None
        except DayRecord.DoesNotExist:
            # Legacy: auto-match from appointment patterns
            jt_name = auto_match_jt(day_date)

    jt_info = get_jt_events(jt_name) if jt_name else {}

    real_events = day["appointments"]
    jt_events   = jt_info.get("events", [])

    diffs = _compute_diffs(jt_events, real_events)

    # Merge fauteils from both sources
    import re
    def _fkey(f):
        parts = re.split(r'(\d+)', f)
        return [int(p) if p.isdigit() else p for p in parts]

    all_fauteils = sorted(
        set(day["fauteils"]) | set(jt_info.get("fauteils", [])),
        key=_fkey,
    )

    # Widen time window to cover both sources
    start = min(day.get("start_time", 570),  jt_info.get("start_time", 570))
    end   = max(day.get("end_time",   1080), jt_info.get("end_time",   1080))

    # Fauteils that have at least one diff
    diff_fauteils = set(
        e["fauteuil"] for e in diffs["missing"] + diffs["extra"]
    )

    return {
        "date":          day_date.isoformat(),
        "fauteils":      all_fauteils,
        "diff_fauteils": list(diff_fauteils),
        "start_time":    start,
        "end_time":      end,
        "jt_name":       jt_name,
        "jt_events":     jt_events,
        "appointments":  real_events,
        "diffs":         diffs,
    }


def get_jt_list() -> list[str]:
    """Return all available JT names."""
    return list(JourneeType.objects.values_list("name", flat=True).order_by("name"))


def get_jt_events(jt_name: str) -> dict:
    """
    Return all events for a given JT, grouped by fauteuil.
    """
    try:
        jt = JourneeType.objects.get(name=jt_name)
    except JourneeType.DoesNotExist:
        return {}

    events = []
    fauteils_seen: set[str] = set()
    min_start: int | None = None
    max_end:   int | None = None

    for evt in jt.events.order_by("fauteuil", "startminutes"):
        fauteils_seen.add(evt.fauteuil)
        end = evt.startminutes + evt.duration
        if min_start is None or evt.startminutes < min_start:
            min_start = evt.startminutes
        if max_end is None or end > max_end:
            max_end = end
        events.append({
            "fauteuil":     evt.fauteuil,
            "startminutes": evt.startminutes,
            "duration":     evt.duration,
            "praticien_id": evt.praticien_id,
            "mt_value":     evt.mt_value,
            "mt_color":     evt.mt_color,
            "mt_as1":       evt.mt_as1,
            "mt_as2":       evt.mt_as2,
            "mt_dr":        evt.mt_dr,
            "mt_duree":     evt.mt_duree,
        })

    def _fauteuil_key(f: str):
        import re
        parts = re.split(r'(\d+)', f)
        return [int(p) if p.isdigit() else p for p in parts]

    return {
        "jt_name":    jt_name,
        "fauteils":   sorted(fauteils_seen, key=_fauteuil_key),
        "start_time": min_start or 570,
        "end_time":   max_end   or 1080,
        "events":     events,
    }


def get_adjacent_dates(day_date: date) -> tuple[date | None, date | None]:
    prev = (
        AppointmentRecord.objects
        .filter(date__lt=day_date)
        .order_by("-date")
        .values_list("date", flat=True)
        .first()
    )
    nxt = (
        AppointmentRecord.objects
        .filter(date__gt=day_date)
        .order_by("date")
        .values_list("date", flat=True)
        .first()
    )
    return prev, nxt


def get_nearest_date(ref: date) -> date | None:
    """Return the nearest date >= ref that has appointments, or the latest past one."""
    day = (
        AppointmentRecord.objects
        .filter(date__gte=ref)
        .order_by("date")
        .values_list("date", flat=True)
        .first()
    )
    if day:
        return day
    return (
        AppointmentRecord.objects
        .order_by("-date")
        .values_list("date", flat=True)
        .first()
    )
