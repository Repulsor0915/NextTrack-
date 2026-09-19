"""Isolated 3x2 Basic CBF feature-weight and similarity study."""

from __future__ import annotations

import csv
import json
import platform
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from statistics import mean, median, pstdev
from time import perf_counter

import django

from recommendations.audio_features import FEATURE_NAMES, build_feature_vector
from recommendations.domain.algorithm_config import (
    CURRENT_FEATURE_WEIGHTS,
    EQUAL_FEATURE_WEIGHTS,
    LITERATURE_INFORMED_FEATURE_WEIGHTS,
    AlgorithmConfig,
)
from recommendations.domain.cbf_ranker import rank_cbf
from recommendations.domain.explanations import build_cbf_explanation
from recommendations.domain.feature_vectors import (
    build_session_profile,
    weighted_euclidean_similarity,
)

from .protocol import ProtocolValidationError, load_json, sha256_file, write_json
from .runner import algorithm_config_from_snapshot


STUDY_SCHEMA_VERSION = "nexttrack-feature-similarity-study-v1"
BASELINE_ID = "current_cosine"
PRIMARY_METRICS = (
    "top10_score_mean",
    "top10_score_median",
    "top10_score_sd",
    "top1_top10_score_gap",
    "candidate_score_mean",
    "candidate_score_median",
    "candidate_score_sd",
    "candidate_score_p10",
    "candidate_score_p90",
    "candidate_score_p90_p10_gap",
    "candidate_fraction_at_least_095",
    "fixed_reference_history_match",
    "artist_hhi",
    "artist_max_share",
    "genre_hhi",
    "genre_max_share",
    "latency_median_ms",
)
COMPARISON_METRICS = (
    "top10_overlap_count",
    "top10_jaccard",
    "mean_absolute_rank_change_common",
    "top1_changed",
)
FACTORIAL_PAIRS = (
    ("current_cosine", "equal_cosine", "weight_effect_at_cosine"),
    ("current_cosine", "literature_cosine", "weight_effect_at_cosine"),
    ("current_euclidean", "equal_euclidean", "weight_effect_at_euclidean"),
    ("current_euclidean", "literature_euclidean", "weight_effect_at_euclidean"),
    ("current_cosine", "current_euclidean", "metric_effect_at_current_weights"),
    ("equal_cosine", "equal_euclidean", "metric_effect_at_equal_weights"),
    ("literature_cosine", "literature_euclidean", "metric_effect_at_literature_weights"),
)


def leave_out_weights(weights: dict, excluded: set[str]) -> dict[str, float]:
    if not excluded or not excluded.issubset(FEATURE_NAMES):
        raise ValueError("Excluded features must be a non-empty subset of the eight features.")
    remaining_total = sum(
        weights[name] for name in FEATURE_NAMES if name not in excluded
    )
    if remaining_total <= 0:
        raise ValueError("At least one positive feature weight must remain.")
    return {
        name: 0.0 if name in excluded else weights[name] / remaining_total
        for name in FEATURE_NAMES
    }


def study_configs(baseline: AlgorithmConfig) -> dict[str, AlgorithmConfig]:
    """Six primary cells plus three current-cosine sensitivity checks."""

    weights_by_name = {
        "current": CURRENT_FEATURE_WEIGHTS,
        "equal": EQUAL_FEATURE_WEIGHTS,
        "literature": LITERATURE_INFORMED_FEATURE_WEIGHTS,
    }
    configs = {
        f"{weight_name}_{metric_name}": replace(
            baseline,
            name=f"feature-similarity-{weight_name}-{metric_name}-v1",
            feature_weights=weights,
            relevance_similarity_metric=metric,
        )
        for weight_name, weights in weights_by_name.items()
        for metric_name, metric in (
            ("cosine", "weighted_cosine"),
            ("euclidean", "weighted_euclidean"),
        )
    }
    for suffix, excluded in (
        ("without_energy", {"energy"}),
        ("without_valence", {"valence"}),
        ("without_energy_valence", {"energy", "valence"}),
    ):
        configs[f"{suffix}_cosine"] = replace(
            baseline,
            name=f"feature-similarity-{suffix}-cosine-v1",
            feature_weights=leave_out_weights(CURRENT_FEATURE_WEIGHTS, excluded),
            relevance_similarity_metric="weighted_cosine",
        )
    return configs


