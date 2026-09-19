import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from offline_evaluation.protocol import (
    ProtocolValidationError,
    load_json,
    sha256_file,
    write_json,
)
from offline_evaluation.runner import (
    algorithm_config_from_snapshot,
    comparison_configs,
    load_frozen_protocol,
    run_configuration,
    save_result_set,
)


class Command(BaseCommand):
    help = "Run the frozen offline baseline or one-factor parameter comparisons."

    def add_arguments(self, parser):
        parser.add_argument("--mode", choices=("baseline", "compare"), required=True)
        parser.add_argument("--evaluation-dir", default="evaluation")

    def handle(self, *args, **options):
        project_root = Path(settings.BASE_DIR).parent.resolve()
        evaluation_dir = Path(options["evaluation_dir"])
        if not evaluation_dir.is_absolute():
            evaluation_dir = project_root / evaluation_dir
        try:
            config, pool, scenarios, tracks = load_frozen_protocol(
                project_root=project_root,
                evaluation_dir=evaluation_dir,
            )
            baseline_config = algorithm_config_from_snapshot(
                config["algorithms"]["algorithm_config"]
            )
            results_dir = evaluation_dir / "results"
            if options["mode"] == "baseline":
                runs, summary = run_configuration(
                    config=config,
                    pool=pool,
                    scenario_file=scenarios,
                    tracks=tracks,
                    algorithm_config=baseline_config,
                    include_random=True,
                )
                expected = config["algorithms"]["expected_baseline_run_count"]
                if len(runs) != expected:
                    raise ProtocolValidationError(
                        f"Expected {expected} baseline runs, got {len(runs)}."
                    )
                manifest = save_result_set(
                    output_dir=results_dir,
                    config=config,
                    algorithm_config=baseline_config,
                    runs=runs,
                    summary=summary,
                    result_set_name="baseline",
                )
                self.stdout.write(self.style.SUCCESS(f"Baseline: {len(runs)} runs."))
                self.stdout.write(manifest)
            else:
                self._run_comparisons(
                    config=config,
                    pool=pool,
                    scenarios=scenarios,
                    tracks=tracks,
                    baseline_config=baseline_config,
                    results_dir=results_dir,
                )
        except (OSError, KeyError, TypeError, ValueError, ProtocolValidationError) as error:
            raise CommandError(str(error)) from error

    def _run_comparisons(
        self, *, config, pool, scenarios, tracks, baseline_config, results_dir
    ):
        baseline_manifest_path = results_dir / "manifest.json"
        baseline_manifest = load_json(baseline_manifest_path)
        for name, entry in baseline_manifest["outputs"].items():
            if sha256_file(results_dir / name) != entry["sha256"]:
                raise ProtocolValidationError(f"Baseline checksum mismatch: {name}.")
        if baseline_manifest["scenarios_sha256"] != config["scenarios"]["sha256"]:
            raise ProtocolValidationError("Baseline used different scenarios.")
        baseline_summary = load_json(results_dir / "summary.json")
        baseline_rows = {
            (row["algorithm"], row["category"]): row
            for row in baseline_summary["groups"]
        }
        variants = comparison_configs(baseline_config)
        comparison_dir = results_dir / "comparisons"
        if comparison_dir.exists() and any(comparison_dir.iterdir()):
            raise ProtocolValidationError("Comparison results already exist; refusing overwrite.")
        output_rows = []
        manifests = {}
        for name, variant in variants.items():
            runs, summary = run_configuration(
                config=config,
                pool=pool,
                scenario_file=scenarios,
                tracks=tracks,
                algorithm_config=variant,
                include_random=False,
            )
            manifest_path = save_result_set(
                output_dir=comparison_dir / name,
                config=config,
                algorithm_config=variant,
                runs=runs,
                summary=summary,
                result_set_name=name,
            )
            manifests[name] = str(Path(manifest_path).relative_to(results_dir))
            for row in summary["groups"]:
                baseline = baseline_rows[(row["algorithm"], row["category"])]
                for metric in (
                    "history_match",
                    "mood_match",
                    "intra_list_diversity",
                    "distinct_artist_fraction",
                ):
                    key = f"mean_{metric}"
                    if row[key] is None or baseline[key] is None:
                        continue
                    output_rows.append(
                        {
                            "variant": name,
                            "algorithm": row["algorithm"],
                            "category": row["category"],
                            "metric": metric,
                            "baseline": baseline[key],
                            "variant_value": row[key],
                            "delta_variant_minus_baseline": round(
                                row[key] - baseline[key], 6
                            ),
                        }
                    )
            self.stdout.write(f"{name}: {len(runs)} runs")
        summary_path = results_dir / "parameter-comparison.json"
        csv_path = results_dir / "parameter-comparison.csv"
        write_json(
            summary_path,
            {
                "schema_version": "nexttrack-parameter-comparison-v1",
                "method": "One-factor-at-a-time against the frozen baseline; same scenarios and candidate pool.",
                "caution": "These are diagnostic proxy differences, not evidence of user preference or a globally optimal parameter.",
                "variant_manifests": manifests,
                "rows": output_rows,
            },
        )
        with csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=list(output_rows[0]), lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(output_rows)
        write_json(
            results_dir / "parameter-comparison-manifest.json",
            {
                "schema_version": "nexttrack-parameter-comparison-manifest-v1",
                "baseline_manifest_sha256": sha256_file(baseline_manifest_path),
                "variant_manifests": {
                    name: sha256_file(results_dir / relative_path)
                    for name, relative_path in manifests.items()
                },
                "outputs": {
                    path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
                    for path in (summary_path, csv_path)
                },
            },
        )
        self.stdout.write(self.style.SUCCESS("Parameter comparisons complete."))
