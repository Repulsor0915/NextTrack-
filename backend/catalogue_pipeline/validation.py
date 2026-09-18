"""Row-level validation without recommendation or content-policy decisions."""

import math
from dataclasses import dataclass

from recommendations.audio_features import FEATURE_NAMES

from .schema import (
    POLICY,
    REQUIRED_NON_EMPTY_COLUMNS,
    SOURCE_COLUMNS,
    TEXT_LIMITS,
    UNIT_INTERVAL_FEATURES,
)


@dataclass(frozen=True)
class RowValidation:
    record: dict | None
    reasons: tuple[str, ...]


def validate_source_row(row, *, policy=POLICY):
    """Validate and convert one CSV row into the catalogue contract."""

    reasons = []
    for column_name in REQUIRED_NON_EMPTY_COLUMNS:
        if _is_missing(row.get(column_name)):
            reasons.append(f"missing_{column_name}")

    for column_name, maximum_length in TEXT_LIMITS.items():
        value = _text(row.get(column_name))
        if len(value) > maximum_length:
            reasons.append(f"too_long_{column_name}")

    genre = _text(row.get(SOURCE_COLUMNS["genre"]))
    if not policy.allow_blank_genre and not genre:
        reasons.append(f'missing_{SOURCE_COLUMNS["genre"]}')

    explicit = None
    explicit_text = _text(row.get(SOURCE_COLUMNS["explicit"])).lower()
    if explicit_text:
        if policy.require_boolean_explicit and explicit_text not in {"true", "false"}:
            reasons.append("invalid_explicit")
        elif explicit_text in {"true", "false"}:
            explicit = explicit_text == "true"

    features = {}
    for feature_name in FEATURE_NAMES:
        raw_value = row.get(feature_name)
        if _is_missing(raw_value):
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            reasons.append(f"non_numeric_{feature_name}")
            continue

        if not math.isfinite(value):
            reasons.append(f"non_finite_{feature_name}")
        elif feature_name in UNIT_INTERVAL_FEATURES and not 0.0 <= value <= 1.0:
            reasons.append(f"out_of_range_{feature_name}")
        elif (
            feature_name == "tempo"
            and policy.require_positive_tempo
            and value <= 0.0
        ):
            reasons.append("out_of_range_tempo")
        else:
            features[feature_name] = value

    unique_reasons = tuple(sorted(set(reasons)))
    if unique_reasons:
        return RowValidation(record=None, reasons=unique_reasons)

    return RowValidation(
        record={
            "id": _text(row[SOURCE_COLUMNS["id"]]),
            "title": _text(row[SOURCE_COLUMNS["title"]]),
            "artist": _text(row[SOURCE_COLUMNS["artist"]]),
            "genres": [genre] if genre else [],
            "explicit": explicit,
            "year": None,
            "features": {
                feature_name: features[feature_name]
                for feature_name in FEATURE_NAMES
            },
        },
        reasons=(),
    )


def _is_missing(value):
    return value is None or not str(value).strip()


def _text(value):
    return "" if value is None else str(value).strip()
