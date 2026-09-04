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

The original 25-track catalogue remains provisional prototype data for parity
testing. The formal FYP catalogue is now
`data/processed/spotify-tracks-kaggle-v1-full/catalogue.json`: all 80,584
schema-compatible valid unique tracks retained after inspecting all 114,000
source rows. The 20-track spike remains as a small ingestion/API sample and the
500-track version remains as an intermediate milestone. The full processed
directory includes a manifest with source/output
SHA-256 checksums, distribution and missing-value statistics, complete excluded
rows, and an observed API smoke-test result.

See [`data/SOURCES.md`](data/SOURCES.md) for provenance, the declared database
licence, field mapping, quality rules, limitations, and exact reproduction
commands. Raw downloads and verification SQLite databases are intentionally
Git-ignored. The Django schema still uses exactly the existing eight features;
no `arousal`, `dominance`, or `0002` migration was needed. DEAM remains a
VA/Music Emotion Recognition literature and benchmark source, not runtime data.

Prepare and import the full version from a verified raw CSV:

```powershell
.\.venv\Scripts\python.exe backend\manage.py prepare_catalogue `
  data\raw\spotify-tracks-kaggle-v1\dataset.csv `
  data\processed\spotify-tracks-kaggle-v1-full `
  --all-valid `
  --catalogue-version spotify-tracks-kaggle-v1-full `
  --retrieved-date 2026-09-05 --write-full-exclusions

.\.venv\Scripts\python.exe backend\manage.py import_catalogue `
  data\processed\spotify-tracks-kaggle-v1-full\catalogue.json `
  --data-source spotify-tracks-kaggle-v1-full
```

The validated raw values remain in JSON/SQLite while min-max scaling and
clamping are centralized in `recommendations/preprocessing/normalization.py`.
See `recommendations/preprocessing/README.md` for the preprocessing boundary.

This catalogue does not by itself prove recommendation quality. Mood targets,
feature weights, history window, context ratio, diversity strength, and
explanation thresholds remain provisional until offline evaluation and
sensitivity checks.

The full import is functional but currently takes about 160 seconds, and a
local full-catalogue Context+MMR smoke request took about 7.5 seconds. These are
known performance baselines to address before production deployment and large
offline experiment runs.
