"""Persistent search settings.

An unattended run - a scheduled job, say - has nobody to pass flags to, so the
criteria it filters on have to live somewhere. That somewhere is a small JSON
file next to the database. Both are under ``~/.jobhunt`` and gitignored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from jobhunt.matching import Criteria
from jobhunt.sources import SOURCES

DEFAULT_CONFIG_PATH = Path.home() / ".jobhunt" / "config.json"


@dataclass
class Config:
    """Saved search settings used when the command line does not override them."""

    keywords: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    remote_only: bool = False
    sources: list[str] = field(default_factory=lambda: list(SOURCES))
    limit: int = 50

    def criteria(self) -> Criteria:
        """Return these settings as filter :class:`Criteria`."""
        return Criteria(
            keywords=tuple(self.keywords),
            exclude=tuple(self.exclude),
            locations=tuple(self.locations),
            remote_only=self.remote_only,
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable view of these settings."""
        return {
            "keywords": list(self.keywords),
            "exclude": list(self.exclude),
            "locations": list(self.locations),
            "remote_only": self.remote_only,
            "sources": list(self.sources),
            "limit": self.limit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Config:
        """Build settings from a decoded config file, ignoring unknown keys."""
        known = {key: data[key] for key in cls().to_dict() if key in data}
        return cls(**known)  # type: ignore[arg-type]


def load(path: str | Path = DEFAULT_CONFIG_PATH) -> Config:
    """Read settings from *path*, returning defaults when the file is absent."""
    config_path = Path(path)
    if not config_path.exists():
        return Config()
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"could not read config at {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"config at {config_path} must be a JSON object")
    return Config.from_dict(data)


def save(config: Config, path: str | Path = DEFAULT_CONFIG_PATH) -> Path:
    """Write *config* to *path*, creating parent directories as needed."""
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config.to_dict(), indent=2) + "\n", encoding="utf-8")
    return config_path
