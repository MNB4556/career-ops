"""Command-line interface for job-hunt."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

from jobhunt import __version__
from jobhunt import sources as source_module
from jobhunt.config import DEFAULT_CONFIG_PATH, Config
from jobhunt.config import load as load_config
from jobhunt.config import save as save_config
from jobhunt.matching import Criteria
from jobhunt.models import STATUSES, Application, Posting
from jobhunt.sources import SOURCES, SourceError
from jobhunt.storage import Store

DEFAULT_DB = Path.home() / ".jobhunt" / "jobhunt.db"

# Adzuna's terms require it to be credited wherever its data is published, and
# a digest pushed to a phone counts as published.
ADZUNA_ATTRIBUTION = "Source: Adzuna (https://www.adzuna.co.uk/)"


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``jobhunt`` command."""
    parser = argparse.ArgumentParser(prog="jobhunt", description="Track job applications locally.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="path to the SQLite database")
    parser.add_argument(
        "--config", default=str(DEFAULT_CONFIG_PATH), help="path to the settings file"
    )
    parser.add_argument("--version", action="version", version=f"jobhunt {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="record a new application")
    add.add_argument("--company", required=True)
    add.add_argument("--role", required=True)
    add.add_argument("--status", default="saved", choices=STATUSES)
    add.add_argument("--url")
    add.add_argument("--source")
    add.add_argument("--applied-on", dest="applied_on")
    add.add_argument("--notes")

    listing = subparsers.add_parser("list", help="list applications")
    listing.add_argument("--status", choices=STATUSES)
    listing.add_argument("--json", action="store_true")

    show = subparsers.add_parser("show", help="show one application")
    show.add_argument("id", type=int)
    show.add_argument("--json", action="store_true")

    update = subparsers.add_parser("update", help="change an application's status")
    update.add_argument("id", type=int)
    update.add_argument("--status", required=True, choices=STATUSES)
    update.add_argument("--notes")

    remove = subparsers.add_parser("remove", help="delete an application")
    remove.add_argument("id", type=int)

    stats = subparsers.add_parser("stats", help="summarise applications")
    stats.add_argument("--json", action="store_true")

    fetch = subparsers.add_parser("fetch", help="search free job boards for new matches")
    fetch.add_argument("--source", action="append", dest="sources", choices=SOURCES)
    fetch.add_argument("--limit", type=int, help="maximum postings to take per source")
    fetch.add_argument("--keyword", action="append", dest="keywords")
    fetch.add_argument(
        "--require",
        action="append",
        dest="require",
        help="terms where at least one must also appear (combine with --keyword as AND)",
    )
    fetch.add_argument("--exclude", action="append", dest="exclude")
    fetch.add_argument("--location", action="append", dest="locations")
    fetch.add_argument("--salary-min", type=int, dest="salary_min")
    fetch.add_argument("--salary-max", type=int, dest="salary_max")
    fetch.add_argument(
        "--adzuna-query",
        action="append",
        dest="adzuna_queries",
        help="phrase to search Adzuna for (repeatable); Adzuna is the UK source",
    )
    fetch.add_argument("--remote-only", action="store_true", default=None)
    fetch.add_argument("--min-score", type=int, default=0, dest="min_score")
    fetch.add_argument(
        "--from-file", dest="from_file", help="parse a saved payload instead of fetching"
    )
    fetch.add_argument(
        "--digest", action="store_true", help="print a short, message-friendly summary"
    )
    fetch.add_argument("--top", type=int, default=10, help="how many matches to print")
    fetch.add_argument("--json", action="store_true")

    matches = subparsers.add_parser("matches", help="show stored postings that match your criteria")
    matches.add_argument("--limit", type=int, default=10)
    matches.add_argument("--digest", action="store_true")
    matches.add_argument("--json", action="store_true")

    save = subparsers.add_parser(
        "save", help="turn a discovered posting into a tracked application"
    )
    save.add_argument("id", type=int)

    criteria = subparsers.add_parser("criteria", help="show or change the saved search settings")
    criteria.add_argument("--keywords", nargs="*")
    criteria.add_argument("--require", nargs="*")
    criteria.add_argument("--exclude", nargs="*")
    criteria.add_argument("--locations", nargs="*")
    criteria.add_argument("--salary-min", type=int, dest="salary_min", help="0 clears it")
    criteria.add_argument("--salary-max", type=int, dest="salary_max", help="0 clears it")
    criteria.add_argument("--adzuna-queries", nargs="*", dest="adzuna_queries")
    criteria.add_argument("--sources", nargs="*", choices=SOURCES)
    criteria.add_argument("--limit", type=int)
    remote = criteria.add_mutually_exclusive_group()
    remote.add_argument("--remote-only", action="store_true", dest="remote_only", default=None)
    remote.add_argument("--no-remote-only", action="store_false", dest="remote_only")

    return parser


def _as_dict(application: Application) -> dict[str, object]:
    return {
        "id": application.id,
        "company": application.company,
        "role": application.role,
        "status": application.status,
        "url": application.url,
        "source": application.source,
        "applied_on": application.applied_on,
        "notes": application.notes,
        "created_at": application.created_at,
        "updated_at": application.updated_at,
    }


def _posting_as_dict(posting: Posting, score: int | None = None) -> dict[str, object]:
    return {
        "id": posting.id,
        "source": posting.source,
        "title": posting.title,
        "company": posting.company,
        "url": posting.url,
        "location": posting.location,
        "remote": posting.remote,
        "salary": posting.salary,
        "salary_min": posting.salary_min,
        "salary_max": posting.salary_max,
        "salary_currency": posting.salary_currency,
        "tags": list(posting.tags),
        "posted_at": posting.posted_at,
        "score": score,
    }


def _print_posting(posting: Posting, *, tags: bool = True) -> None:
    """Print one posting, led by the id that ``jobhunt save`` expects."""
    where = posting.location or ("Remote" if posting.remote else "")
    suffix = f"  ({where})" if where else ""
    print(f"{posting.id:>4}. {posting.title} - {posting.company}{suffix}")
    if posting.url:
        print(f"      {posting.url}")
    if posting.salary:
        print(f"      {posting.salary}")
    if tags and posting.tags:
        print(f"      {', '.join(posting.tags[:8])}")


def _use_utf8_output() -> None:
    """Write UTF-8 whatever the console codepage is.

    A digest is piped to another process rather than shown on a console, and a
    pipe would otherwise mangle the pound sign in "£29,000".
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    _use_utf8_output()
    args = build_parser().parse_args(argv)
    if args.command == "criteria":
        return _cmd_criteria(None, args)
    with Store(args.db) as store:
        handlers = {
            "add": _cmd_add,
            "list": _cmd_list,
            "show": _cmd_show,
            "update": _cmd_update,
            "remove": _cmd_remove,
            "stats": _cmd_stats,
            "fetch": _cmd_fetch,
            "matches": _cmd_matches,
            "save": _cmd_save,
        }
        return handlers[args.command](store, args)


def _cmd_add(store: Store, args: argparse.Namespace) -> int:
    application = store.add(
        Application(
            company=args.company,
            role=args.role,
            status=args.status,
            url=args.url,
            source=args.source,
            applied_on=args.applied_on,
            notes=args.notes,
        )
    )
    print(f"Added application #{application.id}: {application.company} - {application.role}")
    return 0


def _cmd_list(store: Store, args: argparse.Namespace) -> int:
    applications = store.list(args.status)
    if args.json:
        print(json.dumps([_as_dict(a) for a in applications], indent=2))
        return 0
    if not applications:
        print("No applications yet.")
        print("Add one with: jobhunt add --company Acme --role 'Backend Engineer'")
        return 0
    print(f"{'ID':>4}  {'STATUS':<10}  {'COMPANY':<24}  ROLE")
    for application in applications:
        print(
            f"{application.id:>4}  {application.status:<10}  "
            f"{application.company[:24]:<24}  {application.role}"
        )
    return 0


def _cmd_show(store: Store, args: argparse.Namespace) -> int:
    application = store.get(args.id)
    if application is None:
        print(f"No application with id {args.id}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(_as_dict(application), indent=2))
    else:
        for key, value in _as_dict(application).items():
            print(f"{key:>12}: {value}")
    return 0


def _cmd_update(store: Store, args: argparse.Namespace) -> int:
    try:
        application = store.update_status(args.id, args.status, args.notes)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Updated application #{application.id} -> {application.status}")
    return 0


def _cmd_remove(store: Store, args: argparse.Namespace) -> int:
    if store.delete(args.id):
        print(f"Removed application #{args.id}")
        return 0
    print(f"No application with id {args.id}", file=sys.stderr)
    return 1


def _cmd_stats(store: Store, args: argparse.Namespace) -> int:
    counts = store.stats()
    if args.json:
        print(json.dumps(counts, indent=2))
        return 0
    if not counts.get("total"):
        print("No applications yet.")
        return 0
    for status in STATUSES:
        if status in counts:
            print(f"{status:<10} {counts[status]}")
    print(f"{'total':<10} {counts['total']}")
    return 0


def _resolve_criteria(args: argparse.Namespace, config: Config) -> Criteria:
    """Combine command-line flags with saved settings, flags winning per field."""
    return Criteria(
        keywords=tuple(args.keywords if args.keywords is not None else config.keywords),
        require=tuple(args.require if args.require is not None else config.require),
        exclude=tuple(args.exclude if args.exclude is not None else config.exclude),
        locations=tuple(args.locations if args.locations is not None else config.locations),
        remote_only=args.remote_only if args.remote_only is not None else config.remote_only,
        salary_min=args.salary_min if args.salary_min is not None else config.salary_min,
        salary_max=args.salary_max if args.salary_max is not None else config.salary_max,
        salary_currency=config.salary_currency,
    )


def _ranked(postings: list[Posting], criteria: Criteria) -> list[tuple[Posting, int]]:
    """Rank *postings* by score, breaking ties newest-first.

    ``Criteria.rank`` is deliberately stable, but the two commands hand it
    lists in different orders. Adding the id as a tie-break keeps ``fetch`` and
    ``matches`` from disagreeing about which posting is on top.
    """
    return sorted(
        criteria.rank(postings), key=lambda pair: (pair[1], pair[0].id or 0), reverse=True
    )


def _credit_adzuna(sources: Iterable[str]) -> None:
    """Print the credit Adzuna's terms require once its data is shown."""
    if "adzuna" in sources:
        print(f"\n{ADZUNA_ATTRIBUTION}")


def _print_stored_fallback(store: Store, criteria: Criteria, args: argparse.Namespace) -> bool:
    """Show the best stored matches when a digest has nothing new.

    A daily digest that reads "nothing new" on every quiet day stops being
    opened, so on those days it falls back to what is already known, and says
    so rather than pretending it is fresh.
    """
    ranked = [
        pair for pair in _ranked(store.list_postings(), criteria) if pair[1] >= args.min_score
    ]
    if not ranked:
        return False
    shown = ranked[: args.top]
    print("Nothing new today. Best current matches:")
    print()
    for posting, _score in shown:
        _print_posting(posting, tags=False)
    if len(ranked) > len(shown):
        print(f"\n... and {len(ranked) - len(shown)} more.")
    _credit_adzuna({posting.source for posting, _ in shown})
    print("\nSave one with: jobhunt save <id>")
    return True


def _cmd_fetch(store: Store, args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sources = args.sources or config.sources
    criteria = _resolve_criteria(args, config)
    limit = args.limit if args.limit is not None else config.limit
    queries = args.adzuna_queries if args.adzuna_queries is not None else config.adzuna_queries

    if args.from_file:
        if len(sources) != 1:
            print("--from-file needs exactly one --source", file=sys.stderr)
            return 2
        try:
            payload = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"could not read {args.from_file}: {exc}", file=sys.stderr)
            return 2
        fetched = source_module.parse(sources[0], payload)
    else:
        fetched = []
        failures = []
        for name in sources:
            try:
                fetched.extend(source_module.fetch(name, limit, queries))
            except (SourceError, ValueError) as exc:
                failures.append(f"{name}: {exc}")
        for failure in failures:
            print(f"warning: {failure}", file=sys.stderr)
        if failures and len(failures) == len(sources):
            print("no source could be reached", file=sys.stderr)
            return 1

    fresh = []
    for posting in fetched:
        stored, is_new = store.upsert_posting(posting)
        if is_new:
            fresh.append(stored)

    ranked = [pair for pair in _ranked(fresh, criteria) if pair[1] >= args.min_score]
    shown = ranked[: args.top]

    if args.json:
        print(
            json.dumps(
                {
                    "fetched": len(fetched),
                    "new": len(fresh),
                    "matching": len(ranked),
                    "sources": sources,
                    "matches": [_posting_as_dict(p, score) for p, score in shown],
                },
                indent=2,
            )
        )
        return 0

    if args.digest:
        print(f"Job digest: {len(ranked)} new match{'es' if len(ranked) != 1 else ''}")
    else:
        print(
            f"Fetched {len(fetched)} postings from {', '.join(sources)} "
            f"({len(fresh)} new). {len(ranked)} new match"
            f"{'es' if len(ranked) != 1 else ''}."
        )
    if not ranked:
        if args.digest and _print_stored_fallback(store, criteria, args):
            return 0
        print("Nothing matched your criteria this time.")
        return 0
    print()
    for posting, _score in shown:
        _print_posting(posting, tags=not args.digest)
    if len(ranked) > len(shown):
        print(f"\n... and {len(ranked) - len(shown)} more (raise --top to see them).")
    _credit_adzuna({posting.source for posting, _ in shown})
    print("\nSave one with: jobhunt save <id>")
    return 0


def _cmd_matches(store: Store, args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    stored = store.list_postings()
    ranked = _ranked(stored, config.criteria())[: args.limit]
    if args.json:
        print(json.dumps([_posting_as_dict(p, score) for p, score in ranked], indent=2))
        return 0
    if not ranked:
        print("No stored postings match. Run 'jobhunt fetch' first.")
        return 0
    if args.digest:
        print(f"Stored matches: {len(ranked)}")
        print()
    else:
        print(f"{len(ranked)} stored posting{'s' if len(ranked) != 1 else ''} match your criteria.")
        print()
    for posting, _score in ranked:
        _print_posting(posting, tags=not args.digest)
    _credit_adzuna({posting.source for posting, _ in ranked})
    print("\nSave one with: jobhunt save <id>")
    return 0


def _cmd_save(store: Store, args: argparse.Namespace) -> int:
    posting = store.get_posting(args.id)
    if posting is None:
        print(f"No posting with id {args.id}", file=sys.stderr)
        return 1
    application = store.add(posting.to_application())
    print(f"Saved application #{application.id}: {application.company} - {application.role}")
    return 0


def _cmd_criteria(_store: Store | None, args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    changed = False
    if args.keywords is not None:
        config.keywords = args.keywords
        changed = True
    if args.require is not None:
        config.require = args.require
        changed = True
    if args.exclude is not None:
        config.exclude = args.exclude
        changed = True
    if args.locations is not None:
        config.locations = args.locations
        changed = True
    if args.sources is not None:
        config.sources = args.sources
        changed = True
    if args.limit is not None:
        config.limit = args.limit
        changed = True
    if args.remote_only is not None:
        config.remote_only = args.remote_only
        changed = True
    # 0 clears a bound, so "--salary-max 0" means "no ceiling".
    if args.salary_min is not None:
        config.salary_min = args.salary_min or None
        changed = True
    if args.salary_max is not None:
        config.salary_max = args.salary_max or None
        changed = True
    if args.adzuna_queries is not None:
        config.adzuna_queries = args.adzuna_queries
        changed = True
    if changed:
        path = save_config(config, args.config)
        print(f"Saved search settings to {path}")
        print()
    print(json.dumps(config.to_dict(), indent=2))
    return 0
