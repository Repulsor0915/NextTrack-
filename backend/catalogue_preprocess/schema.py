## Defines the Kaggle CSV column names and the preprocessing policy for the recommendation catalogue.
## for now set "artist" could be a null value

from dataclasses import dataclass
from recommendations.audio_features import FEATURE_NAMES

SOURCE_COLUMNS = {
    "id": "track_id",
    "title": "track_name",
    "artist": "artists",
    "genre": "track_genre",
    "explicit": "explicit",
    "album": "album_name",
}

REQUIRED_SOURCE_COLUMNS = tuple(SOURCE_COLUMNS.values()) + FEATURE_NAMES
REQUIRED_NON_EMPTY_COLUMNS = (
    SOURCE_COLUMNS["id"],
    SOURCE_COLUMNS["title"],
    SOURCE_COLUMNS["explicit"],
    *FEATURE_NAMES,
)

TEXT_LIMITS = {
    SOURCE_COLUMNS["id"]: 100,
    SOURCE_COLUMNS["title"]: 255,
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

TRACKS_REQUIRED_COLUMNS = (
    "track_id",
    "name",
    "track_artists",
    "album_name",
    "genres",
    "explicit",
    "album_release_date",
    *FEATURE_NAMES,
)


@dataclass(frozen=True)
class PreprocessingPolicy:
    """Rules used to validate and filter the source CSV rows for the recommendation catalogue."""

    ## allowed to have blank genre
    allow_blank_genre: bool = True

    ## explicit must be a boolean value, either "true" or "false"
    require_boolean_explicit: bool = True

    ## tempo have to > 0
    require_positive_tempo: bool = True

    ## if duplicate track_id, keep the first hard-valid row
    duplicate_policy: str = "keep_first_hard_valid"

    ## if the source row is rejected, whether to filter out the track from the catalogue
    content_policy_filters: tuple[str, ...] = ()


POLICY = PreprocessingPolicy()
