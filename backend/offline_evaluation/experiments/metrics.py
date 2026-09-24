"""One fixed set of diagnostic metrics shared by all experiment studies."""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from statistics import mean, pstdev

from recommendations.domain.algorithm_config import EQUAL_FEATURE_WEIGHTS
from recommendations.domain.feature_vectors import (
    build_recency_weighted_profile,
    weighted_euclidean_similarity,
)
from recommendations.domain.mood_model import calculate_mood_fit


METRIC_NAMES = (
    "history_match",
    "mood_match",
    "intra_list_diversity",
    "artist_diversity",
    "artist_metadata_coverage",
    "mean_relevance",
    "processing_ms",
)


def percentile(values: list[float], fraction: float) -> float:
    if not values or not 0.0 <= fraction <= 1.0:
        raise ValueError("percentile requires values and a fraction from zero to one.")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def recommendation_metrics(
    *, recommendations: list[dict], history_ids: list[str], mood: str | None,
    tracks: dict, processing_ms: float,
) -> dict:
    """Measure fixed proxies; these values are not human relevance labels."""

    selected_ids = [item["track"]["id"] for item in recommendations]
    selected_vectors = [tracks[track_id].vector for track_id in selected_ids]
    history_profile = (
        build_recency_weighted_profile(
            [tracks[track_id].vector for track_id in history_ids], window_size=5
        )
        if history_ids
        else None
    )
    vector_pairs = list(combinations(selected_vectors, 2))
    relevance_values = [
        item["score"] for item in recommendations if item["score"] is not None
    ]
    known_artist_keys = [
        tracks[track_id].artist_key
        for track_id in selected_ids
        if tracks[track_id].artist_key is not None
    ]
    return {
        "history_match": (
            mean(
                weighted_euclidean_similarity(
                    history_profile, vector, weights=EQUAL_FEATURE_WEIGHTS
                )
                for vector in selected_vectors
            )
            if history_profile is not None
            else None
        ),
        "mood_match": (
            mean(calculate_mood_fit(vector, mood) for vector in selected_vectors)
            if mood is not None
            else None
        ),
        "intra_list_diversity": (
            mean(
                1.0
                - weighted_euclidean_similarity(
                    left, right, weights=EQUAL_FEATURE_WEIGHTS
                )
                for left, right in vector_pairs
            )
            if vector_pairs
            else None
        ),
        "artist_diversity": (
            len(set(known_artist_keys)) / len(known_artist_keys)
            if known_artist_keys
            else None
        ),
        "artist_metadata_coverage": len(known_artist_keys) / len(selected_ids),
        "mean_relevance": mean(relevance_values) if relevance_values else None,
        "processing_ms": float(processing_ms),
    }


def summarize_runs(runs: list[dict], *, group_fields: tuple[str, ...], pool_count: int) -> list[dict]:
    groups = defaultdict(list)
    for run in runs:
        groups[tuple(run[field] for field in group_fields)].append(run)
    rows = []
    for group_key, members in sorted(groups.items()):
        row = dict(zip(group_fields, group_key, strict=True))
        row.update(
            {
                "run_count": len(members),
                "scenario_count": len({item["scenario_id"] for item in members}),
                "pool_coverage": len(
                    {
                        track_id
                        for item in members
                        for track_id in item["recommended_ids"]
                    }
                )
                / pool_count,
            }
        )
        for metric_name in METRIC_NAMES:
            values = [
                item["metrics"][metric_name]
                for item in members
                if item["metrics"][metric_name] is not None
            ]
            row[f"mean_{metric_name}"] = mean(values) if values else None
            row[f"sd_{metric_name}"] = pstdev(values) if values else None
        rows.append(row)
    return rows


def compact_recommendations(recommendations: list[dict]) -> list[dict]:
    return [
        {
            "rank": item["rank"],
            "track_id": item["track"]["id"],
            "title": item["track"]["title"],
            "artist": item["track"]["artist"],
            "score": item["score"],
        }
        for item in recommendations
    ]
