"""Django entry point for turning verified summaries into SVG figures."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from offline_evaluation.experiments.artifacts import ArtifactError
from offline_evaluation.visualization.publisher import build_report_figures


class Command(BaseCommand):
    help = "Build report SVGs from one verified evaluation output directory."

    def add_arguments(self, parser):
        parser.add_argument("--input-dir", default="evaluation/v2")
        parser.add_argument("--output-dir")

    def handle(self, *args, **options):
        project_root = Path(settings.BASE_DIR).parent.resolve()

        def resolve(value):
            path = Path(value)
            return path.resolve() if path.is_absolute() else (project_root / path).resolve()

        try:
            manifest = build_report_figures(
                resolve(options["input_dir"]),
                resolve(options["output_dir"]) if options["output_dir"] else None,
            )
        except (OSError, KeyError, TypeError, ValueError, ArtifactError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(f"Figures complete: {manifest}"))
