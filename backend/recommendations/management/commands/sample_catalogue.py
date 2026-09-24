

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalogue_preprocess import CataloguePreparationError, sample_catalogue


class Command(BaseCommand):
    help = "Create a deterministic test sample from a frozen full catalogue."

    def add_arguments(self, parser):
        parser.add_argument("parent_catalogue", type=Path)
        parser.add_argument("output_directory", type=Path)
        parser.add_argument("--limit", type=int, required=True)
        parser.add_argument("--seed", type=int, required=True)
        parser.add_argument("--catalogue-version", required=True)

    def handle(self, *args, **options):
        try:
            result = sample_catalogue(
                options["parent_catalogue"],
                options["output_directory"],
                catalogue_version=options["catalogue_version"],
                limit=options["limit"],
                seed=options["seed"],
            )
        except CataloguePreparationError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                f'Sampled {result["selected_track_count"]} tracks from '
                f'{result["parent_track_count"]} parent tracks.'
            )
        )
