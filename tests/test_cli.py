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
