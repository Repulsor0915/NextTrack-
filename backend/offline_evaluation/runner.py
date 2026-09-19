"""Run frozen, fixed-pool offline recommendation experiments."""

from __future__ import annotations

import csv
import random
from collections import defaultdict
from dataclasses import replace
from itertools import combinations
from pathlib import Path
from statistics import mean, pstdev

from recommendations.audio_features import FEATURE_NAMES, build_feature_vector
from recommendations.domain.algorithm_config import (
    AlgorithmConfig,
    EQUAL_FEATURE_WEIGHTS,
)
from recommendations.domain.feature_vectors import (
    build_recency_weighted_profile,
    weighted_euclidean_similarity,
)
from recommendations.domain.mood_model import score_mood
from recommendations.models import Track
from recommendations.services.recommendation_service import RecommendationService

from .protocol import ProtocolValidationError, load_json, sha256_file, write_json


RESULT_SCHEMA_VERSION = "nexttrack-offline-results-v1"
METRIC_FIELDS = (
    "history_match",
    "mood_match",
    "intra_list_diversity",
    "distinct_artist_fraction",
    "processing_ms",
)


def load_frozen_protocol(*, project_root: Path, evaluation_dir: Path):
    """Verify all immutable inputs before querying the imported catalogue."""

    config_path = evaluation_dir / "experiment-config.json"
    manifest = load_json(evaluation_dir / "protocol-manifest.json")
    for name, entry in manifest["outputs"].items():
        path = evaluation_dir / name
        if sha256_file(path) != entry["sha256"]:
            raise ProtocolValidationError(f"Protocol checksum mismatch: {name}.")
    config = load_json(config_path)
    if config["protocol_status"] != "frozen" or manifest["protocol_status"] != "frozen":
        raise ProtocolValidationError("Scenarios have not been frozen.")
    pool_path = project_root / config["candidate_pool"]["path"]
    scenarios_path = project_root / config["scenarios"]["path"]
    catalogue_path = project_root / config["catalogue"]["path"]
    for path, expected in (
        (pool_path, config["candidate_pool"]["sha256"]),
        (scenarios_path, config["scenarios"]["sha256"]),
        (catalogue_path, config["catalogue"]["sha256"]),
    ):
        if sha256_file(path) != expected:
            raise ProtocolValidationError(f"Input checksum mismatch: {path}.")

    pool = load_json(pool_path)
    scenarios = load_json(scenarios_path)
    if scenarios["status"] != "frozen_after_user_acceptance":
        raise ProtocolValidationError("Scenario file is not the accepted version.")
    if scenarios["scenario_count"] != len(scenarios["scenarios"]):
        raise ProtocolValidationError("Scenario count is inconsistent.")
    pool_ids = pool["track_ids"]
    if len(pool_ids) != len(set(pool_ids)) or len(pool_ids) != pool["track_count"]:
        raise ProtocolValidationError("Candidate pool IDs are inconsistent.")

    needed_ids = set(pool_ids)
    for scenario in scenarios["scenarios"]:
        request = scenario["request_template"]
        if set(request["history"]) & set(pool_ids):
            raise ProtocolValidationError("History overlaps the candidate pool.")
        needed_ids.update(request["history"])
    tracks = {
        track.id: track
        for track in Track.objects.select_related("features").filter(id__in=needed_ids)
    }
    if len(tracks) != len(needed_ids):
        missing = sorted(needed_ids - set(tracks))
        raise ProtocolValidationError(f"Imported DB lacks protocol tracks: {missing}.")
    if Track.objects.count() != config["catalogue"]["track_count"]:
        raise ProtocolValidationError("Imported DB count differs from frozen catalogue.")
    if any(not hasattr(track, "features") for track in tracks.values()):
        raise ProtocolValidationError("One or more protocol tracks lack features.")
    source_records = {
        record["id"]: record
        for record in load_json(catalogue_path)
        if record["id"] in needed_ids
    }
    if set(source_records) != needed_ids:
        raise ProtocolValidationError("Frozen catalogue lacks a protocol track.")
    for track_id, track in tracks.items():
        source = source_records[track_id]
        if (
            track.title != source["title"]
            or track.artist != source["artist"]
            or track.genres != source["genres"]
            or track.explicit != source["explicit"]
            or track.year != source["year"]
            or track.data_source != config["catalogue"]["catalogue_version"]
            or any(
                getattr(track.features, feature_name) != source["features"][feature_name]
                for feature_name in FEATURE_NAMES
            )
        ):
            raise ProtocolValidationError(
                f"Imported DB record differs from frozen catalogue: {track_id}."
            )
    return config, pool, scenarios, tracks


