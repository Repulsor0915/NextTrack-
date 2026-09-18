"""Build reproducible inputs for the NextTrack offline evaluation protocol."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import subprocess
from collections import Counter
from datetime import date
from pathlib import Path

import django

from recommendations.audio_features import (
    FEATURE_NAMES,
    NORMALIZATION_RANGES,
    build_feature_vector,
)
from recommendations.domain.algorithm_config import DEFAULT_ALGORITHM_CONFIG
from recommendations.domain.mood_model import score_mood


EXPERIMENT_CONFIG_SCHEMA_VERSION = "nexttrack-experiment-config-v1"
CANDIDATE_POOL_SCHEMA_VERSION = "nexttrack-candidate-pool-v1"
SCENARIO_SCHEMA_VERSION = "nexttrack-scenarios-v1"
PROTOCOL_MANIFEST_SCHEMA_VERSION = "nexttrack-protocol-manifest-v1"
SCENARIO_GENERATOR_VERSION = "deterministic-scenarios-v1"

DEFAULT_COHERENT_GENRES = ("pop", "rock", "hip-hop")
MOOD_ORDER = ("happy", "energetic", "calm", "sad")
TRANSITION_PAIRS = (
    ("calm", "energetic"),
    ("energetic", "calm"),
    ("sad", "happy"),
    ("happy", "sad"),
)


class ProtocolValidationError(ValueError):
    """Raised when source files cannot produce an auditable protocol."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def write_json(path: Path, value) -> None:
    path.write_bytes(json_bytes(value))


def write_text(path: Path, value: str) -> None:
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def build_candidate_pool(
    candidate_records: list[dict],
    *,
    candidate_catalogue_path: str,
    candidate_catalogue_sha256: str,
    candidate_catalogue_version: str,
    parent_catalogue_path: str,
    parent_catalogue_sha256: str,
    parent_catalogue_version: str,
    selection: dict,
) -> dict:
    track_ids = sorted(record["id"] for record in candidate_records)
    if len(track_ids) != len(set(track_ids)):
        raise ProtocolValidationError("Candidate catalogue contains duplicate IDs.")

    return {
        "schema_version": CANDIDATE_POOL_SCHEMA_VERSION,
        "candidate_pool_id": f"{candidate_catalogue_version}-fixed-pool",
        "track_count": len(track_ids),
        "track_ids": track_ids,
        "ordering": "track_id ascending; ordering does not affect rank scoring",
        "source_candidate_catalogue": {
            "path": candidate_catalogue_path,
            "catalogue_version": candidate_catalogue_version,
            "sha256": candidate_catalogue_sha256,
        },
        "parent_catalogue": {
            "path": parent_catalogue_path,
            "catalogue_version": parent_catalogue_version,
            "sha256": parent_catalogue_sha256,
        },
        "selection": selection,
    }


