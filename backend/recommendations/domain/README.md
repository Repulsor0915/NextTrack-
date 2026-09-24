# Recommendation Domain

This directory contains the ranking logic used by NextTrack. Its modules work
with prepared candidates and normalized audio-feature vectors. Database access,
request validation, and API serialization are handled outside this directory.

## Files

| File | Purpose |
| --- | --- |
| `algorithm_config.py` | Defines validated feature weights, similarity methods, history settings, context ratios, and MMR strength. |
| `feature_vectors.py` | Builds history profiles and calculates weighted cosine or Euclidean similarity. |
| `cbf_ranker.py` | Ranks candidates by similarity to the listening-history profile. |
| `context_ranker.py` | Combines history similarity and mood fit into contextual relevance. |
| `mood_model.py` | Defines the Happy, Energetic, Calm, and Sad target profiles. |
| `mmr.py` | Reranks contextual results to balance relevance and audio-feature diversity. |
| `random_ranker.py` | Provides the non-personalized Random baseline. |
| `explanation_evidence.py` | Collects the numerical history, mood, and feature evidence used in explanations. |
| `explanations.py` | Converts ranking evidence into short user-facing text. |
| `model_versions.py` | Stores the public identifiers for ranking and explanation versions. |

## Ranking flow

NextTrack supports three domain-level paths:

1. **Random** samples eligible candidates without calculating relevance.
2. **Basic CBF** builds an equal-weight profile from up to five recent history
   tracks and ranks candidates by audio-feature similarity.
3. **Context + MMR** uses history, mood, or both to calculate relevance, then
   reranks the list for variety.

`auto` is resolved by the service layer and is not a separate ranker in this
directory.

## Audio features

All ranking modules use these eight normalized features:

- tempo;
- energy;
- valence;
- danceability;
- acousticness;
- instrumentalness;
- loudness;
- speechiness.

Raw catalogue values are normalized by
`recommendations/audio_features.py` before they enter the domain functions.

The current relevance feature weights are:

| Feature | Weight |
| --- | ---: |
| tempo | 0.10 |
| energy | 0.25 |
| valence | 0.25 |
| danceability | 0.15 |
| acousticness | 0.10 |
| instrumentalness | 0.05 |
| loudness | 0.05 |
| speechiness | 0.05 |

## Main scoring rules

Basic CBF uses the configured similarity between the history profile and each
candidate vector.

When both history and mood are supplied, contextual relevance uses:

```text
relevance = 0.65 * history_similarity + 0.35 * mood_fit
```

If only one signal is supplied, relevance equals that signal. The current
context history profile gives greater weight to more recent tracks.

MMR selects the first track by relevance, then applies:

```text
MMR score = (1 - diversity_strength) * relevance
            + diversity_strength * (1 - maximum_selected_similarity)
```

The default `diversity_strength` is `0.20`. Candidate IDs provide stable tie
breaking. Large weighted-cosine candidate pools use the equivalent NumPy MMR
implementation.

## Configuration and evidence

`AlgorithmConfig` is a frozen dataclass. It validates that feature weights are
complete, finite, non-negative, and sum to one. It also validates similarity
methods, history strategy, context ratios, and diversity strength.

Ranking result objects retain the scores and evidence needed by later service
code. Explanation modules describe those completed decisions and do not change
the ranking. Per-feature closeness is descriptive distance evidence rather than
an individual contribution to the cosine score.

## Tests

From the repository root:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test `
  recommendations.tests.test_algorithm_config `
  recommendations.tests.test_rankers `
  recommendations.tests.test_explanation_evidence `
  --noinput
```

System-level algorithm comparisons are documented separately in
`backend/offline_evaluation/README.md`.

## Limits

- The rankers use audio features and the current request context, without
  collaborative listener behavior.
- Mood targets are project-defined rules rather than learned user labels.
- MMR measures variety in the eight-feature space, which may differ from
  perceived musical diversity.
- Evidence-based explanations summarize the calculation and are not causal
  claims.
