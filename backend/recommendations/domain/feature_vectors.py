# This file builds the user's listening profile from normalized track features.
# It also provides the similarity calculations shared by the ranking stages.

from math import sqrt

from recommendations.audio_features import (
    FEATURE_NAMES,
    build_feature_vector,
    normalize_feature,
)
from recommendations.domain.algorithm_config import CURRENT_FEATURE_WEIGHTS

# Use the current configured weights for all eight audio features.
FEATURE_WEIGHTS = CURRENT_FEATURE_WEIGHTS

# Only the five most recent history vectors are used by default.
HISTORY_WINDOW_SIZE = 5


# Build a user profile by giving each recent track equal importance.
def build_session_profile(history_vectors, *, window_size=HISTORY_WINDOW_SIZE):
    """Average the most recent normalized history vectors into one profile."""

    if window_size < 1:
        raise ValueError("window_size must be at least 1")

    # Keep only the latest vectors within the configured history window.
    recent_vectors = list(history_vectors)[-window_size:]
    if not recent_vectors:
        raise ValueError("at least one history vector is required")

    return {
        feature_name: sum(vector[feature_name] for vector in recent_vectors)
        / len(recent_vectors)
        for feature_name in FEATURE_NAMES
    }


# Build a profile where newer history tracks receive greater weight
def build_recency_weighted_profile(
    history_vectors,
    *,
    window_size=HISTORY_WINDOW_SIZE,
):

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


# Compare the direction of two weighted feature vectors.
def weighted_cosine_similarity(
    vector_a,
    vector_b,
    *,
    weights=FEATURE_WEIGHTS,
):

    dot_product = sum(
        weights[name] * vector_a[name] * vector_b[name] for name in FEATURE_NAMES
    )
    magnitude_a = sqrt(
        sum(weights[name] * vector_a[name] ** 2 for name in FEATURE_NAMES)
    )
    magnitude_b = sqrt(
        sum(weights[name] * vector_b[name] ** 2 for name in FEATURE_NAMES)
    )

    # Calculate the weighted magnitude required by cosine similarity.
    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    similarity = dot_product / (magnitude_a * magnitude_b)
    return max(0.0, min(1.0, similarity))


# Define the euclidean similarity between two song
def weighted_euclidean_similarity(
    vector_a,
    vector_b,
    *,
    weights=FEATURE_WEIGHTS,
):
    """Convert normalized weighted Euclidean distance into [0, 1] similarity."""

    total_weight = sum(weights.values())
    if total_weight <= 0.0:
        return 0.0

    squared_distance = sum(
        weights[name] * ((vector_a[name] - vector_b[name]) ** 2)
        for name in FEATURE_NAMES
    )
    distance = sqrt(squared_distance / total_weight)
    return max(0.0, min(1.0, 1.0 - distance))


# # Select the similarity method configured for the current algorithm.
def calculate_similarity(
    vector_a,
    vector_b,
    *,
    metric="weighted_cosine",
    weights=FEATURE_WEIGHTS,
):
    if metric == "weighted_cosine":
        return weighted_cosine_similarity(vector_a, vector_b, weights=weights)
    if metric == "weighted_euclidean":
        return weighted_euclidean_similarity(vector_a, vector_b, weights=weights)
    raise ValueError(f"Unsupported similarity metric: {metric!r}")


#  Report the closeness of each feature for explanation purposes.
#  These values do not represent individual cosine contributions.
def feature_closeness(vector, profile):

    return {
        feature_name: 1.0 - abs(vector[feature_name] - profile[feature_name])
        for feature_name in FEATURE_NAMES
    }
