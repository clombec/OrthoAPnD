import json
import threading
from functools import wraps

from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import ensure_csrf_cookie

from . import loading_state
from .services import (
    get_proth_sorted_records,
    save_proth_colors,
    sync_proth_procedures_to_config,
    refresh_proth_records_from_external,
    refresh_income_from_external,
    get_income_by_month,
    get_income_by_year,
    get_income_all_years,
    get_available_month_range,
    get_available_year_range,
    get_intra_pin,
    is_orthoaget_configured,
    setup_orthoaget,
    SORTABLE_FIELDS,
)

# Column definitions: (field_name, display_label)
COLUMNS = [
    ("prosthetist",      "Prothésiste"),
    ("patient",          "Patient"),
    ("procedure",        "Acte"),
    ("send_date",        "Envoi"),
    ("receive_date",     "Réception"),
    ("impression_date",  "PE"),
    ("duration",         "Durée (m)"),
    ("appointment_date", "RDV"),
]

# ── Background refresh ────────────────────────────────────────────────────────

_refresh_lock = threading.Lock()
_refresh_thread: threading.Thread | None = None


def _run_refresh() -> None:
    global _refresh_thread
    try:
        def progress(text: str, percent: int) -> None:
            loading_state.update(True, text, percent)

        refresh_proth_records_from_external(progress_cb=progress)
        loading_state.update(False, "Chargement terminé", 100)
    except Exception as exc:
        loading_state.update(False, "", 0, error=str(exc))
    finally:
        with _refresh_lock:
            _refresh_thread = None


def _start_refresh_if_idle() -> None:
    """Launch the background refresh thread if none is already running."""
    global _refresh_thread
    with _refresh_lock:
        if _refresh_thread is not None:
            return
        loading_state.update(True, "Démarrage du chargement…", 0)
        _refresh_thread = threading.Thread(target=_run_refresh, daemon=True)
        _refresh_thread.start()


# ── Intra PIN auth ────────────────────────────────────────────────────────────

SESSION_KEY = "intra_authenticated"


def require_intra_auth(view_fn):
    """Decorator: redirect to PIN page if the user is not intra-authenticated."""
    @wraps(view_fn)
    def wrapper(request, *args, **kwargs):
        if not request.session.get(SESSION_KEY):
            return redirect("intra_pin")
        return view_fn(request, *args, **kwargs)
    return wrapper


# ── Views ─────────────────────────────────────────────────────────────────────

def landing(request):
    if not is_orthoaget_configured():
        return redirect("setup")
    return render(request, "dashboard/landing.html")


@ensure_csrf_cookie
def setup_view(request):
    if is_orthoaget_configured():
        return redirect("home")

    error = None
    if request.method == "POST":
        url     = request.POST.get("url",      "").strip()
        login   = request.POST.get("login",    "").strip()
        pwd     = request.POST.get("password", "").strip()
        webhook = request.POST.get("webhook",  "").strip()

        if not url or not login or not pwd:
            error = "L'URL, le login et le mot de passe sont obligatoires."
        else:
            setup_orthoaget(url, login, pwd, webhook)
            return redirect("home")

    return render(request, "dashboard/setup.html", {"error": error})


@ensure_csrf_cookie
def home(request):
    sort_by = request.GET.get("sort", "patient")
    direction = request.GET.get("dir", "asc")

    if sort_by not in SORTABLE_FIELDS:
        sort_by = "patient"
    if direction not in ("asc", "desc"):
        direction = "asc"

    from urllib.parse import urlparse
    cache_control = request.META.get("HTTP_CACHE_CONTROL", "")
    referer = request.META.get("HTTP_REFERER", "")
    is_browser_refresh = "max-age=0" in cache_control or "no-cache" in cache_control
    from_landing = urlparse(referer).path.rstrip("/") == ""  # referer path = "/"
    if not referer or is_browser_refresh or from_landing:
        _start_refresh_if_idle()

    state = loading_state.get()
    is_loading = state["loading"]

    records = get_proth_sorted_records(sort_by=sort_by, direction=direction)
    colors = sync_proth_procedures_to_config()

    columns_with_urls = []
    for field, label in COLUMNS:
        next_dir = "desc" if (sort_by == field and direction == "asc") else "asc"
        url = f"?sort={field}&dir={next_dir}"
        columns_with_urls.append((field, label, url))

    context = {
        "records": records,
        "columns_with_urls": columns_with_urls,
        "sort_by": sort_by,
        "direction": direction,
        "colors": colors,
        "colors_json": json.dumps(colors),
        "is_loading": is_loading,
        "loading_text": state["text"],
        "loading_percent": state["percent"],
    }
    return render(request, "dashboard/index.html", context)


def loading_status_view(request):
    """Return the current background-refresh state as JSON."""
    return JsonResponse(loading_state.get())


