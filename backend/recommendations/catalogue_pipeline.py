import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import fmean

from recommendations.catalogue_schema import FEATURE_FIELDS
from recommendations.domain.feature_vectors import FEATURE_RANGES


SOURCE_COLUMNS = {
    "id": "track_id",
    "title": "track_name",
    "artist": "artists",
    "genre": "track_genre",
}
QUALITY_COLUMNS = ("explicit",)
EXCLUDED_GENRES = {"comedy", "sleep"}
BOUNDED_FEATURES = {
    "energy",
    "valence",
    "danceability",
    "acousticness",
    "instrumentalness",
    "speechiness",
}
SOURCE_INFORMATION = {
    "name": "Spotify Tracks Dataset",
    "publisher": "MaharshiPandya",
    "canonical_url": (
        "https://www.kaggle.com/datasets/maharshipandya/"
        "-spotify-tracks-dataset"
    ),
    "metadata_api_url": (
        "https://www.kaggle.com/api/v1/datasets/view/"
        "maharshipandya/-spotify-tracks-dataset"
    ),
    "retrieval_url": (
        "https://huggingface.co/datasets/maharshipandya/"
        "spotify-tracks-dataset/resolve/"
        "c4609440b24ac4075899f6e60b33775acbe00827/dataset.csv"
    ),
    "retrieval_revision": "c4609440b24ac4075899f6e60b33775acbe00827",
    "version": 1,
    "source_last_updated": "2022-10-22T14:40:15.3Z",
    "declared_database_license": (
        "Open Database License; contents remain © original authors"
    ),
    "license_url": "https://opendatacommons.org/licenses/odbl/1-0/",
    "feature_origin": "Collected using the Spotify Web API",
}


class CataloguePreparationError(ValueError):
    pass


