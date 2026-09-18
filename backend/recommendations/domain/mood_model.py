from dataclasses import dataclass

from .algorithm_config import PANDA_2021_MER_MOOD_FEATURE_WEIGHTS


MOOD_MODEL_VERSION = "va-targets-panda-2021-relieff-weights-v2"

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


def score_mood(
    vector,
    mood,
    *,
    feature_weights=PANDA_2021_MER_MOOD_FEATURE_WEIGHTS,
):
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
    if feature_weights is None:
        active_weights = {feature_name: 1.0 for feature_name in targets}
    else:
        active_weights = {
            feature_name: feature_weights[feature_name]
            for feature_name in targets
        }
    active_weight_total = sum(active_weights.values())
    if active_weight_total <= 0.0:
        raise ValueError("The requested mood must have at least one positive weight")

    return MoodScore(
        fit=sum(
            active_weights[feature_name] * closeness[feature_name]
            for feature_name in targets
        )
        / active_weight_total,
        feature_closeness=closeness,
    )


def calculate_mood_fit(
    vector,
    mood,
    *,
    feature_weights=PANDA_2021_MER_MOOD_FEATURE_WEIGHTS,
):
    """Return the scalar fit for callers that do not need evidence details."""

    if mood is None:
        return None
    return score_mood(vector, mood, feature_weights=feature_weights).fit
