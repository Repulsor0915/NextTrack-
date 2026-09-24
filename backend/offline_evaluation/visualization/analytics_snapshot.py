"""Publish a compact, verified V2 snapshot for the Analytics page."""

from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path

from offline_evaluation.experiments.artifacts import (
    ArtifactError,
    file_metadata,
    load_json,
    verify_outputs,
    write_json,
)

from .loader import load_summary, load_table, load_verified_run


METHOD_ORDER = ("random", "cbf", "context_no_mmr", "context_mmr")
FIGURES = (
    {
        "name": "01-catalogue-clamping.svg",
        "group": "configuration",
        "title": "Catalogue values outside runtime ranges",
        "caption": "Shows the percentage of usable tracks clamped when runtime feature vectors are built.",
    },
    {
        "name": "02-cbf-configuration.svg",
        "group": "configuration",
        "title": "CBF configuration comparison",
        "caption": "Compares feature weights and similarity metrics on the fixed candidate pool.",
    },
    {
        "name": "03-context-configuration.svg",
        "group": "configuration",
        "title": "Context parameter trade-offs",
        "caption": "Compares history profiles, history and mood ratios, and MMR strengths.",
    },
    {
        "name": "04-method-comparison.svg",
        "group": "comparison",
        "title": "Recommendation method comparison",
        "caption": "Compares Random, Basic CBF, Context, and Context with MMR using diagnostic proxies.",
    },
    {
        "name": "05-latency.svg",
        "group": "latency",
        "title": "Recommendation service latency",
        "caption": "Local P50 and P95 service time for fixed-pool and full-catalogue requests.",
    },
)


def _ordered_method_rows(rows: list[dict], category: str) -> list[dict]:
    by_method = {
        row["method"]: row for row in rows if row["category"] == category
    }
    return [by_method[method] for method in METHOD_ORDER if method in by_method]


def aggregate_pairwise(rows: list[dict]) -> list[dict]:
    """Combine scenario-level comparisons using their paired-run counts."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["left_method"], row["right_method"])].append(row)

    output = []
    for (left_method, right_method), group in grouped.items():
        comparison_count = sum(row["comparison_count"] for row in group)

        def weighted(field):
            return sum(
                row[field] * row["comparison_count"] for row in group
            ) / comparison_count

        output.append(
            {
                "left_method": left_method,
                "right_method": right_method,
                "scenario_count": len(group),
                "comparison_count": comparison_count,
                "mean_top10_jaccard": weighted("mean_jaccard"),
                "mean_overlap_count": weighted("mean_overlap"),
                "top1_same_fraction": weighted("top1_same_fraction"),
            }
        )
    return output


def build_analytics_snapshot(run_dir: Path) -> dict:
    manifest = load_verified_run(run_dir)
    protocol = load_json(run_dir / "protocol.json")
    catalogue = load_summary(run_dir, "catalogue")
    comparison = load_summary(run_dir, "comparison")["rows"]
    performance = load_summary(run_dir, "performance")["rows"]
    pairwise = load_table(run_dir, "comparison", "pairwise")

    figure_dir = run_dir / "figures"
    figure_manifest_path = figure_dir / "manifest.json"
    if not figure_manifest_path.is_file():
        raise ArtifactError("The V2 figure manifest is missing.")
    figure_manifest = load_json(figure_manifest_path)
    if figure_manifest.get("schema_version") != "nexttrack-evaluation-figures-v2":
        raise ArtifactError("The V2 figure manifest schema is not supported.")
    if figure_manifest.get("source_evaluation_manifest") != file_metadata(
        run_dir / "manifest.json"
    ):
        raise ArtifactError("The figures were not built from this evaluation run.")
    verify_outputs(figure_dir, figure_manifest["outputs"])

    settings = protocol["evaluation_config"]
    figures = []
    for definition in FIGURES:
        metadata = figure_manifest["outputs"][definition["name"]]
        figures.append(
            {
                "path": f"figures/{definition['name']}",
                "group": definition["group"],
                "title": definition["title"],
                "caption": definition["caption"],
                "sha256": metadata["sha256"],
            }
        )

    return {
        "schema_version": "nexttrack-analytics-snapshot-v2",
        "catalogue": {
            "version": catalogue["catalogue_version"],
            "sha256": catalogue["catalogue_sha256"],
            "track_count": catalogue["database_track_count"],
            "usable_feature_count": catalogue["usable_feature_count"],
            "missing_artist_count": catalogue["missing_artist_display_count"],
            "missing_album_count": catalogue["missing_album_count"],
            "multi_artist_track_count": catalogue["multi_artist_track_count"],
        },
        "protocol": {
            "candidate_count": settings["candidate_count"],
            "scenario_count": len(protocol["scenarios"]),
            "random_seed_count": settings["random_repetitions"],
            "top_n": settings["top_n"],
            "run_count": sum(manifest["run_counts"].values()),
            "run_counts": manifest["run_counts"],
            "candidate_artist_policy": settings["candidate_artist_policy"],
        },
        "methods": _ordered_method_rows(comparison, "all"),
        "transition": _ordered_method_rows(comparison, "mood_transition"),
        "pairwise": aggregate_pairwise(pairwise),
        "warm_performance": [
            row for row in performance if row["phase"] == "same_process_warm"
        ],
        "figures": figures,
        "warnings": catalogue["warnings"],
        "provenance": {
            "evaluation_manifest_sha256": file_metadata(
                run_dir / "manifest.json"
            )["sha256"],
            "figure_manifest_sha256": file_metadata(figure_manifest_path)["sha256"],
        },
    }


def publish_analytics_snapshot(run_dir: Path, destination: Path) -> Path:
    snapshot = build_analytics_snapshot(run_dir)
    destination.mkdir(parents=True, exist_ok=True)
    write_json(destination / "snapshot.json", snapshot)

    source_figures = run_dir / "figures"
    destination_figures = destination / "figures"
    temporary_figures = destination / "figures.tmp"
    if temporary_figures.exists():
        shutil.rmtree(temporary_figures)
    temporary_figures.mkdir()
    for figure in snapshot["figures"]:
        name = Path(figure["path"]).name
        shutil.copy2(source_figures / name, temporary_figures / name)
    if destination_figures.exists():
        shutil.rmtree(destination_figures)
    temporary_figures.replace(destination_figures)
    return destination / "snapshot.json"
