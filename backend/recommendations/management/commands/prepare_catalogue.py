## Django command for running the catalogue preprocessing pipeline
## The actual CSV validation and transformtaion logic is kept in the catalogue_preprocess.

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalogue_preprocess import CataloguePreparationError, prepare_catalogue


class Command(BaseCommand):
    help = "Build a deterministic catalogue from the raw dataset and optional tracks CSV."

    ## Define the source files, output location, and catalogue metadata.
    def add_arguments(self, parser):
        parser.add_argument("source_csv", type=Path)
        parser.add_argument("output_directory", type=Path)
        parser.add_argument("--catalogue-version", required=True)
        parser.add_argument("--retrieved-date", required=True)
        parser.add_argument("--tracks-csv", type=Path)

    def handle(self, *args, **options):
        #Pass the command-line inputs to the preprocessing package
        try:
            result = prepare_catalogue(
                options["source_csv"],
                options["output_directory"],
                catalogue_version=options["catalogue_version"],
                retrieved_date=options["retrieved_date"],
                tracks_source_path=options["tracks_csv"],
            )
        # Convert preprocessing errors into readable Django command errors. 
        except CataloguePreparationError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                f'Prepared {result["selected_track_count"]} tracks from '
                f'{result["source_row_count"]} source rows; '
                f'{result["rejected_row_count"]} rows rejected.'
            )
        )
