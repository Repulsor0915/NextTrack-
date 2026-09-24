"""Audit whether the active catalogue can support the recommender."""

from __future__ import annotations

from collections import Counter
from statistics import mean

from django.db.models import Count, Q

from recommendations.audio_features import FEATURE_NAMES, NORMALIZATION_RANGES
from recommendations.domain.mood_model import MOOD_PROFILES
from recommendations.models import Track, TrackArtist, TrackFeatures

from ..artifacts import StudyResult
from ..protocol import ExperimentContext


def _percentile_from_sorted(values: list[float], fraction: float) -> float:
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def run(context: ExperimentContext) -> StudyResult:
    tracks = context.tracks
    usable = [track for track in tracks if track.raw_features is not None]
    source_counts = Counter(
        dict(
            Track.objects.order_by()
            .values_list("data_source")
            .annotate(track_count=Count("id"))
        )
    )
    distributions = []
    for feature_name in FEATURE_NAMES:
        values = sorted(track.raw_feature(feature_name) for track in usable)
        minimum, maximum = NORMALIZATION_RANGES[feature_name]
        distributions.append(
            {
                "feature": feature_name,
                "minimum": min(values),
                "p05": _percentile_from_sorted(values, 0.05),
                "median": _percentile_from_sorted(values, 0.5),
                "mean": mean(values),
                "p95": _percentile_from_sorted(values, 0.95),
                "maximum": max(values),
                "below_normalization_range": sum(value < minimum for value in values),
                "above_normalization_range": sum(value > maximum for value in values),
            }
        )
    mood_rows = []
    for mood in MOOD_PROFILES:
        fit_total = 0.0
        fit_at_least_0_8 = 0
        fit_at_least_0_9 = 0
        for track in usable:
            value = track.mood_fit(mood)
            fit_total += value
            fit_at_least_0_8 += value >= 0.8
            fit_at_least_0_9 += value >= 0.9
        mood_rows.append(
            {
                "mood": mood,
                "mean_fit": fit_total / len(usable),
                "fit_at_least_0_8": fit_at_least_0_8,
                "fit_at_least_0_9": fit_at_least_0_9,
            }
        )
    multi_artist_track_count = (
        TrackArtist.objects.values("track_id")
        .annotate(artist_count=Count("id"))
        .filter(artist_count__gt=1)
        .count()
    )
    missing_artist_display_count = Track.objects.filter(
        Q(artist_display__isnull=True) | Q(artist_display="")
    ).count()
    warnings = []
    if missing_artist_display_count:
        warnings.append(
            "Artist-based metrics cover only tracks with known artist metadata."
        )
    if len(source_counts) == 1:
        warnings.append(
            "Track.data_source stores the merged catalogue version, so per-input-source analysis is unavailable."
        )
    summary = {
        "catalogue_version": context.catalogue_state["version"],
        "catalogue_sha256": context.catalogue_state["sha256"],
        "state_record_count": context.catalogue_state["record_count"],
        "database_track_count": len(tracks),
        "usable_feature_count": len(usable),
        "missing_feature_count": len(tracks) - len(usable),
        "missing_artist_display_count": missing_artist_display_count,
        "missing_primary_artist_count": Track.objects.filter(
            primary_artist__isnull=True
        ).count(),
        "missing_album_count": Track.objects.filter(album__isnull=True).count(),
        "track_feature_row_count": TrackFeatures.objects.count(),
        "multi_artist_track_count": multi_artist_track_count,
        "source_counts": dict(sorted(source_counts.items())),
        "candidate_pool_count": len(context.candidate_ids),
        "scenario_count": len(context.scenarios),
        "warnings": warnings,
    }
    return StudyResult(
        summary=summary,
        tables={
            "feature-distributions": distributions,
            "mood-coverage": mood_rows,
            "source-counts": [
                {"data_source": source, "track_count": count}
                for source, count in sorted(source_counts.items())
            ],
        },
    )
