"""
loading_state.py

Thread-safe named loading states.
Each consumer (proth, income, …) gets its own isolated slot.
"""
import threading

_lock = threading.Lock()
_states: dict[str, dict] = {}


def _default() -> dict:
    return {"loading": False, "text": "", "percent": 0, "error": None}


def get(name: str = "default") -> dict:
    with _lock:
        return dict(_states.get(name, _default()))


def update(loading: bool, text: str, percent: int,
           error: str | None = None, name: str = "default") -> None:
    with _lock:
        if name not in _states:
            _states[name] = _default()
        _states[name]["loading"] = loading
        _states[name]["text"]    = text
        _states[name]["percent"] = percent
        _states[name]["error"]   = error
