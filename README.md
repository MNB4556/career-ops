# job-hunt

[![CI](https://github.com/MNB4556/job-hunt/actions/workflows/ci.yml/badge.svg)](https://github.com/MNB4556/job-hunt/actions/workflows/ci.yml)

A small, local-first job search tool. It finds adverts on free job boards,
filters and ranks them against what you are actually looking for, and tracks
what you applied to. Everything lives in a single SQLite file on your machine —
no server, no telemetry, no account. One source (Adzuna, the UK one) needs a
free API key; the rest need nothing at all.

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

# Skip lowball adverts (0 clears a bound)
jobhunt fetch --salary-min 29000 --salary-max 0

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

`--salary-min` / `--salary-max` only ever rule an advert out on a **stated**
salary in the currency you have set (GBP by default). Adverts that stay silent
about pay, or that pay in another currency, are kept: most junior roles never
state a salary, and hiding them for that would be worse than showing them. In
practice that makes a *floor* useful and a *ceiling* a good way to lose the best
roles — London graduate schemes routinely pay £40k–£50k.

### Sources

| Source | Coverage | Notes |
| --- | --- | --- |
| [Adzuna](https://developer.adzuna.com) | **UK**, including on-site | Stated GBP salaries. Needs a free key — see below |
| [Remotive](https://remotive.com) | Remote, worldwide | Structured, reliable |
| [Arbeitnow](https://www.arbeitnow.com) | Mostly Germany/EU | Structured, includes on-site |
| [Remote OK](https://remoteok.com) | Remote, worldwide | Structured; [asks for attribution](https://remoteok.com/api) |
| [Hacker News](https://news.ycombinator.com) | Tech, mostly US | Free text — see below |

Adzuna is the source that carries UK junior and graduate roles in volume. The
others are global-remote or non-UK, and in practice return almost nothing for a
UK entry-level search.

### Adzuna setup

Adzuna is free but needs an account. Register at
[developer.adzuna.com](https://developer.adzuna.com), then put the two values
somewhere **outside the repository**:

```json
{
  "adzuna_app_id": "your-app-id",
  "adzuna_app_key": "your-app-key"
}
```

That is `~/.jobhunt/credentials.json`. `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` in
the environment work too, and win over the file. The key is never written to the
repository and never printed: any URL carrying it is masked before it can reach
a log or an error message.

Adzuna is a search API rather than a listing dump, so you search it by phrase,
one request per `--adzuna-query`:

```bash
jobhunt criteria --adzuna-queries "junior software engineer" "graduate software engineer"
jobhunt fetch --source adzuna --top 10
```

It is UK-only (`gb`) by design. The free tier allows 250 calls a day and a daily
digest uses a handful. Adzuna's terms require that it be credited wherever its
data is published, so results it contributes are followed by a `Source: Adzuna`
line — including in a digest sent to your phone.

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

`--digest` reports what is **new** since the last run. On a quiet day, rather
than saying "nothing new" and being ignored, it falls back to the best matches
already stored and says so.

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

Your database defaults to `~/.jobhunt/jobhunt.db`, your settings to
`~/.jobhunt/config.json`, and any API key to `~/.jobhunt/credentials.json`. All
three are **gitignored** and stay on your machine.

Searching downloads each board's public listing with a plain HTTP request and
filters locally. For the four keyless boards that means **your keywords never
leave your machine** — they never learn what you are looking for, and the only
thing sent is an identifying `User-Agent` header.

**Adzuna is the exception.** It is a search API rather than a listing dump, so
the phrases you pass to `--adzuna-queries` are sent to Adzuna as the search
term, along with your app id. Keep those phrases generic ("graduate software
engineer"); your locations, salary band, and exclusions are still applied
locally and are never sent.

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
