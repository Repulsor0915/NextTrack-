# NextTrack Evidence Log

This log records reproducible implementation evidence for the final report. Each
entry must identify the code version, verification commands, observed results,
data version, and known limitations. Claims in Chapters 4 and 5 should link back
to an entry or to a generated artefact referenced by an entry.

## Entry template

```text
Feature or milestone:
Date:
Code commit:
Files or modules:
Endpoint or command:
Input or scenario:
Observed output:
Tests and checks:
Environment:
Data or catalogue version:
Generated artefacts:
Known limitations:
Report sections:
Next action:
```

## 2026-09-02 — Core recommendation engine MVP

**Feature or milestone:** Django REST Framework vertical slice with Track and
TrackFeatures persistence, catalogue import, Random baseline, Basic CBF, and
Context+MMR recommendations.

**Code commit:** `68c6701` (`feat: complete core recommendation engine MVP`)

**Files or modules:**

- `backend/recommendations/models.py`
- `backend/recommendations/migrations/0001_initial.py`
- `backend/recommendations/management/commands/import_catalogue.py`
- `backend/recommendations/domain/`
- `backend/recommendations/services/recommendation_service.py`
- `backend/recommendations/api/`
- `backend/recommendations/tests/`

**Endpoint:**

```text
POST /api/v1/recommendations/
```

**Representative input:**

```json
{
  "history": ["mbid-003"],
  "algorithm": "context_mmr",
  "limit": 5,
  "context": {
    "mood": "happy",
    "bpm": {"min": 60, "max": 140},
    "exploration": 0.3
  }
}
```

**Observed behaviour:**

- Request validation is performed by DRF serializers.
- Unknown track IDs and empty candidate sets return explicit errors.
- History tracks are excluded from recommendations.
- Random returns an unscored baseline selection.
- Basic CBF ranks by weighted cosine similarity to an equal-weight history
  profile.
- Context+MMR combines a recency-weighted profile, heuristic mood fit, BPM hard
  filtering, and diversity-aware Top-N re-ranking.
- Responses include ranking components and deterministic evidence-based
  explanations.

**Verification commands:**

```powershell
.\.venv\Scripts\python.exe backend\manage.py test recommendations --verbosity 1
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend\manage.py showmigrations recommendations
```

**Observed verification result:**

```text
64 tests found
64 tests passed
Django system check: no issues
Model migration drift: none
recommendations.0001_initial: applied
```

**Environment:**

```text
Python 3.14.4
Django 6.1
Django REST Framework 3.18.0
SQLite development database
```

**Catalogue used for development:**

```text
Label: prototype-manual
Tracks: 25
TrackFeatures rows: 25
Runtime database: backend/db.sqlite3 (Git ignored)
```

The development catalogue is imported from the retained Express prototype. It is
only behavioural test data and must not support final recommendation-quality
claims.

**Repository and database hygiene completed:**

- Removed the obsolete tracked root `db.sqlite3`; it did not contain the
  recommendations schema.
- Preserved the active ignored `backend/db.sqlite3` for local development.
- Removed tracked `__pycache__` and `.pyc` files from Git.
- Confirmed `.gitignore` excludes virtual environments, caches, runtime SQLite,
  and `.env` secrets.
- Committed the reproducible migration and catalogue import command instead of a
  runtime database binary.

**Known limitations:**

- The 25-track catalogue has insufficient provenance for the final report.
- Mood targets, feature weights, and exploration mapping are experimental
  defaults that still require review and evaluation.
- `evaluate_recommenders.py`, final dataset ingestion, OpenAPI documentation,
  frontend, production settings, deployment, and final report evidence remain
  incomplete.
- The current README import path depends on the sibling `prototype` directory;
  the final processed catalogue must make the repository independently
  reproducible.
- Production deployment checks are not yet satisfied.

**Report mapping:**

- Chapter 3: implemented architecture, data model, API contract, and algorithm
  separation.
- Chapter 4: Django implementation, import workflow, recommendation service,
  testing strategy, and stateless request flow.
- Chapter 5: software correctness evidence only; recommendation-quality claims
  must wait for the final catalogue and offline evaluation.

**Next action:** Review and freeze the algorithm/API decisions, then perform the
20-track final-dataset ingestion spike before changing the database feature
schema.

## 2026-09-03 - Core algorithm and API semantics review

**Feature or milestone:** Approved and implemented the request-routing, score,
MMR, BPM, history-event, and error-response semantics before final-dataset work.

**Code commit:** `ab6b23b` (`feat: finalize recommendation API semantics`)

**Implemented contract:**

- `algorithm` now defaults to `auto`; history and mood determine the relevance
  model using only the current stateless request.
