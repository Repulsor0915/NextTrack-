"""Compact CBF, history, mood-weight, and MMR configuration study."""

from __future__ import annotations

from dataclasses import replace

from recommendations.domain.algorithm_config import (
    DEFAULT_ALGORITHM_CONFIG,
    EQUAL_FEATURE_WEIGHTS,
)

from ..artifacts import StudyResult
from ..metrics import summarize_runs
from ..protocol import ExperimentContext
from .common import execute_recommendation


def _history_scenarios(context: ExperimentContext) -> list[dict]:
    return [scenario for scenario in context.scenarios if scenario["history"]]


def run(context: ExperimentContext) -> StudyResult:
    baseline = DEFAULT_ALGORITHM_CONFIG
    runs = []
    configurations = {}

    cbf_configs = {
        "current_cosine": baseline,
        "equal_cosine": replace(
            baseline, name="evaluation-equal-cosine", feature_weights=EQUAL_FEATURE_WEIGHTS
        ),
        "current_euclidean": replace(
            baseline,
            name="evaluation-current-euclidean",
            relevance_similarity_metric="weighted_euclidean",
        ),
        "equal_euclidean": replace(
            baseline,
            name="evaluation-equal-euclidean",
            feature_weights=EQUAL_FEATURE_WEIGHTS,
            relevance_similarity_metric="weighted_euclidean",
        ),
    }
    for config_id, algorithm_config in cbf_configs.items():
        configurations[f"cbf/{config_id}"] = algorithm_config.to_dict()
        for scenario in _history_scenarios(context):
            item = execute_recommendation(
                context,
                scenario,
                method="cbf",
                config_id=config_id,
                algorithm_config=algorithm_config,
            )
            item["study"] = "cbf"
            runs.append(item)

    history_configs = {
        f"window_{window}_recency": replace(
            baseline,
            name=f"evaluation-window-{window}-recency",
            history_window_size=window,
            context_history_strategy="linear_recency",
        )
        for window in context.config.history_windows
    }
    longest_window = max(context.config.history_windows)
    if longest_window > 1:
        history_configs[f"window_{longest_window}_equal"] = replace(
            baseline,
            name=f"evaluation-window-{longest_window}-equal",
            history_window_size=longest_window,
            context_history_strategy="equal",
        )
    for config_id, algorithm_config in history_configs.items():
        configurations[f"history/{config_id}"] = algorithm_config.to_dict()
        for scenario in _history_scenarios(context):
            item = execute_recommendation(
                context,
                scenario,
                method="context_no_mmr",
                config_id=config_id,
                algorithm_config=algorithm_config,
                mood=None,
            )
            item["study"] = "history"
            runs.append(item)

    for history_weight, mood_weight in context.config.history_mood_ratios:
        config_id = f"history_{history_weight:g}_mood_{mood_weight:g}"
        algorithm_config = replace(
            baseline,
            name=f"evaluation-{config_id}",
            history_relevance_weight=history_weight,
            mood_relevance_weight=mood_weight,
        )
        configurations[f"history_mood/{config_id}"] = algorithm_config.to_dict()
        for scenario in _history_scenarios(context):
            item = execute_recommendation(
                context,
                scenario,
                method="context_no_mmr",
                config_id=config_id,
                algorithm_config=algorithm_config,
            )
            item["study"] = "history_mood"
            runs.append(item)

    for strength in context.config.mmr_strengths:
        config_id = f"mmr_{strength:g}"
        algorithm_config = replace(
            baseline,
            name=f"evaluation-{config_id}",
            default_diversity_strength=strength,
        )
        configurations[f"mmr/{config_id}"] = algorithm_config.to_dict()
        for scenario in context.scenarios:
            item = execute_recommendation(
                context,
                scenario,
                method="context_mmr",
                config_id=config_id,
                algorithm_config=algorithm_config,
                diversity_strength=strength,
            )
            item["study"] = "mmr"
            runs.append(item)

    category_rows = summarize_runs(
        runs,
        group_fields=("study", "config_id", "category"),
        pool_count=len(context.candidate_ids),
    )
    all_rows = summarize_runs(
        runs,
        group_fields=("study", "config_id"),
        pool_count=len(context.candidate_ids),
    )
    for row in all_rows:
        row["category"] = "all"
    summary_rows = sorted(
        category_rows + all_rows,
        key=lambda row: (row["study"], row["config_id"], row["category"]),
    )
    return StudyResult(
        summary={"run_count": len(runs), "rows": summary_rows},
        runs=runs,
        tables={"summary": summary_rows},
        details={"configurations": configurations},
    )
