"""Input schema and hard-validity rules for the Spotify source CSV."""

from dataclasses import dataclass

from recommendations.audio_features import FEATURE_NAMES


SOURCE_COLUMNS = {
    "id": "track_id",
    "title": "track_name",
    "artist": "artists",
    "genre": "track_genre",
    "explicit": "explicit",
}

REQUIRED_SOURCE_COLUMNS = tuple(SOURCE_COLUMNS.values()) + FEATURE_NAMES
REQUIRED_NON_EMPTY_COLUMNS = (
    SOURCE_COLUMNS["id"],
    SOURCE_COLUMNS["title"],
    SOURCE_COLUMNS["artist"],
    SOURCE_COLUMNS["explicit"],
    *FEATURE_NAMES,
)

TEXT_LIMITS = {
    SOURCE_COLUMNS["id"]: 100,
    SOURCE_COLUMNS["title"]: 255,
    SOURCE_COLUMNS["artist"]: 255,
    SOURCE_COLUMNS["genre"]: 100,
}

UNIT_INTERVAL_FEATURES = {
    "energy",
    "valence",
    "danceability",
    "acousticness",
    "instrumentalness",
    "speechiness",
}


@dataclass(frozen=True)
class PreprocessingPolicy:
    """One explicit, serializable contract for catalogue eligibility."""

    allow_blank_genre: bool = True
    require_boolean_explicit: bool = True
    require_positive_tempo: bool = True
    duplicate_policy: str = "keep_first_hard_valid"
    content_policy_filters: tuple[str, ...] = ()


POLICY = PreprocessingPolicy()
