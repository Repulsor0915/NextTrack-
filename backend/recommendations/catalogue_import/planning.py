## This file compares a verified snapshot with the current database.
## It creates the import plan, preview summary, and confirmation token.

import hashlib
import json
from dataclasses import dataclass

from django.core.management.base import CommandError

from recommendations.models import CatalogueState, Track, TrackFeatures

from .snapshot import CatalogueSnapshot

LARGE_PRUNE_FRACTION = 0.10


## Save current import plan
@dataclass(frozen=True)
class ImportPlan:
    mode: str
    snapshot: CatalogueSnapshot
    existing_ids: frozenset[str]
    active_version: str | None
    active_sha256: str | None

    @property
    def preview_token(self):
        identity = {
            "mode": self.mode,
            "incoming_sha256": self.snapshot.sha256,
            "active_version": self.active_version,
            "active_sha256": self.active_sha256,
            "existing_ids": sorted(self.existing_ids),
        }
        return hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode("utf-8")
        ).hexdigest()

    @property
    def summary(self):
        incoming = self.snapshot.ids
        existing = self.existing_ids
        deleted = (
            len(existing)
            if self.mode == "replace"
            else len(existing - incoming) if self.mode == "prune" else 0
        )
        return {
            "mode": self.mode,
            "version": self.snapshot.version,
            "catalogue_sha256": self.snapshot.sha256,
            "active_version": self.active_version,
            "current_count": len(existing),
            "incoming_count": len(incoming),
            "created": (
                len(incoming) if self.mode == "replace" else len(incoming - existing)
            ),
            "updated": 0 if self.mode == "replace" else len(incoming & existing),
            "deleted": deleted,
            "delete_fraction": deleted / len(existing) if existing else 0.0,
            "requires_confirmation": bool(
                existing and self.mode in {"replace", "prune"}
            ),
            "preview_token": self.preview_token,
        }


def build_import_plan(snapshot, *, replace=False, prune=False):
    if replace and prune:
        raise CommandError("--replace and --prune are mutually exclusive.")
    existing_ids = frozenset(Track.objects.values_list("id", flat=True))
    state = CatalogueState.objects.filter(pk=1).first()
    mode = (
        "replace"
        if replace
        else "prune" if prune else "initial" if not existing_ids else "reimport"
    )
    plan = ImportPlan(
        mode=mode,
        snapshot=snapshot,
        existing_ids=existing_ids,
        active_version=state.version if state else None,
        active_sha256=state.catalogue_sha256 if state else None,
    )
    _check_existing_state(plan)
    return plan


def _state_identity(state):
    if state is None:
        return None, None
    return state.version, state.catalogue_sha256


def _check_existing_state(plan):
    existing_ids = plan.existing_ids
    state = CatalogueState.objects.filter(pk=1).first()
    if not existing_ids:
        if state is not None:
            raise CommandError("CatalogueState exists but the catalogue is empty.")
        return
    if state is None:
        if plan.mode != "replace":
            raise CommandError(
                "Existing rows have no verified active state; use --replace "
                "in a staged database before switching the active database."
            )
        return
    if plan.mode != "replace":
        if TrackFeatures.objects.count() != len(existing_ids):
            raise CommandError("Track and TrackFeatures counts differ.")
        if state.record_count != len(existing_ids):
            raise CommandError("Active catalogue count does not match Track rows.")
        if set(
            Track.objects.order_by().values_list("data_source", flat=True).distinct()
        ) != {state.version}:
            raise CommandError("Track rows contain mixed catalogue versions.")
        if set(
            TrackFeatures.objects.values_list("feature_source", flat=True).distinct()
        ) != {state.version}:
            raise CommandError("TrackFeatures contain mixed catalogue versions.")
    if plan.mode == "reimport" and (
        state.version != plan.snapshot.version
        or state.catalogue_sha256 != plan.snapshot.sha256
    ):
        raise CommandError(
            "A different snapshot is active; use --replace or --prune "
            "after inspecting --dry-run."
        )
