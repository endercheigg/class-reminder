import secrets
import time

# { code: { "tg": telegram_id, "created_at": timestamp } }
_pending: dict = {}

CODE_TTL = 300  # seconds (5 minutes)


def generate_code(tg_id: str) -> str:
    """Create a 6-character alphanumeric code tied to a Telegram user."""
    _cleanup()
    code = secrets.token_hex(3).upper()  # e.g. "A3F9C1"
    _pending[code] = {"tg": tg_id, "created_at": time.time()}
    return code


def consume_code(code: str) -> str | None:
    """
    Validate and consume a code.
    Returns the Telegram ID on success, or None if invalid/expired.
    """
    _cleanup()
    entry = _pending.pop(code.upper(), None)
    if entry is None:
        return None
    return entry["tg"]


def _cleanup():
    now = time.time()
    expired = [c for c, v in _pending.items() if now - v["created_at"] > CODE_TTL]
    for c in expired:
        del _pending[c]
