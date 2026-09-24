## This file provides the random recommendation baseline.
## It is used to compare the main algorithm against a non-personalized method.
import random


def rank_random(candidates, limit, *, random_source=None):

    # A recommendation request must ask for at least one result.
    if limit < 1:
        raise ValueError("limit must be at least 1")

    candidate_list = list(candidates)
    sample_size = min(limit, len(candidate_list))
    source = random_source or random.SystemRandom()

    return source.sample(candidate_list, sample_size)
