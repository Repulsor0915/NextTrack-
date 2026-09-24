from time import perf_counter

from recommendations.domain.algorithm_config import DEFAULT_ALGORITHM_CONFIG
from recommendations.domain.cbf_ranker import rank_cbf
from recommendations.domain.context_ranker import score_context_candidates
from recommendations.domain.feature_vectors import (
    build_recency_weighted_profile,
    build_session_profile,
)
from recommendations.domain.mmr import rerank_mmr
from recommendations.domain.mood_model import MOOD_MODEL_VERSION
from recommendations.domain.model_versions import (
    ALGORITHM_CONTRACT_VERSION,
    CBF_MODEL_VERSION,
    EXPLANATION_MODEL_VERSION,
    RERANKER_VERSION,
)
from recommendations.domain.random_ranker import rank_random
from recommendations.audio_features import build_feature_vector

from .candidate_repository import CandidateRepository

from .errors import (
    MissingTrackFeaturesError,
    NoCandidatesError,
    RecommendationServiceError,
    UnknownTrackIdsError,
    UnsupportedAlgorithmError,
)
from .result_builders import (
    build_cbf_result,
    build_context_result,
    build_random_result,
    collect_used_history_vectors,
)


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

        active_catalogue = CandidateRepository.get_active_catalogue()
        meta = {
            "algorithm_contract_version": ALGORITHM_CONTRACT_VERSION,
            "explanation_model_version": EXPLANATION_MODEL_VERSION,
            "cbf_model_version": None,
            "mood_model_version": None,
            "reranker_version": None,
            "catalogue_version": (
                active_catalogue.version
                if active_catalogue is not None
                else self._catalogue_version(
                    history=history,
                    candidate_ids=candidate_ids,
                    context=context,
                )
            ),
            "catalogue_sha256": (
                active_catalogue.catalogue_sha256
                if active_catalogue is not None else None
            ),
            "candidate_count": len(candidates),
            "requested_algorithm": requested_algorithm,
            "resolved_algorithm": resolved_algorithm,
            "bpm_filter": context.get("bpm"),
        }

        if resolved_algorithm == "random":
            recommendations, algorithm_meta = self._recommend_random(
                candidates,
                limit=request_data["limit"],
            )
        elif resolved_algorithm == "cbf" and requested_algorithm == "cbf":
            recommendations, algorithm_meta = self._recommend_cbf(
                candidates,
                history=history,
                limit=request_data["limit"],
            )
        else:
            recommendations, algorithm_meta = self._recommend_context_mmr(
                candidates,
                history=history,
                mood=mood,
                context=context,
                limit=request_data["limit"],
                resolved_algorithm=resolved_algorithm,
            )
        meta.update(algorithm_meta)
        elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
        meta["returned_count"] = len(recommendations)
        meta["processing_ms"] = elapsed_ms

        return {
            "algorithm": requested_algorithm,
            "recommendations": recommendations,
            "meta": meta,
        }

    def _recommend_random(self, candidates, *, limit):
        selected_tracks = rank_random(
            candidates,
            limit,
            random_source=self.random_source,
        )
        self._attach_selected_metadata(selected_tracks)
        recommendations = [
            build_random_result(track, rank)
            for rank, track in enumerate(selected_tracks, start=1)
        ]
        return recommendations, {
            "relevance_model": "random",
            "reranker": None,
        }

    def _recommend_cbf(self, candidates, *, history, limit):
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
        vectors_by_id = {track.id: vector for track, vector in candidate_vectors}
        ranked_candidates = rank_cbf(
            candidate_vectors,
            session_profile,
            limit,
            algorithm_config=self.algorithm_config,
        )
        self._attach_selected_metadata(
            [result.candidate for result in ranked_candidates]
        )
        used_history_vectors = collect_used_history_vectors(
            history_tracks,
            history_vectors,
            self.algorithm_config.history_window_size,
        )
        recommendations = [
            build_cbf_result(
                result,
                rank,
                vector=vectors_by_id[result.candidate.id],
                session_profile=session_profile,
                used_history_vectors=used_history_vectors,
                algorithm_config=self.algorithm_config,
            )
            for rank, result in enumerate(ranked_candidates, start=1)
        ]
        return recommendations, {
            "history_count_used": min(
                len(history_tracks), self.algorithm_config.history_window_size
            ),
            "history_window_size": self.algorithm_config.history_window_size,
            "cbf_model_version": CBF_MODEL_VERSION,
            "relevance_model": "history_cbf",
            "reranker": None,
        }

    def _recommend_context_mmr(
        self,
        candidates,
        *,
        history,
        mood,
        context,
        limit,
        resolved_algorithm,
    ):
        diversity_strength = context.get(
            "diversity_strength",
            self.algorithm_config.default_diversity_strength,
        )
        history_tracks = self._get_history_tracks(history) if history else []
        history_vectors = []
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
            limit,
            diversity_strength=diversity_strength,
            algorithm_config=self.algorithm_config,
        )
        self._attach_selected_metadata(
            [result.context.candidate for result in reranked_candidates]
        )
        base_ranks = {
            result.candidate.id: rank
            for rank, result in enumerate(context_rankings, start=1)
        }
        used_history_vectors = collect_used_history_vectors(
            history_tracks,
            history_vectors,
            self.algorithm_config.history_window_size,
        )
        profile_method = (
            "equal"
            if resolved_algorithm == "cbf"
            else self.algorithm_config.context_history_strategy
        )
        recommendations = [
            build_context_result(
                result,
                rank,
                base_rank=base_ranks[result.context.candidate.id],
                mood=mood,
                diversity_strength=diversity_strength,
                session_profile=session_profile,
                used_history_vectors=used_history_vectors,
                profile_method=profile_method,
                algorithm_config=self.algorithm_config,
            )
            for rank, result in enumerate(reranked_candidates, start=1)
        ]
        return recommendations, {
            "history_count_used": min(
                len(history_tracks), self.algorithm_config.history_window_size
            ),
            "history_window_size": self.algorithm_config.history_window_size,
            "mood": mood,
            "mood_model": MOOD_MODEL_VERSION if mood else None,
            "cbf_model_version": CBF_MODEL_VERSION if history else None,
            "mood_model_version": MOOD_MODEL_VERSION if mood else None,
            "reranker_version": RERANKER_VERSION,
            "relevance_model": self._relevance_model(
                history=history,
                mood=mood,
            ),
            "reranker": "mmr",
            "diversity_strength": diversity_strength,
            "mmr_lambda": round(1.0 - diversity_strength, 4),
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
        return CandidateRepository.validate_track_ids(history, candidate_ids)

    @staticmethod
    def _candidate_queryset(*, history, candidate_ids, context):
        return CandidateRepository.candidate_queryset(
            history=history,
            candidate_ids=candidate_ids,
            context=context,
        )

    @classmethod
    def _get_candidates(cls, *, history, candidate_ids, context):
        return CandidateRepository.get_candidates(
            history=history,
            candidate_ids=candidate_ids,
            context=context,
        )

    @staticmethod
    def _attach_selected_metadata(selected_tracks):
        return CandidateRepository.attach_selected_metadata(selected_tracks)

    @staticmethod
    def _get_history_tracks(history):
        return CandidateRepository.get_history_tracks(history)

    @staticmethod
    def _used_history_vectors(history_tracks, history_vectors, window_size):
        return collect_used_history_vectors(
            history_tracks,
            history_vectors,
            window_size,
        )

    @staticmethod
    def _build_random_result(track, rank):
        return build_random_result(track, rank)

    def _build_cbf_result(
        self, result, rank, *, vector, session_profile, used_history_vectors
    ):
        return build_cbf_result(
            result,
            rank,
            vector=vector,
            session_profile=session_profile,
            used_history_vectors=used_history_vectors,
            algorithm_config=self.algorithm_config,
        )

    def _build_context_result(
        self,
        result,
        rank,
        *,
        base_rank,
        mood,
        diversity_strength,
        session_profile,
        used_history_vectors,
        profile_method,
    ):
        return build_context_result(
            result,
            rank,
            base_rank=base_rank,
            mood=mood,
            diversity_strength=diversity_strength,
            session_profile=session_profile,
            used_history_vectors=used_history_vectors,
            profile_method=profile_method,
            algorithm_config=self.algorithm_config,
        )

    @classmethod
    def _catalogue_version(cls, *, history, candidate_ids, context):
        return CandidateRepository.catalogue_version(
            history=history,
            candidate_ids=candidate_ids,
            context=context,
        )
