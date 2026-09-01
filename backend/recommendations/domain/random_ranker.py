import random


def rank_random(candidates, limit, *, random_source=None):
    """Return up to ``limit`` unique candidates in random order.

    The ranker deliberately knows nothing about Django, HTTP, mood, or audio
    features. A seeded ``random_source`` can be injected for repeatable tests and
    offline evaluation.
    """

    if limit < 1:
        raise ValueError("limit must be at least 1")

    candidate_list = list(candidates)
    sample_size = min(limit, len(candidate_list))
    source = random_source or random.SystemRandom()

    return source.sample(candidate_list, sample_size)