def percentile(values: list[float], proportion: float) -> float:
    if not values or not 0 <= proportion <= 1:
        raise ValueError("A non-empty sample and proportion in [0, 1] are required.")
    ordered = sorted(values)
    position = (len(ordered) - 1) * proportion
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def concentration(tracks: list) -> dict[str, float]:
    """HHI uses fractional multi-label genre counts so every song contributes 1."""

    artist_counts = Counter(track.artist for track in tracks)
    genre_counts = defaultdict(float)
    for track in tracks:
        genres = sorted(set(track.genres)) or ["<unknown>"]
        for genre in genres:
            genre_counts[genre] += 1 / len(genres)
    total = len(tracks)
    return {
        "artist_hhi": sum((count / total) ** 2 for count in artist_counts.values()),
        "artist_max_share": max(artist_counts.values()) / total,
        "genre_hhi": sum((count / total) ** 2 for count in genre_counts.values()),
        "genre_max_share": max(genre_counts.values()) / total,
    }


def top10_comparison(baseline_ids: list[str], variant_ids: list[str]) -> dict:
    baseline_rank = {track_id: rank for rank, track_id in enumerate(baseline_ids, 1)}
    variant_rank = {track_id: rank for rank, track_id in enumerate(variant_ids, 1)}
    if len(baseline_rank) != len(baseline_ids) or len(variant_rank) != len(variant_ids):
        raise ValueError("Top-10 lists must not contain duplicate IDs.")
    common = set(baseline_rank) & set(variant_rank)
    union = set(baseline_rank) | set(variant_rank)
    rank_changes = [
        {
            "track_id": track_id,
            "baseline_rank": baseline_rank.get(track_id),
            "variant_rank": variant_rank.get(track_id),
            "rank_delta_variant_minus_baseline": (
                variant_rank[track_id] - baseline_rank[track_id]
                if track_id in common else None
            ),
        }
        for track_id in sorted(
            union, key=lambda item: (baseline_rank.get(item, 11), variant_rank.get(item, 11), item)
        )
    ]
    return {
        "top10_overlap_count": len(common),
        "top10_jaccard": len(common) / len(union) if union else 1.0,
        "mean_absolute_rank_change_common": (
            mean(abs(variant_rank[item] - baseline_rank[item]) for item in common)
            if common else None
        ),
        "top1_changed": baseline_ids[0] != variant_ids[0],
        "rank_changes": rank_changes,
    }


