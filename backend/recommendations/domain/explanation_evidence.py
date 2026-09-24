## This file prepares numerical evidence for recommendation explanations.
## Reports the values used by the algorithem without changing ranking.

from recommendations.audio_features import FEATURE_NAMES

from .feature_vectors import calculate_similarity
from .mood_model import MOOD_PROFILES

## Comapre each normalized feature with its target value.
## Closeness is descriptive evidence and is not a cosine-score contribution.
def feature_evidence(actual_vector, target_vector):
    """Closeness describes distance; it is not a cosine contribution."""

    return {
        name: {
            "actual": actual_vector[name],
            "target": target,
            "closeness": 1.0 - abs(actual_vector[name] - target),
        }
        for name, target in target_vector.items()
    }

## Find the previously used track that is most similar to this candidate.
def history_evidence(
    candidate_vector,
    session_profile,
    history_vectors,
    *,
    metric,
    feature_weights,
    profile_method,
):
    """Identify the nearest used play without conflating it with the profile."""

    closest = None
    for request_index, track_id, vector in history_vectors:
        similarity = calculate_similarity(
            candidate_vector,
            vector,
            metric=metric,
            weights=feature_weights,
        )

        ## If similarity is tied, prefer the more recent request index.
        if closest is None or (similarity, request_index) > (
            closest["similarity"],
            closest["request_index"],
        ):
            closest = {
                "track_id": track_id,
                "request_index": request_index,
                "similarity": similarity,
            }

    ## Report the session-profile comparison and the nearest history track.
    return {
        "similarity_metric": metric,
        "profile_method": profile_method,
        "feature_weights": {name: feature_weights[name] for name in FEATURE_NAMES},
        "features": feature_evidence(candidate_vector, session_profile),
        "closest_track": closest,
    }

## Only works when mood feature active in the requested.
def mood_evidence(candidate_vector, mood, *, feature_weights):

    ## Only the features defined by the requested mood are included.
    targets = MOOD_PROFILES[mood]
    if feature_weights is None:
        weights = {name: 1.0 for name in targets}
    else:
        weights = {name: feature_weights[name] for name in targets}
    total = sum(weights.values())

    # Normalize the active weights so their reported total equals one. 
    return {
        "requested_mood": mood,
        "active_feature_weights": {
            name: weight / total for name, weight in weights.items()
        },
        "features": feature_evidence(candidate_vector, targets),
    }
