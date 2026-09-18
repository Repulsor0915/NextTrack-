from dataclasses import dataclass

from .algorithm_config import DEFAULT_ALGORITHM_CONFIG
from .feature_vectors import calculate_similarity, feature_closeness


@dataclass(frozen=True)
class CbfRanking:
    candidate: object
    score: float
    feature_closeness: dict


def rank_cbf(
    candidate_vectors,
    session_profile,
    limit,
    *,
    algorithm_config=DEFAULT_ALGORITHM_CONFIG,
):
    """Rank candidates using the configured eight-feature similarity."""

    if limit < 1:
        raise ValueError("limit must be at least 1")

    scored_candidates = []
    for candidate, vector in candidate_vectors:
        scored_candidates.append(
            CbfRanking(
                candidate=candidate,
                score=calculate_similarity(
                    session_profile,
                    vector,
                    metric=algorithm_config.relevance_similarity_metric,
                    weights=algorithm_config.feature_weights,
                ),
                feature_closeness=feature_closeness(vector, session_profile),
            )
        )

    scored_candidates.sort(
        key=lambda result: (-result.score, str(getattr(result.candidate, "id", "")))
    )
    return scored_candidates[:limit]