def run_study(*, protocol_config: dict, pool: dict, scenarios: dict, tracks: dict,
              latency_repetitions: int = 5) -> tuple[dict, list[dict], list[dict], list[dict]]:
    if latency_repetitions < 1:
        raise ValueError("At least one latency repetition is required.")
    baseline = algorithm_config_from_snapshot(
        protocol_config["algorithms"]["algorithm_config"]
    )
    configs = study_configs(baseline)
    pool_ids = pool["track_ids"]
    vectors = {track_id: build_feature_vector(track.features) for track_id, track in tracks.items()}
    candidate_vectors = [(tracks[track_id], vectors[track_id]) for track_id in pool_ids]
    selected_scenarios = [
        scenario for scenario in scenarios["scenarios"]
        if "cbf" in scenario["applicable_algorithms"]
        and scenario["request_template"]["history"]
    ]
    if len(selected_scenarios) != protocol_config["algorithms"]["eligible_scenario_counts"]["cbf"]:
        raise ProtocolValidationError("Frozen CBF scenario count changed.")
    runs = []
    metric_rows = []
    comparison_rows = []
    for scenario in selected_scenarios:
        history = scenario["request_template"]["history"]
        profile = build_session_profile(
            [vectors[track_id] for track_id in history],
            window_size=baseline.history_window_size,
        )
        scenario_runs = {}
        for config_id, algorithm_config in configs.items():
            # The warm-up is not measured. Profile/vector construction, DB access,
            # serialization and file I/O are outside the ranking timer.
            ranked = rank_cbf(
                candidate_vectors, profile, len(candidate_vectors),
                algorithm_config=algorithm_config,
            )
            elapsed = []
            for _ in range(latency_repetitions):
                started = perf_counter()
                repeated = rank_cbf(
                    candidate_vectors, profile, len(candidate_vectors),
                    algorithm_config=algorithm_config,
                )
                elapsed.append((perf_counter() - started) * 1000)
                if [item.candidate.id for item in repeated[:10]] != [
                    item.candidate.id for item in ranked[:10]
                ]:
                    raise ProtocolValidationError("CBF ranking changed between repetitions.")
            top = ranked[:scenario["request_template"]["limit"]]
            top_ids = [item.candidate.id for item in top]
            candidate_scores = [item.score for item in ranked]
            top_scores = [item.score for item in top]
            metrics = {
                "top10_score_mean": mean(top_scores),
                "top10_score_median": median(top_scores),
                "top10_score_sd": pstdev(top_scores),
                "top1_top10_score_gap": top_scores[0] - top_scores[-1],
                "candidate_score_mean": mean(candidate_scores),
                "candidate_score_median": median(candidate_scores),
                "candidate_score_sd": pstdev(candidate_scores),
                "candidate_score_p10": percentile(candidate_scores, 0.1),
                "candidate_score_p90": percentile(candidate_scores, 0.9),
                "candidate_score_p90_p10_gap": (
                    percentile(candidate_scores, 0.9)
                    - percentile(candidate_scores, 0.1)
                ),
                "candidate_fraction_at_least_095": sum(
                    score >= 0.95 for score in candidate_scores
                ) / len(candidate_scores),
                "fixed_reference_history_match": mean(
                    weighted_euclidean_similarity(
                        profile, vectors[item.candidate.id],
                        weights=EQUAL_FEATURE_WEIGHTS,
                    )
                    for item in top
                ),
                "latency_median_ms": median(elapsed),
                "latency_samples_ms": elapsed,
                **concentration([item.candidate for item in top]),
            }
            run = {
                "scenario_id": scenario["scenario_id"],
                "category": scenario["category"],
                "config_id": config_id,
                "history": history,
                "requested_mood_ignored_by_cbf": scenario["request_template"]["context"].get("mood"),
                "candidate_scores_ranked": [
                    {"rank": rank, "track_id": item.candidate.id, "score": item.score}
                    for rank, item in enumerate(ranked, 1)
                ],
                "top10": [
                    {
                        "rank": rank,
                        "id": item.candidate.id,
                        "title": item.candidate.title,
                        "artist": item.candidate.artist,
                        "genres": item.candidate.genres,
                        "score": item.score,
                        "feature_closeness": item.feature_closeness,
                        "existing_explanation": build_cbf_explanation(
                            item.score, item.feature_closeness,
                            feature_weights=algorithm_config.feature_weights,
                        ),
                    }
                    for rank, item in enumerate(top, 1)
                ],
                "metrics": metrics,
            }
            runs.append(run)
            scenario_runs[config_id] = run
            metric_rows.append({
                "scenario_id": scenario["scenario_id"],
                "category": scenario["category"],
                "config_id": config_id,
                **{name: metrics[name] for name in PRIMARY_METRICS},
            })
        baseline_ids = [item["id"] for item in scenario_runs[BASELINE_ID]["top10"]]
        for config_id, run in scenario_runs.items():
            compared = top10_comparison(
                baseline_ids, [item["id"] for item in run["top10"]]
            )
            comparison_rows.append({
                "scenario_id": scenario["scenario_id"],
                "category": scenario["category"],
                "config_id": config_id,
                **compared,
            })
    return configs, runs, metric_rows, comparison_rows


