"""Django entry point for publishing verified V2 Analytics assets."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from offline_evaluation.experiments.artifacts import ArtifactError
from offline_evaluation.visualization.analytics_snapshot import (
    publish_analytics_snapshot,
)


class Command(BaseCommand):
    help = "Publish the verified V2 snapshot and figures used by Analytics."

    def add_arguments(self, parser):
        parser.add_argument("--input-dir", default="evaluation/v2")
        parser.add_argument(
            "--output-dir", default="frontend/static/frontend/analytics"
        )

    def handle(self, *args, **options):
        project_root = Path(settings.BASE_DIR).parent.resolve()

        def resolve(value):
            path = Path(value)
            return path.resolve() if path.is_absolute() else (project_root / path).resolve()

        try:
            output = publish_analytics_snapshot(
                resolve(options["input_dir"]), resolve(options["output_dir"])
            )
        except (OSError, KeyError, TypeError, ValueError, ArtifactError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(f"Analytics snapshot published: {output}"))
