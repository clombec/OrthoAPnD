"""
loading_state.py

Thread-safe singleton that tracks the background refresh progress.
"""
import threading

_lock = threading.Lock()
_state: dict = {
    "loading": False,
    "text": "",
    "percent": 0,
    "error": None,
}


def get() -> dict:
    with _lock:
        return dict(_state)


def update(loading: bool, text: str, percent: int, error: str | None = None) -> None:
    with _lock:
        _state["loading"] = loading
        _state["text"] = text
        _state["percent"] = percent
        _state["error"] = error
