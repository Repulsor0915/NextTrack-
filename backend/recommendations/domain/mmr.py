from dataclasses import dataclass

from .algorithm_config import DEFAULT_ALGORITHM_CONFIG
from .feature_vectors import calculate_similarity


@dataclass(frozen=True)
class MmrRanking:
    context: object
    mmr_score: float
    diversity_penalty: float
    diversity_gain: float


def rerank_mmr(
    context_rankings,
    limit,
    *,
    diversity_strength,
    algorithm_config=DEFAULT_ALGORITHM_CONFIG,
):
    """Greedily balance contextual relevance and intra-list diversity.

    For selections after rank one, the normalized utility is equivalent to the
    standard MMR objective up to an additive constant:
    ``(1-d) * relevance + d * (1-max_similarity)``. The public
    ``diversity_strength`` value ``d`` corresponds to standard MMR
    ``lambda = 1-d``.
    """

    if limit < 1:
        raise ValueError("limit must be at least 1")
    if not 0 <= diversity_strength <= 1:
        raise ValueError("diversity_strength must be between 0 and 1")

    remaining = list(context_rankings)
    selected = []
    selected_contexts = []

    while remaining and len(selected) < limit:
        scored_options = []
        for context in remaining:
            if not selected_contexts:
                diversity_penalty = 0.0
                diversity_gain = 0.0
                mmr_score = context.relevance
            else:
                diversity_penalty = max(
                    calculate_similarity(
                        context.vector,
                        selected_context.vector,
                        metric=algorithm_config.diversity_similarity_metric,
                        weights=algorithm_config.feature_weights,
                    )
                    for selected_context in selected_contexts
                )
                diversity_gain = 1.0 - diversity_penalty
                mmr_score = (
                    (1.0 - diversity_strength) * context.relevance
                    + diversity_strength * diversity_gain
                )

            scored_options.append(
                MmrRanking(
                    context=context,
                    mmr_score=mmr_score,
                    diversity_penalty=diversity_penalty,
                    diversity_gain=diversity_gain,
                )
            )

        best = min(
            scored_options,
            key=lambda result: (
                -result.mmr_score,
                -result.context.relevance,
                _candidate_id(result.context.candidate),
            ),
        )
        selected.append(best)
        selected_contexts.append(best.context)
        remaining.remove(best.context)

    return selected


def _candidate_id(candidate):
    return str(getattr(candidate, "id", candidate))
