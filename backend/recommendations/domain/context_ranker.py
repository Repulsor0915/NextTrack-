from dataclasses import dataclass, field

from .feature_vectors import feature_closeness, weighted_cosine_similarity
from .mood_model import score_mood

HISTORY_RELEVANCE_WEIGHT = 0.65
MOOD_RELEVANCE_WEIGHT = 0.35


@dataclass(frozen=True)
class ContextRanking:
    candidate: object
    vector: dict
    relevance: float
    history_similarity: float | None
    mood_fit: float | None
    bpm_constraint_satisfied: bool | None
    feature_closeness: dict
    mood_feature_closeness: dict = field(default_factory=dict)


def score_context_candidates(
    candidate_vectors,
    *,
    session_profile=None,
    mood=None,
    bpm_constraint_applied=False,
):
    """Score candidates using available session and explicit mood evidence."""

    if session_profile is None and mood is None:
        raise ValueError("session_profile or mood is required")

    rankings = []
    for candidate, vector in candidate_vectors:
        history_similarity = (
            weighted_cosine_similarity(session_profile, vector)
            if session_profile is not None
            else None
        )
        mood_score = score_mood(vector, mood) if mood is not None else None
        mood_fit = mood_score.fit if mood_score is not None else None

        if history_similarity is not None and mood_fit is not None:
            relevance = (
                HISTORY_RELEVANCE_WEIGHT * history_similarity
                + MOOD_RELEVANCE_WEIGHT * mood_fit
            )
        elif history_similarity is not None:
            relevance = history_similarity
        else:
            relevance = mood_fit

        rankings.append(
            ContextRanking(
                candidate=candidate,
                vector=vector,
                relevance=relevance,
                history_similarity=history_similarity,
                mood_fit=mood_fit,
                bpm_constraint_satisfied=True if bpm_constraint_applied else None,
                feature_closeness=(
                    feature_closeness(vector, session_profile)
                    if session_profile is not None
                    else {}
                ),
                mood_feature_closeness=(
                    mood_score.feature_closeness
                    if mood_score is not None
                    else {}
                ),
            )
        )

    rankings.sort(
        key=lambda result: (-result.relevance, _candidate_id(result.candidate))
    )
    return rankings


def _candidate_id(candidate):
    return str(getattr(candidate, "id", candidate))
