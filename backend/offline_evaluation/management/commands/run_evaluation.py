"""Django entry point for the current offline evaluation."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from offline_evaluation.experiments.artifacts import ArtifactError
from offline_evaluation.experiments.config import STUDY_NAMES, load_config
from offline_evaluation.experiments.protocol import ProtocolError
from offline_evaluation.experiments.runner import run_evaluation


class Command(BaseCommand):
    help = "Run the compact catalogue, configuration, comparison, and performance studies."

    def add_arguments(self, parser):
        parser.add_argument("--config", type=Path)
        parser.add_argument("--output-dir", default="evaluation/v2")
        parser.add_argument(
            "--study",
            nargs="+",
            choices=STUDY_NAMES,
            default=list(STUDY_NAMES),
        )

    def handle(self, *args, **options):
        project_root = Path(settings.BASE_DIR).parent.resolve()

        def resolve(path_value):
            path = Path(path_value)
            return path.resolve() if path.is_absolute() else (project_root / path).resolve()

        try:
            config_path = resolve(options["config"]) if options["config"] else None
            manifest = run_evaluation(
                config=load_config(config_path),
                output_dir=resolve(options["output_dir"]),
                selected_studies=tuple(dict.fromkeys(options["study"])),
                progress=self.stdout.write,
            )
        except (OSError, KeyError, TypeError, ValueError, ArtifactError, ProtocolError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(f"Evaluation complete: {manifest}"))
