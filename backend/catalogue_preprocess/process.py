## Process full csv from Kaggle
## Extra generate tracks in 20/500 demo version under seed:221611
## write the final catalogue.json, preprocessing-report.json and manifest.json to the output directory

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from recommendations.audio_features import FEATURE_NAMES, NORMALIZATION_RANGES

from .schema import POLICY, REQUIRED_SOURCE_COLUMNS
from .validation import validate_source_row
from .sources import (
    CataloguePreparationError,
    _collect_merged_records,
    _read_valid_unique_rows,
)


## Prepare_catalogue is the main function to process the complete catalogue
def prepare_catalogue(
    source_path,
    output_directory,
    *,
    catalogue_version,
    retrieved_date,
    tracks_source_path=None,
):

    ## Validate input parameters and prepare output directory
    source_path = Path(source_path).resolve()
    output_directory = Path(output_directory).resolve()
    if not source_path.is_file():
        raise CataloguePreparationError(f"Source CSV does not exist: {source_path}")
    if not catalogue_version.strip():
        raise CataloguePreparationError("catalogue_version cannot be empty")
    if not retrieved_date.strip():
        raise CataloguePreparationError("retrieved_date cannot be empty")
    _require_empty_output_directory(output_directory)

    if tracks_source_path is None:
        read_result = _read_valid_unique_rows(
            source_path,
            required_columns=REQUIRED_SOURCE_COLUMNS,
            validate_row=validate_source_row,
        )
        catalogue = sorted(
            read_result["valid_catalogue"],
            key=lambda item: item["id"],
        )
        source_results = {"kaggle": read_result}
        overlap_count = 0
        selection = {
            "mode": "all_valid_unique",
            "method": "all hard-valid unique tracks sorted by track_id",
        }
    else:
        tracks_source_path = Path(tracks_source_path).resolve()
        if tracks_source_path == source_path:
            raise CataloguePreparationError("The two CSV paths must differ")

        bundle = _collect_merged_records(source_path, tracks_source_path)
        catalogue = bundle["catalogue"]
        source_results = {
            "kaggle": bundle["kaggle"],
            "tracks": bundle["tracks"],
        }
        overlap_count = bundle["overlap_count"]
        selection = {
            "mode": "two_source_id_merge",
            "method": "keep Kaggle records on shared track IDs; add new tracks.csv IDs",
        }

    output_directory.mkdir(parents=True, exist_ok=True)
    ## final output files: catalogue.json, preprocessing-report.json and manifest.json
    catalogue_path = output_directory / "catalogue.json"
    report_path = output_directory / "preprocessing-report.json"
    manifest_path = output_directory / "manifest.json"

    source_row_count = sum(result["source_row_count"] for result in source_results.values())
    rejected_count = sum(result["rejected_count"] for result in source_results.values())
    reason_names = {
        name
        for result in source_results.values()
        for name in result["rejection_counts"]
    }
    if tracks_source_path is None:
        rejection_examples = source_results["kaggle"]["rejected_rows"]
    else:
        rejection_examples = [
            {"source": source_name, **example}
            for source_name, result in source_results.items()
            for example in result["rejected_rows"]
        ][:100]
    report = {
        "source_row_count": source_row_count,
        "hard_valid_unique_count": len(catalogue),
        "rejected_row_count": rejected_count,
        "selected_track_count": len(catalogue),
        "cross_source_overlap_count": overlap_count,
        "selection": selection,
        "rejection_reason_counts": {
            name: sum(
                result["rejection_counts"].get(name, 0)
                for result in source_results.values()
            )
            for name in sorted(reason_names)
        },
        "rejection_examples": rejection_examples,
        "rejection_examples_truncated": rejected_count > len(rejection_examples),
        "source_report": {
            name: {
                "source_row_count": result["source_row_count"],
                "valid_unique_count": len(result["valid_catalogue"]),
                "rejected_row_count": result["rejected_count"],
                "rejection_reason_counts": dict(
                    sorted(result["rejection_counts"].items())
                ),
                "rejection_examples": result["rejected_rows"],
            }
            for name, result in source_results.items()
        },
    }
    _write_json(catalogue_path, catalogue)
    _write_json(report_path, report)

    manifest = {
        "schema_version": (
            "nexttrack-catalogue-v2"
            if tracks_source_path is None
            else "nexttrack-catalogue-merged-v1"
        ),
        "catalogue_version": catalogue_version,
        "retrieved_date": retrieved_date,
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
    source_paths = {"kaggle": source_path}
    if tracks_source_path is not None:
        source_paths["tracks"] = tracks_source_path
    source_descriptors = {
        name: {
            "file_name": path.name,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for name, path in source_paths.items()
    }
    if tracks_source_path is None:
        manifest["source"] = source_descriptors["kaggle"]
    else:
        manifest["sources"] = source_descriptors
        manifest["preprocessing"]["cross_source_overlap_policy"] = (
            "keep Kaggle record unchanged for shared track IDs"
        )
    _write_json(manifest_path, manifest)
    return {
        "catalogue_path": catalogue_path,
        "report_path": report_path,
        "manifest_path": manifest_path,
        "source_row_count": source_row_count,
        "valid_unique_count": len(catalogue),
        "rejected_row_count": rejected_count,
        "selected_track_count": len(catalogue),
    }


## Check through any loss or duplicate ID in the processed csv.
## This function was used to generate offline testcase dataset.
## By entering the same seed, the same catalogue can be generated for testing.
## 20/500 demo would be generated by using seed 221611
def sample_catalogue(
    parent_catalogue_path,
    output_directory,
    *,
    catalogue_version,
    limit,
    seed,
):
    # Create a deterministic test catalogue from one frozen full catalogue.

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


## write a .tmp json file first, then rename it to the final output file to avoid partial writes.
def _write_json(path, value):
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
        output.write("\n")
    temporary_path.replace(path)


## Prevent ovewriting existing file
def _require_empty_output_directory(output_directory):
    if output_directory.exists() and any(output_directory.iterdir()):
        raise CataloguePreparationError(
            f"Output directory is not empty: {output_directory}. "
            "Use a new catalogue version directory."
        )


## Read the version of the parent catalogue
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


## This function used to calculate the SHA-256 as a checksum for the source CSV
## Avoiding the changes of the CSV file during processing, ensure the version of the dataset
def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
