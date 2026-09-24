"""Build deterministic inputs from the active catalogue database."""

from __future__ import annotations

import hashlib
import heapq
from dataclasses import dataclass

from recommendations.audio_features import FEATURE_NAMES, normalize_feature
from recommendations.domain.algorithm_config import (
    DEFAULT_ALGORITHM_CONFIG,
    PANDA_2021_MER_MOOD_FEATURE_WEIGHTS,
)
from recommendations.domain.mood_model import MOOD_PROFILES
from recommendations.models import CatalogueState, Track

from .config import EvaluationConfig, SCHEMA_VERSION


class ProtocolError(ValueError):
    """Raised when the active database cannot support a valid experiment."""


@dataclass(frozen=True)
class TrackSnapshot:
    """The catalogue fields required by audits, metrics, and scenario selection."""

    track_id: str
    artist_identity: str | None
    raw_features: tuple[float, ...] | None
    normalized_features: tuple[float, ...] | None

    @property
    def artist_key(self) -> str | None:
        return self.artist_identity.casefold() if self.artist_identity else None

    @property
    def vector(self) -> dict[str, float] | None:
        if self.normalized_features is None:
            return None
        return dict(zip(FEATURE_NAMES, self.normalized_features, strict=True))

    def raw_feature(self, feature_name: str) -> float:
        if self.raw_features is None:
            raise ProtocolError(f"Track {self.track_id} has no complete feature row.")
        return self.raw_features[FEATURE_NAMES.index(feature_name)]

    def mood_fit(self, mood: str) -> float:
        if self.normalized_features is None:
            raise ProtocolError(f"Track {self.track_id} has no complete feature row.")
        targets = MOOD_PROFILES[mood]
        total_weight = sum(
            PANDA_2021_MER_MOOD_FEATURE_WEIGHTS[name] for name in targets
        )
        return sum(
            PANDA_2021_MER_MOOD_FEATURE_WEIGHTS[name]
            * (
                1.0
                - abs(
                    self.normalized_features[FEATURE_NAMES.index(name)] - target
                )
            )
            for name, target in targets.items()
        ) / total_weight


@dataclass
class ExperimentContext:
    config: EvaluationConfig
    catalogue_state: dict
    tracks: tuple[TrackSnapshot, ...]
    selected_tracks: dict[str, TrackSnapshot]
    candidate_ids: list[str]
    scenarios: list[dict]

    def protocol_document(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "catalogue": self.catalogue_state,
            "evaluation_config": self.config.to_dict(),
            "candidate_pool": {
                "selection": "lowest SHA256(seed:track_id), excluding history tracks",
                "track_count": len(self.candidate_ids),
                "track_ids": self.candidate_ids,
            },
            "scenarios": self.scenarios,
            "algorithm_config": DEFAULT_ALGORITHM_CONFIG.to_dict(),
            "metric_scope": "Diagnostic proxies without human relevance labels.",
        }


def _load_tracks() -> tuple[TrackSnapshot, ...]:
    feature_fields = [f"features__{name}" for name in FEATURE_NAMES]
    rows = (
        Track.objects.order_by()
        .values(
            "id",
            "artist",
            "artist_display",
            "primary_artist_id",
            *feature_fields,
        )
        .iterator(chunk_size=2000)
    )
    snapshots = []
    for row in rows:
        values = [row[name] for name in feature_fields]
        has_features = all(value is not None for value in values)
        raw_features = tuple(float(value) for value in values) if has_features else None
        normalized_features = (
            tuple(
                normalize_feature(name, value)
                for name, value in zip(FEATURE_NAMES, raw_features, strict=True)
            )
            if raw_features is not None
            else None
        )
        artist_identity = (
            f"artist:{row['primary_artist_id']}"
            if row["primary_artist_id"] is not None
            else row["artist_display"] or row["artist"] or None
        )
        snapshots.append(
            TrackSnapshot(
                track_id=row["id"],
                artist_identity=artist_identity,
                raw_features=raw_features,
                normalized_features=normalized_features,
            )
        )
    return tuple(snapshots)