- Auto without history/mood resolves to Random. History resolves to history CBF;
  mood resolves to mood CBF; history plus mood resolves to contextual CBF.
- Auto content-based paths apply MMR with `diversity_strength = 0.2` by default,
  equivalent to MMR `lambda = 0.8`.
- Explicit `random`, pure `cbf`, and `context_mmr` modes remain available for
  controlled evaluation.
- Public `score` represents relevance. MMR utility remains in
  `components.mmr_score`, while `rank` is the final reranked order.
- Optional BPM input remains an inclusive hard filter. The response uses the
  boolean `bpm_constraint_satisfied`, separate from the track `tempo` feature.
- Parser, validation, and service errors use the same structured envelope while
  retaining field-, ID-, and constraint-specific details.
- History order and repeated play events are preserved; duplicate candidate IDs
  cannot create duplicate results.

**Verification commands:**

```powershell
.\.venv\Scripts\python.exe backend\manage.py test recommendations
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
git diff --check
```

**Observed verification result:**

```text
72 tests found
72 tests passed
Django system check: no issues
Model migration drift: none
Git whitespace-error check: passed
```

**Newly covered scenarios:**

- Auto to Random, history CBF, mood CBF, and combined contextual CBF routing.
- Default MMR diversity strength and its lambda metadata.
- Optional BPM-only filtering followed by Random.
- Repeated history events and duplicate candidate IDs.
- Context response score equals relevance rather than MMR step utility.
- Detailed validation and malformed-JSON error envelopes.

**Known limitations:**

- The parameter values remain provisional pending final-dataset distribution
  checks and offline evaluation.
- The development catalogue remains the 25-track prototype catalogue.
- The legacy request field `exploration` now returns a specific validation error;
  callers must use `diversity_strength`.

**Report mapping:**

- Chapter 3: final API semantics, Auto routing, relevance/reranking separation,
  stateless request design, and error contract.
- Chapter 4: implemented service orchestration, MMR integration, validation, and
  automated testing.
- Chapter 5: software-correctness evidence only; quality evaluation still waits
  for the final dataset.

**Next action (superseded on 2026-09-04):** The data spike remains next, but DEAM
is now a theory/benchmark source rather than the assumed catalogue. See the next
entry for the revised eight-feature dataset criteria.

## 2026-09-04 - Mood theory and implementation boundary

**Feature or milestone:** Archived the DEAM/VA and PAD/VAD design decision, then
separated mood scoring from context orchestration without adding emotion fields
to the database.

**Code commit:** `7d358c7` (`feat: isolate VA-informed mood scoring`)

**Approved boundary:**

- History CBF and mood CBF continue to use the same normalized eight-feature
  track representation.
- DEAM and valence/arousal research support the literature and design rationale;
  DEAM is not assumed to be the final runtime catalogue.
- The implementation does not calculate standalone arousal, does not equate
  energy with ground-truth arousal, and does not add a dominance value.
- PAD/VAD is Future Work only. It would require suitable dominance-labelled
  data, new mood requirements, and separate validation.
- The four project-defined targets remain provisional and are explicitly
  versioned as `va-informed-8-feature-heuristic-v1`.

**Files or modules:**

- `backend/recommendations/domain/mood_model.py`
- `backend/recommendations/domain/context_ranker.py`
- `backend/recommendations/domain/explanations.py`
- `backend/recommendations/services/recommendation_service.py`
- `backend/recommendations/tests/test_rankers.py`
- `backend/recommendations/tests/test_service.py`
- `backend/recommendations/tests/test_api.py`
- `README.md`
- sibling planning record: `../Codex/08_情绪模型与数据方向决策.md`

**Observable API additions:**

- Mood-based responses identify `meta.mood_model`.
- Context result components expose `mood_feature_closeness` for only the
  features that actually participate in the selected mood profile.
- Deterministic explanations cite the closest mood-profile cues rather than
  implying a hidden AI or validated arousal prediction.

**Verification commands:**

```powershell
.\.venv\Scripts\python.exe backend\manage.py test recommendations --verbosity 1
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
git diff --check
```

**Observed verification result:**

```text
74 tests found
74 tests passed
Django system check: no issues
Model migration drift: none
Git whitespace-error check: passed
```

**Database impact:** None. `TrackFeatures` still contains exactly the existing
eight audio-feature fields; no `0002` migration was generated.

**Known limitations:** Mood targets and equal-within-profile mood-fit aggregation
are engineering defaults. They require distribution inspection, sensitivity
analysis, ablation, and offline evaluation on the selected final dataset.

**Next action:** Run an eight-feature final-dataset 20-track spike. Verify exact
source, licence, version, field definitions, units, missingness, duplicates, and
outliers before selecting a dataset or changing the schema.
