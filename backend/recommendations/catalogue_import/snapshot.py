## This file reads and validates the processed catalogue snapshot.
## It checks the manifest, SHA256 value, JSON structure, and track records.

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from django.core.management.base import CommandError

from recommendations.audio_features import FEATURE_NAMES

UNIT_INTERVAL_FEATURES = frozenset(
    {
        "energy",
        "valence",
        "danceability",
        "acousticness",
        "instrumentalness",
        "speechiness",
    }
)


@dataclass(frozen=True)
class CatalogueSnapshot:
    path: Path
    version: str
    sha256: str
    records: list[dict]

    @property
    def ids(self):
        return {item["id"] for item in self.records}


def read_verified_snapshot(path, *, asserted_version=None):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise CommandError(f"Catalogue file does not exist: {path}")
    manifest_path = path.with_name("manifest.json")
    if not manifest_path.is_file():
        raise CommandError(f"Catalogue manifest does not exist: {manifest_path}")
    try:
        with manifest_path.open(encoding="utf-8") as source:
            manifest = json.load(source)
    except (OSError, ValueError) as error:
        raise CommandError(f"Could not read catalogue manifest: {error}") from error
    if not isinstance(manifest, dict):
        raise CommandError("Catalogue manifest must be a JSON object.")

    version = manifest.get("catalogue_version")
    if not isinstance(version, str) or not version or len(version) > 100:
        raise CommandError("Manifest has an invalid catalogue_version.")
    if asserted_version is not None and asserted_version != version:
        raise CommandError("--data-source must match manifest catalogue_version.")
    outputs = manifest.get("outputs")
    output = outputs.get(path.name) if isinstance(outputs, dict) else None
    if not isinstance(output, dict):
        raise CommandError("Manifest has no catalogue output entry.")

    try:
        raw = path.read_bytes()
    except OSError as error:
        raise CommandError(f"Could not read catalogue: {error}") from error
    checksum = hashlib.sha256(raw).hexdigest()
    if output.get("sha256") != checksum or output.get("bytes") != len(raw):
        raise CommandError("Catalogue checksum or byte size differs from manifest.")

    try:
        records = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise CommandError(f"Could not read catalogue JSON: {error}") from error
    if not isinstance(records, list) or not records:
        raise CommandError("Catalogue must be a nonempty JSON list.")
    _validate_records(records)
    return CatalogueSnapshot(
        path=path, version=version, sha256=checksum, records=records
    )


def _validate_records(records):
    seen_ids = set()
    required_features = set(FEATURE_NAMES)
    for index, item in enumerate(records, start=1):
        if not isinstance(item, dict):
            raise CommandError(f"Invalid track at item {index}: expected object.")
        track_id = item.get("id")
        if not isinstance(track_id, str) or not track_id or len(track_id) > 100:
            raise CommandError(f"Invalid track at item {index}: invalid ID.")
        if track_id in seen_ids:
            raise CommandError(f"Invalid track at item {index}: duplicate ID.")
        seen_ids.add(track_id)

        title = item.get("title")
        if not isinstance(title, str) or not title or len(title) > 255:
            raise CommandError(f"Invalid track at item {index}: invalid title.")

        for name in ("artist_display", "album_display"):
            if name not in item:
                raise CommandError(f"Invalid track at item {index}:missing {name}.")

            value = item[name]
            if value is not None and not isinstance(value, str):
                raise CommandError(f"Invalid track at item {index}:invalid {name}.")

        genres = item.get("genres", [])
        if not isinstance(genres, list) or any(
            not isinstance(genre, str)
            or not genre.strip()
            or len(genre) > 100
            or len(genre.strip().casefold()) > 255
            for genre in genres
        ):
            raise CommandError(f"Invalid track at item {index}: invalid genres.")
        if not isinstance(item.get("explicit"), bool):
            raise CommandError(f"Invalid track at item {index}: invalid explicit.")
        year = item.get("year")
        if year is not None and (type(year) is not int or not 1800 <= year <= 2100):
            raise CommandError(f"Invalid track at item {index}: invalid year.")
        features = item.get("features")
        if not isinstance(features, dict) or set(features) != required_features:
            raise CommandError(
                f"Invalid track at item {index}: eight features required."
            )
        for name in FEATURE_NAMES:
            value = features[name]
            if type(value) not in (int, float) or not math.isfinite(value):
                raise CommandError(f"Invalid track at item {index}: non-finite {name}.")
            if name in UNIT_INTERVAL_FEATURES and not 0 <= value <= 1:
                raise CommandError(
                    f"Invalid track at item {index}: out-of-range {name}."
                )
            if name == "tempo" and value <= 0:
                raise CommandError(
                    f"Invalid track at item {index}: non-positive tempo."
                )
