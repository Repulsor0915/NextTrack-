from collections.abc import Mapping

from .schema import FEATURE_FIELDS


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

FEATURE_NAMES = FEATURE_FIELDS


def normalize_feature(feature_name, value):
    """Min-max normalise one raw feature and clamp it to [0, 1]."""

    minimum, maximum = FEATURE_RANGES[feature_name]
    normalized = (float(value) - minimum) / (maximum - minimum)
    return max(0.0, min(1.0, normalized))


def build_feature_vector(features):
    """Build a normalized vector from raw mapping/model feature values."""

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
