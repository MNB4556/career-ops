# career-ops

[![CI](https://github.com/MNB4556/career-ops/actions/workflows/ci.yml/badge.svg)](https://github.com/MNB4556/career-ops/actions/workflows/ci.yml)

**A local-first job search CLI and application tracker.** It finds adverts on
free job boards, filters and ranks them against what you are actually looking
for, and keeps one honest list of what you applied to and where it stands.
Everything lives in a single SQLite file on your machine — no server, no
telemetry, no account. One source (Adzuna, the UK one) needs a free API key;
the rest need nothing at all.

The project is `career-ops`; the command you run is `jobhunt`.

## What it does

- **Searches five boards** — Adzuna (UK), Remotive, Arbeitnow, Remote OK and
  Hacker News — from one command.
- **Filters honestly** — whole-word matches, two independent AND-ed groups,
  locations, remote, and stated salaries only. `intern` never drags in
  `internal`, and an advert that stays silent about pay is never hidden for
  being silent.
- **Remembers your criteria**, so an unattended run needs no flags at all.
- **Tracks every application** through `saved → applied → screening →
  interview → offer`, with each move recorded as it happens rather than only
  the final state.
- **Chases silence**, because most applications die of that rather than
  rejection — and says *nothing at all* when there is nothing to chase.
- **Sends a phone-shaped digest**, cut down to a `#id`, the role, the place,
  the pay and the link, so the scheduled version is worth reading.

## At a glance

| | |
|---|---|
| Runtime | Python 3.11+, no dependencies beyond the standard library |
| Data | one SQLite file, `~/.jobhunt/jobhunt.db` |
| Sources | Adzuna · Remotive · Arbeitnow · Remote OK · Hacker News |
| Interface | a CLI, plus an optional WhatsApp digest |
| Tests | 140, all offline, run against saved payloads |

## What a digest looks like

`jobhunt fetch --digest --top 5` keeps only what a phone can act on: the handle
a reply refers to, the role, then company, place and pay on one line, then the
advert itself.

```text
Job digest: 3 new matches

#274  Junior Backend Engineer
Northwind Systems · London, UK · £38,000-£45,000
https://example.com/adverts/northwind-junior-backend

#277  Graduate Software Engineer
Halden Labs · Remote (UK) · £32,000-£36,000
https://example.com/adverts/halden-graduate-engineer

#281  Software Engineer (Entry Level)
Meridian Retail Group · Manchester, UK
https://example.com/adverts/meridian-entry-level-swe

... and 4 more.

Source: Adzuna (https://www.adzuna.co.uk/)
```

Those postings are invented. Note `#281`: it carries no pay line because the
advert never stated a salary, and it is shown anyway rather than hidden for the
omission. The attribution line is not optional — Adzuna's terms require it
wherever its data is published, and a digest sent to a phone counts.

Ranking prefers a job you could start now. An advert that names a year still to
come — `2027 Summer Internship` — is stating when the work begins, so it is
ranked below an otherwise similar role and labelled `starts 2027` in the digest.
It is demoted, not hidden: next year's intake is worth knowing about, just not
before the openings you can apply to today. If you would rather not see them at
all, `jobhunt criteria --hide-deferred` drops them from results entirely.

> [!IMPORTANT]
> **It is a filter, not an autopilot.** The digest stops at a shortlist. Nothing
> is applied to on your behalf, no form is filled in, and nothing is sent to an
> employer. The `#id` is a handle for *you* to reply with — `save 13`,
> `applied 4` — and the advert's own link remains the authoritative way in. A
> ranking can be wrong; the link wins every time.

## Why

Job hunting means juggling dozens of applications across tabs, emails and
notes, on top of the tedium of re-reading the same boards. `career-ops` does the
boring half — searching and filtering — and keeps one honest list of what you
applied to and where each application stands. It is deliberately tiny so you
can read the whole thing, and it has no runtime dependencies beyond the Python
standard library.

## Install

```bash
git clone https://github.com/MNB4556/career-ops.git
cd career-ops
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

# Already applied? One number, no saving first, no second step
jobhunt applied 42
```

`--locations` is an OR-list, and a **remote** advert always survives it:
asking for `--locations london remote` should not drop a remote role that
happens to name Leeds. A named on-site role still has to match one of the
places you listed, and an on-site role stating no place at all is not worth
guessing at.

`fetch` prints the **posting id** next to each result, and `save` takes exactly
that id. Nothing is applied to automatically — `jobhunt` is a filter, not an
autopilot, and the link in each result is authoritative.

`applied` takes that same id at the moment you send the application, creating
the track if the advert was never saved. It exists because applying is exactly
where a second step gets forgotten: you have the `#id` in front of you for the
next thirty seconds and not for the next three days. It takes several ids at
once (`jobhunt applied 41 42 47`) so a morning's batch is one message.

Criteria are saved to `~/.jobhunt/config.json`, so an unattended run needs no
flags at all. Any flag you pass overrides the saved value for that run only.

Terms match **whole words**, not bare substrings, so `intern` will not drag in
`internal` and `uk` will not match `Ukraine`. Common inflections still count:
`engineer` matches `engineers` and `engineering`, and `intern` matches
`internship`.

`--keyword` and `--require` are separate OR-groups, and **both** must be
satisfied. That is what lets you ask for software roles *and* a junior level,
instead of either term matching on its own.

One of those terms must appear where the advert names the job — its title, or
the board's tags — not only somewhere in the blurb. That is deliberate. An
advert has to say what it is: a travel company describing itself as "an
entry-level opportunity" is not a software role, and one phrase buried in a
2,000-character description should not be enough to make it look like one.

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

`--adzuna-where` confines it to a place — and you then always get both passes:

```bash
jobhunt criteria --adzuna-where london --locations london remote
```

Each query runs twice: once **inside** London, and once for **remote** adverts
anywhere.

The place pass has to be done by Adzuna rather than by filtering the text
locally. A nationwide advert comes back labelled simply `"UK"`, and its `area`
list is `["UK"]` too, so nothing local separates a London role from a Leeds one
— filtering on the text silently discards perfectly good roles. Geocoding is
the only signal that works.

The remote pass exists because the place filter would otherwise hide remote
work entirely. Adzuna has no remote field, so `what_and=remote` is the only
lever, and a hit is taken as the evidence.

That is two requests per query. Adzuna is UK-only (`gb`) by design, the free
tier allows 250 calls a day, and a daily digest using eight sits well inside it.
Adzuna's terms require that it be credited wherever its data is published, so
results it contributes are followed by a `Source: Adzuna` line — including in a
digest sent to your phone.

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

A digest entry is cut down to what a phone can use — a short `#id` handle, the
role, then company, place and pay on one line, then the advert link. The
padded terminal layout and the `jobhunt save` command line are left out: they
are useful on a terminal and noise in a chat message. The advert's own link
remains the authoritative way in.

The `#id` stays because it is what a reply refers to. With the agent wired up to
the tracker, "save 13" acts on the entry numbered `#13` in the message, and
"applied 13" records that you sent it. The link is still the way in for
everything else.

The same shape is used by `jobhunt followups --digest`, which is the other half
of the loop: one scheduled job brings new adverts, the other brings back the
applications you have gone quiet on.

If a board cannot be reached, the digest names it in the message rather than
quietly arriving short. A partial list that looks complete is worse than one
that admits the gap: you would apply to what arrived, conclude the market was
thin, and never learn that the best source was down.

## Tracking applications

```bash
# Record something you applied to elsewhere
jobhunt add --company "Acme" --role "Backend Engineer" --status applied \
    --url https://acme.example/jobs/123 --source linkedin

# Or promote something you found, keeping the advert attached
jobhunt save 42

# Or record that you already applied, in one step
jobhunt applied 42

# See everything, or just the ones you're still waiting on
jobhunt list
jobhunt list --status applied

# Move an application forward
jobhunt update 1 --status interview --notes "Technical screen booked"

# The application, the advert it came from, and everything that happened to it
jobhunt show 1

# What has gone quiet and wants chasing?
jobhunt followups

# Where does everything stand?
jobhunt stats
```

Add `--json` to any listing command for machine-readable output. Point the tool
at a different database with `--db path/to/jobhunt.db`, or a different settings
file with `--config path/to/config.json`.

### Statuses

`saved` → `applied` → `screening` → `interview` → `offer`, plus the terminal
`rejected` and `withdrawn`.

Every move is recorded as it happens, so `show` tells you the whole story rather
than only where things ended up. The first move to `applied` also stamps
`applied_on` on its own: that date is what a follow-up gets measured from, and it
should not depend on remembering to pass it.

### Chasing what has gone quiet

Most applications die of silence rather than rejection, so `followups` exists to
stop that happening unnoticed. It lists open applications with no movement for
`follow_up_days` (default 10; set it with `jobhunt criteria --follow-up-days 21`),
most stale first. `rejected` and `withdrawn` drop out; an unanswered `offer`
stays in, because that still needs an answer.

```bash
jobhunt followups                 # terminal view
jobhunt followups --after-days 5  # a one-off threshold, saving nothing
jobhunt followups --digest        # message view
```

`--digest` prints **nothing at all** when there is nothing to chase. That is
deliberate, and it is what makes the scheduled version worth having: an
automation that produces no output sends no message, so the nudge only arrives
on the days it is worth reading. A daily "nothing to chase" would be trained out
of your attention within a week.

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
`career-ops` has no account to sync to and no code that phones home.

## Development

```bash
ruff check .
ruff format --check .
pytest -q
```

The parsers are tested against saved payloads rather than the live boards, so
the suite runs offline.

## License

All rights reserved — see [LICENSE](LICENSE).
