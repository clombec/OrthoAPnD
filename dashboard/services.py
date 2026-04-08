import yaml
import keyring
from pathlib import Path

from orthoaget import PROJECT_ROOT
import dashboard.app_services.proth_services as proth_services

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