def algorithm_config_from_snapshot(snapshot: dict) -> AlgorithmConfig:
    fields = dict(snapshot)
    fields.pop("schema_version", None)
    return AlgorithmConfig(**fields)


def comparison_configs(baseline: AlgorithmConfig) -> dict[str, AlgorithmConfig]:
    """Change one experimental dimension at a time from the frozen baseline."""

    return {
        "equal_feature_weights": replace(
            baseline,
            name="equal-feature-weights-v1",
            feature_weights=EQUAL_FEATURE_WEIGHTS,
        ),
        "euclidean_relevance": replace(
            baseline,
            name="euclidean-relevance-v1",
            relevance_similarity_metric="weighted_euclidean",
        ),
        "equal_history_mood_ratio": replace(
            baseline,
            name="history-mood-50-50-v1",
            history_relevance_weight=0.5,
            mood_relevance_weight=0.5,
        ),
        "mmr_60_40": replace(
            baseline,
            name="mmr-relevance-60-diversity-40-v1",
            default_diversity_strength=0.4,
        ),
    }


def run_configuration(
    *,
    config: dict,
    pool: dict,
    scenario_file: dict,
    tracks: dict,
    algorithm_config: AlgorithmConfig,
    include_random: bool,
) -> tuple[list[dict], dict]:
    pool_ids = pool["track_ids"]
    vectors = {track_id: build_feature_vector(track.features) for track_id, track in tracks.items()}
    reference_config = algorithm_config_from_snapshot(config["algorithms"]["algorithm_config"])
    runs = []
    seeds = config["randomness"]["random_baseline_seeds"]
    for scenario in scenario_file["scenarios"]:
        template = scenario["request_template"]
        for algorithm in scenario["applicable_algorithms"]:
            if algorithm == "random" and not include_random:
                continue
            run_seeds = seeds if algorithm == "random" else [None]
            for seed in run_seeds:
                request = {
                    **template,
                    "algorithm": algorithm,
                    "candidate_ids": pool_ids,
                }
                service = RecommendationService(
                    random_source=random.Random(seed) if seed is not None else None,
                    algorithm_config=algorithm_config,
                )
                response = service.recommend(request)
                if response["meta"]["candidate_count"] != len(pool_ids):
                    raise ProtocolValidationError(
                        f"Candidate count changed in {scenario['scenario_id']}."
                    )
                if len(response["recommendations"]) != template["limit"]:
                    raise ProtocolValidationError(
                        f"Top-N not returned in {scenario['scenario_id']}."
                    )
                recommended_ids = [
                    item["track"]["id"] for item in response["recommendations"]
                ]
                if len(set(recommended_ids)) != len(recommended_ids):
                    raise ProtocolValidationError("Recommendation contains duplicates.")
                if not set(recommended_ids).issubset(pool_ids):
                    raise ProtocolValidationError("Recommendation escaped candidate pool.")
                run = {
                    "scenario_id": scenario["scenario_id"],
                    "category": scenario["category"],
                    "algorithm": algorithm,
                    "seed": seed,
                    "algorithm_config_name": algorithm_config.name,
                    "request": {
                        "history": template["history"],
                        "context": template["context"],
                        "limit": template["limit"],
                    },
                    "recommendations": response["recommendations"],
                    "meta": response["meta"],
                    "metrics": diagnostic_metrics(
                        recommended_ids=recommended_ids,
                        history_ids=template["history"],
                        mood=template["context"].get("mood"),
                        tracks=tracks,
                        vectors=vectors,
                        reference_config=reference_config,
                        processing_ms=response["meta"]["processing_ms"],
                    ),
                }
                runs.append(run)
    summary = summarize_runs(runs, pool_count=len(pool_ids))
    return runs, summary


