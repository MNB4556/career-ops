# job-hunt

[![CI](https://github.com/MNB4556/job-hunt/actions/workflows/ci.yml/badge.svg)](https://github.com/MNB4556/job-hunt/actions/workflows/ci.yml)

A small, local-first job search tool. It finds adverts on free job boards,
filters and ranks them against what you are actually looking for, and tracks
what you applied to. Everything lives in a single SQLite file on your machine —
no accounts, no server, no telemetry, no API keys.

## Why

Job hunting means juggling dozens of applications across tabs, emails and
notes, on top of the tedium of re-reading the same boards. `job-hunt` does the
boring half — searching and filtering — and keeps one honest list of what you
applied to and where each application stands. It is deliberately tiny so you
can read the whole thing, and it has no runtime dependencies beyond the Python
standard library.

## Install

```bash
git clone https://github.com/MNB4556/job-hunt.git
cd job-hunt
python -m venv .venv
. .venv/Scripts/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Finding jobs

Tell it what you want once, then ask it to search:

```bash
# What am I looking for?
jobhunt criteria --keywords python backend --locations london --no-remote-only

# Pick a field AND a level: keywords and require are separate groups and
# both must be satisfied, so senior roles can't sneak in on "engineer" alone
jobhunt fetch --keyword engineer --require junior --require graduate

# Search every board, show the best matches
jobhunt fetch

# Only the boards you care about, more results
jobhunt fetch --source remotive --source remoteok --limit 100 --top 20

# Come back to what you found earlier
jobhunt matches

# Turn an interesting posting into a tracked application
jobhunt save 42
```

`fetch` prints the **posting id** next to each result, and `save` takes exactly
that id. Nothing is applied to automatically — `jobhunt` is a filter, not an
autopilot, and the link in each result is authoritative.

Criteria are saved to `~/.jobhunt/config.json`, so an unattended run needs no
flags at all. Any flag you pass overrides the saved value for that run only.

Terms match **whole words**, not bare substrings, so `intern` will not drag in
`internal` and `uk` will not match `Ukraine`. Common inflections still count:
`engineer` matches `engineers` and `engineering`, and `intern` matches
`internship`.

`--keyword` and `--require` are separate OR-groups, and **both** must be
satisfied. That is what lets you ask for software roles *and* a junior level,
instead of either term matching on its own.

### Sources

| Source | Coverage | Notes |
| --- | --- | --- |
| [Remotive](https://remotive.com) | Remote, worldwide | Structured, reliable |
| [Arbeitnow](https://www.arbeitnow.com) | Mostly Germany/EU | Structured, includes on-site |
| [Remote OK](https://remoteok.com) | Remote, worldwide | Structured; [asks for attribution](https://remoteok.com/api) |
| [Hacker News](https://news.ycombinator.com) | Tech, mostly US | Free text — see below |

All four are public, keyless endpoints, which is why `job-hunt` needs no
credentials to read them.

**Hacker News is best-effort.** Those postings are prose, not data, so the
company and role are guessed from the first line of each comment, which
conventionally reads `Company (Location) | Role | stack`. Some entries will be
mis-read, and a few will be skipped. The link is the source of truth.

### Making it automatic

`--digest` keeps the output short enough to send as a chat message, which makes
it safe to run on a schedule:

```bash
jobhunt fetch --digest --top 5
```

## Tracking applications

```bash
# Record something you applied to elsewhere
jobhunt add --company "Acme" --role "Backend Engineer" --status applied \
    --url https://acme.example/jobs/123 --source linkedin

# See everything
jobhunt list

# Just the ones you're still waiting on
jobhunt list --status applied

# Move an application forward
jobhunt update 1 --status interview --notes "Technical screen booked"

# Where does everything stand?
jobhunt stats
```

Add `--json` to any listing command for machine-readable output. Point the tool
at a different database with `--db path/to/jobhunt.db`, or a different settings
file with `--config path/to/config.json`.

### Statuses

`saved` → `applied` → `screening` → `interview` → `offer`, plus the terminal
`rejected` and `withdrawn`.

## Privacy

Your database defaults to `~/.jobhunt/jobhunt.db` and your settings to
`~/.jobhunt/config.json`. Both are **gitignored**, and both stay on your
machine.

Searching downloads each board's public listing with a plain HTTP request and
does the filtering locally, so **your keywords never leave your machine** — the
boards never learn what you are looking for. The only thing sent is an
identifying `User-Agent` header.

Your applications, notes, and anything you put in them are never sent anywhere:
`job-hunt` has no account to sync to and no code that phones home.

## Development

```bash
ruff check .
ruff format --check .
pytest -q
```

The parsers are tested against saved payloads rather than the live boards, so
the suite runs offline.

## License

MIT — see [LICENSE](LICENSE).
