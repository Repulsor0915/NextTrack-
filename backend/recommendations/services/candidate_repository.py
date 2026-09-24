"""Database access used by the recommendation service."""

from collections import namedtuple

from recommendations.audio_features import FEATURE_NAMES
from recommendations.models import CatalogueState, Track

from .errors import MissingTrackFeaturesError, UnknownTrackIdsError


CandidateFeatures = namedtuple("CandidateFeatures", FEATURE_NAMES)


class CandidateTrack:
    __slots__ = ("id", "features", "title", "artist")

    def __init__(self, track_id, features):
        self.id = track_id
        self.features = features
        self.title = None
        self.artist = None


class CandidateRepository:
    @staticmethod
    def validate_track_ids(history, candidate_ids):
        supplied_ids = set(history)
        if candidate_ids is not None:
            supplied_ids.update(candidate_ids)

        if not supplied_ids:
            return

        known_ids = set(
            Track.objects.filter(id__in=supplied_ids).values_list("id", flat=True)
        )
        unknown_ids = sorted(supplied_ids - known_ids)
        if unknown_ids:
            raise UnknownTrackIdsError(
                "One or more track identifiers were not found.",
                details={"ids": unknown_ids},
            )

    @staticmethod
    def candidate_queryset(*, history, candidate_ids, context):
        queryset = Track.objects.filter(features__isnull=False)

        if candidate_ids is not None:
            queryset = queryset.filter(id__in=set(candidate_ids))
        if history:
            queryset = queryset.exclude(id__in=set(history))

        bpm_range = context.get("bpm")
        if bpm_range:
            queryset = queryset.filter(
                features__tempo__gte=bpm_range["min"],
                features__tempo__lte=bpm_range["max"],
            )

        return queryset

    @classmethod
    def get_candidates(cls, *, history, candidate_ids, context):
        queryset = cls.candidate_queryset(
            history=history,
            candidate_ids=candidate_ids,
            context=context,
        )

        feature_fields = tuple(f"features__{name}" for name in FEATURE_NAMES)
        rows = queryset.values_list("id", *feature_fields).iterator(chunk_size=2000)
        return [
            CandidateTrack(row[0], CandidateFeatures(*row[1:]))
            for row in rows
        ]

    @staticmethod
    def attach_selected_metadata(selected_tracks):
        if not selected_tracks:
            return
        metadata = {
            track_id: (title, artist)
            for track_id, title, artist in Track.objects.filter(
                id__in={track.id for track in selected_tracks}
            ).values_list("id", "title", "artist")
        }
        for track in selected_tracks:
            track.title, track.artist = metadata[track.id]

    @staticmethod
    def get_history_tracks(history):
        tracks = Track.objects.select_related("features").filter(id__in=set(history))
        track_map = {track.id: track for track in tracks}
        missing_feature_ids = sorted(
            track_id
            for track_id, track in track_map.items()
            if not hasattr(track, "features")
        )
        if missing_feature_ids:
            raise MissingTrackFeaturesError(
                "One or more history tracks do not have usable audio features.",
                details={"ids": missing_feature_ids},
            )

        return [track_map[track_id] for track_id in history]

    @staticmethod
    def get_active_catalogue():
        return CatalogueState.objects.filter(pk=1).first()

    @classmethod
    def catalogue_version(cls, *, history, candidate_ids, context):
        sources = sorted(
            cls.candidate_queryset(
                history=history,
                candidate_ids=candidate_ids,
                context=context,
            ).order_by().values_list("data_source", flat=True).distinct()
        )
        if len(sources) == 1:
            return sources[0]
        return "mixed:" + ",".join(sources)
