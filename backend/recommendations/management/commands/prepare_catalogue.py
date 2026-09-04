from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from recommendations.preprocessing.catalogue import (
    CataloguePreparationError,
    prepare_catalogue,
)


class Command(BaseCommand):
    help = "Validate and prepare the pinned Spotify Tracks Dataset catalogue."

    def add_arguments(self, parser):
        parser.add_argument("source_csv", type=Path)
        parser.add_argument("output_directory", type=Path)
        selection_group = parser.add_mutually_exclusive_group()
        selection_group.add_argument("--limit", type=int, default=20)
        selection_group.add_argument(
            "--all-valid",
            action="store_true",
            help="Include every valid unique track instead of taking a sample.",
        )
        parser.add_argument("--seed", type=int, default=20260904)
        parser.add_argument(
            "--catalogue-version",
            default="spotify-tracks-kaggle-v1-spike-20",
        )
        parser.add_argument("--retrieved-date", default="2026-09-04")
        parser.add_argument("--write-full-exclusions", action="store_true")

    def handle(self, *args, **options):
        try:
            result = prepare_catalogue(
                options["source_csv"],
                options["output_directory"],
                limit=None if options["all_valid"] else options["limit"],
                seed=options["seed"],
                catalogue_version=options["catalogue_version"],
                retrieved_date=options["retrieved_date"],
                write_full_exclusions=options["write_full_exclusions"],
            )
        except CataloguePreparationError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                "Prepared "
                f'{result["selected_track_count"]} tracks from '
                f'{result["valid_unique_track_count"]} valid unique tracks; '
                f'{result["excluded_source_row_count"]} source rows excluded.'
            )
        )
