from dataclasses import dataclass

from .feature_vectors import weighted_cosine_similarity


@dataclass(frozen=True)
class MmrRanking:
    context: object
    mmr_score: float
    diversity_penalty: float
    diversity_gain: float


def rerank_mmr(context_rankings, limit, *, exploration):
    """Greedily balance contextual relevance and intra-list diversity.

    For selections after rank one, the normalized utility is equivalent to the
    standard MMR objective up to an additive constant:
    ``(1-e) * relevance + e * (1-max_similarity)``.
    """

    if limit < 1:
        raise ValueError("limit must be at least 1")
    if not 0 <= exploration <= 1:
        raise ValueError("exploration must be between 0 and 1")

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
                    weighted_cosine_similarity(
                        context.vector,
                        selected_context.vector,
                    )
                    for selected_context in selected_contexts
                )
                diversity_gain = 1.0 - diversity_penalty
                mmr_score = (
                    (1.0 - exploration) * context.relevance
                    + exploration * diversity_gain
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
