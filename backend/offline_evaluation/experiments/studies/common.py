"""Shared recommendation execution used by configuration and comparison studies."""

from __future__ import annotations

import random

from recommendations.domain.algorithm_config import (
    AlgorithmConfig,
    DEFAULT_ALGORITHM_CONFIG,
)
from recommendations.services.recommendation_service import RecommendationService

from ..metrics import compact_recommendations, recommendation_metrics
from ..protocol import ExperimentContext, ProtocolError


def execute_recommendation(
    context: ExperimentContext,
    scenario: dict,
    *,
    method: str,
    config_id: str,
    algorithm_config: AlgorithmConfig = DEFAULT_ALGORITHM_CONFIG,
    seed: int | None = None,
    mood: str | None | object = ...,
    diversity_strength: float | None = None,
) -> dict:
    """Run one method and return the common compact run record."""

    resolved_mood = scenario["mood"] if mood is ... else mood
    if method == "cbf" and not scenario["history"]:
        raise ProtocolError("CBF requires at least one history track.")
    if method not in {"random", "cbf", "context_no_mmr", "context_mmr"}:
        raise ProtocolError(f"Unsupported experiment method: {method}.")

    request_context = {}
    if resolved_mood is not None:
        request_context["mood"] = resolved_mood
    if method.startswith("context_"):
        request_context["diversity_strength"] = (
            0.0
            if method == "context_no_mmr"
            else (
                diversity_strength
                if diversity_strength is not None
                else algorithm_config.default_diversity_strength
            )
        )
    service_method = "context_mmr" if method.startswith("context_") else method
    response = RecommendationService(
        random_source=random.Random(seed) if seed is not None else None,
        algorithm_config=algorithm_config,
    ).recommend(
        {
            "algorithm": service_method,
            "history": scenario["history"],
            "context": request_context,
            "limit": scenario["top_n"],
            "candidate_ids": context.candidate_ids,
        }
    )
    recommendations = response["recommendations"]
    selected_ids = [item["track"]["id"] for item in recommendations]
    if response["meta"]["candidate_count"] != len(context.candidate_ids):
        raise ProtocolError(f"Candidate count changed in {scenario['scenario_id']}.")
    if len(selected_ids) != scenario["top_n"]:
        raise ProtocolError(f"Top-N is incomplete in {scenario['scenario_id']}.")
    if len(selected_ids) != len(set(selected_ids)):
        raise ProtocolError(f"Duplicate recommendation in {scenario['scenario_id']}.")
    if not set(selected_ids).issubset(context.candidate_ids):
        raise ProtocolError(f"Recommendation escaped the fixed candidate pool.")

    metrics = recommendation_metrics(
        recommendations=recommendations,
        history_ids=scenario["history"],
        mood=resolved_mood,
        tracks=context.selected_tracks,
        processing_ms=response["meta"]["processing_ms"],
    )
    return {
        "scenario_id": scenario["scenario_id"],
        "category": scenario["category"],
        "method": method,
        "config_id": config_id,
        "seed": seed,
        "history": scenario["history"],
        "mood": resolved_mood,
        "recommended_ids": selected_ids,
        "recommendations": compact_recommendations(recommendations),
        "metrics": metrics,
    }
