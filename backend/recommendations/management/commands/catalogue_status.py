## Read-only status for the single active catalogue.

import json

from django.core.management.base import BaseCommand

from recommendations.models import CatalogueState, Track, TrackFeatures


class Command(BaseCommand):
    help = "Show active catalogue metadata and database row counts."

    def handle(self, *args, **options):
        state = CatalogueState.objects.filter(pk=1).first()
        track_count = Track.objects.count()
        feature_count = TrackFeatures.objects.count()
        versions = sorted(
            Track.objects.order_by().values_list("data_source", flat=True).distinct()
        )
        result = {
            "active_version": state.version if state else None,
            "catalogue_sha256": state.catalogue_sha256 if state else None,
            "record_count": state.record_count if state else None,
            "imported_at": state.imported_at.isoformat() if state else None,
            "import_mode": state.import_mode if state else None,
            "track_count": track_count,
            "feature_count": feature_count,
            "track_data_sources": versions,
            "state_consistent": bool(
                state
                and state.record_count == track_count == feature_count
                and versions == [state.version]
            ),
        }
        self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
