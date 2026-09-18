"""Versioned, validated configuration for recommendation algorithms.

The public REST API intentionally does not accept this complete object. It is
injected by trusted backend code (for example, the future offline evaluator)
so experiments are reproducible without editing algorithm source files. The
documented request-level diversity control remains a separate API input.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from recommendations.audio_features import FEATURE_NAMES


ALGORITHM_CONFIG_SCHEMA_VERSION = "nexttrack-algorithm-config-v1"
SUPPORTED_SIMILARITY_METRICS = frozenset(
    {"weighted_cosine", "weighted_euclidean"}
)
SUPPORTED_CONTEXT_HISTORY_STRATEGIES = frozenset(
    {"equal", "linear_recency"}
)


CURRENT_FEATURE_WEIGHTS = {
    "tempo": 0.10,
    "energy": 0.25,
    "valence": 0.25,
    "danceability": 0.15,
    "acousticness": 0.10,
    "instrumentalness": 0.05,
    "loudness": 0.05,
    "speechiness": 0.05,
}

EQUAL_FEATURE_WEIGHTS = {
    feature_name: 1.0 / len(FEATURE_NAMES)
    for feature_name in FEATURE_NAMES
}

# Literature-informed experimental preset retained for controlled comparison.
# These are the eight NextTrack-overlapping values reported by a 2025 HDSR
# genre-classification study; that study also used other features. The values
# below are therefore re-normalised only for an experiment, and are not treated
# as a universal optimum for music recommendation.
# Source: https://hdsr.mitpress.mit.edu/pub/t4txmd81/release/2
_LITERATURE_INFORMED_RAW_FEATURE_WEIGHTS = {
    "tempo": 0.12,
    "energy": 0.092,
    "valence": 0.07,
    "danceability": 0.01,
    "acousticness": 0.06,
    "instrumentalness": 0.03,
    "loudness": 0.17,
    "speechiness": 0.35,
}
_literature_weight_total = sum(
    _LITERATURE_INFORMED_RAW_FEATURE_WEIGHTS.values()
)
LITERATURE_INFORMED_FEATURE_WEIGHTS = {
    feature_name: weight / _literature_weight_total
    for feature_name, weight in _LITERATURE_INFORMED_RAW_FEATURE_WEIGHTS.items()
}


def _validated_frozen_weights(
    weights: Mapping[str, float],
    *,
    field_name: str,
) -> Mapping[str, float]:
    expected_names = set(FEATURE_NAMES)
    actual_names = set(weights)
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        raise ValueError(
            f"{field_name} must contain exactly the eight audio features; "
            f"missing={missing}, extra={extra}."
        )

    validated: dict[str, float] = {}
    for feature_name in FEATURE_NAMES:
        value = float(weights[feature_name])
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(
                f"{field_name}.{feature_name} must be a finite, non-negative number."
            )
        validated[feature_name] = value

    total = sum(validated.values())
    if not math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError(f"{field_name} must sum to 1.0; received {total!r}.")
    return MappingProxyType(validated)


@dataclass(frozen=True)
class AlgorithmConfig:
    """Immutable settings shared by Random, CBF, Context and MMR code.

    ``mood_feature_weights=None`` means that the features present in each mood
    profile contribute equally. A supplied mood weight vector is renormalised
    over the features used by the requested mood.
    """

    name: str = "baseline-current-v1"
    feature_weights: Mapping[str, float] = field(
        default_factory=lambda: dict(CURRENT_FEATURE_WEIGHTS)
    )
    relevance_similarity_metric: str = "weighted_cosine"
    diversity_similarity_metric: str = "weighted_cosine"
    history_window_size: int = 5
    context_history_strategy: str = "linear_recency"
    history_relevance_weight: float = 0.65
    mood_relevance_weight: float = 0.35
    mood_feature_weights: Mapping[str, float] | None = None
    default_diversity_strength: float = 0.20

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("AlgorithmConfig.name must not be blank.")
        if self.relevance_similarity_metric not in SUPPORTED_SIMILARITY_METRICS:
            raise ValueError(
                "Unsupported relevance_similarity_metric: "
                f"{self.relevance_similarity_metric!r}."
            )
        if self.diversity_similarity_metric not in SUPPORTED_SIMILARITY_METRICS:
            raise ValueError(
                "Unsupported diversity_similarity_metric: "
                f"{self.diversity_similarity_metric!r}."
            )
        if self.context_history_strategy not in SUPPORTED_CONTEXT_HISTORY_STRATEGIES:
            raise ValueError(
                "Unsupported context_history_strategy: "
                f"{self.context_history_strategy!r}."
            )
        if self.history_window_size < 1:
            raise ValueError("history_window_size must be at least 1.")

        history_weight = float(self.history_relevance_weight)
        mood_weight = float(self.mood_relevance_weight)
        if history_weight < 0.0 or mood_weight < 0.0:
            raise ValueError("History and mood relevance weights must be non-negative.")
        if not math.isclose(
            history_weight + mood_weight,
            1.0,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise ValueError("History and mood relevance weights must sum to 1.0.")

        diversity_strength = float(self.default_diversity_strength)
        if not 0.0 <= diversity_strength <= 1.0:
            raise ValueError("default_diversity_strength must be between 0 and 1.")

        object.__setattr__(
            self,
            "feature_weights",
            _validated_frozen_weights(
                self.feature_weights,
                field_name="feature_weights",
            ),
        )
        if self.mood_feature_weights is not None:
            object.__setattr__(
                self,
                "mood_feature_weights",
                _validated_frozen_weights(
                    self.mood_feature_weights,
                    field_name="mood_feature_weights",
                ),
            )

    def to_dict(self) -> dict:
        """Return a JSON-serialisable snapshot for experiment manifests."""

        return {
            "schema_version": ALGORITHM_CONFIG_SCHEMA_VERSION,
            "name": self.name,
            "feature_weights": dict(self.feature_weights),
            "relevance_similarity_metric": self.relevance_similarity_metric,
            "diversity_similarity_metric": self.diversity_similarity_metric,
            "history_window_size": self.history_window_size,
            "context_history_strategy": self.context_history_strategy,
            "history_relevance_weight": self.history_relevance_weight,
            "mood_relevance_weight": self.mood_relevance_weight,
            "mood_feature_weights": (
                dict(self.mood_feature_weights)
                if self.mood_feature_weights is not None
                else None
            ),
            "default_diversity_strength": self.default_diversity_strength,
        }


DEFAULT_ALGORITHM_CONFIG = AlgorithmConfig()
