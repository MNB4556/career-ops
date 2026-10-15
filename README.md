# job-hunt

[![CI](https://github.com/MNB4556/job-hunt/actions/workflows/ci.yml/badge.svg)](https://github.com/MNB4556/job-hunt/actions/workflows/ci.yml)

A small, local-first tracker for your job search. Everything lives in a single
SQLite file on your machine — no accounts, no server, no telemetry.

## Why

Job hunting means juggling dozens of applications across tabs, emails and
notes. `job-hunt` keeps one honest list: what you applied to, when, and where
each application stands. It is deliberately tiny so you can read the whole
thing, and it has no runtime dependencies beyond the Python standard library.

## Install

```bash
git clone https://github.com/MNB4556/job-hunt.git
cd job-hunt
python -m venv .venv
. .venv/Scripts/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Usage

```bash
# Record an application
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

Add `--json` to `list`, `show` or `stats` to get machine-readable output.
Point the tool at a different database with `--db path/to/jobhunt.db`.

### Statuses

`saved` → `applied` → `screening` → `interview` → `offer`, plus the terminal
`rejected` and `withdrawn`.

## Privacy

Your database defaults to `~/.jobhunt/jobhunt.db` and is **gitignored**. The
tracker contains no personal data — the *data* you put in it does, and it never
leaves your machine.

## Development

```bash
ruff check .
ruff format --check .
pytest -q
```

## License

MIT — see [LICENSE](LICENSE).
