# career-ops

[![CI](https://github.com/MNB4556/career-ops/actions/workflows/ci.yml/badge.svg)](https://github.com/MNB4556/career-ops/actions/workflows/ci.yml)

A job-search CLI and application tracker. It searches five job boards, filters
results against criteria you save once, and keeps one list of what you applied
to and where it stands. Everything lives in a single SQLite file on your
machine: no server, no telemetry, no account. Adzuna, the UK board, needs a free
API key; the other four need nothing.

The project is `career-ops`. The command is `jobhunt`.

## What it does

- Searches Adzuna (UK), Remotive, Arbeitnow, Remote OK and Hacker News from one
  command.
- Filters on whole words, with two independent groups that both have to match,
  plus location, remote and stated salary.
- Saves your criteria, so an unattended run needs no flags.
- Tracks each application through `saved`, `applied`, `screening`, `interview`
  and `offer`, recording every move rather than only the current state.
- Lists applications that have gone quiet, and prints nothing at all when there
  is nothing to chase.
- Prints a short digest sized for a phone.

## At a glance

| | |
|---|---|
| Runtime | Python 3.11+, standard library only |
| Data | one SQLite file, `~/.jobhunt/jobhunt.db` |
| Sources | Adzuna, Remotive, Arbeitnow, Remote OK, Hacker News |
| Interface | a CLI, with a plain-text digest for a phone or chat app |
| Tests | 155, all offline, run against saved payloads |

## A digest

`jobhunt fetch --digest --top 5` keeps only what a phone can act on: the handle a
reply refers to, the role, then company, place and pay on one line, then the
advert.

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

Those postings are invented. `#281` has no pay line because the advert did not
state a salary, and it is shown anyway rather than hidden for the omission. The
source line is required by Adzuna's terms wherever its data is published, and a
digest sent to a phone counts.

Ranking prefers a job you could start now. An advert naming a year still to come,
such as `2027 Summer Internship`, is ranked below an otherwise similar role and
labelled `starts 2027`, because next year's intake is worth knowing about but not
before today's openings. `jobhunt criteria --hide-deferred` drops them instead.

> The tool does not apply to anything for you. It fills in no form and sends
> nothing to an employer. The `#id` is a handle for your own reply, and the
> advert's link remains the way in. A ranking can be wrong; the link wins.

## Install

```bash
git clone https://github.com/MNB4556/career-ops.git
cd career-ops
python -m venv .venv
. .venv/Scripts/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Searching

Set your criteria once, then ask for results:

```bash
# What am I looking for?
jobhunt criteria --keywords python backend --locations london --no-remote-only

# Keywords and required terms are separate groups, and both must match, so a
# senior role cannot get in on "engineer" alone
jobhunt fetch --keyword engineer --require junior --require graduate

# Skip lowball adverts (0 clears a bound)
jobhunt fetch --salary-min 29000 --salary-max 0

# Search every board
jobhunt fetch

# Only the boards you care about, more results
jobhunt fetch --source remotive --source remoteok --limit 100 --top 20

# Come back to what you found earlier
jobhunt matches

# Turn a posting into a tracked application
jobhunt save 42

# Already applied? One number, no saving first
jobhunt applied 42
```

`--locations` is an OR-list, and a remote advert always survives it: asking for
`--locations london remote` should not drop a remote role that happens to name
Leeds. A named on-site role still has to match one of the places you listed, and
an on-site role that names no place at all is not worth guessing at.

`fetch` prints the posting id next to each result, and `save` takes exactly that
id. `applied` takes it too, creating the record if the advert was never saved,
which exists because applying is where a second step gets forgotten. It accepts
several ids at once (`jobhunt applied 41 42 47`), so a morning's batch is one
command.

Criteria are saved to `~/.jobhunt/config.json`. Any flag you pass overrides the
saved value for that run only.

Terms match whole words, so `intern` does not drag in `internal` and `uk` does
not match `Ukraine`. Common inflections still count: `engineer` matches
`engineers` and `engineering`, `intern` matches `internship`.

`--keyword` and `--require` are separate OR-groups and both have to be
satisfied. One of the terms must appear where the advert names the job, in its
title or the board's tags, rather than once in the blurb. An advert has to say
what it is: a travel company describing itself as "an entry-level opportunity"
is not a software role.

`--salary-min` and `--salary-max` only rule an advert out on a salary it states,
in the currency you have set (GBP by default). Adverts that say nothing about pay,
or pay in another currency, are kept, because most junior roles never state a
salary. That makes a floor useful and a ceiling a good way to lose the best
roles; London graduate schemes routinely pay £40k to £50k.

### Sources

| Source | Coverage | Notes |
| --- | --- | --- |
| [Adzuna](https://developer.adzuna.com) | UK, including on-site | Stated GBP salaries. Needs a free key |
| [Remotive](https://remotive.com) | Remote, worldwide | Structured |
| [Arbeitnow](https://www.arbeitnow.com) | Mostly Germany and the EU | Structured, includes on-site |
| [Remote OK](https://remoteok.com) | Remote, worldwide | Structured; [asks for attribution](https://remoteok.com/api) |
| [Hacker News](https://news.ycombinator.com) | Tech, mostly US | Free text |

Adzuna carries UK junior and graduate roles in volume. The others are
global-remote or non-UK and return almost nothing for a UK entry-level search.

### Adzuna setup

Register at [developer.adzuna.com](https://developer.adzuna.com), then put the
two values outside the repository, in `~/.jobhunt/credentials.json`:

```json
{
  "adzuna_app_id": "your-app-id",
  "adzuna_app_key": "your-app-key"
}
```

`ADZUNA_APP_ID` and `ADZUNA_APP_KEY` in the environment work as well and win over
the file. The key is never written to the repository and never printed: any URL
carrying it is masked before it reaches a log or an error message.

Adzuna is a search API rather than a listing dump, so you search it by phrase,
one request per `--adzuna-query`:

```bash
jobhunt criteria --adzuna-queries "junior software engineer" "graduate software engineer"
jobhunt fetch --source adzuna --top 10
```

`--adzuna-where` confines it to a place, and you then always get both passes:

```bash
jobhunt criteria --adzuna-where london --locations london remote
```

Each query runs twice, once inside London and once for remote adverts anywhere.

The place pass has to be done by Adzuna rather than by filtering text locally. A
nationwide advert comes back labelled `UK`, and its `area` list is `["UK"]`, so
nothing local separates a London role from a Leeds one; filtering on the text
silently discards good roles. Geocoding is the only signal that works.

The remote pass exists because the place filter would otherwise hide remote work.
Adzuna has no remote field, so `what_and=remote` is the only lever.

That is two requests per query. Adzuna is UK-only by design, the free tier allows
250 calls a day, and a daily digest using eight sits well inside it.

### Hacker News

Those postings are prose, not data, so the company and role are guessed from the
first line of each comment, which conventionally reads
`Company (Location) | Role | stack`. Some entries will be misread and a few will
be skipped. The link is the source of truth.

## Running it on a schedule

`--digest` reports what is new since the last run. On a quiet day it falls back
to the best matches already stored and says so, rather than reporting nothing and
being ignored.

`jobhunt followups --digest` is the other half of the loop: one scheduled job
brings new adverts, the other brings back applications that have gone quiet.

If a board cannot be reached, the digest names it rather than quietly arriving
short, so a partial list is never mistaken for a complete one.

## Tracking applications

```bash
# Record something you applied to elsewhere
jobhunt add --company "Acme" --role "Backend Engineer" --status applied \
    --url https://acme.example/jobs/123 --source linkedin

# Or promote something you found, keeping the advert attached
jobhunt save 42

# See everything, or just what you are waiting on
jobhunt list
jobhunt list --status applied

# Move an application forward
jobhunt update 1 --status interview --notes "Technical screen booked"

# The application, its advert, and everything that happened to it
jobhunt show 1

# What has gone quiet?
jobhunt followups

# Where does everything stand?
jobhunt stats
```

Add `--json` to any listing command for machine-readable output. Point the tool
at another database with `--db path/to/jobhunt.db`, or another settings file with
`--config path/to/config.json`.

### Statuses

`saved` → `applied` → `screening` → `interview` → `offer`, plus the terminal
`rejected` and `withdrawn`.

Every move is recorded as it happens, so `show` gives the whole history rather
than only the final state. The first move to `applied` stamps `applied_on` by
itself, because that date is what a follow-up is measured from and should not
depend on remembering to pass it.

### Follow-ups

`followups` lists open applications with no movement for `follow_up_days`
(default 10, set with `jobhunt criteria --follow-up-days 21`), most stale first.
`rejected` and `withdrawn` drop out; an unanswered `offer` stays in.

```bash
jobhunt followups                 # terminal view
jobhunt followups --after-days 5  # one-off threshold, saves nothing
jobhunt followups --digest        # message view
```

`--digest` prints nothing when there is nothing to chase. An automation that
produces no output sends no message, so the nudge only arrives on days worth
reading.

## Privacy

The database defaults to `~/.jobhunt/jobhunt.db`, settings to
`~/.jobhunt/config.json`, and any API key to `~/.jobhunt/credentials.json`. All
three are gitignored.

Searching downloads each board's public listing with a plain HTTP request and
filters locally. For the four keyless boards your keywords never leave your
machine; the only thing sent is a `User-Agent` header.

Adzuna is the exception. It is a search API, so the phrases you pass to
`--adzuna-queries` go to Adzuna as the search term along with your app id. Keep
those phrases generic ("graduate software engineer"); locations, salary band and
exclusions are applied locally and are never sent.

Applications and notes are never sent anywhere. There is no account to sync to
and no code that phones home.

## Development

```bash
ruff check .
ruff format --check .
pytest -q
```

The parsers are tested against saved payloads rather than live boards, so the
suite runs offline.

## License

All rights reserved. See [LICENSE](LICENSE).
