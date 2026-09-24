## Django command for importing a verified processed catalogue into the Database.
## Handling validation, import planning, and databse writing

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from recommendations.catalogue_import import (
    apply_import_plan,
    build_import_plan,
    read_verified_snapshot,
)


class Command(BaseCommand):
    help = "Import one verified catalogue snapshot into the active database."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path, help="Processed catalogue.json path.")
        parser.add_argument(
            "--data-source",
            help="Optional version assertion; must match the sibling manifest.",
        )
        modes = parser.add_mutually_exclusive_group()
        modes.add_argument(
            "--replace",
            action="store_true",
            help="Rebuild the catalogue from the verified snapshot.",
        )
        modes.add_argument(
            "--prune",
            action="store_true",
            help="Synchronize rows and remove IDs absent from the snapshot.",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Validate and preview only."
        )
        parser.add_argument(
            "--confirm-version",
            help="Required for a nonempty database with --replace or --prune.",
        )
        parser.add_argument(
            "--confirm-sha256",
            help="Required for a nonempty database with --replace or --prune.",
        )
        parser.add_argument(
            "--confirm-plan",
            help="Preview token from --dry-run; required for destructive sync.",
        )
        parser.add_argument(
            "--allow-large-prune",
            action="store_true",
            help="Explicitly allow pruning more than 10 percent of existing tracks.",
        )

    def handle(self, *args, **options):
        snapshot = read_verified_snapshot(
            options["path"], asserted_version=options.get("data_source")
        )
        plan = build_import_plan(
            snapshot, replace=options["replace"], prune=options["prune"]
        )
        if options["dry_run"]:
            self.stdout.write(json.dumps(plan.summary, sort_keys=True))
            return

        summary = apply_import_plan(
            plan,
            confirm_version=options.get("confirm_version"),
            confirm_sha256=options.get("confirm_sha256"),
            confirm_plan=options.get("confirm_plan"),
            allow_large_prune=options["allow_large_prune"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {summary['incoming_count']} tracks from {snapshot.path} "
                f"({summary['created']} created, {summary['updated']} updated, "
                f"{summary['deleted']} deleted, mode={summary['mode']}, "
                f"version={snapshot.version})."
            )
        )