def summarize_study(metric_rows: list[dict], comparison_rows: list[dict]) -> list[dict]:
    comparisons = {
        (row["scenario_id"], row["config_id"]): row
        for row in comparison_rows
    }
    groups = defaultdict(list)
    for row in metric_rows:
        groups[(row["config_id"], "all_history")].append(row)
        groups[(row["config_id"], row["category"])].append(row)
    summary = []
    for (config_id, category), rows in sorted(groups.items()):
        item = {"config_id": config_id, "category": category, "scenario_count": len(rows)}
        for name in PRIMARY_METRICS:
            item[f"mean_{name}"] = mean(row[name] for row in rows)
        for name in COMPARISON_METRICS:
            values = [
                comparisons[(row["scenario_id"], config_id)][name]
                for row in rows
            ]
            available = [value for value in values if value is not None]
            item[f"mean_{name}"] = mean(available) if available else None
        summary.append(item)
    return summary


def factorial_comparisons(runs: list[dict]) -> tuple[list[dict], list[dict]]:
    by_scenario = defaultdict(dict)
    for run in runs:
        by_scenario[run["scenario_id"]][run["config_id"]] = run
    rows = []
    for scenario_id, configurations in by_scenario.items():
        for reference_id, variant_id, question in FACTORIAL_PAIRS:
            reference = configurations[reference_id]
            variant = configurations[variant_id]
            compared = top10_comparison(
                [item["id"] for item in reference["top10"]],
                [item["id"] for item in variant["top10"]],
            )
            rows.append({
                "scenario_id": scenario_id,
                "category": reference["category"],
                "reference_config_id": reference_id,
                "variant_config_id": variant_id,
                "question": question,
                **compared,
            })
    groups = defaultdict(list)
    for row in rows:
        groups[(row["reference_config_id"], row["variant_config_id"], "all_history")].append(row)
        groups[(row["reference_config_id"], row["variant_config_id"], row["category"])].append(row)
    summary = []
    for (reference_id, variant_id, category), members in sorted(groups.items()):
        common_rank_changes = [
            member["mean_absolute_rank_change_common"]
            for member in members
            if member["mean_absolute_rank_change_common"] is not None
        ]
        summary.append({
            "reference_config_id": reference_id,
            "variant_config_id": variant_id,
            "category": category,
            "scenario_count": len(members),
            "mean_top10_overlap_count": mean(item["top10_overlap_count"] for item in members),
            "mean_top10_jaccard": mean(item["top10_jaccard"] for item in members),
            "mean_absolute_rank_change_common": (
                mean(common_rank_changes) if common_rank_changes else None
            ),
            "top1_changed_count": sum(item["top1_changed"] for item in members),
        })
    return rows, summary


def validate_baseline_replay(runs: list[dict], baseline_results_path: Path) -> None:
    baseline_file = load_json(baseline_results_path)
    previous = {
        run["scenario_id"]: run
        for run in baseline_file["runs"] if run["algorithm"] == "cbf"
    }
    current = {
        run["scenario_id"]: run
        for run in runs if run["config_id"] == BASELINE_ID
    }
    if previous.keys() != current.keys():
        raise ProtocolValidationError("CBF scenario IDs differ from the frozen baseline.")
    for scenario_id, run in current.items():
        old = previous[scenario_id]["recommendations"]
        new = run["top10"]
        if [item["track"]["id"] for item in old] != [item["id"] for item in new]:
            raise ProtocolValidationError(f"Baseline Top-10 mismatch: {scenario_id}.")
        if any(item["score"] != round(other["score"], 4)
               for item, other in zip(old, new, strict=True)):
            raise ProtocolValidationError(f"Baseline score mismatch: {scenario_id}.")