@require_POST
def save_colors_view(request):
    """Receive a JSON payload and persist color config to YAML."""
    try:
        data = json.loads(request.body)
        colors = data.get("colors", {})
        if not isinstance(colors, dict):
            return JsonResponse({"error": "Invalid payload"}, status=400)
        save_proth_colors(colors)
        return JsonResponse({"ok": True})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@require_POST
def sync_records_view(request):
    """Trigger a manual sync from the external project."""
    try:
        _start_refresh_if_idle()
        return JsonResponse({"ok": True, "started": True})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


# ── Intra views ───────────────────────────────────────────────────────────────

@ensure_csrf_cookie
def intra_pin_view(request):
    """PIN login page for the intranet section."""
    if request.session.get(SESSION_KEY):
        return redirect("intra_landing")

    error = None
    if request.method == "POST":
        pin = request.POST.get("pin", "").strip()
        if pin == get_intra_pin():
            request.session[SESSION_KEY] = True
            return redirect("intra_landing")
        error = "Code PIN incorrect."

    return render(request, "dashboard/intra_pin.html", {"error": error})


@require_intra_auth
def intra_landing_view(request):
    return render(request, "dashboard/landing_intra.html")


MONTH_NAMES = [
    "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]


@require_intra_auth
def recettes_view(request):
    from datetime import date
    today = date.today()

    view_type = request.GET.get("view", "daily")
    if view_type not in ("daily", "monthly", "yearly"):
        view_type = "daily"

    year  = int(request.GET.get("year",  today.year))
    month = int(request.GET.get("month", today.month))

    has_prev = has_next = False
    prev_year = prev_month = next_year = next_month = None

    if view_type == "yearly":
        data = get_income_all_years()

    elif view_type == "monthly":
        data = get_income_by_year(year)
        year_range = get_available_year_range()
        if year_range:
            first_year, last_year = year_range
            has_prev = year > first_year
            has_next = year < last_year
        prev_year, next_year = year - 1, year + 1
        prev_month = next_month = month

    else:  # daily
        data = get_income_by_month(year, month)
        month_range = get_available_month_range()
        current_ym = f"{year:04d}-{month:02d}"
        if month_range:
            first_ym, last_ym = month_range
            has_prev = current_ym > first_ym
            has_next = current_ym < last_ym
        prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
        next_year, next_month = (year + 1,  1) if month == 12 else (year, month + 1)

    return render(request, "dashboard/recettes.html", {
        "chart_data_json": json.dumps(data),
        "view_type":  view_type,
        "year":       year,
        "month":      month,
        "month_name": MONTH_NAMES[month],
        "has_prev":   has_prev,
        "has_next":   has_next,
        "prev_year":  prev_year,
        "prev_month": prev_month,
        "next_year":  next_year,
        "next_month": next_month,
    })


_income_refresh_lock = threading.Lock()
_income_refresh_thread: threading.Thread | None = None


def _run_income_refresh() -> None:
    global _income_refresh_thread
    try:
        def progress(text: str, percent: int) -> None:
            loading_state.update(True, text, percent, name="income")

        refresh_income_from_external(progress_cb=progress)
        loading_state.update(False, "Chargement terminé", 100, name="income")
    except Exception as exc:
        loading_state.update(False, "", 0, error=str(exc), name="income")
    finally:
        with _income_refresh_lock:
            _income_refresh_thread = None


def _start_income_refresh_if_idle() -> bool:
    """Start background income refresh. Returns True if started, False if already running."""
    global _income_refresh_thread
    with _income_refresh_lock:
        if _income_refresh_thread is not None:
            return False
        loading_state.update(True, "Démarrage du chargement…", 0, name="income")
        _income_refresh_thread = threading.Thread(target=_run_income_refresh, daemon=True)
        _income_refresh_thread.start()
        return True


@require_POST
@require_intra_auth
def recettes_refresh_view(request):
    """Start a background income refresh."""
    started = _start_income_refresh_if_idle()
    return JsonResponse({"ok": True, "started": started})


@require_GET
@require_intra_auth
def recettes_loading_status_view(request):
    """Return the income refresh state as JSON."""
    return JsonResponse(loading_state.get(name="income"))


@require_GET
@require_intra_auth
def recettes_data_view(request):
    """Return income data as JSON for the chart (view-type aware)."""
    from datetime import date
    today = date.today()
    view_type = request.GET.get("view", "daily")
    year  = int(request.GET.get("year",  today.year))
    month = int(request.GET.get("month", today.month))

    if view_type == "yearly":
        data = get_income_all_years()
    elif view_type == "monthly":
        data = get_income_by_year(year)
    else:
        data = get_income_by_month(year, month)

    return JsonResponse({"data": data})
