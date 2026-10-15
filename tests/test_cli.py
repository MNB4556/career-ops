"""Tests for the command-line interface."""

from __future__ import annotations

import json

from jobhunt.cli import main


def test_add_then_list_json(tmp_path, capsys):
    db = str(tmp_path / "cli.db")
    assert main(["--db", db, "add", "--company", "Acme", "--role", "Dev"]) == 0
    capsys.readouterr()

    assert main(["--db", db, "list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 1
    assert payload[0]["company"] == "Acme"


def test_list_empty_explains_how_to_add(tmp_path, capsys):
    assert main(["--db", str(tmp_path / "empty.db"), "list"]) == 0
    assert "No applications yet" in capsys.readouterr().out


def test_update_then_stats(tmp_path, capsys):
    db = str(tmp_path / "upd.db")
    main(["--db", db, "add", "--company", "Acme", "--role", "Dev"])
    capsys.readouterr()

    assert main(["--db", db, "update", "1", "--status", "interview"]) == 0
    capsys.readouterr()

    assert main(["--db", db, "stats", "--json"]) == 0
    counts = json.loads(capsys.readouterr().out)
    assert counts["interview"] == 1


def test_show_missing_returns_error_code(tmp_path, capsys):
    assert main(["--db", str(tmp_path / "missing.db"), "show", "7"]) == 1
    assert "No application with id 7" in capsys.readouterr().err


def test_remove_missing_returns_error_code(tmp_path):
    assert main(["--db", str(tmp_path / "gone.db"), "remove", "7"]) == 1
