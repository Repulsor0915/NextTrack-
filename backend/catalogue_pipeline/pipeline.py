"""Deterministic preparation and sampling of the NextTrack catalogue."""

import csv
import hashlib
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from recommendations.audio_features import FEATURE_NAMES, NORMALIZATION_RANGES

from .schema import POLICY, REQUIRED_SOURCE_COLUMNS
from .validation import validate_source_row


class CataloguePreparationError(ValueError):
    """Raised when a reproducible catalogue cannot be prepared."""


def prepare_catalogue(
    source_path,
    output_directory,
    *,
    catalogue_version,
    retrieved_date,
):
    """Validate, deduplicate and write the complete hard-valid catalogue."""

    source_path = Path(source_path).resolve()
    output_directory = Path(output_directory).resolve()
    if not source_path.is_file():
        raise CataloguePreparationError(f"Source CSV does not exist: {source_path}")
    if not catalogue_version.strip():
        raise CataloguePreparationError("catalogue_version cannot be empty")
    if not retrieved_date.strip():
        raise CataloguePreparationError("retrieved_date cannot be empty")
    _require_empty_output_directory(output_directory)

    read_result = _read_valid_unique_rows(source_path)
    catalogue = sorted(read_result["valid_catalogue"], key=lambda item: item["id"])
    selection = {
        "mode": "all_valid_unique",
        "method": "all hard-valid unique tracks sorted by track_id",
    }

    output_directory.mkdir(parents=True, exist_ok=True)
    catalogue_path = output_directory / "catalogue.json"
    report_path = output_directory / "preprocessing-report.json"
    manifest_path = output_directory / "manifest.json"

    rejection_counts = Counter(
        reason
        for rejected in read_result["rejected_rows"]
        for reason in rejected["reasons"]
    )
    report = {
        "source_row_count": read_result["source_row_count"],
        "hard_valid_unique_count": len(catalogue),
        "rejected_row_count": len(read_result["rejected_rows"]),
        "selected_track_count": len(catalogue),
        "rejection_reason_counts": dict(sorted(rejection_counts.items())),
        "rejection_examples": read_result["rejected_rows"][:100],
        "rejection_examples_truncated": len(read_result["rejected_rows"]) > 100,
        "selection": selection,
    }
    _write_json(catalogue_path, catalogue)
    _write_json(report_path, report)

    manifest = {
        "schema_version": "nexttrack-catalogue-v2",
        "catalogue_version": catalogue_version,
        "retrieved_date": retrieved_date,
        "source": {
            "file_name": source_path.name,
            "bytes": source_path.stat().st_size,
            "sha256": _sha256(source_path),
        },
        "preprocessing": {
            "required_features": list(FEATURE_NAMES),
            "validation_policy": "hard validity only",
            "hard_validation_policy": asdict(POLICY),
            "deduplication_key": "track_id",
            "genre_policy": "merge unique non-empty labels and sort",
            "stored_feature_values": "raw source values",
            "selection": selection,
        },
        "runtime_normalization": {
            feature_name: {"minimum": bounds[0], "maximum": bounds[1]}
            for feature_name, bounds in NORMALIZATION_RANGES.items()
        },
        "outputs": {
            catalogue_path.name: {
                "bytes": catalogue_path.stat().st_size,
                "sha256": _sha256(catalogue_path),
            },
            report_path.name: {
                "bytes": report_path.stat().st_size,
                "sha256": _sha256(report_path),
            },
        },
    }
    _write_json(manifest_path, manifest)
    return {
        "catalogue_path": catalogue_path,
        "report_path": report_path,
        "manifest_path": manifest_path,
        "source_row_count": read_result["source_row_count"],
        "valid_unique_count": len(catalogue),
        "rejected_row_count": len(read_result["rejected_rows"]),
        "selected_track_count": len(catalogue),
    }