def diagnostic_metrics(
    *,
    recommended_ids: list[str],
    history_ids: list[str],
    mood: str | None,
    tracks: dict,
    vectors: dict,
    reference_config: AlgorithmConfig,
    processing_ms: float,
) -> dict:
    """Compute fixed-ruler proxies, not human relevance or accuracy labels."""

    profile = (
        build_recency_weighted_profile(
            [vectors[track_id] for track_id in history_ids],
            window_size=reference_config.history_window_size,
        )
        if history_ids
        else None
    )
    recommended_vectors = [vectors[track_id] for track_id in recommended_ids]
    pairs = list(combinations(recommended_vectors, 2))
    return {
        "history_match": (
            _rounded_mean(
                weighted_euclidean_similarity(
                    profile, vector, weights=EQUAL_FEATURE_WEIGHTS
                )
                for vector in recommended_vectors
            )
            if profile is not None
            else None
        ),
        "mood_match": (
            _rounded_mean(
                score_mood(
                    vector,
                    mood,
                    feature_weights=reference_config.mood_feature_weights,
                ).fit
                for vector in recommended_vectors
            )
            if mood is not None
            else None
        ),
        "intra_list_diversity": _rounded_mean(
            1.0
            - weighted_euclidean_similarity(
                left, right, weights=EQUAL_FEATURE_WEIGHTS
            )
            for left, right in pairs
        ) if pairs else None,
        "distinct_artist_fraction": round(
            len({tracks[track_id].artist for track_id in recommended_ids})
            / len(recommended_ids),
            6,
        ),
        "processing_ms": processing_ms,
    }


def summarize_runs(runs: list[dict], *, pool_count: int) -> dict:
    groups = defaultdict(list)
    for run in runs:
        groups[(run["algorithm"], run["category"])].append(run)
    rows = []
    for (algorithm, category), group in sorted(groups.items()):
        recommended_ids = {
            item["track"]["id"]
            for run in group
            for item in run["recommendations"]
        }
        row = {
            "algorithm": algorithm,
            "category": category,
            "run_count": len(group),
            "scenario_count": len({run["scenario_id"] for run in group}),
            "catalogue_coverage": round(len(recommended_ids) / pool_count, 6),
        }
        for field in METRIC_FIELDS:
            values = [
                run["metrics"][field]
                for run in group
                if run["metrics"][field] is not None
            ]
            row[f"mean_{field}"] = _rounded_mean(values) if values else None
            row[f"sd_{field}"] = round(pstdev(values), 6) if values else None
        rows.append(row)
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "run_count": len(runs),
        "candidate_pool_count": pool_count,
        "metrics_are_diagnostic_proxies_not_user_relevance": True,
        "metric_definitions": {
            "history_match": "Mean equal-weight normalized Euclidean similarity to a recency-weighted history profile.",
            "mood_match": "Mean fit to the fixed Panda-weighted project mood profile.",
            "intra_list_diversity": "Mean pairwise equal-weight normalized Euclidean distance within Top-N.",
            "distinct_artist_fraction": "Distinct artists divided by returned count.",
            "catalogue_coverage": "Unique recommended pool tracks divided by 500, within a group.",
            "processing_ms": "Service-reported wall time; machine-dependent, not deterministic.",
        },
        "groups": rows,
    }


def save_result_set(
    *,
    output_dir: Path,
    config: dict,
    algorithm_config: AlgorithmConfig,
    runs: list[dict],
    summary: dict,
    result_set_name: str,
):
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ProtocolValidationError(f"Refusing to overwrite results: {output_dir}.")
    output_dir.mkdir(parents=True, exist_ok=True)
    runs_path = output_dir / "recommendation-runs.json"
    summary_path = output_dir / "summary.json"
    csv_path = output_dir / "summary.csv"
    manifest_path = output_dir / "manifest.json"
    write_json(
        runs_path,
        {
            "schema_version": RESULT_SCHEMA_VERSION,
            "result_set_name": result_set_name,
            "algorithm_config": algorithm_config.to_dict(),
            "runs": runs,
        },
    )
    write_json(summary_path, summary)
    rows = summary["groups"]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    write_json(
        manifest_path,
        {
            "schema_version": RESULT_SCHEMA_VERSION,
            "result_set_name": result_set_name,
            "experiment_id": config["experiment_id"],
            "catalogue_sha256": config["catalogue"]["sha256"],
            "candidate_pool_sha256": config["candidate_pool"]["sha256"],
            "scenarios_sha256": config["scenarios"]["sha256"],
            "algorithm_config": algorithm_config.to_dict(),
            "random_seeds": (
                config["randomness"]["random_baseline_seeds"]
                if any(run["algorithm"] == "random" for run in runs)
                else []
            ),
            "run_count": len(runs),
            "outputs": {
                path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
                for path in (runs_path, summary_path, csv_path)
            },
        },
    )
    return str(manifest_path)


def _rounded_mean(values) -> float:
    return round(mean(values), 6)
