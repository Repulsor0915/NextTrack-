"""Attach verified metadata to a matching pre-Stage-4 database."""

from pathlib import Path

from django.core.management.base import BaseCommand

from recommendations.catalogue_import import (
    adopt_existing_snapshot,
    read_verified_snapshot,
)


class Command(BaseCommand):
    help = "Verify all legacy rows against a snapshot, then register it as active."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path)

    def handle(self, *args, **options):
        snapshot = read_verified_snapshot(options["path"])
        adopt_existing_snapshot(snapshot)
        self.stdout.write(
            self.style.SUCCESS(
                f"Adopted {len(snapshot.records)} matching rows as "
                f"{snapshot.version} ({snapshot.sha256})."
            )
        )
