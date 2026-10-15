"""Command-line interface for job-hunt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jobhunt import __version__
from jobhunt.models import STATUSES, Application
from jobhunt.storage import Store

DEFAULT_DB = Path.home() / ".jobhunt" / "jobhunt.db"


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``jobhunt`` command."""
    parser = argparse.ArgumentParser(prog="jobhunt", description="Track job applications locally.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="path to the SQLite database")
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


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    args = build_parser().parse_args(argv)
    with Store(args.db) as store:
        handlers = {
            "add": _cmd_add,
            "list": _cmd_list,
            "show": _cmd_show,
            "update": _cmd_update,
            "remove": _cmd_remove,
            "stats": _cmd_stats,
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
