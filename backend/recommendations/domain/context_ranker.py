## This file score each candidate using the user's listening history
## requested mood, or a weighted combination of both
## The scoring evidence is kept for the explanation and MMR stages.


from dataclasses import dataclass, field

from .algorithm_config import DEFAULT_ALGORITHM_CONFIG
from .feature_vectors import calculate_similarity, feature_closeness
from .mood_model import score_mood


# Deafult contribution of listening history and mood to the relevance score.
HISTORY_RELEVANCE_WEIGHT = DEFAULT_ALGORITHM_CONFIG.history_relevance_weight
MOOD_RELEVANCE_WEIGHT = DEFAULT_ALGORITHM_CONFIG.mood_relevance_weight

# Store the score and supporting evidence for one candidate track.
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

# At least one source of user context matches the recent listening profile.
def score_context_candidates(
    candidate_vectors,
    *,
    session_profile=None,
    mood=None,
    bpm_constraint_applied=False,
    algorithm_config=DEFAULT_ALGORITHM_CONFIG,
):

    if session_profile is None and mood is None:
        raise ValueError("session_profile or mood is required")

    rankings = []
    for candidate, vector in candidate_vectors:
        history_similarity = (
            calculate_similarity(
                session_profile,
                vector,
                metric=algorithm_config.relevance_similarity_metric,
                weights=algorithm_config.feature_weights,
            )
            if session_profile is not None
            else None
        )
        mood_score = (
            score_mood(
                vector,
                mood,
                feature_weights=algorithm_config.mood_feature_weights,
            )
            if mood is not None
            else None
        )
        mood_fit = mood_score.fit if mood_score is not None else None

        if history_similarity is not None and mood_fit is not None:
            relevance = (
                algorithm_config.history_relevance_weight * history_similarity
                + algorithm_config.mood_relevance_weight * mood_fit
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

# Return a stable string ID for sorting different candidate object types. 
def _candidate_id(candidate):
    return str(getattr(candidate, "id", candidate))