def generate_scenario_draft(
    catalogue_records: list[dict],
    *,
    candidate_ids: set[str],
    catalogue_version: str,
    catalogue_sha256: str,
    candidate_pool_sha256: str,
    top_n: int,
    coherent_genres: tuple[str, ...] = DEFAULT_COHERENT_GENRES,
) -> dict:
    """Generate deterministic, auditable scenario candidates for human review."""

    eligible_records = [
        record for record in catalogue_records if record["id"] not in candidate_ids
    ]
    _validate_records(eligible_records)

    reserved_ids: set[str] = set()
    reserved_artists: set[str] = set()
    scenarios: list[dict] = []

    for mood in MOOD_ORDER:
        selected = _select_mood_tracks(
            eligible_records,
            mood=mood,
            count=1,
            excluded_ids=reserved_ids,
            excluded_artists=reserved_artists,
        )
        record = selected[0]
        reserved_ids.add(record["id"])
        reserved_artists.add(record["artist"])
        scenarios.append(
            _scenario(
                scenario_id=f"single_{mood}_anchor",
                category="single_track_history",
                description=(
                    f"Single history track selected near the {mood} profile; "
                    "no requested mood is supplied."
                ),
                history_records=[record],
                history_roles=["single_anchor"],
                context={},
                top_n=top_n,
                applicable_algorithms=["random", "cbf", "context_mmr"],
                audit={
                    "selection_method": (
                        f"highest {mood} mood fit outside the candidate pool, "
                        "with globally distinct history artists"
                    ),
                    "anchor_mood": mood,
                },
            )
        )

    for genre in coherent_genres:
        selected = _select_coherent_genre_tracks(
            eligible_records,
            genre=genre,
            count=5,
            excluded_ids=reserved_ids,
            excluded_artists=reserved_artists,
        )
        reserved_ids.update(record["id"] for record in selected)
        reserved_artists.update(record["artist"] for record in selected)

        for history_length in (1, 3, 5):
            # Keep the most centroid-like track as the most recent event while
            # making the 1/3/5 variants nested and directly comparable.
            history_records = list(reversed(selected[:history_length]))
            scenarios.append(
                _scenario(
                    scenario_id=f"coherent_{_slug(genre)}_h{history_length}",
                    category="coherent_multi_track_history",
                    description=(
                        f"{history_length}-track coherent {genre} history with "
                        "distinct artists and no requested mood."
                    ),
                    history_records=history_records,
                    history_roles=["coherent_history"] * history_length,
                    context={},
                    top_n=top_n,
                    applicable_algorithms=["random", "cbf", "context_mmr"],
                    audit={
                        "selection_method": (
                            "closest distinct-artist tracks to the normalized "
                            f"{genre} centroid"
                        ),
                        "genre": genre,
                        "history_length": history_length,
                        "nested_history_family": f"coherent_{_slug(genre)}",
                    },
                )
            )

    for source_mood, target_mood in TRANSITION_PAIRS:
        source_records = _select_mood_tracks(
            eligible_records,
            mood=source_mood,
            count=3,
            excluded_ids=reserved_ids,
            excluded_artists=reserved_artists,
        )
        local_ids = reserved_ids | {record["id"] for record in source_records}
        local_artists = reserved_artists | {
            record["artist"] for record in source_records
        }
        target_records = _select_mood_tracks(
            eligible_records,
            mood=target_mood,
            count=2,
            excluded_ids=local_ids,
            excluded_artists=local_artists,
        )
        source_records = list(reversed(source_records))
        target_records = list(reversed(target_records))
        history_records = source_records + target_records
        reserved_ids.update(record["id"] for record in history_records)
        reserved_artists.update(record["artist"] for record in history_records)

        scenarios.append(
            _scenario(
                scenario_id=f"transition_{source_mood}_to_{target_mood}",
                category="transition_conflicting_history",
                description=(
                    f"Earlier {source_mood} evidence transitions to recent "
                    f"{target_mood} evidence; requested mood is {target_mood}."
                ),
                history_records=history_records,
                history_roles=(
                    ["earlier_source_mood"] * len(source_records)
                    + ["recent_target_mood"] * len(target_records)
                ),
                context={"mood": target_mood},
                top_n=top_n,
                applicable_algorithms=["random", "cbf", "context_mmr"],
                audit={
                    "selection_method": (
                        "three high-fit source-mood tracks followed by two "
                        "high-fit target-mood tracks; all artists distinct"
                    ),
                    "source_mood": source_mood,
                    "requested_mood": target_mood,
                    "expected_recent_direction": target_mood,
                },
            )
        )

    for mood in MOOD_ORDER:
        scenarios.append(
            _scenario(
                scenario_id=f"mood_only_{mood}",
                category="mood_only",
                description=f"No history; recommendation is driven by {mood} mood.",
                history_records=[],
                history_roles=[],
                context={"mood": mood},
                top_n=top_n,
                applicable_algorithms=["random", "context_mmr"],
                audit={
                    "selection_method": "no history selection",
                    "requested_mood": mood,
                },
            )
        )

    scenario_ids = [scenario["scenario_id"] for scenario in scenarios]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ProtocolValidationError("Generated scenario IDs are not unique.")
    for scenario in scenarios:
        scenario["expected_candidate_count"] = len(candidate_ids)

    return {
        "schema_version": SCENARIO_SCHEMA_VERSION,
        "generator_version": SCENARIO_GENERATOR_VERSION,
        "status": "draft_requires_human_review",
        "human_review_required": True,
        "instructions": [
            "Check track title, artist, genre and feature evidence for plausibility.",
            "Reject accidental duplicates, unsuitable metadata or incoherent histories.",
            "Do not rename to scenarios.json until the review is approved.",
        ],
        "source": {
            "catalogue_version": catalogue_version,
            "catalogue_sha256": catalogue_sha256,
            "candidate_pool_sha256": candidate_pool_sha256,
            "history_tracks_are_outside_candidate_pool": True,
        },
        "scenario_count": len(scenarios),
        "category_counts": dict(
            sorted(Counter(scenario["category"] for scenario in scenarios).items())
        ),
        "coherent_genres": list(coherent_genres),
        "scenarios": scenarios,
    }


