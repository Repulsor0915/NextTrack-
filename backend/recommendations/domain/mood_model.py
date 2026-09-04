from dataclasses import dataclass


MOOD_MODEL_VERSION = "va-informed-8-feature-heuristic-v1"

# These profiles operate in the same normalized eight-feature space as the
# recommender. Valence/arousal theory informs their interpretation, but the
# values are project-defined engineering defaults: they are not DEAM labels,
# clinical boundaries, or a learned arousal model.
MOOD_PROFILES = {
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


@dataclass(frozen=True)
class MoodScore:
    fit: float
    feature_closeness: dict


def score_mood(vector, mood):
    """Score proximity to a project-defined mood profile.

    No standalone arousal or dominance value is inferred. Activation-related
    differences are represented only by the audio features explicitly listed
    in the selected profile.
    """

    if mood not in MOOD_PROFILES:
        raise ValueError(f'Unsupported mood "{mood}"')

    targets = MOOD_PROFILES[mood]
    closeness = {
        feature_name: 1.0 - abs(vector[feature_name] - target)
        for feature_name, target in targets.items()
    }
    return MoodScore(
        fit=sum(closeness.values()) / len(closeness),
        feature_closeness=closeness,
    )


def calculate_mood_fit(vector, mood):
    """Return the scalar fit for callers that do not need evidence details."""

    if mood is None:
        return None
    return score_mood(vector, mood).fit
