from collections.abc import Mapping
from math import sqrt


FEATURE_RANGES = {
    "tempo": (40.0, 220.0),
    "energy": (0.0, 1.0),
    "valence": (0.0, 1.0),
    "danceability": (0.0, 1.0),
    "acousticness": (0.0, 1.0),
    "instrumentalness": (0.0, 1.0),
    "loudness": (-30.0, 0.0),
    "speechiness": (0.0, 1.0),
}

FEATURE_WEIGHTS = {
    "tempo": 0.10,
    "energy": 0.25,
    "valence": 0.25,
    "danceability": 0.15,
    "acousticness": 0.10,
    "instrumentalness": 0.05,
    "loudness": 0.05,
    "speechiness": 0.05,
}

FEATURE_NAMES = tuple(FEATURE_RANGES)
HISTORY_WINDOW_SIZE = 5


def normalize_feature(feature_name, value):
    """Min-max normalise one feature and clamp it to the [0, 1] interval."""

    minimum, maximum = FEATURE_RANGES[feature_name]
    normalized = (float(value) - minimum) / (maximum - minimum)
    return max(0.0, min(1.0, normalized))


def build_feature_vector(features):
    """Build a normalized vector from a mapping or TrackFeatures-like object."""

    def get_value(feature_name):
        if isinstance(features, Mapping):
            return features[feature_name]
        return getattr(features, feature_name)

    return {
        feature_name: normalize_feature(
            feature_name,
            get_value(feature_name),
        )
        for feature_name in FEATURE_NAMES
    }


def build_session_profile(history_vectors, *, window_size=HISTORY_WINDOW_SIZE):
    """Average the most recent normalized history vectors into one profile."""

    if window_size < 1:
        raise ValueError("window_size must be at least 1")

    recent_vectors = list(history_vectors)[-window_size:]
    if not recent_vectors:
        raise ValueError("at least one history vector is required")

    return {
        feature_name: sum(
            vector[feature_name] for vector in recent_vectors
        )
        / len(recent_vectors)
        for feature_name in FEATURE_NAMES
    }


def build_recency_weighted_profile(
    history_vectors,
    *,
    window_size=HISTORY_WINDOW_SIZE,
):
    """Build a profile with linear weights favouring more recent history."""

    if window_size < 1:
        raise ValueError("window_size must be at least 1")

    recent_vectors = list(history_vectors)[-window_size:]
    if not recent_vectors:
        raise ValueError("at least one history vector is required")

    recency_weights = list(range(1, len(recent_vectors) + 1))
    total_weight = sum(recency_weights)
    return {
        feature_name: sum(
            weight * vector[feature_name]
            for weight, vector in zip(recency_weights, recent_vectors, strict=True)
        )
        / total_weight
        for feature_name in FEATURE_NAMES
    }


def weighted_cosine_similarity(
    vector_a,
    vector_b,
    *,
    weights=FEATURE_WEIGHTS,
):
    """Calculate weighted cosine similarity, returning a value in [0, 1]."""

    dot_product = sum(
        weights[name] * vector_a[name] * vector_b[name] for name in FEATURE_NAMES
    )
    magnitude_a = sqrt(
        sum(weights[name] * vector_a[name] ** 2 for name in FEATURE_NAMES)
    )
    magnitude_b = sqrt(
        sum(weights[name] * vector_b[name] ** 2 for name in FEATURE_NAMES)
    )

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    similarity = dot_product / (magnitude_a * magnitude_b)
    return max(0.0, min(1.0, similarity))


def feature_closeness(vector, profile):
    """Return per-feature proximity where 1 is identical and 0 is farthest."""

    return {
        feature_name: 1.0 - abs(vector[feature_name] - profile[feature_name])
        for feature_name in FEATURE_NAMES
    }
