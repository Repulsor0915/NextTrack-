from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from offline_evaluation.protocol import (
    DEFAULT_COHERENT_GENRES,
    ProtocolValidationError,
    prepare_protocol,
)


class Command(BaseCommand):
    help = (
        "Create experiment-config.json, a fixed candidate pool, and a "
        "deterministic scenarios draft for human review."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--full-catalogue",
            default="data/processed/spotify-tracks-kaggle-full/catalogue.json",
        )
        parser.add_argument(
            "--full-manifest",
            default="data/processed/spotify-tracks-kaggle-full/manifest.json",
        )
        parser.add_argument(
            "--candidate-catalogue",
            default=(
                "data/processed/spotify-tracks-kaggle-test-500/catalogue.json"
            ),
        )
        parser.add_argument(
            "--candidate-manifest",
            default="data/processed/spotify-tracks-kaggle-test-500/manifest.json",
        )
        parser.add_argument("--output-directory", default="evaluation")
        parser.add_argument("--protocol-date", required=True)
        parser.add_argument("--seed", type=int, default=221611)
        parser.add_argument("--top-n", type=int, default=10)
        parser.add_argument("--random-repetitions", type=int, default=30)
        parser.add_argument("--expected-candidate-count", type=int, default=500)
        parser.add_argument(
            "--coherent-genres",
            nargs="+",
            default=list(DEFAULT_COHERENT_GENRES),
        )
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        project_root = Path(settings.BASE_DIR).parent.resolve()

        def source_path(option_name):
            path = Path(options[option_name])
            return path if path.is_absolute() else project_root / path

        output_directory = Path(options["output_directory"])
        if not output_directory.is_absolute():
            output_directory = project_root / output_directory

        try:
            result = prepare_protocol(
                project_root=project_root,
                full_catalogue_path=source_path("full_catalogue"),
                full_manifest_path=source_path("full_manifest"),
                candidate_catalogue_path=source_path("candidate_catalogue"),
                candidate_manifest_path=source_path("candidate_manifest"),
                output_directory=output_directory,
                protocol_date=options["protocol_date"],
                seed=options["seed"],
                top_n=options["top_n"],
                random_repetitions=options["random_repetitions"],
                expected_candidate_count=options["expected_candidate_count"],
                coherent_genres=tuple(options["coherent_genres"]),
                force=options["force"],
            )
        except (OSError, KeyError, TypeError, ProtocolValidationError) as error:
            raise CommandError(str(error)) from error

        self.stdout.write(self.style.SUCCESS("Evaluation protocol draft created."))
        self.stdout.write(f'Candidate tracks: {result["candidate_count"]}')
        self.stdout.write(f'Scenarios: {result["scenario_count"]}')
        self.stdout.write(f'Categories: {result["category_counts"]}')
        self.stdout.write(
            f'Expected baseline runs after approval: '
            f'{result["expected_baseline_run_count"]}'
        )
        self.stdout.write(
            "Human review is required before scenarios.draft.json can be frozen."
        )
