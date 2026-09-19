from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from offline_evaluation.feature_similarity import (
    factorial_comparisons,
    run_study,
    summarize_study,
    validate_baseline_replay,
    write_study,
)
from offline_evaluation.protocol import ProtocolValidationError, load_json, sha256_file
from offline_evaluation.runner import load_frozen_protocol


class Command(BaseCommand):
    help = "Run isolated 3x2 Basic CBF feature-weight/similarity study (step 2.2)."

    def add_arguments(self, parser):
        parser.add_argument("--evaluation-dir", default="evaluation")
        parser.add_argument(
            "--output-dir", default="evaluation/studies/feature-similarity-v2"
        )
        parser.add_argument("--latency-repetitions", type=int, default=5)

    def handle(self, *args, **options):
        project_root = Path(settings.BASE_DIR).parent.resolve()

        def resolve_project_path(value):
            path = Path(value)
            return path.resolve() if path.is_absolute() else (project_root / path).resolve()

        evaluation_dir = resolve_project_path(options["evaluation_dir"])
        output_dir = resolve_project_path(options["output_dir"])
        if output_dir.exists() and any(output_dir.iterdir()):
            raise CommandError(f"Refusing to overwrite existing study: {output_dir}")
        try:
            protocol_config, pool, scenarios, tracks = load_frozen_protocol(
                project_root=project_root, evaluation_dir=evaluation_dir
            )
            baseline_dir = evaluation_dir / "results"
            baseline_manifest = load_json(baseline_dir / "manifest.json")
            baseline_path = baseline_dir / "recommendation-runs.json"
            if (
                sha256_file(baseline_path)
                != baseline_manifest["outputs"]["recommendation-runs.json"]["sha256"]
            ):
                raise ProtocolValidationError("Prior baseline result checksum differs.")
            if baseline_manifest["scenarios_sha256"] != protocol_config["scenarios"]["sha256"]:
                raise ProtocolValidationError("Prior baseline used different scenarios.")
            configs, runs, metric_rows, comparison_rows = run_study(
                protocol_config=protocol_config,
                pool=pool,
                scenarios=scenarios,
                tracks=tracks,
                latency_repetitions=options["latency_repetitions"],
            )
            validate_baseline_replay(runs, baseline_path)
            summary_rows = summarize_study(metric_rows, comparison_rows)
            factorial_rows, factorial_summary = factorial_comparisons(runs)
            source_checksums = {
                str(path.relative_to(project_root)).replace("\\", "/"): sha256_file(path)
                for path in (
                    project_root / "backend/recommendations/domain/algorithm_config.py",
                    project_root / "backend/recommendations/domain/cbf_ranker.py",
                    project_root / "backend/recommendations/domain/feature_vectors.py",
                    project_root / "backend/recommendations/domain/explanations.py",
                    project_root / "backend/offline_evaluation/feature_similarity.py",
                )
            }
            result = write_study(
                output_dir=output_dir,
                protocol_config=protocol_config,
                configs=configs,
                runs=runs,
                metric_rows=metric_rows,
                comparison_rows=comparison_rows,
                summary_rows=summary_rows,
                factorial_rows=factorial_rows,
                factorial_summary=factorial_summary,
                latency_repetitions=options["latency_repetitions"],
                source_checksums=source_checksums,
            )
        except (OSError, KeyError, TypeError, ValueError, ProtocolValidationError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS("Feature/similarity study complete."))
        self.stdout.write(str(result))