def build_scenario_review(scenario_draft: dict, *, draft_sha256: str) -> str:
    """Create a compact Markdown checklist for the required human review."""

    scenarios = scenario_draft["scenarios"]
    lines = [
        "# Scenario review checklist",
        "",
        "Status: **awaiting human approval**",
        "",
        f"Draft SHA-256: `{draft_sha256}`",
        "",
        "Approve only after checking that the selected titles, artists, genres,",
        "feature values, history order, and requested moods are plausible.",
        "",
        "## Single-track histories",
        "",
        "| Approve | Scenario | Track | Artist | Genre | Energy | Valence | Acousticness | Tempo |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for scenario in _category(scenarios, "single_track_history"):
        track = scenario["history_tracks"][0]
        lines.append(
            "| [ ] | {scenario} | {title} | {artist} | {genres} | {energy:.3f} | "
            "{valence:.3f} | {acousticness:.3f} | {tempo:.3f} |".format(
                scenario=_markdown(scenario["scenario_id"]),
                title=_markdown(track["title"]),
                artist=_markdown(track["artist"]),
                genres=_markdown(", ".join(track["genres"])),
                energy=track["raw_features"]["energy"],
                valence=track["raw_features"]["valence"],
                acousticness=track["raw_features"]["acousticness"],
                tempo=track["raw_features"]["tempo"],
            )
        )

    lines.extend(
        [
            "",
            "## Coherent history families",
            "",
            "Each H1/H3/H5 family is nested. The table shows the full H5 order",
            "from oldest to newest.",
            "",
            "| Approve family | Family | Ordered H5 tracks | Artists |",
            "| --- | --- | --- | --- |",
        ]
    )
    coherent_h5 = [
        scenario
        for scenario in _category(scenarios, "coherent_multi_track_history")
        if scenario["audit"]["history_length"] == 5
    ]
    for scenario in coherent_h5:
        tracks = scenario["history_tracks"]
        lines.append(
            "| [ ] | {family} | {titles} | {artists} |".format(
                family=_markdown(scenario["audit"]["nested_history_family"]),
                titles=" → ".join(
                    _markdown(track["title"]) for track in tracks
                ),
                artists=" → ".join(
                    _markdown(track["artist"]) for track in tracks
                ),
            )
        )

    lines.extend(
        [
            "",
            "## Transition/conflicting histories",
            "",
            "The first three tracks are older source-mood evidence; the last two",
            "are recent target-mood evidence.",
            "",
            "| Approve | Scenario | Older source tracks | Recent target tracks | Requested mood |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for scenario in _category(scenarios, "transition_conflicting_history"):
        older = [
            track["title"]
            for track in scenario["history_tracks"]
            if track["role"] == "earlier_source_mood"
        ]
        recent = [
            track["title"]
            for track in scenario["history_tracks"]
            if track["role"] == "recent_target_mood"
        ]
        lines.append(
            "| [ ] | {scenario} | {older} | {recent} | {mood} |".format(
                scenario=_markdown(scenario["scenario_id"]),
                older=" → ".join(_markdown(title) for title in older),
                recent=" → ".join(_markdown(title) for title in recent),
                mood=_markdown(scenario["request_template"]["context"]["mood"]),
            )
        )

    lines.extend(
        [
            "",
            "## Mood-only controls",
            "",
            "| Approve | Scenario | Requested mood | Applicable algorithms |",
            "| --- | --- | --- | --- |",
        ]
    )
    for scenario in _category(scenarios, "mood_only"):
        lines.append(
            "| [ ] | {scenario} | {mood} | {algorithms} |".format(
                scenario=_markdown(scenario["scenario_id"]),
                mood=_markdown(scenario["request_template"]["context"]["mood"]),
                algorithms=", ".join(scenario["applicable_algorithms"]),
            )
        )

    lines.extend(
        [
            "",
            "## Approval decision",
            "",
            "- [ ] Approve all scenarios as written.",
            "- [ ] Request replacements listed below.",
            "",
            "Replacement requests:",
            "",
            "- Scenario ID:",
            "- Track(s) to replace:",
            "- Reason:",
            "",
            "Do not run or freeze the evaluation while any checkbox decision is",
            "unresolved.",
        ]
    )
    return "\n".join(lines)


def prepare_protocol(
    *,
    project_root: Path,
    full_catalogue_path: Path,
    full_manifest_path: Path,
    candidate_catalogue_path: Path,
    candidate_manifest_path: Path,
    output_directory: Path,
    protocol_date: str,
    seed: int,
    top_n: int,
    random_repetitions: int,
    expected_candidate_count: int,
    coherent_genres: tuple[str, ...] = DEFAULT_COHERENT_GENRES,
    force: bool = False,
) -> dict:
    """Create experiment config, fixed pool and reviewable scenario draft."""

    date.fromisoformat(protocol_date)
    if not 1 <= top_n <= 10:
        raise ProtocolValidationError("top_n must be between 1 and 10.")
    if random_repetitions < 1:
        raise ProtocolValidationError("random_repetitions must be at least 1.")
    if expected_candidate_count < top_n:
        raise ProtocolValidationError(
            "expected_candidate_count must be at least top_n."
        )
    if len(coherent_genres) < 1:
        raise ProtocolValidationError("At least one coherent genre is required.")

    project_root = project_root.resolve()
    paths = {
        "experiment_config": output_directory / "experiment-config.json",
        "candidate_pool": output_directory / "candidate-pool.json",
        "scenario_draft": output_directory / "scenarios.draft.json",
        "scenario_review": output_directory / "scenario-review.md",
        "protocol_manifest": output_directory / "protocol-manifest.json",
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not force:
        raise ProtocolValidationError(
            "Refusing to overwrite protocol files without force: "
            + ", ".join(str(path) for path in existing)
        )
    output_directory.mkdir(parents=True, exist_ok=True)

    full_manifest = load_json(full_manifest_path)
    candidate_manifest = load_json(candidate_manifest_path)
    full_sha256 = sha256_file(full_catalogue_path)
    candidate_sha256 = sha256_file(candidate_catalogue_path)
    _verify_manifest_hash(full_manifest, full_catalogue_path, full_sha256)
    _verify_manifest_hash(
        candidate_manifest,
        candidate_catalogue_path,
        candidate_sha256,
    )

    expected_parent_sha = candidate_manifest.get("parent", {}).get("sha256")
    if expected_parent_sha != full_sha256:
        raise ProtocolValidationError(
            "Candidate catalogue parent checksum does not match full catalogue."
        )
    selection = candidate_manifest.get("selection", {})
    if selection.get("seed") != seed:
        raise ProtocolValidationError(
            "Candidate catalogue seed does not match the protocol seed."
        )

    full_records = load_json(full_catalogue_path)
    candidate_records = load_json(candidate_catalogue_path)
    _validate_records(full_records)
    _validate_records(candidate_records)
    if len(candidate_records) != expected_candidate_count:
        raise ProtocolValidationError(
            "Candidate catalogue track count does not match the expected count: "
            f"{len(candidate_records)} != {expected_candidate_count}."
        )

    full_ids = {record["id"] for record in full_records}
    candidate_ids = {record["id"] for record in candidate_records}
    if not candidate_ids.issubset(full_ids):
        raise ProtocolValidationError(
            "Candidate catalogue contains IDs absent from the full catalogue."
        )

    full_version = full_manifest["catalogue_version"]
    candidate_version = candidate_manifest["catalogue_version"]
    candidate_pool = build_candidate_pool(
        candidate_records,
        candidate_catalogue_path=_relative_path(
            candidate_catalogue_path,
            project_root,
        ),
        candidate_catalogue_sha256=candidate_sha256,
        candidate_catalogue_version=candidate_version,
        parent_catalogue_path=_relative_path(full_catalogue_path, project_root),
        parent_catalogue_sha256=full_sha256,
        parent_catalogue_version=full_version,
        selection=selection,
    )
    write_json(paths["candidate_pool"], candidate_pool)
    candidate_pool_sha256 = sha256_file(paths["candidate_pool"])

    scenario_draft = generate_scenario_draft(
        full_records,
        candidate_ids=candidate_ids,
        catalogue_version=full_version,
        catalogue_sha256=full_sha256,
        candidate_pool_sha256=candidate_pool_sha256,
        top_n=top_n,
        coherent_genres=coherent_genres,
    )
    write_json(paths["scenario_draft"], scenario_draft)
    scenario_draft_sha256 = sha256_file(paths["scenario_draft"])
    write_text(
        paths["scenario_review"],
        build_scenario_review(
            scenario_draft,
            draft_sha256=scenario_draft_sha256,
        ),
    )

    scenario_counts_by_algorithm = {
        algorithm: sum(
            algorithm in scenario["applicable_algorithms"]
            for scenario in scenario_draft["scenarios"]
        )
        for algorithm in ("random", "cbf", "context_mmr")
    }
    repetitions = {
        "random": random_repetitions,
        "cbf": 1,
        "context_mmr": 1,
    }
    expected_run_count = sum(
        scenario_counts_by_algorithm[algorithm] * repetitions[algorithm]
        for algorithm in repetitions
    )

    experiment_config = {
        "schema_version": EXPERIMENT_CONFIG_SCHEMA_VERSION,
        "experiment_id": "nexttrack-offline-baseline-v1",
        "protocol_status": "awaiting_human_scenario_review",
        "protocol_date": protocol_date,
        "catalogue": {
            "path": _relative_path(full_catalogue_path, project_root),
            "catalogue_version": full_version,
            "sha256": full_sha256,
            "track_count": len(full_records),
        },
        "candidate_pool": {
            "path": _relative_path(paths["candidate_pool"], project_root),
            "sha256": candidate_pool_sha256,
            "track_count": len(candidate_ids),
            "source_catalogue_sha256": candidate_sha256,
        },
        "scenarios": {
            "path": _relative_path(paths["scenario_draft"], project_root),
            "sha256": scenario_draft_sha256,
            "status": "draft_requires_human_review",
            "scenario_count": scenario_draft["scenario_count"],
            "category_counts": scenario_draft["category_counts"],
            "review_path": _relative_path(paths["scenario_review"], project_root),
        },
        "randomness": {
            "master_seed": seed,
            "candidate_pool_seed": selection["seed"],
            "random_baseline_seeds": list(
                range(seed, seed + random_repetitions)
            ),
        },
        "ranking": {
            "top_n": top_n,
            "history_max_length": DEFAULT_ALGORITHM_CONFIG.history_window_size,
            "candidate_pool_policy": "same fixed pool for every scenario",
            "history_candidate_overlap_policy": "history IDs must be outside pool",
            "bpm_filter": None,
        },
        "normalization": {
            feature_name: {
                "minimum": NORMALIZATION_RANGES[feature_name][0],
                "maximum": NORMALIZATION_RANGES[feature_name][1],
                "outlier_policy": "clamp to [0, 1]",
            }
            for feature_name in FEATURE_NAMES
        },
        "algorithms": {
            "modes": ["random", "cbf", "context_mmr"],
            "algorithm_config": DEFAULT_ALGORITHM_CONFIG.to_dict(),
            "repetitions": repetitions,
            "eligible_scenario_counts": scenario_counts_by_algorithm,
            "expected_baseline_run_count": expected_run_count,
        },
        "environment": {
            "python": platform.python_version(),
            "django": django.get_version(),
            "operating_system": platform.platform(),
            "database_engine": "SQLite",
            "algorithm_git_commit": _git_head(project_root),
        },
        "planned_outputs": {
            "recommendation_runs": "evaluation/results/recommendation-runs.json",
            "summary_json": "evaluation/results/summary.json",
            "summary_csv": "evaluation/results/summary.csv",
            "manifest": "evaluation/results/manifest.json",
        },
    }
    write_json(paths["experiment_config"], experiment_config)

    protocol_manifest = {
        "schema_version": PROTOCOL_MANIFEST_SCHEMA_VERSION,
        "protocol_status": "awaiting_human_scenario_review",
        "outputs": {
            path.name: {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in (
                paths["experiment_config"],
                paths["candidate_pool"],
                paths["scenario_draft"],
                paths["scenario_review"],
            )
        },
    }
    write_json(paths["protocol_manifest"], protocol_manifest)

    return {
        "paths": {key: str(value) for key, value in paths.items()},
        "candidate_count": len(candidate_ids),
        "scenario_count": scenario_draft["scenario_count"],
        "category_counts": scenario_draft["category_counts"],
        "expected_baseline_run_count": expected_run_count,
    }


def _scenario(
    *,
    scenario_id: str,
    category: str,
    description: str,
    history_records: list[dict],
    history_roles: list[str],
    context: dict,
    top_n: int,
    applicable_algorithms: list[str],
    audit: dict,
) -> dict:
    if len(history_records) != len(history_roles):
        raise ProtocolValidationError("History records and roles do not align.")

    return {
        "scenario_id": scenario_id,
        "category": category,
        "description": description,
        "applicable_algorithms": applicable_algorithms,
        "request_template": {
            "history": [record["id"] for record in history_records],
            "limit": top_n,
            "context": context,
        },
        "expected_candidate_count": None,
        "history_tracks": [
            _track_snapshot(record, position=index, role=role)
            for index, (record, role) in enumerate(
                zip(history_records, history_roles, strict=True),
                start=1,
            )
        ],
        "audit": audit,
    }


def _track_snapshot(record: dict, *, position: int, role: str) -> dict:
    vector = build_feature_vector(record["features"])
    return {
        "position": position,
        "role": role,
        "id": record["id"],
        "title": record["title"],
        "artist": record["artist"],
        "genres": record["genres"],
        "raw_features": {
            feature_name: record["features"][feature_name]
            for feature_name in FEATURE_NAMES
        },
        "normalized_features": {
            feature_name: round(vector[feature_name], 6)
            for feature_name in FEATURE_NAMES
        },
        "mood_fit": {
            mood: round(score_mood(vector, mood).fit, 6)
            for mood in MOOD_ORDER
        },
    }


def _select_mood_tracks(
    records: list[dict],
    *,
    mood: str,
    count: int,
    excluded_ids: set[str],
    excluded_artists: set[str],
) -> list[dict]:
    ranked = sorted(
        records,
        key=lambda record: (
            -score_mood(build_feature_vector(record["features"]), mood).fit,
            record["id"],
        ),
    )
    return _take_distinct_artists(
        ranked,
        count=count,
        excluded_ids=excluded_ids,
        excluded_artists=excluded_artists,
        purpose=f"{mood} mood selection",
    )


def _select_coherent_genre_tracks(
    records: list[dict],
    *,
    genre: str,
    count: int,
    excluded_ids: set[str],
    excluded_artists: set[str],
) -> list[dict]:
    genre_records = [record for record in records if genre in record["genres"]]
    if not genre_records:
        raise ProtocolValidationError(f'No tracks found for coherent genre "{genre}".')

    vectors = [build_feature_vector(record["features"]) for record in genre_records]
    centroid = {
        feature_name: sum(vector[feature_name] for vector in vectors) / len(vectors)
        for feature_name in FEATURE_NAMES
    }

    def distance(record):
        vector = build_feature_vector(record["features"])
        return math.sqrt(
            sum(
                (vector[feature_name] - centroid[feature_name]) ** 2
                for feature_name in FEATURE_NAMES
            )
            / len(FEATURE_NAMES)
        )

    ranked = sorted(genre_records, key=lambda record: (distance(record), record["id"]))
    return _take_distinct_artists(
        ranked,
        count=count,
        excluded_ids=excluded_ids,
        excluded_artists=excluded_artists,
        purpose=f'coherent genre "{genre}"',
    )


def _take_distinct_artists(
    ranked_records: list[dict],
    *,
    count: int,
    excluded_ids: set[str],
    excluded_artists: set[str],
    purpose: str,
) -> list[dict]:
    selected: list[dict] = []
    selected_artists = set(excluded_artists)
    for record in ranked_records:
        if record["id"] in excluded_ids or record["artist"] in selected_artists:
            continue
        selected.append(record)
        selected_artists.add(record["artist"])
        if len(selected) == count:
            return selected
    raise ProtocolValidationError(
        f"Could not select {count} distinct-artist tracks for {purpose}."
    )


def _validate_records(records: list[dict]) -> None:
    if not isinstance(records, list) or not records:
        raise ProtocolValidationError("Catalogue must be a non-empty JSON list.")
    ids: set[str] = set()
    for index, record in enumerate(records):
        required = {"id", "title", "artist", "genres", "features"}
        missing = required - set(record)
        if missing:
            raise ProtocolValidationError(
                f"Catalogue record {index} is missing {sorted(missing)}."
            )
        if record["id"] in ids:
            raise ProtocolValidationError(
                f'Duplicate catalogue ID: {record["id"]!r}.'
            )
        ids.add(record["id"])
        feature_names = set(record["features"])
        if not set(FEATURE_NAMES).issubset(feature_names):
            raise ProtocolValidationError(
                f'Catalogue record {record["id"]!r} lacks required features.'
            )


def _verify_manifest_hash(manifest: dict, catalogue_path: Path, actual_hash: str):
    expected_hash = manifest.get("outputs", {}).get(catalogue_path.name, {}).get(
        "sha256"
    )
    if expected_hash != actual_hash:
        raise ProtocolValidationError(
            f"Manifest checksum mismatch for {catalogue_path}: "
            f"expected {expected_hash!r}, calculated {actual_hash!r}."
        )


def _relative_path(path: Path, project_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(project_root).as_posix()
    except ValueError:
        return str(resolved)


def _git_head(project_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _slug(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_")


def _category(scenarios: list[dict], category: str) -> list[dict]:
    return [scenario for scenario in scenarios if scenario["category"] == category]


def _markdown(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
