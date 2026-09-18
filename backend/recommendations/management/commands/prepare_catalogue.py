from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalogue_pipeline import CataloguePreparationError, prepare_catalogue


class Command(BaseCommand):
    help = "Build a deterministic recommendation catalogue from a raw CSV."

    def add_arguments(self, parser):
        parser.add_argument("source_csv", type=Path)
        parser.add_argument("output_directory", type=Path)
        parser.add_argument("--catalogue-version", required=True)
        parser.add_argument("--retrieved-date", required=True)

    def handle(self, *args, **options):
        try:
            result = prepare_catalogue(
                options["source_csv"],
                options["output_directory"],
                catalogue_version=options["catalogue_version"],
                retrieved_date=options["retrieved_date"],
            )
        except CataloguePreparationError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                f'Prepared {result["selected_track_count"]} tracks from '
                f'{result["source_row_count"]} source rows; '
                f'{result["rejected_row_count"]} rows rejected.'
            )
        )
