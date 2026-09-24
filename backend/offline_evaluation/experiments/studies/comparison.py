"""Final paired comparison of the four product recommendation paths."""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations, product
from statistics import mean

from ..artifacts import StudyResult
from ..metrics import summarize_runs
from ..protocol import ExperimentContext
from .common import execute_recommendation


METHODS = ("random", "cbf", "context_no_mmr", "context_mmr")


def _pairwise(runs: list[dict]) -> list[dict]:
    grouped = defaultdict(lambda: defaultdict(list))
    for item in runs:
        grouped[item["scenario_id"]][item["method"]].append(item)
    rows = []
    for scenario_id, methods in sorted(grouped.items()):
        for left_method, right_method in combinations(METHODS, 2):
            if left_method not in methods or right_method not in methods:
                continue
            comparisons = []
            for left, right in product(methods[left_method], methods[right_method]):
                left_ids = set(left["recommended_ids"])
                right_ids = set(right["recommended_ids"])
                union = left_ids | right_ids
                comparisons.append(
                    {
                        "overlap": len(left_ids & right_ids),
                        "jaccard": len(left_ids & right_ids) / len(union),
                        "top1_same": left["recommended_ids"][0]
                        == right["recommended_ids"][0],
                    }
                )
            rows.append(
                {
                    "scenario_id": scenario_id,
                    "left_method": left_method,
                    "right_method": right_method,
                    "comparison_count": len(comparisons),
                    "mean_overlap": mean(item["overlap"] for item in comparisons),
                    "mean_jaccard": mean(item["jaccard"] for item in comparisons),
                    "top1_same_fraction": mean(
                        item["top1_same"] for item in comparisons
                    ),
                }
            )
    return rows


def run(context: ExperimentContext) -> StudyResult:
    runs = []
    for scenario in context.scenarios:
        for repetition in range(context.config.random_repetitions):
            runs.append(
                execute_recommendation(
                    context,
                    scenario,
                    method="random",
                    config_id="production_default",
                    seed=context.config.seed + repetition,
                )
            )
        if scenario["history"]:
            runs.append(
                execute_recommendation(
                    context,
                    scenario,
                    method="cbf",
                    config_id="production_default",
                )
            )
        runs.append(
            execute_recommendation(
                context,
                scenario,
                method="context_no_mmr",
                config_id="production_default",
                diversity_strength=0.0,
            )
        )
        runs.append(
            execute_recommendation(
                context,
                scenario,
                method="context_mmr",
                config_id="production_default",
            )
        )

    category_rows = summarize_runs(
        runs,
        group_fields=("method", "category"),
        pool_count=len(context.candidate_ids),
    )
    all_rows = summarize_runs(
        runs, group_fields=("method",), pool_count=len(context.candidate_ids)
    )
    for row in all_rows:
        row["category"] = "all"
    summary_rows = sorted(
        category_rows + all_rows, key=lambda row: (row["method"], row["category"])
    )
    pairwise_rows = _pairwise(runs)
    return StudyResult(
        summary={"run_count": len(runs), "rows": summary_rows},
        runs=runs,
        tables={"summary": summary_rows, "pairwise": pairwise_rows},
    )