def _select_mood_histories(tracks: list[TrackSnapshot]) -> dict[str, list[str]]:
    """Choose five high-fit tracks per mood with distinct primary artists."""

    histories = {}
    globally_used = set()
    for mood in MOOD_PROFILES:
        ranked = heapq.nsmallest(
            250,
            tracks,
            key=lambda track: (
                -track.mood_fit(mood),
                track.track_id,
            ),
        )
        selected = []
        artist_keys = set()
        for track in ranked:
            if (
                track.artist_key is None
                or track.track_id in globally_used
                or track.artist_key in artist_keys
            ):
                continue
            selected.append(track.track_id)
            artist_keys.add(track.artist_key)
            globally_used.add(track.track_id)
            if len(selected) == 5:
                break
        if len(selected) != 5:
            raise ProtocolError(f"Could not select five distinct tracks for mood {mood}.")
        histories[mood] = selected
    return histories


def _build_scenarios(histories: dict[str, list[str]], top_n: int) -> list[dict]:
    scenarios = []
    for mood in MOOD_PROFILES:
        scenarios.append(
            {
                "scenario_id": f"coherent_{mood}",
                "category": "coherent_history",
                "history": histories[mood],
                "mood": mood,
                "top_n": top_n,
            }
        )
    for source, target in (
        ("calm", "energetic"),
        ("energetic", "calm"),
        ("sad", "happy"),
        ("happy", "sad"),
    ):
        scenarios.append(
            {
                "scenario_id": f"transition_{source}_to_{target}",
                "category": "mood_transition",
                "history": histories[source],
                "mood": target,
                "top_n": top_n,
            }
        )
    for mood in MOOD_PROFILES:
        scenarios.append(
            {
                "scenario_id": f"mood_only_{mood}",
                "category": "mood_only",
                "history": [],
                "mood": mood,
                "top_n": top_n,
            }
        )
    return scenarios


def _candidate_pool(
    tracks: list[TrackSnapshot], *, excluded_ids: set[str], seed: int, count: int,
    require_known_artist: bool,
) -> list[str]:
    eligible = (
        track
        for track in tracks
        if track.track_id not in excluded_ids
        and (not require_known_artist or track.artist_key is not None)
    )
    selected = heapq.nsmallest(
        count,
        eligible,
        key=lambda track: hashlib.sha256(
            f"{seed}:{track.track_id}".encode("utf-8")
        ).digest(),
    )
    if len(selected) != count:
        raise ProtocolError(
            f"Requested {count} candidate tracks but only found {len(selected)}."
        )
    return [track.track_id for track in selected]


def build_context(config: EvaluationConfig) -> ExperimentContext:
    """Load the active DB once and derive every deterministic experiment input."""

    state = CatalogueState.objects.filter(pk=1).first()
    if state is None:
        raise ProtocolError("CatalogueState is missing; import a verified catalogue first.")

    tracks = _load_tracks()
    if len(tracks) != state.record_count:
        raise ProtocolError(
            "CatalogueState record_count does not match the active Track table."
        )
    usable = [track for track in tracks if track.normalized_features is not None]
    if len(usable) < config.candidate_count + 20:
        raise ProtocolError("The active catalogue has too few tracks with audio features.")

    histories = _select_mood_histories(usable)
    history_ids = {track_id for values in histories.values() for track_id in values}
    candidate_ids = _candidate_pool(
        usable,
        excluded_ids=history_ids,
        seed=config.seed,
        count=config.candidate_count,
        require_known_artist=config.candidate_artist_policy == "require_known",
    )
    scenarios = _build_scenarios(histories, config.top_n)
    selected_ids = set(candidate_ids) | history_ids
    selected_tracks = {
        track.track_id: track for track in usable if track.track_id in selected_ids
    }
    return ExperimentContext(
        config=config,
        catalogue_state={
            "version": state.version,
            "sha256": state.catalogue_sha256,
            "record_count": state.record_count,
            "database_track_count": len(tracks),
            "usable_feature_count": len(usable),
        },
        tracks=tracks,
        selected_tracks=selected_tracks,
        candidate_ids=candidate_ids,
        scenarios=scenarios,
    )
