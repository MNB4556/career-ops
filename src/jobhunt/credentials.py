"""Local API credentials, read from outside the repository.

Adzuna is the one source that needs a key. That key is read from the
environment or from ``~/.jobhunt/credentials.json`` - never from the
repository, and never written back to it - and any URL carrying it is masked
before it can reach a log or an error message.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CREDENTIALS_PATH = Path.home() / ".jobhunt" / "credentials.json"

ENV_APP_ID = "ADZUNA_APP_ID"
ENV_APP_KEY = "ADZUNA_APP_KEY"

_MASKED_PARAM_RE = re.compile(r"(?i)\b(app_(?:id|key)=)[^&\s]+")


def redact(text: str) -> str:
    """Mask credential-looking query parameters so they cannot reach a log."""
    return _MASKED_PARAM_RE.sub(r"\1***", text)


@dataclass(frozen=True)
class AdzunaCredentials:
    """An Adzuna app id/key pair. Never print or log these."""

    app_id: str
    app_key: str


def load_adzuna(path: str | Path = DEFAULT_CREDENTIALS_PATH) -> AdzunaCredentials | None:
    """Return Adzuna credentials from the environment or *path*, or ``None``.

    Environment variables win, so a scheduled run can be handed credentials
    without anything being written to disk. A byte-order mark is tolerated
    because PowerShell's ``Set-Content -Encoding utf8`` writes one.
    """
    app_id = os.environ.get(ENV_APP_ID, "").strip()
    app_key = os.environ.get(ENV_APP_KEY, "").strip()
    if app_id and app_key:
        return AdzunaCredentials(app_id=app_id, app_key=app_key)

    credentials_path = Path(path)
    if not credentials_path.exists():
        return None
    try:
        data = json.loads(credentials_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    app_id = str(data.get("adzuna_app_id") or "").strip()
    app_key = str(data.get("adzuna_app_key") or "").strip()
    if not app_id or not app_key:
        return None
    return AdzunaCredentials(app_id=app_id, app_key=app_key)
