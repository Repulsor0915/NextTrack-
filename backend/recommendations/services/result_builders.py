"""Build stable recommendation response items from domain ranking results."""

from recommendations.domain.explanation_evidence import (
    history_evidence,
    mood_evidence,
)
from recommendations.domain.explanations import (
    build_cbf_explanation,
    build_context_explanation,
)


def collect_used_history_vectors(history_tracks, history_vectors, window_size):
    start = max(0, len(history_tracks) - window_size)
    return [
        (index, history_tracks[index].id, history_vectors[index])
        for index in range(start, len(history_tracks))
    ]


def build_random_result(track, rank):
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
        "explanation_evidence": {
            "path": "random",
            "base_score": None,
            "history_similarity": None,
            "mood_fit": None,
            "base_rank": None,
            "final_rank": rank,
            "rank_change": None,
            "history": None,
            "mood": None,
            "mmr": None,
        },
    }


def build_cbf_result(
    result,
    rank,
    *,
    vector,
    session_profile,
    used_history_vectors,
    algorithm_config,
):
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
            feature_weights=algorithm_config.feature_weights,
        ),
        "explanation_evidence": {
            "path": "basic_cbf",
            "base_score": result.score,
            "history_similarity": result.score,
            "mood_fit": None,
            "base_rank": rank,
            "final_rank": rank,
            "rank_change": 0,
            "history": history_evidence(
                vector,
                session_profile,
                used_history_vectors,
                metric=algorithm_config.relevance_similarity_metric,
                feature_weights=algorithm_config.feature_weights,
                profile_method="equal",
            ),
            "mood": None,
            "mmr": None,
        },
    }


def build_context_result(
    result,
    rank,
    *,
    base_rank,
    mood,
    diversity_strength,
    session_profile,
    used_history_vectors,
    profile_method,
    algorithm_config,
):
    context = result.context
    rank_change = base_rank - rank
    has_diversity_comparison = rank > 1 and diversity_strength > 0
    supporting_track = (
        {
            "track_id": result.supporting_track_id,
            "similarity": result.diversity_penalty,
        }
        if has_diversity_comparison
        else None
    )

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
            base_rank=base_rank,
            rank_change=rank_change,
        ),
        "explanation_evidence": {
            "path": (
                "combined_mmr"
                if session_profile is not None and mood is not None
                else "mood_mmr" if mood is not None else "history_mmr"
            ),
            "base_score": context.relevance,
            "history_similarity": context.history_similarity,
            "mood_fit": context.mood_fit,
            "base_rank": base_rank,
            "final_rank": rank,
            "rank_change": rank_change,
            "relevance_weights": (
                {
                    "history": algorithm_config.history_relevance_weight,
                    "mood": algorithm_config.mood_relevance_weight,
                }
                if session_profile is not None and mood is not None
                else None
            ),
            "history": (
                history_evidence(
                    context.vector,
                    session_profile,
                    used_history_vectors,
                    metric=algorithm_config.relevance_similarity_metric,
                    feature_weights=algorithm_config.feature_weights,
                    profile_method=profile_method,
                )
                if session_profile is not None
                else None
            ),
            "mood": (
                mood_evidence(
                    context.vector,
                    mood,
                    feature_weights=algorithm_config.mood_feature_weights,
                )
                if mood is not None
                else None
            ),
            "mmr": {
                "selection_score": result.mmr_score,
                "diversity_strength": diversity_strength,
                "similarity_metric": algorithm_config.diversity_similarity_metric,
                "supporting_track": supporting_track,
                "diversity_gain": (
                    result.diversity_gain if has_diversity_comparison else None
                ),
                "ranking_changed": diversity_strength > 0 and rank_change != 0,
            },
        },
    }
