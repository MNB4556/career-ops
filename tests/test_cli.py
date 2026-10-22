"""Tests for the command-line interface."""

from __future__ import annotations

import json

from jobhunt import sources as source_module
from jobhunt.cli import main
from jobhunt.sources import SourceError


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


REMOTIVE_FIXTURE = {
    "jobs": [
        {
            "id": 1,
            "title": "Python Developer",
            "company_name": "Acme",
            "tags": ["python"],
            "candidate_required_location": "Worldwide",
            "description": "<p>Write python</p>",
            "url": "https://example.com/1",
        },
        {
            "id": 2,
            "title": "Sales Lead",
            "company_name": "Beta",
            "tags": ["sales"],
            "candidate_required_location": "Worldwide",
            "description": "<p>Sell things</p>",
            "url": "https://example.com/2",
        },
    ]
}


def _fixture(tmp_path):
    """Write the sample payload and return (payload_path, db_path, config_path)."""
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps(REMOTIVE_FIXTURE), encoding="utf-8")
    return str(payload), str(tmp_path / "fetch.db"), str(tmp_path / "config.json")


def test_fetch_from_file_reports_only_matches(tmp_path, capsys):
    payload, db, config = _fixture(tmp_path)
    code = main(
        [
            "--db",
            db,
            "--config",
            config,
            "fetch",
            "--from-file",
            payload,
            "--source",
            "remotive",
            "--keyword",
            "python",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Python Developer" in out
    assert "Sales Lead" not in out


def test_fetch_from_file_persists_postings_for_later(tmp_path, capsys):
    payload, db, config = _fixture(tmp_path)
    main(["--db", db, "--config", config, "fetch", "--from-file", payload, "--source", "remotive"])
    capsys.readouterr()

    assert main(["--db", db, "--config", config, "matches", "--json"]) == 0
    stored = json.loads(capsys.readouterr().out)
    assert {item["title"] for item in stored} == {"Python Developer", "Sales Lead"}


def test_fetch_json_reports_counts(tmp_path, capsys):
    payload, db, config = _fixture(tmp_path)
    main(
        [
            "--db",
            db,
            "--config",
            config,
            "fetch",
            "--from-file",
            payload,
            "--source",
            "remotive",
            "--json",
        ]
    )
    body = json.loads(capsys.readouterr().out)
    assert body["fetched"] == 2
    assert body["new"] == 2
    assert body["matching"] == 2


def test_fetch_digest_is_message_friendly(tmp_path, capsys):
    payload, db, config = _fixture(tmp_path)
    main(
        [
            "--db",
            db,
            "--config",
            config,
            "fetch",
            "--from-file",
            payload,
            "--source",
            "remotive",
            "--digest",
        ]
    )
    assert capsys.readouterr().out.startswith("Job digest:")


def test_fetch_from_file_needs_exactly_one_source(tmp_path, capsys):
    payload, db, config = _fixture(tmp_path)
    code = main(
        [
            "--db",
            db,
            "--config",
            config,
            "fetch",
            "--from-file",
            payload,
            "--source",
            "remotive",
            "--source",
            "arbeitnow",
        ]
    )
    assert code == 2
    assert "exactly one --source" in capsys.readouterr().err


def test_fetch_missing_file_returns_error(tmp_path, capsys):
    code = main(
        [
            "--db",
            str(tmp_path / "x.db"),
            "--config",
            str(tmp_path / "c.json"),
            "fetch",
            "--from-file",
            str(tmp_path / "absent.json"),
            "--source",
            "remotive",
        ]
    )
    assert code == 2
    assert "could not read" in capsys.readouterr().err


def test_digest_names_a_source_that_did_not_respond(tmp_path, capsys, monkeypatch):
    """A partial fetch must not read as a complete digest."""
    _payload, db, config = _fixture(tmp_path)
    stored = source_module.parse("remotive", REMOTIVE_FIXTURE)

    def fake_fetch(name, limit=50, queries=(), where=None):
        if name == "adzuna":
            raise SourceError("HTTP Error 503: Service Temporarily Unavailable")
        return list(stored)

    monkeypatch.setattr(source_module, "fetch", fake_fetch)
    args = [
        "--db",
        db,
        "--config",
        config,
        "fetch",
        "--source",
        "adzuna",
        "--source",
        "remotive",
        "--digest",
    ]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "Job digest:" in out
    assert "Note: adzuna did not respond" in out


def test_digest_stays_quiet_when_every_source_answers(tmp_path, capsys, monkeypatch):
    _payload, db, config = _fixture(tmp_path)
    stored = source_module.parse("remotive", REMOTIVE_FIXTURE)
    monkeypatch.setattr(source_module, "fetch", lambda *a, **k: list(stored))

    args = ["--db", db, "--config", config, "fetch", "--source", "remotive", "--digest"]
    assert main(args) == 0
    assert "did not respond" not in capsys.readouterr().out


def test_save_promotes_a_posting(tmp_path, capsys):
    payload, db, config = _fixture(tmp_path)
    main(["--db", db, "--config", config, "fetch", "--from-file", payload, "--source", "remotive"])
    capsys.readouterr()

    assert main(["--db", db, "--config", config, "save", "1"]) == 0
    assert "Saved application #1" in capsys.readouterr().out

    assert main(["--db", db, "--config", config, "list", "--json"]) == 0
    applications = json.loads(capsys.readouterr().out)
    assert applications[0]["role"] == "Python Developer"
    assert applications[0]["source"] == "remotive"
    assert applications[0]["status"] == "saved"


def test_listed_number_is_the_id_that_save_accepts(tmp_path, capsys):
    """The number shown must be the posting id, not its rank in the list."""
    payload, db, config = _fixture(tmp_path)
    main(
        [
            "--db",
            db,
            "--config",
            config,
            "fetch",
            "--from-file",
            payload,
            "--source",
            "remotive",
            "--keyword",
            "sales",
        ]
    )
    out = capsys.readouterr().out
    assert "\n   2. Sales Lead" in out  # second posting fetched, so id 2

    assert main(["--db", db, "--config", config, "save", "2"]) == 0
    assert "Saved application #1: Beta - Sales Lead" in capsys.readouterr().out


def test_fetch_and_matches_agree_on_tie_order(tmp_path, capsys):
    """Both commands must rank equal-scoring postings the same way."""
    payload, db, config = _fixture(tmp_path)
    main(
        [
            "--db",
            db,
            "--config",
            config,
            "fetch",
            "--from-file",
            payload,
            "--source",
            "remotive",
            "--json",
        ]
    )
    fetched_first = json.loads(capsys.readouterr().out)["matches"][0]["id"]

    assert main(["--db", db, "--config", config, "matches", "--json"]) == 0
    stored_first = json.loads(capsys.readouterr().out)[0]["id"]

    assert fetched_first == stored_first


def test_fetch_requires_are_anded_with_keywords(tmp_path, capsys):
    """--keyword picks the field; --require picks the level; both must hold."""
    payload = {
        "jobs": [
            {
                "id": 1,
                "title": "Junior Software Engineer",
                "company_name": "Acme",
                "candidate_required_location": "London",
                "description": "<p>graduate scheme</p>",
            },
            {
                "id": 2,
                "title": "Senior Software Engineer",
                "company_name": "Beta",
                "candidate_required_location": "London",
                "description": "<p>ten years</p>",
            },
            {
                "id": 3,
                "title": "Junior Sales Executive",
                "company_name": "Gamma",
                "candidate_required_location": "London",
                "description": "<p>sales</p>",
            },
        ]
    }
    path = tmp_path / "level.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    code = main(
        [
            "--db",
            str(tmp_path / "level.db"),
            "--config",
            str(tmp_path / "level-cfg.json"),
            "fetch",
            "--from-file",
            str(path),
            "--source",
            "remotive",
            "--keyword",
            "engineer",
            "--require",
            "junior",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "1 new match" in out
    assert "Junior Software Engineer" in out
    assert "Senior Software Engineer" not in out
    assert "Junior Sales Executive" not in out


def test_criteria_persists_require(tmp_path, capsys):
    config = str(tmp_path / "config.json")
    assert (
        main(["--config", config, "criteria", "--keywords", "engineer", "--require", "junior"]) == 0
    )
    capsys.readouterr()

    assert main(["--config", config, "criteria"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["require"] == ["junior"]


def test_save_missing_posting_returns_error(tmp_path, capsys):
    _payload, db, config = _fixture(tmp_path)
    assert main(["--db", db, "--config", config, "save", "99"]) == 1
    assert "No posting with id 99" in capsys.readouterr().err


def test_criteria_saves_and_reads_back(tmp_path, capsys):
    config = str(tmp_path / "config.json")
    assert (
        main(["--config", config, "criteria", "--keywords", "python", "django", "--remote-only"])
        == 0
    )
    capsys.readouterr()

    assert main(["--config", config, "criteria"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["keywords"] == ["python", "django"]
    assert saved["remote_only"] is True


def test_saved_criteria_are_applied_by_fetch(tmp_path, capsys):
    payload, db, config = _fixture(tmp_path)
    main(["--config", config, "criteria", "--keywords", "python"])
    capsys.readouterr()

    main(["--db", db, "--config", config, "fetch", "--from-file", payload, "--source", "remotive"])
    out = capsys.readouterr().out
    assert "1 new match" in out
    assert "Sales Lead" not in out


def test_adzuna_results_are_credited(tmp_path, capsys):
    """Adzuna's terms require the source be credited wherever data is shown."""
    payload = {
        "results": [
            {
                "id": "1",
                "title": "Junior Software Engineer",
                "company": {"display_name": "Acme"},
                "location": {"display_name": "London, UK"},
                "redirect_url": "https://www.adzuna.co.uk/jobs/land/ad/1",
                "salary_min": 29000,
                "salary_max": 33000,
                "salary_is_predicted": 0,
                "description": "<p>Graduate Python role</p>",
            }
        ]
    }
    path = tmp_path / "adzuna.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    code = main(
        [
            "--db",
            str(tmp_path / "adzuna.db"),
            "--config",
            str(tmp_path / "adzuna-cfg.json"),
            "fetch",
            "--from-file",
            str(path),
            "--source",
            "adzuna",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Junior Software Engineer" in out
    assert "£29,000-£33,000" in out
    assert "Source: Adzuna" in out


def test_fetch_applies_the_salary_band(tmp_path, capsys):
    """A stated salary outside the band is dropped; a silent advert is kept."""
    payload = {
        "results": [
            {
                "id": "1",
                "title": "Junior Developer",
                "company": {"display_name": "Acme"},
                "location": {"display_name": "London, UK"},
                "salary_min": 18000,
                "salary_max": 20000,
                "salary_is_predicted": 0,
                "description": "<p>python</p>",
            },
            {
                "id": "2",
                "title": "Junior Developer",
                "company": {"display_name": "MegaCorp"},
                "location": {"display_name": "London, UK"},
                "salary_min": 30000,
                "salary_max": 32000,
                "salary_is_predicted": 0,
                "description": "<p>python</p>",
            },
            {
                "id": "3",
                "title": "Junior Developer",
                "company": {"display_name": "Silent Ltd"},
                "location": {"display_name": "London, UK"},
                "description": "<p>python</p>",
            },
        ]
    }
    path = tmp_path / "adzuna-salary.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    code = main(
        [
            "--db",
            str(tmp_path / "salary.db"),
            "--config",
            str(tmp_path / "salary-cfg.json"),
            "fetch",
            "--from-file",
            str(path),
            "--source",
            "adzuna",
            "--keyword",
            "developer",
            "--salary-min",
            "29000",
            "--salary-max",
            "35000",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "2 new matches" in out
    assert "MegaCorp" in out
    assert "Silent Ltd" in out
    assert "Acme" not in out


def test_criteria_persists_the_salary_band(tmp_path, capsys):
    config = str(tmp_path / "config.json")
    assert (
        main(
            [
                "--config",
                config,
                "criteria",
                "--salary-min",
                "29000",
                "--salary-max",
                "35000",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["--config", config, "criteria"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["salary_min"] == 29000
    assert saved["salary_max"] == 35000
    assert saved["salary_currency"] == "GBP"


def test_salary_max_zero_clears_the_ceiling(tmp_path, capsys):
    config = str(tmp_path / "config.json")
    main(["--config", config, "criteria", "--salary-max", "35000"])
    capsys.readouterr()

    main(["--config", config, "criteria", "--salary-max", "0"])
    capsys.readouterr()

    assert main(["--config", config, "criteria"]) == 0
    assert json.loads(capsys.readouterr().out)["salary_max"] is None


def test_digest_falls_back_to_stored_matches(tmp_path, capsys):
    """A quiet day still shows the best known matches rather than nothing."""
    payload, db, config = _fixture(tmp_path)
    args = [
        "--db",
        db,
        "--config",
        config,
        "fetch",
        "--from-file",
        payload,
        "--source",
        "remotive",
        "--keyword",
        "python",
    ]
    main(args)
    capsys.readouterr()

    assert main([*args, "--digest", "--top", "5"]) == 0
    out = capsys.readouterr().out
    assert "Nothing new today" in out
    assert "Python Developer" in out


def test_matches_credits_adzuna_when_it_is_shown(tmp_path, capsys):
    payload = {
        "results": [
            {
                "id": "1",
                "title": "Junior Developer",
                "company": {"display_name": "Acme"},
                "location": {"display_name": "London, UK"},
                "description": "<p>python</p>",
            }
        ]
    }
    path = tmp_path / "credit.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    db = str(tmp_path / "credit.db")
    config = str(tmp_path / "credit-cfg.json")

    main(["--db", db, "--config", config, "fetch", "--from-file", str(path), "--source", "adzuna"])
    capsys.readouterr()

    assert main(["--db", db, "--config", config, "matches"]) == 0
    assert "Source: Adzuna" in capsys.readouterr().out


def test_a_digest_entry_is_built_for_a_phone(tmp_path, capsys):
    """Role, company, place, pay, link - and no database id or CLI advice."""
    payload = {
        "results": [
            {
                "id": "1",
                "title": "Junior Developer",
                "company": {"display_name": "Acme"},
                "location": {"display_name": "London, UK"},
                "redirect_url": "https://example.com/job/1",
                "salary_min": 30000,
                "salary_max": 32000,
                "salary_is_predicted": 0,
                "description": "<p>python</p>",
            }
        ]
    }
    path = tmp_path / "digest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    code = main(
        [
            "--db",
            str(tmp_path / "digest.db"),
            "--config",
            str(tmp_path / "digest-cfg.json"),
            "fetch",
            "--from-file",
            str(path),
            "--source",
            "adzuna",
            "--digest",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "\n#1  Junior Developer\n" in out
    assert "Acme · London, UK · £30,000-£32,000" in out
    assert "https://example.com/job/1" in out
    assert "  1. " not in out  # the id-led terminal layout
    assert "jobhunt save" not in out
    assert "Source: Adzuna" in out


def test_criteria_persists_the_adzuna_place(tmp_path, capsys):
    config = str(tmp_path / "config.json")
    main(["--config", config, "criteria", "--adzuna-where", "london"])
    capsys.readouterr()

    assert main(["--config", config, "criteria"]) == 0
    assert json.loads(capsys.readouterr().out)["adzuna_where"] == "london"


def test_save_links_the_advert_and_refuses_a_second_save(tmp_path, capsys):
    payload, db, config = _fixture(tmp_path)
    main(["--db", db, "--config", config, "fetch", "--from-file", payload, "--source", "remotive"])
    capsys.readouterr()

    assert main(["--db", db, "--config", config, "save", "1"]) == 0
    capsys.readouterr()

    assert main(["--db", db, "--config", config, "save", "1"]) == 0
    assert "Already saved as application #1" in capsys.readouterr().out

    assert main(["--db", db, "--config", config, "list", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1


def test_applied_records_a_posting_that_was_never_saved(tmp_path, capsys):
    """Applying is the common case, so it must not require saving first."""
    payload, db, config = _fixture(tmp_path)
    main(["--db", db, "--config", config, "fetch", "--from-file", payload, "--source", "remotive"])
    capsys.readouterr()

    assert main(["--db", db, "--config", config, "applied", "1"]) == 0
    assert "Applied #1 Acme - Python Developer" in capsys.readouterr().out

    assert main(["--db", db, "--config", config, "list", "--json"]) == 0
    applications = json.loads(capsys.readouterr().out)
    assert len(applications) == 1
    assert applications[0]["status"] == "applied"
    assert applications[0]["applied_on"] is not None
    assert applications[0]["posting_id"] == 1


def test_applied_advances_a_saved_application_without_duplicating_it(tmp_path, capsys):
    payload, db, config = _fixture(tmp_path)
    main(["--db", db, "--config", config, "fetch", "--from-file", payload, "--source", "remotive"])
    main(["--db", db, "--config", config, "save", "1"])
    capsys.readouterr()

    assert main(["--db", db, "--config", config, "applied", "1"]) == 0
    assert "Applied #1 Acme - Python Developer" in capsys.readouterr().out

    assert main(["--db", db, "--config", config, "list", "--json"]) == 0
    applications = json.loads(capsys.readouterr().out)
    assert len(applications) == 1
    assert applications[0]["status"] == "applied"


def test_applied_takes_a_batch_and_reports_the_missing_id(tmp_path, capsys):
    payload, db, config = _fixture(tmp_path)
    main(["--db", db, "--config", config, "fetch", "--from-file", payload, "--source", "remotive"])
    capsys.readouterr()

    assert main(["--db", db, "--config", config, "applied", "1", "2", "999"]) == 1
    captured = capsys.readouterr()
    assert "No posting with id 999" in captured.err
    assert "2 marked applied, 1 not found." in captured.out

    assert main(["--db", db, "--config", config, "list", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2


def test_show_prints_the_advert_and_the_history(tmp_path, capsys):
    payload, db, config = _fixture(tmp_path)
    main(["--db", db, "--config", config, "fetch", "--from-file", payload, "--source", "remotive"])
    main(["--db", db, "--config", config, "save", "1"])
    main(["--db", db, "--config", config, "update", "1", "--status", "applied"])
    capsys.readouterr()

    assert main(["--db", db, "--config", config, "show", "1"]) == 0
    out = capsys.readouterr().out
    assert "advert" in out
    assert "https://example.com/1" in out  # the advert comes back with it
    assert "history" in out
    assert "applied" in out


def test_applied_is_stamped_and_the_history_is_visible_as_json(tmp_path, capsys):
    db = str(tmp_path / "stamp.db")
    config = str(tmp_path / "stamp-cfg.json")
    main(["--db", db, "--config", config, "add", "--company", "Acme", "--role", "Dev"])
    main(["--db", db, "--config", config, "update", "1", "--status", "applied"])
    capsys.readouterr()

    assert main(["--db", db, "--config", config, "show", "1", "--json"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["applied_on"] is not None
    assert [event["status"] for event in body["timeline"]] == ["saved", "applied"]


def test_followups_lists_what_has_gone_quiet(tmp_path, capsys):
    db = str(tmp_path / "fu.db")
    config = str(tmp_path / "fu-cfg.json")
    main(
        [
            "--db",
            db,
            "--config",
            config,
            "add",
            "--company",
            "Acme",
            "--role",
            "Junior Dev",
            "--url",
            "https://example.com/1",
        ]
    )
    capsys.readouterr()

    assert main(["--db", db, "--config", config, "followups", "--after-days", "0"]) == 0
    out = capsys.readouterr().out
    assert "Junior Dev" in out
    assert "https://example.com/1" in out


def test_the_followup_digest_stays_silent_when_all_is_well(tmp_path, capsys):
    """A nudge that fires every day regardless would stop being read."""
    db = str(tmp_path / "quiet.db")
    config = str(tmp_path / "quiet-cfg.json")
    main(["--db", db, "--config", config, "add", "--company", "Acme", "--role", "Junior Dev"])
    capsys.readouterr()

    assert main(["--db", db, "--config", config, "followups", "--digest"]) == 0
    assert capsys.readouterr().out == ""


def test_the_followup_digest_is_shaped_for_a_phone(tmp_path, capsys):
    db = str(tmp_path / "fu2.db")
    config = str(tmp_path / "fu2-cfg.json")
    main(["--db", db, "--config", config, "add", "--company", "Acme", "--role", "Junior Dev"])
    capsys.readouterr()

    assert main(["--db", db, "--config", config, "followups", "--after-days", "0", "--digest"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("1 to chase")
    assert "#1  Junior Dev" in out  # the handle a reply ("applied 1") uses
    assert "Acme · saved · 0 days quiet" in out


def test_followups_honours_a_saved_threshold(tmp_path, capsys):
    config = str(tmp_path / "cfg.json")
    main(["--config", config, "criteria", "--follow-up-days", "21"])
    capsys.readouterr()

    assert main(["--config", config, "criteria"]) == 0
    assert json.loads(capsys.readouterr().out)["follow_up_days"] == 21
