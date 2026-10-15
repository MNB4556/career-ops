"""Tests for reading and masking API credentials."""

from __future__ import annotations

import json
from pathlib import Path

from jobhunt.credentials import (
    ENV_APP_ID,
    ENV_APP_KEY,
    AdzunaCredentials,
    load_adzuna,
    redact,
)


def write(path: Path, **values: str) -> Path:
    path.write_text(json.dumps(values), encoding="utf-8")
    return path


def clear_env(monkeypatch) -> None:
    monkeypatch.delenv(ENV_APP_ID, raising=False)
    monkeypatch.delenv(ENV_APP_KEY, raising=False)


def test_missing_file_returns_none(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    assert load_adzuna(tmp_path / "nope.json") is None


def test_reads_a_credentials_file(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    path = write(tmp_path / "c.json", adzuna_app_id="id123", adzuna_app_key="key456")
    assert load_adzuna(path) == AdzunaCredentials(app_id="id123", app_key="key456")


def test_environment_wins_over_the_file(tmp_path, monkeypatch):
    path = write(tmp_path / "c.json", adzuna_app_id="file", adzuna_app_key="file")
    monkeypatch.setenv(ENV_APP_ID, "env")
    monkeypatch.setenv(ENV_APP_KEY, "env")
    assert load_adzuna(path) == AdzunaCredentials(app_id="env", app_key="env")


def test_a_byte_order_mark_is_tolerated(tmp_path, monkeypatch):
    """PowerShell's `Set-Content -Encoding utf8` writes a BOM."""
    clear_env(monkeypatch)
    path = tmp_path / "bom.json"
    path.write_text(json.dumps({"adzuna_app_id": "a", "adzuna_app_key": "b"}), encoding="utf-8-sig")
    assert load_adzuna(path) == AdzunaCredentials(app_id="a", app_key="b")


def test_partial_and_broken_files_are_ignored(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    assert load_adzuna(write(tmp_path / "half.json", adzuna_app_id="only")) is None
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert load_adzuna(broken) is None


def test_redact_hides_both_query_secrets():
    url = "https://api.adzuna.com/v1/api/jobs/gb/search/1?app_id=abc&app_key=deadbeef&what=x"
    masked = redact(url)
    assert "abc" not in masked
    assert "deadbeef" not in masked
    assert "app_id=***" in masked
    assert "app_key=***" in masked
    assert "what=x" in masked
