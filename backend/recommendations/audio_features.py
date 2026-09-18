"""Shared audio-feature contract for catalogue data and recommendation code."""

from collections.abc import Mapping


FEATURE_NAMES = (
    "tempo",
    "energy",
    "valence",
    "danceability",
    "acousticness",
    "instrumentalness",
    "loudness",
    "speechiness",
)

# Runtime normalization ranges. These are model parameters, not source-data
# validity rules. Values outside a range remain valid but are clamped to [0, 1]
# when a recommendation vector is built.
NORMALIZATION_RANGES = {
    "tempo": (40.0, 220.0),
    "energy": (0.0, 1.0),
    "valence": (0.0, 1.0),
    "danceability": (0.0, 1.0),
    "acousticness": (0.0, 1.0),
    "instrumentalness": (0.0, 1.0),
    "loudness": (-30.0, 0.0),
    "speechiness": (0.0, 1.0),
}


def normalize_feature(feature_name, value):
    """Min-max normalize one raw value and clamp the result to [0, 1]."""

    minimum, maximum = NORMALIZATION_RANGES[feature_name]
    normalized = (float(value) - minimum) / (maximum - minimum)
    return max(0.0, min(1.0, normalized))


def build_feature_vector(features):
    """Build the normalized eight-dimensional recommendation vector."""

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
