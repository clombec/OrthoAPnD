import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie

from .services import (
    get_sorted_records,
    save_colors,
    sync_procedures_to_config,
    refresh_records_from_external,
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

@ensure_csrf_cookie
def home(request):
    """Display the sortable prosthesis records table."""
    sort_by = request.GET.get("sort", "patient")
    direction = request.GET.get("dir", "asc")

    if sort_by not in SORTABLE_FIELDS:
        sort_by = "patient"
    if direction not in ("asc", "desc"):
        direction = "asc"

    records = get_sorted_records(sort_by=sort_by, direction=direction)
    colors = sync_procedures_to_config()

    # Pre-compute sort URLs for each column header
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
    }
    return render(request, "dashboard/index.html", context)


@require_POST
def save_colors_view(request):
    """Receive a JSON payload and persist color config to YAML."""
    try:
        data = json.loads(request.body)
        colors = data.get("colors", {})
        if not isinstance(colors, dict):
            return JsonResponse({"error": "Invalid payload"}, status=400)
        save_colors(colors)
        return JsonResponse({"ok": True})
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"error": str(exc)}, status=500)

@require_POST
def sync_records_view(request):
    """Trigger a manual sync from the external project."""
    try:
        result = refresh_records_from_external()
        return JsonResponse({"ok": True, "result": result})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)    