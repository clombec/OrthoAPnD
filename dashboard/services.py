import yaml
import keyring
from pathlib import Path

from orthoaget import PROJECT_ROOT
import dashboard.app_services.proth_services as proth_services
import dashboard.app_services.income_services as income_services

SORTABLE_FIELDS = proth_services.SORTABLE_FIELDS

KEYRING_SERVICE = "orthoaget"

CONFIG_PATH = Path(__file__).parent / "configuration.yaml"
ORTHOAGET_CONFIG_PATH = Path(PROJECT_ROOT) / "OrthoABase" / "config.yaml"

# ── OrthoAGet setup ───────────────────────────────────────────────────────────

def is_orthoaget_configured() -> bool:
    if not ORTHOAGET_CONFIG_PATH.exists():
        return False
    login = keyring.get_password(KEYRING_SERVICE, "login")
    pwd   = keyring.get_password(KEYRING_SERVICE, "password")
    return bool(login and pwd)


def setup_orthoaget(url: str, login: str, pwd: str, webhook: str = "") -> None:
    data = {
        "connexion": {"url": url},
        "discord":   {"webhook": webhook},
    }
    ORTHOAGET_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ORTHOAGET_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
    keyring.set_password(KEYRING_SERVICE, "login",    login)
    keyring.set_password(KEYRING_SERVICE, "password", pwd)


# ── Intra PIN ────────────────────────────────────────────────────────────────

DEFAULT_INTRA_PIN = "1234"

def get_intra_pin() -> str:
    """Return the intra PIN from configuration.yaml, or the default."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        pin = data.get("intra", {}).get("pin")
        if pin:
            return str(pin)
    return DEFAULT_INTRA_PIN


# ── Proth Color config ──────────────────────────────────────────────────────────────

def sync_proth_procedures_to_config() -> dict:
    return proth_services.sync_procedures_to_config(CONFIG_PATH)

def save_proth_colors(colors: dict) -> None:
    proth_services.save_colors(CONFIG_PATH, colors)

# ── Proth Record queries ─────────────────────────────────────────────────────────────

def get_proth_sorted_records(sort_by: str = "patient", direction: str = "asc"):
    return proth_services.get_sorted_records(sort_by, direction)

def refresh_proth_records_from_external(progress_cb=None) -> dict:
    return proth_services.refresh_records_from_external(progress_cb=progress_cb)


# ── Income (recettes) ─────────────────────────────────────────────────────────

def refresh_income_from_external(progress_cb=None) -> dict:
    return income_services.refresh_income_from_external(progress_cb=progress_cb)

def get_income_by_month(year: int, month: int) -> list[dict]:
    return income_services.get_income_by_month(year=year, month=month)

def get_available_month_range():
    return income_services.get_available_month_range()
