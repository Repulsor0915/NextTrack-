# NextTrack

Stateless Django REST Framework API for session-informed music recommendation.
The client supplies optional track history, mood, and filters in every request;
the server does not require a user account or store a listening session.

## Local development

Run these commands from the `NextTrack` directory in PowerShell:

```powershell
.\.venv\Scripts\python.exe backend\manage.py migrate
.\.venv\Scripts\python.exe backend\manage.py import_catalogue data\processed\spotify-tracks-kaggle-full\catalogue.json
.\.venv\Scripts\python.exe backend\manage.py catalogue_status
.\.venv\Scripts\python.exe backend\manage.py test
.\.venv\Scripts\python.exe backend\manage.py runserver
```

Open `http://127.0.0.1:8000/` for the recommendation page. It supports
track search, ordered listening history, mood and BPM controls, an MMR variety
slider, Auto plus advanced CBF choices, a separate Random discovery button,
and evidence-backed results. The page uses a responsive Soft Indigo layout;
the decorative record motion is disabled for reduced-motion preferences.
The page uses the existing same-origin API without a separate frontend build
step. See [`frontend/README.md`](frontend/README.md) for its code map and test
commands. The separate Analytics page at `/analytics/` is intended to display
a compact, read-only snapshot of frozen results and verified figures. Browser
acceptance is pending because the user's page currently remains in its loading
state. The page does not run new experiments or publish raw runs; see
[`frontend/README.md`](frontend/README.md) for its sources and update process.

The API entry points are:

```text
GET  /health/
GET  /api/v1/catalogue/
GET  /api/v1/tracks/
GET  /api/v1/tracks/{id}/
POST /api/v1/recommendations/
POST /api/v1/track-suggestions/
GET  /api/v1/schema/
GET  /api/v1/docs/swagger/
GET  /api/v1/docs/redoc/
```

Track discovery supports title/artist search, exact artist and genre filters,
BPM bounds, and page-number pagination. Public requests cannot write tracks or
change the active catalogue. A submitted track suggestion enters a separate
staff-review queue; review does not automatically import it. Staff status and
suggestion-review endpoints require a staff token. See
[`docs/api-contract-and-access.md`](docs/api-contract-and-access.md) for endpoint contracts, examples,
limits, security settings, and deployment prerequisites. `/api/v1/` itself is
not an index page. The live schema, Swagger, and ReDoc routes require a Django
superuser session; log in at `/admin/` first.

The import command above is for a **new, empty database**. A database from
before Stage 4 should use the verified adoption workflow; changing snapshots
requires an explicit `--replace` or `--prune` preview and confirmation. See
[`docs/stage-4-catalogue-database.md`](docs/stage-4-catalogue-database.md).

Django Admin is available at `/admin/` for staff and superusers. It provides
read-only catalogue inspection and track-suggestion review; it cannot change
the active snapshot. Public recommendations still need no login. See
[`docs/admin-and-catalogue-operations.md`](docs/admin-and-catalogue-operations.md)
for permissions, setup, and the decision to defer bulk upload.

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

For a simpler client payload, `mood`, `bpm`, and `diversity_strength` may also
be supplied at the top level. Do not supply the same field both there and in
`context`.

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
- Each result also exposes `explanation_evidence`, with the unrounded scoring
  evidence, applicable feature targets, relevance and final ranks, and MMR
  selection evidence. `meta.explanation_model_version` identifies its contract.
  See `docs/stage-3-explanation-contract.md` for field and `null` semantics.

## Mood model boundary

Mood recommendation remains content-based and uses the same normalized eight
audio features as history CBF. The current project-defined profiles are
versioned as `va-targets-panda-2021-relieff-weights-v2`. The target values remain
project-defined; feature contributions within each mood use the normalized
Panda et al. (2021) ReliefF importance values for the eight features available
in NextTrack. Valence/arousal research, including DEAM, informs the design
rationale, but the API does not calculate or store a standalone arousal value
and does not treat `energy` as ground-truth arousal. PAD/VAD dominance is not
part of the implemented model.

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

The default configuration is named `baseline-panda-mood-v1`. It preserves the
existing Basic CBF, context-relevance, and MMR defaults while making the
Panda-derived mood feature weights the formal mood calculation. The detailed
algorithm boundary and configurable experiment choices are recorded in
`backend/recommendations/domain/README.md`.

## Offline evaluation protocol draft

Protocol steps 6-8 can be reproduced from the project root with:

```powershell
.\.venv\Scripts\python.exe backend\manage.py prepare_evaluation_protocol `
  --protocol-date 2026-09-19 `
  --seed 221611 `
  --top-n 10 `
  --random-repetitions 30 `
  --expected-candidate-count 500 `
  --coherent-genres pop rock hip-hop
```

Single-line version:

```powershell
.\.venv\Scripts\python.exe backend\manage.py prepare_evaluation_protocol --protocol-date 2026-09-19 --seed 221611 --top-n 10 --random-repetitions 30 --expected-candidate-count 500 --coherent-genres pop rock hip-hop
```

The command creates `evaluation/experiment-config.json`, the fixed
`candidate-pool.json`, `scenarios.draft.json`, a human-readable
`scenario-review.md`, and `protocol-manifest.json`. It refuses to overwrite
these files unless `--force` is supplied. The draft must be reviewed and frozen
as `scenarios.json` before an evaluation runner is implemented or executed.

## Error responses

Parser, serializer, and recommendation-service errors use one envelope while
retaining actionable details:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed. See details for specific fields.",
    "details": {
      "limit": ["Ensure this value is less than or equal to 20."]
    }
  }
}
```

Invalid input and unknown IDs return HTTP 400. A valid request with no eligible
candidates returns HTTP 422. With production `DEBUG=False`, internal stack
traces, database paths, and server configuration are not exposed. Local
`DEBUG=True` is not safe to publish.

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
offline workflow. Stage 2 studies and the reviewed v1 decision are documented
in [`backend/offline_evaluation/README.md`](backend/offline_evaluation/README.md)
and [`docs/stage-2-decision.md`](docs/stage-2-decision.md). The scoring defaults
remain unchanged; API metadata now exposes the reviewed algorithm versions.

The four-path offline comparison and separate full-catalogue latency study are
documented in [`docs/recommender-comparison.md`](docs/recommender-comparison.md).
These results are report evidence, not API responses or user relevance labels.