def write_study(*, output_dir: Path, protocol_config: dict, configs: dict,
                runs: list[dict], metric_rows: list[dict], comparison_rows: list[dict],
                summary_rows: list[dict], factorial_rows: list[dict],
                factorial_summary: list[dict], latency_repetitions: int,
                source_checksums: dict) -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ProtocolValidationError(f"Refusing to overwrite study: {output_dir}.")
    output_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "schema_version": STUDY_SCHEMA_VERSION,
        "study_id": "feature-similarity-v2",
        "source_experiment_id": protocol_config["experiment_id"],
        "catalogue_sha256": protocol_config["catalogue"]["sha256"],
        "candidate_pool_sha256": protocol_config["candidate_pool"]["sha256"],
        "scenarios_sha256": protocol_config["scenarios"]["sha256"],
        "algorithm": "basic_cbf_only",
        "scenario_policy": "all frozen history scenarios; requested mood ignored by Basic CBF",
        "candidate_count": protocol_config["candidate_pool"]["track_count"],
        "candidate_pool_selection_seed": protocol_config["randomness"]["candidate_pool_seed"],
        "top_n": protocol_config["ranking"]["top_n"],
        "primary_matrix": [
            f"{weight}_{metric}"
            for weight in ("current", "equal", "literature")
            for metric in ("cosine", "euclidean")
        ],
        "sensitivity_checks": [
            "without_energy_cosine", "without_valence_cosine",
            "without_energy_valence_cosine",
        ],
        "literature_weight_preset_is_experimental_not_proven_optimal": True,
        "latency": {
            "repetitions": latency_repetitions,
            "warmup_calls": 1,
            "scope": "rank_cbf only; excludes DB, vector/profile construction and JSON I/O",
        },
        "genre_concentration": "fractional multi-label genre shares; HHI=sum(share^2)",
        "reference_history_match": "Equal-weight Euclidean fit to the same Basic CBF session profile; diagnostic, not a relevance label.",
        "scores_across_metrics_are_not_calibrated_or_directly_comparable": True,
        "production_default_unchanged": True,
        "environment": {
            "python": platform.python_version(),
            "django": django.get_version(),
            "operating_system": platform.platform(),
        },
        "source_checksums": source_checksums,
        "configs": {key: value.to_dict() for key, value in configs.items()},
    }
    files = {
        "experiment-config.json": config,
        "runs.json": {
            "schema_version": STUDY_SCHEMA_VERSION,
            "run_count": len(runs),
            "runs": runs,
        },
        "scenario-metrics.json": {
            "schema_version": STUDY_SCHEMA_VERSION,
            "rows": metric_rows,
        },
        "comparisons.json": {
            "schema_version": STUDY_SCHEMA_VERSION,
            "baseline_config_id": BASELINE_ID,
            "rows": comparison_rows,
        },
        "factorial-comparisons.json": {
            "schema_version": STUDY_SCHEMA_VERSION,
            "method": "Paired weight changes at fixed metric and metric changes at fixed weights.",
            "rows": factorial_rows,
        },
        "factorial-summary.json": {
            "schema_version": STUDY_SCHEMA_VERSION,
            "rows": factorial_summary,
        },
        "summary.json": {
            "schema_version": STUDY_SCHEMA_VERSION,
            "rows": summary_rows,
        },
    }
    for name, content in files.items():
        if name == "runs.json":
            # Keep the complete 500-score evidence without turning a review
            # diff into hundreds of thousands of formatting-only lines.
            (output_dir / name).write_bytes(
                (json.dumps(content, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")) + "\n").encode("utf-8")
            )
        else:
            write_json(output_dir / name, content)
    _write_csv(output_dir / "scenario-metrics.csv", metric_rows)
    _write_csv(
        output_dir / "comparisons.csv",
        [{key: value for key, value in row.items() if key != "rank_changes"}
         for row in comparison_rows],
    )
    _write_csv(output_dir / "summary.csv", summary_rows)
    _write_csv(
        output_dir / "factorial-comparisons.csv",
        [{key: value for key, value in row.items() if key != "rank_changes"}
         for row in factorial_rows],
    )
    _write_csv(output_dir / "factorial-summary.csv", factorial_summary)
    output_files = sorted(path for path in output_dir.iterdir() if path.is_file())
    write_json(output_dir / "manifest.json", {
        "schema_version": STUDY_SCHEMA_VERSION,
        "catalogue_sha256": config["catalogue_sha256"],
        "candidate_pool_sha256": config["candidate_pool_sha256"],
        "scenarios_sha256": config["scenarios_sha256"],
        "primary_run_count": len(config["primary_matrix"]) * (len(runs) // len(configs)),
        "sensitivity_run_count": len(config["sensitivity_checks"]) * (len(runs) // len(configs)),
        "outputs": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in output_files
        },
    })
    return {"run_count": len(runs), "scenario_count": len(runs) // len(configs),
            "manifest": str(output_dir / "manifest.json")}


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
