from time import perf_counter

from recommendations.domain.cbf_ranker import rank_cbf
from recommendations.domain.context_ranker import score_context_candidates
from recommendations.domain.explanations import (
    build_cbf_explanation,
    build_context_explanation,
)
from recommendations.domain.feature_vectors import (
    HISTORY_WINDOW_SIZE,
    build_feature_vector,
    build_recency_weighted_profile,
    build_session_profile,
)
from recommendations.domain.mmr import rerank_mmr
from recommendations.domain.random_ranker import rank_random
from recommendations.models import Track


class RecommendationServiceError(Exception):
    code = "RECOMMENDATION_ERROR"
    status_code = 400

    def __init__(self, message, *, details=None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def as_dict(self):
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class UnknownTrackIdsError(RecommendationServiceError):
    code = "UNKNOWN_TRACK_ID"


class NoCandidatesError(RecommendationServiceError):
    code = "NO_CANDIDATES"
    status_code = 422


class UnsupportedAlgorithmError(RecommendationServiceError):
    code = "UNSUPPORTED_ALGORITHM"


class MissingTrackFeaturesError(RecommendationServiceError):
    code = "MISSING_TRACK_FEATURES"
    status_code = 422


class RecommendationService:
    def __init__(self, *, random_source=None):
        self.random_source = random_source

    def recommend(self, request_data):
        started_at = perf_counter()
        algorithm = request_data["algorithm"]

        if algorithm not in {"random", "cbf", "context_mmr"}:
            raise UnsupportedAlgorithmError(
                f'Algorithm "{algorithm}" has not been implemented yet.',
                details={"algorithm": algorithm},
            )

        history = request_data["history"]
        candidate_ids = request_data.get("candidate_ids")
        self._validate_track_ids(history, candidate_ids)

        candidates = self._get_candidates(
            history=history,
            candidate_ids=candidate_ids,
            context=request_data.get("context", {}),
        )
        if not candidates:
            raise NoCandidatesError(
                "No unplayed tracks satisfy the requested candidate constraints."
            )

        meta = {
            "catalogue_version": self._catalogue_version(candidates),
            "candidate_count": len(candidates),
        }

        if algorithm == "random":
            selected_tracks = rank_random(
                candidates,
                request_data["limit"],
                random_source=self.random_source,
            )
            recommendations = [
                self._build_random_result(track, rank)
                for rank, track in enumerate(selected_tracks, start=1)
            ]
        elif algorithm == "cbf":
            history_tracks = self._get_history_tracks(history)
            history_vectors = [
                build_feature_vector(track.features) for track in history_tracks
            ]
            session_profile = build_session_profile(history_vectors)
            candidate_vectors = [
                (track, build_feature_vector(track.features)) for track in candidates
            ]
            ranked_candidates = rank_cbf(
                candidate_vectors,
                session_profile,
                request_data["limit"],
            )
            recommendations = [
                self._build_cbf_result(result, rank)
                for rank, result in enumerate(ranked_candidates, start=1)
            ]
            meta["history_count_used"] = min(
                len(history_tracks), HISTORY_WINDOW_SIZE
            )
            meta["history_window_size"] = HISTORY_WINDOW_SIZE
        else:
            context = request_data.get("context", {})
            mood = context.get("mood")
            exploration = context.get("exploration", 0.2)
            history_tracks = self._get_history_tracks(history) if history else []
            session_profile = None
            if history_tracks:
                history_vectors = [
                    build_feature_vector(track.features) for track in history_tracks
                ]
                session_profile = build_recency_weighted_profile(history_vectors)

            candidate_vectors = [
                (track, build_feature_vector(track.features)) for track in candidates
            ]
            context_rankings = score_context_candidates(
                candidate_vectors,
                session_profile=session_profile,
                mood=mood,
                tempo_constrained=bool(context.get("bpm")),
            )
            reranked_candidates = rerank_mmr(
                context_rankings,
                request_data["limit"],
                exploration=exploration,
            )
            recommendations = [
                self._build_context_result(
                    result,
                    rank,
                    mood=mood,
                    exploration=exploration,
                )
                for rank, result in enumerate(reranked_candidates, start=1)
            ]
            meta.update(
                {
                    "history_count_used": min(
                        len(history_tracks), HISTORY_WINDOW_SIZE
                    ),
                    "history_window_size": HISTORY_WINDOW_SIZE,
                    "mood": mood,
                    "exploration": exploration,
                }
            )

        elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
        meta["returned_count"] = len(recommendations)
        meta["processing_ms"] = elapsed_ms

        return {
            "algorithm": algorithm,
            "recommendations": recommendations,
            "meta": meta,
        }

    @staticmethod
    def _validate_track_ids(history, candidate_ids):
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
    def _get_candidates(*, history, candidate_ids, context):
        queryset = Track.objects.select_related("features").filter(
            features__isnull=False
        )

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

        return list(queryset)

    @staticmethod
    def _get_history_tracks(history):
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
    def _build_random_result(track, rank):
        return {
            "rank": rank,
            "track": {
                "id": track.id,
                "title": track.title,
                "artist": track.artist,
            },
            "score": None,
            "components": {},
            "explanation": {
                "summary": "Selected randomly from the eligible unplayed tracks.",
                "evidence": ["random baseline selection"],
            },
        }

    @staticmethod
    def _build_cbf_result(result, rank):
        rounded_closeness = {
            feature_name: round(value, 4)
            for feature_name, value in result.feature_closeness.items()
        }
        rounded_score = round(result.score, 4)

        return {
            "rank": rank,
            "track": {
                "id": result.candidate.id,
                "title": result.candidate.title,
                "artist": result.candidate.artist,
            },
            "score": rounded_score,
            "components": {
                "history_similarity": rounded_score,
                "feature_closeness": rounded_closeness,
            },
            "explanation": build_cbf_explanation(
                result.score,
                result.feature_closeness,
            ),
        }

    @staticmethod
    def _build_context_result(result, rank, *, mood, exploration):
        context = result.context

        def rounded(value):
            return round(value, 4) if value is not None else None

        return {
            "rank": rank,
            "track": {
                "id": context.candidate.id,
                "title": context.candidate.title,
                "artist": context.candidate.artist,
            },
            "score": rounded(result.mmr_score),
            "components": {
                "history_similarity": rounded(context.history_similarity),
                "mood_fit": rounded(context.mood_fit),
                "tempo_fit": rounded(context.tempo_fit),
                "context_relevance": rounded(context.relevance),
                "diversity_penalty": rounded(result.diversity_penalty),
                "diversity_gain": rounded(result.diversity_gain),
                "mmr_score": rounded(result.mmr_score),
                "feature_closeness": {
                    feature_name: round(value, 4)
                    for feature_name, value in context.feature_closeness.items()
                },
            },
            "explanation": build_context_explanation(
                history_similarity=context.history_similarity,
                mood=mood,
                mood_fit=context.mood_fit,
                tempo_fit=context.tempo_fit,
                diversity_penalty=result.diversity_penalty,
                exploration=exploration,
                rank=rank,
            ),
        }

    @staticmethod
    def _catalogue_version(candidates):
        sources = sorted({track.data_source for track in candidates})
        if len(sources) == 1:
            return sources[0]
        return "mixed:" + ",".join(sources)
