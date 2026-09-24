"""Map verified study summaries to the five report figures."""

from __future__ import annotations

from pathlib import Path

from .loader import load_summary, load_table
from .svg import COLORS, grouped_bar_chart


def build_figures(run_dir: Path) -> dict[str, str]:
    catalogue = load_summary(run_dir, "catalogue")
    distributions = load_table(run_dir, "catalogue", "feature-distributions")
    configuration = load_summary(run_dir, "configuration")["rows"]
    comparison = load_summary(run_dir, "comparison")["rows"]
    performance = load_summary(run_dir, "performance")["rows"]

    usable = catalogue["usable_feature_count"]
    clamp_rows = [
        {
            "label": row["feature"],
            "clamped_percent": 100.0
            * (row["below_normalization_range"] + row["above_normalization_range"])
            / usable,
        }
        for row in distributions
    ]
    cbf_rows = [
        {
            "label": row["config_id"],
            "history_match": row["mean_history_match"],
            "coverage": row["pool_coverage"],
        }
        for row in configuration
        if row["study"] == "cbf" and row["category"] == "all"
    ]
    context_rows = [
        {
            "label": f"{row['study']}: {row['config_id']}",
            "history_match": row["mean_history_match"],
            "mood_match": row["mean_mood_match"],
            "diversity": row["mean_intra_list_diversity"],
        }
        for row in configuration
        if row["study"] != "cbf" and row["category"] == "all"
    ]
    method_rows = [
        {
            "label": row["method"],
            "history_match": row["mean_history_match"],
            "mood_match": row["mean_mood_match"],
            "diversity": row["mean_intra_list_diversity"],
            "artist_diversity": row["mean_artist_diversity"],
            "artist_metadata": row["mean_artist_metadata_coverage"],
        }
        for row in comparison
        if row["category"] == "all"
    ]
    latency_rows = [
        {
            "label": f"{row['scope']} / {row['method']} / {row['phase']}",
            "p50_ms": row["p50_ms"],
            "p95_ms": row["p95_ms"],
        }
        for row in performance
    ]
    return {
        "01-catalogue-clamping.svg": grouped_bar_chart(
            title="Catalogue values outside runtime normalisation ranges",
            subtitle="Percentage of usable tracks clamped when feature vectors are built.",
            rows=clamp_rows,
            series=[("clamped_percent", COLORS["primary"])],
            value_suffix="%",
        ),
        "02-cbf-configuration.svg": grouped_bar_chart(
            title="CBF configuration comparison",
            subtitle="Fixed-pool diagnostic proxies; higher values indicate closer history fit or broader coverage.",
            rows=cbf_rows,
            series=[
                ("history_match", COLORS["primary"]),
                ("coverage", COLORS["secondary"]),
            ],
            maximum=1.0,
        ),
        "03-context-configuration.svg": grouped_bar_chart(
            title="Context parameter trade-offs",
            subtitle="History profile, history/mood ratio, and MMR settings on the same scenarios and pool.",
            rows=context_rows,
            series=[
                ("history_match", COLORS["primary"]),
                ("mood_match", COLORS["secondary"]),
                ("diversity", COLORS["tertiary"]),
            ],
            maximum=1.0,
        ),
        "04-method-comparison.svg": grouped_bar_chart(
            title="Final recommendation method comparison",
            subtitle="Random, Basic CBF, Context, and Context with MMR using diagnostic proxy metrics.",
            rows=method_rows,
            series=[
                ("history_match", COLORS["primary"]),
                ("mood_match", COLORS["secondary"]),
                ("diversity", COLORS["tertiary"]),
                ("artist_diversity", COLORS["quaternary"]),
                ("artist_metadata", "#6b7280"),
            ],
            maximum=1.0,
        ),
        "05-latency.svg": grouped_bar_chart(
            title="Recommendation service latency",
            subtitle="P50 and P95 wall time for fixed-pool and full-catalogue requests.",
            rows=latency_rows,
            series=[("p50_ms", COLORS["primary"]), ("p95_ms", COLORS["secondary"])],
            value_suffix=" ms",
        ),
    }
