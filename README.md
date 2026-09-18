# NextTrack

Stateless Django REST Framework API for session-informed music recommendation.
The client supplies optional track history, mood, and filters in every request;
the server does not require a user account or store a listening session.

## Local development

Run these commands from the `NextTrack` directory in PowerShell:

```powershell
.\.venv\Scripts\python.exe backend\manage.py migrate
.\.venv\Scripts\python.exe backend\manage.py import_catalogue ..\prototype\data\tracks.json --data-source prototype-manual
.\.venv\Scripts\python.exe backend\manage.py test recommendations
.\.venv\Scripts\python.exe backend\manage.py runserver
```

The recommendation endpoint is:

```text
POST /api/v1/recommendations/
```

## Default Auto mode

`algorithm` is optional and defaults to `auto`. Auto chooses a relevance model
from the signals supplied in the current stateless request:

| Request signals | Resolved method |
|---|---|
| No history and no mood | Random |
| History only | History-based CBF |
| Mood only | Mood-based CBF |
| History and mood | History-and-mood contextual CBF |

BPM does not select an algorithm. It is an optional inclusive hard filter that
is applied to the candidate pool before ranking. A BPM-only request therefore
filters the catalogue and then resolves to Random.

Example mood-only Auto request:

```json
{
  "limit": 5,
  "context": {
    "mood": "happy",
    "bpm": {"min": 60, "max": 140},
    "diversity_strength": 0.2
  }
}
```

When Auto resolves to a content-based method, MMR reranking is enabled by
default with `diversity_strength = 0.2`. This is equivalent to standard MMR
`lambda = 0.8`: 80% relevance weight and 20% diversity-gain weight. Set
`diversity_strength` to `0` to preserve the base relevance order.

The response records both the requested and resolved methods:

```json
{
  "algorithm": "auto",
  "meta": {
    "requested_algorithm": "auto",
    "resolved_algorithm": "context_mmr",
    "relevance_model": "mood_cbf",
    "reranker": "mmr",
    "diversity_strength": 0.2,
    "mmr_lambda": 0.8
  }
}
```

## Explicit experiment modes

Explicit modes remain available for controlled comparisons:

- `random` forces the unscored Random baseline, even if history or mood is
  present.
- `cbf` requires history and runs the pure Basic CBF baseline without MMR.
- `context_mmr` requires history or mood and runs the contextual CBF scorer
  followed by MMR.

Example Basic CBF baseline request:

```json
{
  "history": ["mbid-003"],
  "algorithm": "cbf",
  "limit": 3,
  "candidate_ids": [
    "mbid-003",
    "mbid-004",
    "mbid-006",
    "mbid-012",
    "mbid-025"
  ]
}
```

Example explicit Context+MMR request:

```json
{
  "history": ["mbid-003"],
  "algorithm": "context_mmr",
  "limit": 5,
  "context": {
    "mood": "happy",
    "bpm": {"min": 60, "max": 140},
    "diversity_strength": 0.3
  }
}
```

## Contract details

- History is ordered from oldest to newest. Repeated IDs represent repeated
  play events and are intentionally preserved.
- History tracks are excluded from the returned candidates.
- Duplicate `candidate_ids` do not produce duplicate recommendations.
- Missing or `null` `candidate_ids` means the full catalogue; an empty list is
  an empty candidate pool.
- Basic CBF averages at most the five most recent history events. Contextual CBF
  uses a linearly recency-weighted profile of the same maximum size.
- When history and mood are both supplied to contextual CBF, the current
  provisional relevance formula is 65% history similarity and 35% mood fit.
- The public recommendation `score` is always relevance: `null` for Random,
  history similarity for history CBF, mood fit for mood-only CBF, and contextual
  relevance for combined history and mood. MMR utility remains in
  `components.mmr_score`; `rank` is the final reranked order.
- `bpm_constraint_satisfied` is a boolean eligibility fact, not a scoring
  component. The separate track `tempo` feature may still contribute to CBF.
- Explanations are deterministic and evidence-based; they do not use an AI
  agent or LLM.

## Mood model boundary

Mood recommendation remains content-based and uses the same normalized eight
audio features as history CBF. The current project-defined profiles are
versioned as `va-informed-8-feature-heuristic-v1`. Valence/arousal research,
including DEAM, informs the design rationale, but the API does not calculate or
store a standalone arousal value and does not treat `energy` as ground-truth
arousal. PAD/VAD dominance is not part of the implemented model.

For mood requests, `meta.mood_model` identifies the profile version and each
result exposes `components.mood_feature_closeness`. These values let the
deterministic explanation cite the actual feature cues used in `mood_fit`.

## Internal algorithm configuration

The finalized baseline parameters are collected in the immutable
`AlgorithmConfig` defined in
`backend/recommendations/domain/algorithm_config.py`. This lets the future
offline evaluator inject and record alternative feature weights, similarity
metrics, history:mood ratios, mood-feature weights, and MMR defaults without
editing ranker source code. The public API does not accept this complete
configuration object.

The default configuration is named `baseline-current-v1` and preserves the
behaviour documented above. The detailed algorithm boundary and configurable
experiment choices are recorded in
`backend/recommendations/domain/README.md`.

## Error responses

Parser, serializer, and recommendation-service errors use one envelope while
retaining actionable details:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed. See details for specific fields.",
    "details": {
      "limit": ["Ensure this value is less than or equal to 10."]
    }
  }
}
```

Invalid input and unknown IDs return HTTP 400. A valid request with no eligible
candidates returns HTTP 422. Internal stack traces, database paths, and server
configuration are not exposed.

## Data status

The rebuilt preprocessing contract now produces one frozen full catalogue with
89,566 hard-valid unique tracks from 114,000 raw rows. Two deterministic test
catalogues contain 20 and 500 tracks. Both samples use seed `221611` and are
derived from the full catalogue rather than independently from the raw CSV.

See [`data/SOURCES.md`](data/SOURCES.md) for provenance, the declared database
licence, raw checksum, field mapping, and the current preprocessing boundary.
Raw downloads and SQLite databases are intentionally Git-ignored.

The pipeline separates hard data validation from content policy. It requires
the eight recommendation features, validates their numeric values, and
deduplicates by track ID. It does not remove explicit tracks or particular
genres. The complete manual workflow, commands, path behaviour, seed rules,
outputs, and optional database import are documented in
[`backend/catalogue_pipeline/README.md`](backend/catalogue_pipeline/README.md).

A verified manual run produced full catalogue checksum
`82bd95b1e5d4e983f172af116904740bb43eb599f5d7e37cd6e0f558f84de65b`.
The full, 20-track, and 500-track processed catalogues are now present and their
manifest checksums have been verified. Algorithm evaluation remains a separate
next stage.
