"""Tests for saved search settings."""

from __future__ import annotations

import pytest

from jobhunt.config import Config, load, save
from jobhunt.sources import SOURCES


def test_load_missing_file_gives_defaults(tmp_path):
    config = load(tmp_path / "absent.json")
    assert config.keywords == []
    assert config.sources == list(SOURCES)
    assert config.limit == 50


def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / "config.json"
    config = Config(
        keywords=["python"],
        exclude=["senior"],
        locations=["london"],
        remote_only=True,
        sources=["remotive"],
        limit=7,
    )
    save(config, path)
    assert load(path) == config


def test_save_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "deeper" / "config.json"
    save(Config(), path)
    assert path.exists()


def test_from_dict_ignores_unknown_keys():
    config = Config.from_dict({"keywords": ["go"], "nonsense": True})
    assert config.keywords == ["go"]
    assert config.limit == 50


def test_load_rejects_unreadable_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="could not read config"):
        load(path)


def test_load_rejects_a_non_object(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON object"):
        load(path)


def test_criteria_reflects_settings():
    criteria = Config(keywords=["python"], remote_only=True).criteria()
    assert criteria.keywords == ("python",)
    assert criteria.remote_only is True


def test_saved_file_stays_human_editable(tmp_path):
    path = tmp_path / "config.json"
    save(Config(keywords=["python"]), path)
    assert '"keywords"' in path.read_text(encoding="utf-8")


def test_require_round_trips_into_criteria(tmp_path):
    path = tmp_path / "config.json"
    save(Config(keywords=["engineer"], require=["junior", "graduate"]), path)
    criteria = load(path).criteria()
    assert criteria.require == ("junior", "graduate")
    assert criteria.keywords == ("engineer",)
