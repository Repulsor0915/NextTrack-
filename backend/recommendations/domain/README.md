# Recommendation algorithm contract

This directory contains the deterministic ranking logic. The three explicit
experiment modes have separate responsibilities:

| Mode | Input used for relevance | Final ranking |
| --- | --- | --- |
| `random` | No history or mood signal | Seedable sample without replacement |
| `cbf` | Equal average of up to five recent history vectors | Eight-feature similarity only |
| `context_mmr` | Recency-weighted history and/or a requested mood | Context relevance followed by MMR |

`auto` is API routing rather than a fourth algorithm. It selects Random, CBF,
or Context+MMR from the request signals.

## Baseline formulas

Basic CBF compares the session profile and each candidate using the current
eight-feature engineering weights and weighted cosine similarity.

When both history and mood exist, contextual relevance is:

```text
relevance = 0.65 * history_similarity + 0.35 * mood_fit
```

The current mood model uses project-defined target profiles. Feature closeness
within each profile is weighted using the eight NextTrack-overlapping ReliefF
importance values reported by Panda et al. (2021), renormalized over the
features used by the requested mood.

MMR keeps the most relevant track first. From rank two onward:

```text
mmr_score = (1 - diversity_strength) * relevance
          + diversity_strength * (1 - max_similarity_to_selected)
```

The baseline `diversity_strength` is `0.20`, equivalent in ranking to standard
MMR `lambda = 0.80`.

## AlgorithmConfig

`algorithm_config.py` is the single source of truth for tunable algorithm
parameters. `AlgorithmConfig` is validated and immutable so one experimental
run cannot silently change another. `to_dict()` produces the serialisable
snapshot that the offline evaluator should store in its experiment manifest.

It controls:

- eight-feature weights;
- relevance and MMR similarity metrics;
- history window size and contextual history strategy;
- history:mood relevance ratio;
- optional internal mood-feature weights; and
- the default MMR diversity strength.

It does not contain the catalogue, candidate pool, Top-N, test scenarios, or
random seed. Those describe an experiment run and belong in
`experiment-config.json`, not in the ranking formula.

The default `baseline-panda-mood-v1` configuration preserves the Basic CBF,
context-relevance, and MMR defaults, and formally uses the Panda-derived mood
feature weights. Experimental alternatives currently supported by the
algorithm layer are:

- equal, current heuristic, or literature-informed eight-feature weights;
- weighted cosine or normalized weighted Euclidean relevance similarity;
- equal or Panda-derived mood-profile feature weights;
- configurable history:mood ratio; and
- configurable MMR relevance:diversity ratio.

The general CBF literature-informed feature preset is only an experimental
comparison. It is not asserted to be a universal or already validated optimum
for NextTrack. The separate Panda-derived weights are used only inside
`mood_fit`; they do not alter Basic CBF similarity, the 65:35 history:mood
ratio, or the 80:20 MMR relevance:diversity setting.
