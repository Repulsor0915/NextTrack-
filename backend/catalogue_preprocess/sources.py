import ast
import csv
from datetime import date
from pathlib import Path

from recommendations.audio_features import FEATURE_NAMES

from .schema import REQUIRED_SOURCE_COLUMNS, TRACKS_REQUIRED_COLUMNS
from .validation import RowValidation, validate_source_row

from collections import Counter


class CataloguePreparationError(ValueError):
    """Raised when a reproducible catalogue cannot be prepared."""


def _merge_catalogue_records(kaggle_records, tracks_records):
    by_id = {record["id"]: record for record in kaggle_records}
    overlap_count = 0

    for record in tracks_records:
        if record["id"] in by_id:
            overlap_count += 1
            continue
        by_id[record["id"]] = record

    merged = sorted(by_id.values(), key=lambda record: record["id"])
    return merged, overlap_count


def _collect_merged_records(kaggle_path, tracks_path):
    kaggle_path = Path(kaggle_path).resolve()
    tracks_path = Path(tracks_path).resolve()

    for path in (kaggle_path, tracks_path):
        if not path.is_file():
            raise CataloguePreparationError(f"Source CSV does not exist: {path}")

    kaggle_result = _read_valid_unique_rows(
        kaggle_path,
        required_columns=REQUIRED_SOURCE_COLUMNS,
        validate_row=validate_source_row,
    )
    tracks_result = _read_valid_unique_rows(
        tracks_path,
        required_columns=TRACKS_REQUIRED_COLUMNS,
        validate_row=_validate_tracks_row,
    )
    catalogue, overlap_count = _merge_catalogue_records(
        kaggle_result["valid_catalogue"],
        tracks_result["valid_catalogue"],
    )

    return {
        "catalogue": catalogue,
        "kaggle": kaggle_result,
        "tracks": tracks_result,
        "overlap_count": overlap_count,
    }


## Classify the original csv dataset into valid and invalid rows, and remove duplicates based on track_id.
## The valid rows are then written to catalogue.json, and a report is generated in preprocessing-report.json.
## A manifest.json file is also created to document the process and outputs.
def _read_valid_unique_rows(source_path, *, required_columns, validate_row):
    rejected_count = 0
    rejection_counts = Counter()

    valid_catalogue = []
    rejected_rows = []
    accepted_by_id = {}
    source_row_count = 0

    with source_path.open(encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)
        source_columns = reader.fieldnames or []
        missing_columns = sorted(set(required_columns) - set(source_columns))
        if missing_columns:
            raise CataloguePreparationError(
                "Source CSV is missing required columns: " + ", ".join(missing_columns)
            )

        for row_number, row in enumerate(reader, start=2):
            source_row_count += 1
            validation = validate_row(row)
            if validation.reasons:
                reasons = list(validation.reasons)
                rejected_count += 1
                rejection_counts.update(reasons)

                if len(rejected_rows) < 100:
                    rejected_rows.append(
                        {
                            "source_row_number": row_number,
                            "track_id": (row.get("track_id") or "").strip() or None,
                            "reasons": reasons,
                        }
                    )
                continue

            record = validation.record
            if record["id"] in accepted_by_id:
                first_record = accepted_by_id[record["id"]]
                reasons = ["duplicate_track_id"]
                if record["features"] != first_record["features"]:
                    reasons.append("duplicate_conflicting_features")
                new_genres = set(record["genres"]) - set(first_record["genres"])
                if new_genres:
                    reasons.append("duplicate_conflicting_genres")
                    first_record["genres"] = sorted(
                        set(first_record["genres"]) | new_genres
                    )
                if record["explicit"] != first_record["explicit"]:
                    reasons.append("duplicate_conflicting_explicit")

                rejected_count += 1
                rejection_counts.update(reasons)

                if len(rejected_rows) < 100:
                    rejected_rows.append(
                        {
                            "source_row_number": row_number,
                            "track_id": record["id"],
                            "reasons": reasons,
                        }
                    )
                continue

            accepted_by_id[record["id"]] = record
            valid_catalogue.append(record)

    return {
        "source_row_count": source_row_count,
        "valid_catalogue": valid_catalogue,
        "rejected_rows": rejected_rows,
        "rejected_count": rejected_count,
        "rejection_counts": rejection_counts,
    }


## Below codes are target to process tracks.csv
def _normalize_tracks_row(row):
    ## Change the variable name of track.csv to fit the catalogue schema
    normalized = {
        "track_id": row.get("track_id"),
        "track_name": row.get("name"),
        "artists": row.get("track_artists"),
        "album_name": row.get("album_name"),
        "track_genre": "",
        "explicit": row.get("explicit"),
    }
    normalized.update({name: row.get(name) for name in FEATURE_NAMES})
    return normalized


def _validate_tracks_row(row):
    validation = validate_source_row(_normalize_tracks_row(row))
    genres, genre_error = _parse_genres(row.get("genres"))

    reasons = list(validation.reasons)
    if genre_error:
        reasons.append(genre_error)
    if reasons:
        return RowValidation(record=None, reasons=tuple(sorted(set(reasons))))

    record = validation.record
    record["genres"] = genres
    record["year"] = _release_year(row.get("album_release_date"))
    return RowValidation(record=record, reasons=())


##  Categories genre such as ["Pop", "Rock"] to a sorted list
def _parse_genres(raw_value):
    if raw_value is None or not str(raw_value).strip():
        return [], None
    try:
        value = ast.literal_eval(raw_value)
    except (SyntaxError, ValueError, TypeError):
        return [], "invalid_genres"
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return [], "invalid_genres"
    if any(len(item.strip()) > 100 for item in value):
        return [], "too_long_track_genre"
    return sorted({item.strip() for item in value if item.strip()}), None


## abstract the release year from the album_release_date,
## which can be in various formats such as "YYYY", "YYYY-MM", or "YYYY-MM-DD".
def _release_year(raw_value):
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        if len(value) == 4:
            year = int(value)
        elif len(value) == 7:
            year = date.fromisoformat(value + "-01").year
        else:
            year = date.fromisoformat(value).year
    except ValueError:
        return None
    return year if 1800 <= year <= 2100 else None