def prepare_catalogue(
    source_path,
    output_directory,
    *,
    limit,
    seed,
    catalogue_version,
    retrieved_date,
    write_full_exclusions=False,
):
    source_path = Path(source_path).resolve()
    output_directory = Path(output_directory).resolve()

    if limit < 1:
        raise CataloguePreparationError("limit must be at least 1")
    if not source_path.is_file():
        raise CataloguePreparationError(f"source CSV does not exist: {source_path}")

    prepared = _read_and_validate(source_path)
    valid_catalogue = prepared["valid_catalogue"]
    if limit > len(valid_catalogue):
        raise CataloguePreparationError(
            f"limit {limit} exceeds {len(valid_catalogue)} valid unique tracks"
        )

    selected = sorted(
        valid_catalogue,
        key=lambda item: hashlib.sha256(
            f'{seed}:{item["id"]}'.encode("utf-8")
        ).hexdigest(),
    )[:limit]
    selected.sort(key=lambda item: item["id"])
    output_directory.mkdir(parents=True, exist_ok=True)

    catalogue_path = output_directory / "catalogue.json"
    exclusions_summary_path = output_directory / "excluded-rows-summary.json"
    summary_path = output_directory / "dataset-summary.json"

    _write_json(catalogue_path, selected)

    exclusion_counts = Counter(
        reason
        for exclusion in prepared["excluded_rows"]
        for reason in exclusion["reasons"]
    )
    exclusions_summary = {
        "excluded_source_row_count": len(prepared["excluded_rows"]),
        "reason_counts": dict(sorted(exclusion_counts.items())),
        "examples": prepared["excluded_rows"][:100],
        "examples_are_truncated": len(prepared["excluded_rows"]) > 100,
    }
    _write_json(exclusions_summary_path, exclusions_summary)

    if write_full_exclusions:
        _write_json(
            output_directory / "excluded-rows.json",
            prepared["excluded_rows"],
        )

    feature_statistics = {
        feature_name: _feature_statistics(
            [item["features"][feature_name] for item in valid_catalogue],
            feature_name,
        )
        for feature_name in FEATURE_FIELDS
    }
    summary = {
        "source_row_count": prepared["source_row_count"],
        "source_column_count": len(prepared["source_columns"]),
        "source_columns": prepared["source_columns"],
        "required_columns": prepared["required_columns"],
        "missing_value_counts": prepared["missing_value_counts"],
        "valid_unique_track_count": len(valid_catalogue),
        "excluded_source_row_count": len(prepared["excluded_rows"]),
        "unselected_valid_track_count": len(valid_catalogue) - len(selected),
        "selected_track_count": len(selected),
        "selection_method": (
            "lowest SHA-256 priorities of seed:track_id over valid unique tracks"
        ),
        "selection_seed": seed,
        "feature_statistics_for_valid_unique_tracks": feature_statistics,
        "selected_genre_count": len({item["genre"] for item in selected}),
        "selected_artist_count": len({item["artist"] for item in selected}),
    }
    _write_json(summary_path, summary)

    outputs = {
        path.name: {
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(output_directory.glob("*.json"))
        if path.name != "manifest.json"
    }
    manifest = {
        "schema_version": 1,
        "catalogue_version": catalogue_version,
        "retrieved_date": retrieved_date,
        "source": {
            **SOURCE_INFORMATION,
            "raw_file": source_path.name,
            "raw_sha256": _sha256(source_path),
            "raw_bytes": source_path.stat().st_size,
        },
        "transform": {
            "required_audio_features": list(FEATURE_FIELDS),
            "deduplication_key": "track_id",
            "duplicate_policy": "keep first valid source row",
            "invalid_row_policy": "exclude and report reasons",
            "spoken_word_policy": "exclude speechiness greater than 0.66",
            "explicit_content_policy": "exclude source rows marked explicit",
            "genre_policy": "exclude comedy and sleep as non-song categories",
            "year_policy": "null because the source does not provide release year",
            "selection_limit": limit,
            "selection_seed": seed,
        },
        "outputs": outputs,
        "licence_note": (
            "The Kaggle metadata declares the database licence; track and artist "
            "names remain content attributed to their original authors. Preserve "
            "attribution and review ODbL share-alike obligations before public "
            "redistribution of an adapted database."
        ),
    }
    manifest_path = output_directory / "manifest.json"
    _write_json(manifest_path, manifest)

    return {
        "catalogue_path": catalogue_path,
        "manifest_path": manifest_path,
        "summary_path": summary_path,
        "exclusions_summary_path": exclusions_summary_path,
        "selected_track_count": len(selected),
        "valid_unique_track_count": len(valid_catalogue),
        "excluded_source_row_count": len(prepared["excluded_rows"]),
    }


def _read_and_validate(source_path):
    required_columns = (
        list(SOURCE_COLUMNS.values())
        + list(QUALITY_COLUMNS)
        + list(FEATURE_FIELDS)
    )
    valid_catalogue = []
    excluded_rows = []
    seen_ids = set()
    missing_value_counts = Counter()
    source_row_count = 0

    with source_path.open(encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)
        source_columns = reader.fieldnames or []
        absent_columns = sorted(set(required_columns) - set(source_columns))
        if absent_columns:
            raise CataloguePreparationError(
                "source CSV is missing required columns: "
                + ", ".join(absent_columns)
            )

        for source_row_number, row in enumerate(reader, start=2):
            source_row_count += 1
            reasons = []

            for column_name in required_columns:
                if _is_missing(row.get(column_name)):
                    missing_value_counts[column_name] += 1
                    reasons.append(f"missing_{column_name}")

            track_id = (row.get(SOURCE_COLUMNS["id"]) or "").strip()
            if track_id and track_id in seen_ids:
                reasons.append("duplicate_track_id")

            explicit_value = (row.get("explicit") or "").strip().lower()
            if explicit_value not in {"true", "false"}:
                reasons.append("invalid_explicit")
            elif explicit_value == "true":
                reasons.append("explicit_content")

            genre = (row.get(SOURCE_COLUMNS["genre"]) or "").strip()
            if genre.lower() in EXCLUDED_GENRES:
                reasons.append("non_song_genre")

            features = {}
            if not reasons:
                for feature_name in FEATURE_FIELDS:
                    try:
                        value = float(row[feature_name])
                    except (TypeError, ValueError):
                        reasons.append(f"invalid_{feature_name}")
                        continue

                    if not math.isfinite(value):
                        reasons.append(f"non_finite_{feature_name}")
                    elif feature_name in BOUNDED_FEATURES and not 0 <= value <= 1:
                        reasons.append(f"out_of_range_{feature_name}")
                    elif feature_name == "tempo" and not 0 < value <= 300:
                        reasons.append("out_of_range_tempo")
                    elif feature_name == "loudness" and not -60 <= value <= 5:
                        reasons.append("out_of_range_loudness")
                    else:
                        features[feature_name] = value

            if not reasons and features["speechiness"] > 0.66:
                reasons.append("likely_spoken_word")

            if reasons:
                excluded_rows.append(
                    {
                        "source_row_number": source_row_number,
                        "track_id": track_id or None,
                        "reasons": sorted(set(reasons)),
                    }
                )
                continue

            seen_ids.add(track_id)
            valid_catalogue.append(
                {
                    "id": track_id,
                    "title": row[SOURCE_COLUMNS["title"]].strip(),
                    "artist": row[SOURCE_COLUMNS["artist"]].strip(),
                    "genre": genre,
                    "year": None,
                    "features": {
                        feature_name: features[feature_name]
                        for feature_name in FEATURE_FIELDS
                    },
                }
            )

    return {
        "source_row_count": source_row_count,
        "source_columns": source_columns,
        "required_columns": required_columns,
        "missing_value_counts": {
            column_name: missing_value_counts[column_name]
            for column_name in required_columns
        },
        "valid_catalogue": valid_catalogue,
        "excluded_rows": excluded_rows,
    }


def _feature_statistics(values, feature_name):
    sorted_values = sorted(values)
    configured_minimum, configured_maximum = FEATURE_RANGES[feature_name]
    return {
        "minimum": round(min(values), 6),
        "p01": round(_percentile(sorted_values, 0.01), 6),
        "median": round(_percentile(sorted_values, 0.50), 6),
        "mean": round(fmean(values), 6),
        "p99": round(_percentile(sorted_values, 0.99), 6),
        "maximum": round(max(values), 6),
        "below_current_normalization_minimum": sum(
            value < configured_minimum for value in values
        ),
        "above_current_normalization_maximum": sum(
            value > configured_maximum for value in values
        ),
    }


def _percentile(sorted_values, proportion):
    position = (len(sorted_values) - 1) * proportion
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return sorted_values[lower_index]
    fraction = position - lower_index
    return (
        sorted_values[lower_index] * (1 - fraction)
        + sorted_values[upper_index] * fraction
    )


def _is_missing(value):
    return value is None or not str(value).strip()


def _write_json(path, value):
    with path.open("w", encoding="utf-8", newline="\n") as output_file:
        json.dump(value, output_file, ensure_ascii=False, indent=2, sort_keys=True)
        output_file.write("\n")


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
