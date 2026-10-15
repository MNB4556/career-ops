"""Tests for the storage layer."""

from __future__ import annotations

import pytest

from jobhunt.models import Application
from jobhunt.storage import Store


@pytest.fixture()
def store(tmp_path):
    with Store(tmp_path / "test.db") as opened:
        yield opened


def test_add_assigns_id_and_timestamps(store):
    application = store.add(Application(company="Acme", role="Backend Engineer"))
    assert application.id == 1
    assert application.status == "saved"
    assert application.created_at
    assert application.updated_at


def test_get_roundtrip(store):
    created = store.add(Application(company="Acme", role="Dev", url="https://example.com/job"))
    assert store.get(created.id) == created


def test_get_missing_returns_none(store):
    assert store.get(999) is None


def test_list_filters_by_status(store):
    store.add(Application(company="A", role="Dev", status="applied"))
    store.add(Application(company="B", role="Dev", status="rejected"))
    assert [a.company for a in store.list("applied")] == ["A"]
    assert len(store.list()) == 2


def test_update_status_records_notes(store):
    application = store.add(Application(company="A", role="Dev"))
    updated = store.update_status(application.id, "interview", notes="call booked")
    assert updated.status == "interview"
    assert updated.notes == "call booked"


def test_update_missing_raises(store):
    with pytest.raises(KeyError):
        store.update_status(4242, "offer")


def test_delete(store):
    application = store.add(Application(company="A", role="Dev"))
    assert store.delete(application.id) is True
    assert store.delete(application.id) is False


def test_stats_counts_every_status(store):
    store.add(Application(company="A", role="Dev", status="applied"))
    store.add(Application(company="B", role="Dev", status="applied"))
    store.add(Application(company="C", role="Dev", status="offer"))
    counts = store.stats()
    assert counts["applied"] == 2
    assert counts["offer"] == 1
    assert counts["total"] == 3


def test_invalid_status_is_rejected():
    with pytest.raises(ValueError):
        Application(company="A", role="Dev", status="ghosted")


def test_blank_company_is_rejected():
    with pytest.raises(ValueError):
        Application(company="   ", role="Dev")
