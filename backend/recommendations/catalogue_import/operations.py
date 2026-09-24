## This file applies a verified import plan as one database transaction.
## It handles confirmation, replace or prune operations, cleanup, and catalogue state.

from django.core.management.base import CommandError
from django.db import transaction

from recommendations.audio_features import FEATURE_NAMES
from recommendations.models import (
    Album,
    Artist,
    CatalogueState,
    Track,
    TrackFeatures,
)

from .planning import (
    LARGE_PRUNE_FRACTION,
    _check_existing_state,
    _state_identity,
)
from .writer import BATCH_SIZE, _batches, _write_batches


def apply_import_plan(
    plan,
    *,
    confirm_version=None,
    confirm_sha256=None,
    confirm_plan=None,
    allow_large_prune=False,
):
    """Commit an already validated snapshot as one database transaction."""

    _check_existing_state(plan)
    summary = plan.summary
    if plan.existing_ids and plan.mode in {"replace", "prune"}:
        if (
            confirm_version != plan.snapshot.version
            or confirm_sha256 != plan.snapshot.sha256
            or confirm_plan != plan.preview_token
        ):
            raise CommandError(
                "Destructive sync requires --confirm-version and "
                "--confirm-sha256 matching the verified manifest, plus "
                "--confirm-plan from the current --dry-run preview."
            )
    if (
        plan.mode == "prune"
        and plan.existing_ids
        and summary["deleted"] / len(plan.existing_ids) > LARGE_PRUNE_FRACTION
        and not allow_large_prune
    ):
        raise CommandError(
            "Prune would delete more than 10 percent of existing tracks; "
            "inspect --dry-run and explicitly add --allow-large-prune."
        )

    with transaction.atomic():
        locked_state = CatalogueState.objects.select_for_update().filter(pk=1).first()
        if frozenset(
            Track.objects.values_list("id", flat=True)
        ) != plan.existing_ids or _state_identity(locked_state) != (
            plan.active_version,
            plan.active_sha256,
        ):
            raise CommandError("Catalogue changed during preflight; retry import.")

        existing_ids = plan.existing_ids
        if plan.mode == "replace":
            Track.objects.all().delete()
            existing_ids = frozenset()
        _write_batches(plan.snapshot.records, existing_ids, plan.snapshot.version)

        if plan.mode == "prune":
            obsolete_ids = sorted(plan.existing_ids - plan.snapshot.ids)
            for batch in _batches(obsolete_ids):
                Track.objects.filter(pk__in=batch).delete()

        # Removed tracks and changed album/artist links can leave unused rows.
        Album.objects.filter(tracks__isnull=True).delete()
        Artist.objects.filter(
            primary_tracks__isnull=True,
            track_links__isnull=True,
            albums__isnull=True,
        ).delete()

        CatalogueState.objects.update_or_create(
            pk=1,
            defaults={
                "version": plan.snapshot.version,
                "catalogue_sha256": plan.snapshot.sha256,
                "record_count": len(plan.snapshot.records),
                "import_mode": plan.mode,
            },
        )
    return summary


def adopt_existing_snapshot(snapshot):
    """Register legacy rows only when every stored value matches the snapshot."""

    with transaction.atomic():
        if CatalogueState.objects.select_for_update().filter(pk=1).exists():
            raise CommandError("The database already has an active catalogue state.")
        if Track.objects.count() != len(
            snapshot.records
        ) or TrackFeatures.objects.count() != len(snapshot.records):
            raise CommandError("Stored row counts do not match the snapshot.")

        stored = (
            Track.objects.select_related("features")
            .order_by("id")
            .iterator(chunk_size=BATCH_SIZE)
        )
        for expected in sorted(snapshot.records, key=lambda item: item["id"]):
            track = next(stored, None)
            if track is None or track.id != expected["id"]:
                raise CommandError("Stored track IDs do not match the snapshot.")
            if (
                track.title != expected["title"]
                or track.artist != expected["artist"]
                or track.genres != expected.get("genres", [])
                or track.explicit != expected["explicit"]
                or track.year != expected.get("year")
                or track.data_source != snapshot.version
            ):
                raise CommandError(f"Stored track metadata differs: {track.id}.")
            if not hasattr(track, "features"):
                raise CommandError(f"Stored track has no features: {track.id}.")
            features = track.features
            if features.feature_source != snapshot.version or any(
                getattr(features, name) != expected["features"][name]
                for name in FEATURE_NAMES
            ):
                raise CommandError(f"Stored audio features differ: {track.id}.")
        if next(stored, None) is not None:
            raise CommandError("Stored track IDs do not match the snapshot.")

        CatalogueState.objects.create(
            pk=1,
            version=snapshot.version,
            catalogue_sha256=snapshot.sha256,
            record_count=len(snapshot.records),
            import_mode="adopt",
        )
