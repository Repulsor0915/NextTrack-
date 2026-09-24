# This file converts recommendation evidence into user-facing explanations.
# Describes existing scores and does not calculate or change the ranking.

from .feature_vectors import FEATURE_WEIGHTS

# Display labels used when audiop features are mentioned in an explanation.
FEATURE_LABELS = {
    "tempo": "tempo",
    "energy": "energy",
    "valence": "valence",
    "danceability": "danceability",
    "acousticness": "acousticness",
    "instrumentalness": "instrumentalness",
    "loudness": "loudness",
    "speechiness": "speechiness",
}

## Descibe score and proximity without inventing cosine contributions.
## Weight argujment remains accepted by the offline evaluator,
## But per-feature wording is ordered by descriptive clossness only.
def build_cbf_explanation(score, closeness, *, feature_weights=FEATURE_WEIGHTS):

    if score >= 0.90:
        summary = "High similarity score for the recent listening profile."
    elif score >= 0.75:
        summary = "Good similarity score for the recent listening profile."
    else:
        summary = "Selected from the closest available audio-feature matches."

    strongest_matches = sorted(
        closeness.items(),
        key=lambda item: (-item[1], item[0]),
    )
    evidence = [f"history similarity {score:.2f}"]
    evidence.extend(
        f"similar {FEATURE_LABELS[feature_name]} to the recent profile"
        for feature_name, match_value in strongest_matches
        if match_value >= 0.80
    )

    ## Add vidence only when the corresponding score or constraint exists.
    return {
        "summary": summary,
        "evidence": evidence[:3],
    }

## Select a summary based on the signals that were actually used.
def build_context_explanation(
    *,
    history_similarity,
    mood,
    mood_fit,
    mood_feature_closeness,
    bpm_constraint_satisfied,
    diversity_penalty,
    diversity_strength,
    rank,
    base_rank,
    rank_change,
):
    if history_similarity is not None and mood_fit is not None:
        summary = "Balances recent-listening similarity with the requested mood."
    elif mood_fit is not None:
        summary = "Selected using the requested mood profile."
    else:
        summary = "Selected for similarity to the recent listening history."

    ## Add evidence only when the corresponding score or constraint exists. 
    evidence = []
    if history_similarity is not None:
        evidence.append(f"history similarity {history_similarity:.2f}")
    if mood_fit is not None:
        evidence.append(f'{mood} mood fit {mood_fit:.2f}')
        closest_mood_features = sorted(
            mood_feature_closeness.items(),
            key=lambda item: (-item[1], item[0]),
        )[:2]
        if closest_mood_features:
            evidence.append(
                "closest mood-profile cues: "
                + ", ".join(
                    f"{FEATURE_LABELS[feature_name]} {closeness:.2f}"
                    for feature_name, closeness in closest_mood_features
                )
            )
    if bpm_constraint_satisfied is not None:
        evidence.append("within the requested BPM range")
    if rank_change != 0 and diversity_strength > 0:
        evidence.append(
            f"MMR changed relevance rank {base_rank} to final rank {rank}"
        )
    if rank_change != 0 and rank > 1 and diversity_strength > 0:
        evidence.append(
            "maximum similarity to an earlier recommendation: "
            f"{diversity_penalty:.2f}"
        )

    return {
        "summary": summary,
        "evidence": evidence,
    }
