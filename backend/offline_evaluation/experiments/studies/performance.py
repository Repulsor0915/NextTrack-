"""Measure service latency on the fixed pool and the complete catalogue."""

from __future__ import annotations

import random
from statistics import median
from time import perf_counter

from recommendations.services.recommendation_service import RecommendationService

from ..artifacts import StudyResult
from ..metrics import percentile
from ..protocol import ExperimentContext, ProtocolError


METHODS = ("random", "cbf", "context_no_mmr", "context_mmr")


def _request(context, scenario, method, scope):
    request_context = {"mood": scenario["mood"]}
    if method.startswith("context_"):
        request_context["diversity_strength"] = (
            0.0 if method == "context_no_mmr" else 0.2
        )
    return {
        "algorithm": "context_mmr" if method.startswith("context_") else method,
        "history": scenario["history"],
        "context": request_context,
        "limit": scenario["top_n"],
        "candidate_ids": context.candidate_ids if scope == "fixed_pool" else None,
    }


def _measure(service, request):
    started = perf_counter()
    response = service.recommend(request)
    return {
        "wall_ms": (perf_counter() - started) * 1000.0,
        "service_ms": response["meta"]["processing_ms"],
        "candidate_count": response["meta"]["candidate_count"],
        "returned_count": len(response["recommendations"]),
    }


def run(context: ExperimentContext) -> StudyResult:
    scenario = next(
        item
        for item in context.scenarios
        if item["scenario_id"] == "transition_calm_to_energetic"
    )
    samples = []
    for scope in ("fixed_pool", "full_catalogue"):
        for method in METHODS:
            request = _request(context, scenario, method, scope)
            for repetition in range(context.config.performance_fresh_repetitions):
                service = RecommendationService(
                    random_source=random.Random(context.config.seed)
                )
                sample = _measure(service, request)
                samples.append(
                    {
                        "scope": scope,
                        "method": method,
                        "phase": "fresh_service",
                        "sample_index": repetition,
                        **sample,
                    }
                )
            service = RecommendationService(
                random_source=random.Random(context.config.seed)
            )
            _measure(service, request)
            for repetition in range(context.config.performance_warm_repetitions):
                sample = _measure(service, request)
                samples.append(
                    {
                        "scope": scope,
                        "method": method,
                        "phase": "same_process_warm",
                        "sample_index": repetition,
                        **sample,
                    }
                )

    rows = []
    for scope in ("fixed_pool", "full_catalogue"):
        for method in METHODS:
            for phase in ("fresh_service", "same_process_warm"):
                group = [
                    item
                    for item in samples
                    if item["scope"] == scope
                    and item["method"] == method
                    and item["phase"] == phase
                ]
                if len({item["candidate_count"] for item in group}) != 1:
                    raise ProtocolError("Candidate count changed during latency sampling.")
                values = [item["wall_ms"] for item in group]
                rows.append(
                    {
                        "scope": scope,
                        "method": method,
                        "phase": phase,
                        "sample_count": len(group),
                        "candidate_count": group[0]["candidate_count"],
                        "p50_ms": median(values),
                        "p95_ms": percentile(values, 0.95),
                        "minimum_ms": min(values),
                        "maximum_ms": max(values),
                    }
                )
    return StudyResult(
        summary={
            "scenario_id": scenario["scenario_id"],
            "timed_region": "RecommendationService.recommend in the current process",
            "fresh_service_is_not_cold_process": True,
            "rows": rows,
        },
        runs=samples,
        tables={"summary": rows},
    )
