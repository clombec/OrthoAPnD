import json
import threading

from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie

from . import loading_state
from .services import (
    get_proth_sorted_records,
    save_proth_colors,
    sync_proth_procedures_to_config,
    refresh_proth_records_from_external,
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
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"error": str(exc)}, status=500)

@require_POST
def sync_records_view(request):
    """Trigger a manual sync from the external project."""
    try:
        _start_refresh_if_idle()
        return JsonResponse({"ok": True, "started": True})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)
