from dataclasses import dataclass

from .feature_vectors import feature_closeness, weighted_cosine_similarity


@dataclass(frozen=True)
class CbfRanking:
    candidate: object
    score: float
    feature_closeness: dict


def rank_cbf(candidate_vectors, session_profile, limit):
    """Rank ``(candidate, vector)`` pairs by weighted cosine similarity."""

    if limit < 1:
        raise ValueError("limit must be at least 1")

    scored_candidates = []
    for candidate, vector in candidate_vectors:
        scored_candidates.append(
            CbfRanking(
                candidate=candidate,
                score=weighted_cosine_similarity(session_profile, vector),
                feature_closeness=feature_closeness(vector, session_profile),
            )
        )

    scored_candidates.sort(
        key=lambda result: (-result.score, str(getattr(result.candidate, "id", "")))
    )
    return scored_candidates[:limit]
