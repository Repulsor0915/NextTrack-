from dataclasses import dataclass

from .feature_vectors import feature_closeness, weighted_cosine_similarity


# Heuristic targets in normalized feature space. They are configurable project
# parameters, not claims of clinically or psychologically validated boundaries.
MOOD_TARGETS = {
    "happy": {
        "valence": 0.85,
        "energy": 0.70,
        "danceability": 0.65,
    },
    "energetic": {
        "energy": 0.90,
        "tempo": 0.75,
        "danceability": 0.75,
    },
    "calm": {
        "energy": 0.20,
        "tempo": 0.25,
        "acousticness": 0.70,
        "speechiness": 0.10,
    },
    "sad": {
        "valence": 0.15,
        "energy": 0.25,
        "tempo": 0.30,
        "acousticness": 0.60,
    },
}

HISTORY_RELEVANCE_WEIGHT = 0.65
MOOD_RELEVANCE_WEIGHT = 0.35


@dataclass(frozen=True)
class ContextRanking:
    candidate: object
    vector: dict
    relevance: float
    history_similarity: float | None
    mood_fit: float | None
    tempo_fit: float | None
    feature_closeness: dict


def calculate_mood_fit(vector, mood):
    """Return mean proximity to a mood's heuristic normalized targets."""

    if mood is None:
        return None
    if mood not in MOOD_TARGETS:
        raise ValueError(f'Unsupported mood "{mood}"')

    targets = MOOD_TARGETS[mood]
    return sum(
        1.0 - abs(vector[feature_name] - target)
        for feature_name, target in targets.items()
    ) / len(targets)


def score_context_candidates(
    candidate_vectors,
    *,
    session_profile=None,
    mood=None,
    tempo_constrained=False,
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
        mood_fit = calculate_mood_fit(vector, mood)

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
                tempo_fit=1.0 if tempo_constrained else None,
                feature_closeness=(
                    feature_closeness(vector, session_profile)
                    if session_profile is not None
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