def sample_catalogue(
    parent_catalogue_path,
    output_directory,
    *,
    catalogue_version,
    limit,
    seed,
):
    """Create a deterministic test catalogue from one frozen full catalogue."""

    parent_catalogue_path = Path(parent_catalogue_path).resolve()
    output_directory = Path(output_directory).resolve()
    if not parent_catalogue_path.is_file():
        raise CataloguePreparationError(
            f"Parent catalogue does not exist: {parent_catalogue_path}"
        )
    if not catalogue_version.strip():
        raise CataloguePreparationError("catalogue_version cannot be empty")
    if limit < 1:
        raise CataloguePreparationError("limit must be at least 1")
    _require_empty_output_directory(output_directory)

    try:
        with parent_catalogue_path.open(encoding="utf-8") as source:
            parent_catalogue = json.load(source)
    except (OSError, json.JSONDecodeError) as error:
        raise CataloguePreparationError(
            f"Could not read parent catalogue: {error}"
        ) from error

    if not isinstance(parent_catalogue, list) or not parent_catalogue:
        raise CataloguePreparationError(
            "Parent catalogue must be a non-empty JSON array"
        )
    track_ids = [str(track.get("id", "")).strip() for track in parent_catalogue]
    if any(not track_id for track_id in track_ids):
        raise CataloguePreparationError("Parent catalogue contains a missing track ID")
    if len(set(track_ids)) != len(track_ids):
        raise CataloguePreparationError("Parent catalogue contains duplicate track IDs")
    if limit > len(parent_catalogue):
        raise CataloguePreparationError(
            f"limit {limit} exceeds parent size {len(parent_catalogue)}"
        )

    selected = sorted(
        parent_catalogue,
        key=lambda item: hashlib.sha256(
            f'{seed}:{item["id"]}'.encode("utf-8")
        ).hexdigest(),
    )[:limit]
    selected.sort(key=lambda item: item["id"])

    parent_sha256 = _sha256(parent_catalogue_path)
    parent_version = _read_parent_version(parent_catalogue_path, parent_sha256)
    output_directory.mkdir(parents=True, exist_ok=True)
    catalogue_path = output_directory / "catalogue.json"
    report_path = output_directory / "sample-report.json"
    manifest_path = output_directory / "manifest.json"
    method = "lowest SHA-256 priorities of seed:track_id over parent catalogue"

    report = {
        "parent_track_count": len(parent_catalogue),
        "selected_track_count": len(selected),
        "seed": seed,
        "method": method,
    }
    _write_json(catalogue_path, selected)
    _write_json(report_path, report)

    manifest = {
        "schema_version": "nexttrack-catalogue-sample-v1",
        "catalogue_version": catalogue_version,
        "parent": {
            "catalogue_version": parent_version,
            "file_name": parent_catalogue_path.name,
            "bytes": parent_catalogue_path.stat().st_size,
            "sha256": parent_sha256,
        },
        "selection": {
            "mode": "deterministic_hash_sample",
            "limit": limit,
            "seed": seed,
            "method": method,
        },
        "outputs": {
            catalogue_path.name: {
                "bytes": catalogue_path.stat().st_size,
                "sha256": _sha256(catalogue_path),
            },
            report_path.name: {
                "bytes": report_path.stat().st_size,
                "sha256": _sha256(report_path),
            },
        },
    }
    _write_json(manifest_path, manifest)
    return {
        "catalogue_path": catalogue_path,
        "report_path": report_path,
        "manifest_path": manifest_path,
        "parent_track_count": len(parent_catalogue),
        "selected_track_count": len(selected),
    }


def _read_valid_unique_rows(source_path):
    valid_catalogue = []
    rejected_rows = []
    accepted_by_id = {}
    source_row_count = 0

    with source_path.open(encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)
        source_columns = reader.fieldnames or []
        missing_columns = sorted(set(REQUIRED_SOURCE_COLUMNS) - set(source_columns))
        if missing_columns:
            raise CataloguePreparationError(
                "Source CSV is missing required columns: "
                + ", ".join(missing_columns)
            )

        for row_number, row in enumerate(reader, start=2):
            source_row_count += 1
            validation = validate_source_row(row)
            if validation.reasons:
                rejected_rows.append(
                    {
                        "source_row_number": row_number,
                        "track_id": (row.get("track_id") or "").strip() or None,
                        "reasons": list(validation.reasons),
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
    }


def _write_json(path, value):
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
        output.write("\n")
    temporary_path.replace(path)


def _require_empty_output_directory(output_directory):
    if output_directory.exists() and any(output_directory.iterdir()):
        raise CataloguePreparationError(
            f"Output directory is not empty: {output_directory}. "
            "Use a new catalogue version directory."
        )


def _read_parent_version(parent_catalogue_path, expected_sha256):
    manifest_path = parent_catalogue_path.with_name("manifest.json")
    if not manifest_path.is_file():
        raise CataloguePreparationError(
            f"Parent manifest does not exist: {manifest_path}"
        )
    try:
        with manifest_path.open(encoding="utf-8") as source:
            manifest = json.load(source)
    except (OSError, json.JSONDecodeError) as error:
        raise CataloguePreparationError(
            f"Could not read parent manifest: {error}"
        ) from error

    recorded_sha256 = (
        manifest.get("outputs", {}).get(parent_catalogue_path.name, {}).get("sha256")
    )
    if recorded_sha256 != expected_sha256:
        raise CataloguePreparationError(
            "Parent catalogue checksum does not match its manifest"
        )
    version = str(manifest.get("catalogue_version", "")).strip()
    if not version:
        raise CataloguePreparationError("Parent manifest has no catalogue_version")
    return version


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
