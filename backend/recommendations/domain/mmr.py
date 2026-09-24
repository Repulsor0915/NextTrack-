## This file reranks relevant candidates using Maximal Marginal Relevance.
## It reduces repetition by balancing relevance with playlist diversity.

from dataclasses import dataclass
from math import sqrt
from operator import mul

import numpy as np

from recommendations.audio_features import FEATURE_NAMES
from .algorithm_config import DEFAULT_ALGORITHM_CONFIG
from .feature_vectors import calculate_similarity

# Use the NumPy implementation when the candidate pool is large enough.
_VECTORIZED_MIN_CANDIDATES = 1000

# Store the final MMR result and the track responsible for its diversity penalty.
@dataclass(frozen=True)
class MmrRanking:
    context: object
    mmr_score: float
    diversity_penalty: float
    diversity_gain: float
    supporting_track_id: str | None = None

# Validate values that directly control the number and balance of results.
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
    if (
        len(remaining) >= _VECTORIZED_MIN_CANDIDATES
        and limit > 1
        and algorithm_config.diversity_similarity_metric == "weighted_cosine"
    ):
        return _rerank_mmr_vectorized(
            remaining,
            limit,
            diversity_strength=diversity_strength,
            algorithm_config=algorithm_config,
        )

    selected = []
    selected_contexts = []
    maximum_similarity = {}
    cosine_cache = (
        {
            _candidate_id(context.candidate): (
                tuple(
                    algorithm_config.feature_weights[name] * context.vector[name]
                    for name in FEATURE_NAMES
                ),
                tuple(context.vector[name] for name in FEATURE_NAMES),
                sqrt(
                    sum(
                        algorithm_config.feature_weights[name]
                        * context.vector[name] ** 2
                        for name in FEATURE_NAMES
                    )
                ),
            )
            for context in remaining
        }
        if limit > 1
        and algorithm_config.diversity_similarity_metric == "weighted_cosine"
        else None
    )

    while remaining and len(selected) < limit:
        best = None
        best_key = None
        for context in remaining:
            if not selected_contexts:
                diversity_penalty = 0.0
                diversity_gain = 0.0
                mmr_score = context.relevance
                supporting_track_id = None
            else:
                diversity_penalty, supporting_track_id = maximum_similarity[
                    _candidate_id(context.candidate)
                ]
                diversity_gain = 1.0 - diversity_penalty
                mmr_score = (
                    (1.0 - diversity_strength) * context.relevance
                    + diversity_strength * diversity_gain
                )

            key = (
                -mmr_score,
                -context.relevance,
                _candidate_id(context.candidate),
            )
            if best_key is None or key < best_key:
                best_key = key
                best = MmrRanking(
                    context=context,
                    mmr_score=mmr_score,
                    diversity_penalty=diversity_penalty,
                    diversity_gain=diversity_gain,
                    supporting_track_id=supporting_track_id,
                )

        selected.append(best)
        selected_contexts.append(best.context)
        remaining.remove(best.context)

        if remaining and len(selected) < limit:
            selected_id = _candidate_id(best.context.candidate)
            for context in remaining:
                candidate_id = _candidate_id(context.candidate)
                if cosine_cache is None:
                    similarity = calculate_similarity(
                        context.vector,
                        best.context.vector,
                        metric=algorithm_config.diversity_similarity_metric,
                        weights=algorithm_config.feature_weights,
                    )
                else:
                    weighted_values, _, candidate_norm = cosine_cache[candidate_id]
                    _, selected_values, selected_norm = cosine_cache[selected_id]
                    norm_product = candidate_norm * selected_norm
                    similarity = (
                        max(
                            0.0,
                            min(
                                1.0,
                                sum(map(mul, weighted_values, selected_values))
                                / norm_product,
                            ),
                        )
                        if norm_product else 0.0
                    )
                previous = maximum_similarity.get(candidate_id)
                if previous is None or similarity > previous[0]:
                    maximum_similarity[candidate_id] = (similarity, selected_id)

    return selected

# Convert the candidate vectors into matrix form for batch calculations.
def _rerank_mmr_vectorized(
    rankings, limit, *, diversity_strength, algorithm_config,
):
    """Apply the same greedy MMR rule to large pools in NumPy batches."""
    count = len(rankings)
    values = np.fromiter(
        (ranking.vector[name] for ranking in rankings for name in FEATURE_NAMES),
        dtype=np.float64,
        count=count * len(FEATURE_NAMES),
    ).reshape(count, len(FEATURE_NAMES))
    weights = np.asarray(
        [algorithm_config.feature_weights[name] for name in FEATURE_NAMES],
        dtype=np.float64,
    )
    weighted_values = values * weights
    norms = np.sqrt(np.sum(weights * values ** 2, axis=1))
    relevances = np.fromiter(
        (ranking.relevance for ranking in rankings),
        dtype=np.float64,
        count=count,
    )
    candidate_ids = [_candidate_id(ranking.candidate) for ranking in rankings]
    selected_mask = np.zeros(count, dtype=np.bool_)
    maximum_similarity = np.zeros(count, dtype=np.float64)
    supporting_indices = np.full(count, -1, dtype=np.int64)
    selected = []

    while len(selected) < min(limit, count):
        if not selected:
            scores = relevances.copy()
        else:
            scores = (
                (1.0 - diversity_strength) * relevances
                + diversity_strength * (1.0 - maximum_similarity)
            )
        scores[selected_mask] = -np.inf
        maximum_score = np.max(scores)
        tied_indices = np.flatnonzero(scores == maximum_score)
        best_index = min(
            tied_indices,
            key=lambda index: (-relevances[index], candidate_ids[index]),
        )
        supporting_index = supporting_indices[best_index]
        penalty = float(maximum_similarity[best_index]) if selected else 0.0
        selected.append(
            MmrRanking(
                context=rankings[best_index],
                mmr_score=float(scores[best_index]),
                diversity_penalty=penalty,
                diversity_gain=1.0 - penalty if len(selected) else 0.0,
                supporting_track_id=(
                    candidate_ids[supporting_index]
                    if supporting_index >= 0 else None
                ),
            )
        )
        selected_mask[best_index] = True
        if len(selected) >= min(limit, count):
            break

        norm_products = norms * norms[best_index]
        dot_products = np.einsum(
            "ij,j->i", weighted_values, values[best_index], optimize=False,
        )
        similarities = np.divide(
            dot_products,
            norm_products,
            out=np.zeros(count, dtype=np.float64),
            where=norm_products != 0,
        )
        np.clip(similarities, 0.0, 1.0, out=similarities)
        improved = (~selected_mask) & (
            (supporting_indices < 0) | (similarities > maximum_similarity)
        )
        maximum_similarity[improved] = similarities[improved]
        supporting_indices[improved] = best_index

    return selected


def _candidate_id(candidate):
    return str(getattr(candidate, "id", candidate))
