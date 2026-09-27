"""Server-side MAX WebApp initData validation (MAX docs, checked 2026-09-27)."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from urllib.parse import unquote

from app.errors import ApiError


_BAD_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def validate_init_data(raw: str, bot_token: str, *, current_time: int | None = None) -> int:
    """Return authenticated MAX user id; never expose or retain the raw data."""
    invalid = lambda: ApiError(401, "INVALID_MAX_AUTH", "Не удалось проверить вход MAX.")
    if not isinstance(raw, str) or not 1 <= len(raw) <= 8192 or _BAD_PERCENT.search(raw):
        raise invalid()
    values: dict[str, str] = {}
    for pair in raw.split("&"):
        key, separator, encoded_value = pair.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key) or key in values:
            raise invalid()
        try:
            values[key] = unquote(encoded_value, encoding="utf-8", errors="strict")
        except UnicodeDecodeError:
            raise invalid() from None
    supplied_hash = values.pop("hash", None)
    if supplied_hash is None or not _HASH.fullmatch(supplied_hash) or not bot_token:
        raise invalid()
    launch_params = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, launch_params.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, supplied_hash):
        raise invalid()
    try:
        auth_date = int(values["auth_date"])
        user = json.loads(values["user"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise invalid() from None
    moment = int(time.time()) if current_time is None else current_time
    if not (moment - 300 <= auth_date <= moment + 30):
        raise invalid()
    if not isinstance(user, dict) or type(user.get("id")) is not int or user["id"] <= 0:
        raise invalid()
    return user["id"]
