from time import perf_counter

from recommendations.domain.algorithm_config import DEFAULT_ALGORITHM_CONFIG
from recommendations.domain.cbf_ranker import rank_cbf
from recommendations.domain.context_ranker import score_context_candidates
from recommendations.domain.explanations import (
    build_cbf_explanation,
    build_context_explanation,
)
from recommendations.domain.feature_vectors import (
    build_recency_weighted_profile,
    build_session_profile,
)
from recommendations.domain.mmr import rerank_mmr
from recommendations.domain.mood_model import MOOD_MODEL_VERSION
from recommendations.domain.random_ranker import rank_random
from recommendations.models import Track
from recommendations.audio_features import build_feature_vector


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
    SUPPORTED_ALGORITHMS = {"auto", "random", "cbf", "context_mmr"}
    DEFAULT_DIVERSITY_STRENGTH = (
        DEFAULT_ALGORITHM_CONFIG.default_diversity_strength
    )

    def __init__(
        self,
        *,
        random_source=None,
        algorithm_config=DEFAULT_ALGORITHM_CONFIG,
    ):
        self.random_source = random_source
        self.algorithm_config = algorithm_config

    def recommend(self, request_data):
        started_at = perf_counter()
        requested_algorithm = request_data["algorithm"]

        if requested_algorithm not in self.SUPPORTED_ALGORITHMS:
            raise UnsupportedAlgorithmError(
                f'Algorithm "{requested_algorithm}" has not been implemented yet.',
                details={"algorithm": requested_algorithm},
            )

        history = request_data["history"]
        context = request_data.get("context", {})
        mood = context.get("mood")
        resolved_algorithm = self._resolve_algorithm(
            requested_algorithm,
            history=history,
            mood=mood,
        )
        candidate_ids = request_data.get("candidate_ids")
        self._validate_track_ids(history, candidate_ids)

        candidates = self._get_candidates(
            history=history,
            candidate_ids=candidate_ids,
            context=context,
        )
        if not candidates:
            raise NoCandidatesError(
                "No unplayed tracks satisfy the requested candidate constraints.",
                details={
                    "candidate_ids_supplied": candidate_ids is not None,
                    "bpm_filter": context.get("bpm"),
                    "history_count": len(history),
                },
            )

        meta = {
            "catalogue_version": self._catalogue_version(candidates),
            "candidate_count": len(candidates),
            "requested_algorithm": requested_algorithm,
            "resolved_algorithm": resolved_algorithm,
            "bpm_filter": context.get("bpm"),
        }

        if resolved_algorithm == "random":
            selected_tracks = rank_random(
                candidates,
                request_data["limit"],
                random_source=self.random_source,
            )
            recommendations = [
                self._build_random_result(track, rank)
                for rank, track in enumerate(selected_tracks, start=1)
            ]
            meta.update({"relevance_model": "random", "reranker": None})
        elif resolved_algorithm == "cbf" and requested_algorithm == "cbf":
            history_tracks = self._get_history_tracks(history)
            history_vectors = [
                build_feature_vector(track.features) for track in history_tracks
            ]
            session_profile = build_session_profile(
                history_vectors,
                window_size=self.algorithm_config.history_window_size,
            )
            candidate_vectors = [
                (track, build_feature_vector(track.features)) for track in candidates
            ]
            ranked_candidates = rank_cbf(
                candidate_vectors,
                session_profile,
                request_data["limit"],
                algorithm_config=self.algorithm_config,
            )
            recommendations = [
                self._build_cbf_result(result, rank)
                for rank, result in enumerate(ranked_candidates, start=1)
            ]
            meta["history_count_used"] = min(
                len(history_tracks), self.algorithm_config.history_window_size
            )
            meta["history_window_size"] = self.algorithm_config.history_window_size
            meta.update({"relevance_model": "history_cbf", "reranker": None})
        else:
            diversity_strength = context.get(
                "diversity_strength",
                self.algorithm_config.default_diversity_strength,
            )
            history_tracks = self._get_history_tracks(history) if history else []
            session_profile = None
            if history_tracks:
                history_vectors = [
                    build_feature_vector(track.features) for track in history_tracks
                ]
                if resolved_algorithm == "cbf":
                    session_profile = build_session_profile(
                        history_vectors,
                        window_size=self.algorithm_config.history_window_size,
                    )
                elif self.algorithm_config.context_history_strategy == "equal":
                    session_profile = build_session_profile(
                        history_vectors,
                        window_size=self.algorithm_config.history_window_size,
                    )
                else:
                    session_profile = build_recency_weighted_profile(
                        history_vectors,
                        window_size=self.algorithm_config.history_window_size,
                    )

            candidate_vectors = [
                (track, build_feature_vector(track.features)) for track in candidates
            ]
            context_rankings = score_context_candidates(
                candidate_vectors,
                session_profile=session_profile,
                mood=mood,
                bpm_constraint_applied=bool(context.get("bpm")),
                algorithm_config=self.algorithm_config,
            )
            reranked_candidates = rerank_mmr(
                context_rankings,
                request_data["limit"],
                diversity_strength=diversity_strength,
                algorithm_config=self.algorithm_config,
            )
            recommendations = [
                self._build_context_result(
                    result,
                    rank,
                    mood=mood,
                    diversity_strength=diversity_strength,
                )
                for rank, result in enumerate(reranked_candidates, start=1)
            ]
            meta.update(
                {
                    "history_count_used": min(
                        len(history_tracks), self.algorithm_config.history_window_size
                    ),
                    "history_window_size": self.algorithm_config.history_window_size,
                    "mood": mood,
                    "mood_model": MOOD_MODEL_VERSION if mood else None,
                    "relevance_model": self._relevance_model(
                        history=history,
                        mood=mood,
                    ),
                    "reranker": "mmr",
                    "diversity_strength": diversity_strength,
                    "mmr_lambda": round(1.0 - diversity_strength, 4),
                }
            )

        elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
        meta["returned_count"] = len(recommendations)
        meta["processing_ms"] = elapsed_ms

        return {
            "algorithm": requested_algorithm,
            "recommendations": recommendations,
            "meta": meta,
        }

    @staticmethod
    def _resolve_algorithm(requested_algorithm, *, history, mood):
        if requested_algorithm != "auto":
            return requested_algorithm
        if mood:
            return "context_mmr"
        if history:
            return "cbf"
        return "random"

    @staticmethod
    def _relevance_model(*, history, mood):
        if history and mood:
            return "history_mood_cbf"
        if mood:
            return "mood_cbf"
        return "history_cbf"

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

    def _build_cbf_result(self, result, rank):
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
                feature_weights=self.algorithm_config.feature_weights,
            ),
        }

    @staticmethod
    def _build_context_result(result, rank, *, mood, diversity_strength):
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
            "score": rounded(context.relevance),
            "components": {
                "history_similarity": rounded(context.history_similarity),
                "mood_fit": rounded(context.mood_fit),
                "mood_feature_closeness": {
                    feature_name: round(value, 4)
                    for feature_name, value in context.mood_feature_closeness.items()
                },
                "bpm_constraint_satisfied": context.bpm_constraint_satisfied,
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
                mood_feature_closeness=context.mood_feature_closeness,
                bpm_constraint_satisfied=context.bpm_constraint_satisfied,
                diversity_penalty=result.diversity_penalty,
                diversity_strength=diversity_strength,
                rank=rank,
            ),
        }

    @staticmethod
    def _catalogue_version(candidates):
        sources = sorted({track.data_source for track in candidates})
        if len(sources) == 1:
            return sources[0]
        return "mixed:" + ",".join(sources)
