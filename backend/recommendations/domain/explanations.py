from .feature_vectors import FEATURE_WEIGHTS


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


def build_cbf_explanation(score, closeness, *, feature_weights=FEATURE_WEIGHTS):
    """Generate a deterministic explanation supported by ranking evidence."""

    if score >= 0.90:
        summary = "Strong audio-feature match for the recent listening history."
    elif score >= 0.75:
        summary = "Good audio-feature match for the recent listening history."
    else:
        summary = "Selected from the closest available audio-feature matches."

    strongest_matches = sorted(
        closeness.items(),
        key=lambda item: (-(item[1] * feature_weights[item[0]]), item[0]),
    )
    evidence = [f"weighted history similarity {score:.2f}"]
    evidence.extend(
        f"similar {FEATURE_LABELS[feature_name]} to the recent profile"
        for feature_name, match_value in strongest_matches
        if match_value >= 0.80
    )

    return {
        "summary": summary,
        "evidence": evidence[:3],
    }


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
):
    """Explain only the components that actually affected eligibility/ranking."""

    if history_similarity is not None and mood_fit is not None:
        summary = "Balances recent-listening similarity with the requested mood."
    elif mood_fit is not None:
        summary = "Selected using the requested mood profile."
    else:
        summary = "Selected for similarity to the recent listening history."

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
    if rank > 1 and diversity_strength > 0:
        evidence.append(
            f"maximum similarity to earlier recommendations {diversity_penalty:.2f}"
        )

    return {
        "summary": summary,
        "evidence": evidence,
    }
