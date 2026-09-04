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

## 2026-09-04 - Final-dataset spike and 500-track catalogue

**Status:** Superseded on 2026-09-05 by the full-catalogue entry below. A full
import exposed source text longer than the Django schema limits, so eligibility
was tightened and the valid count changed from 80,598 to 80,584.

**Feature or milestone:** Completed the provenance-aware eight-feature
20-track ingestion spike and expanded the verified pipeline to the formal
500-track FYP catalogue baseline.

**Code commit:** `73e051f` (`feat: build provenance-aware 500-track catalogue`)

**Checksum portability commit:** `0a6063e` fixes processed JSON to LF across
Git checkouts so the recorded SHA-256 values remain stable on Windows.

**Selected source:** MaharshiPandya, *Spotify Tracks Dataset*, version 1. The
Kaggle metadata declares an Open Database Licence for the database and reserves
contents to their original authors. A pinned Hugging Face retrieval revision is
used to make the exact CSV repeatable.

```text
Source rows: 114,000
Raw bytes: 20,118,244
Raw SHA-256: b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd
Pinned revision: c4609440b24ac4075899f6e60b33775acbe00827
Valid unique tracks: 80,598
Excluded source rows: 33,402
Required audio-feature missing values: 0
```

**Quality/exclusion evidence:**

```text
duplicate_track_id: 22,207
explicit_content: 9,747
non_song_genre (comedy/sleep): 2,000
likely_spoken_word: 91
out_of_range_tempo: 19
missing_artists: 1
missing_track_name: 1
```

A source row may have more than one reason. The 500-track version retains the
complete 33,402-row exclusion report as well as a compact summary.

**Schema decision:** All eight required fields map directly to the existing
`TrackFeatures` model. The source has no release-year field, and the existing
nullable `Track.year` stores `null`. No `arousal` or `dominance` is derived and
no `0002` migration is required.

**Normalisation evidence:** Current robust ranges cover 99.976% of valid tempo
values, 99.454% of valid loudness values, and 100% of the other six fields. The
existing normaliser clamps the small number of more extreme tempo/loudness
values; this is retained as an explicit limitation.

**20-track spike result:**

```text
Tracks imported: 20
TrackFeatures imported: 20
Artists: 20
Genres: 19
Recommendation HTTP status: 200
Returned recommendations: 5
Resolved algorithm: context_mmr
Mood model: va-informed-8-feature-heuristic-v1
```

**500-track expansion result:**

```text
Tracks imported: 500
TrackFeatures imported: 500
Artists: 477
Genres: 107
History ID: 00a5Fzao5KLmrJ68NJUYGF
Recommendation HTTP status: 200
Returned recommendations: 5
Relevance model: history_mood_cbf
Resolved algorithm: context_mmr
Mood model: va-informed-8-feature-heuristic-v1
```

**Verification commands:**

```powershell
.\.venv\Scripts\python.exe backend\manage.py prepare_catalogue `
  data\raw\spotify-tracks-kaggle-v1\dataset.csv `
  data\processed\spotify-tracks-kaggle-v1-500 `
  --limit 500 --seed 20260904 `
  --catalogue-version spotify-tracks-kaggle-v1-500 `
  --retrieved-date 2026-09-04 --write-full-exclusions

.\.venv\Scripts\python.exe backend\manage.py test recommendations --verbosity 1
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
git diff --check
```

**Observed verification result:**

```text
77 tests found
77 tests passed
Django system check: no issues
Model migration drift: none
Git whitespace-error check: passed
```

**Generated artefacts:**

- `data/SOURCES.md`
- `data/processed/spotify-tracks-kaggle-v1-spike-20/`
- `data/processed/spotify-tracks-kaggle-v1-500/catalogue.json`
- `data/processed/spotify-tracks-kaggle-v1-500/dataset-summary.json`
- `data/processed/spotify-tracks-kaggle-v1-500/excluded-rows-summary.json`
- `data/processed/spotify-tracks-kaggle-v1-500/excluded-rows.json`
- `data/processed/spotify-tracks-kaggle-v1-500/manifest.json`
- `data/processed/spotify-tracks-kaggle-v1-500/smoke-test-result.json`

The manifest records the raw checksum and the SHA-256/byte size of each JSON
output. Raw CSV downloads and verification SQLite files remain Git-ignored.

**Known limitations:** Source-provided explicit and genre labels may be
imperfect. The deterministic hash sample is reproducible and broad but is not
popularity-balanced. The source says features were collected via Spotify Web
API, so this project must not claim that NextTrack calculated them or that the
dataset is a first-party Spotify release. Dataset readiness does not establish
recommendation quality.

**Report mapping:** Chapter 3 can now state the actual field mapping, quality
rules, fixed catalogue version, and schema decision. Chapter 4 can document the
pipeline and isolated import. Chapter 5 can use the manifest and distribution
summary as data evidence, but quality claims must wait for offline evaluation.

**Next action:** Freeze `spotify-tracks-kaggle-v1-500` and build the repeatable
offline evaluation for Random, Basic CBF, and Context+MMR.

## 2026-09-05 - All-valid final catalogue and preprocessing package

**Feature or milestone:** Retained the 20-track spike and promoted every
schema-compatible valid unique track to the formal final catalogue. Moved raw
catalogue processing and min-max normalisation into a dedicated preprocessing
package.

**Code commit:** `aff5f1d` (`feat: promote all valid tracks to final catalogue`)

**Final data hierarchy:**

```text
Raw source rows: 114,000
Retained 20-track spike: 20
Formal full catalogue: 80,584
Unselected valid tracks in full mode: 0
Distinct artists: 28,153
Distinct genres: 111
Excluded source rows: 33,416
```

The existing 500-track deterministic sample remains as an intermediate
milestone, but it is no longer the final catalogue.

**Final exclusion evidence:**

```text
duplicate_track_id: 22,206
explicit_content: 9,747
non_song_genre: 2,000
likely_spoken_word: 88
out_of_range_tempo: 19
too_long_artists: 18
too_long_track_name: 1
missing_artists: 1
missing_track_name: 1
```

One row can have multiple reasons. Text-length validation was added after the
first full import correctly failed on a 316-character artist value that could
not fit `Track.artist(max_length=255)`. The failed transaction rolled back, the
preprocessor was corrected, and the final import was rerun from zero.

**Preprocessing modules:**

- `backend/recommendations/preprocessing/schema.py`
- `backend/recommendations/preprocessing/catalogue.py`
- `backend/recommendations/preprocessing/normalization.py`
- `backend/recommendations/preprocessing/README.md`

Processed JSON and SQLite preserve the validated raw values. The normalization
module converts them into the recommender's `[0, 1]` vector space using min-max
scaling followed by clamping. Each full manifest records the exact bounds. No
normalized duplicate columns, `arousal`, `dominance`, or `0002` migration were
added.

**Full preparation command:**

```powershell
.\.venv\Scripts\python.exe backend\manage.py prepare_catalogue `
  data\raw\spotify-tracks-kaggle-v1\dataset.csv `
  data\processed\spotify-tracks-kaggle-v1-full `
  --all-valid `
  --catalogue-version spotify-tracks-kaggle-v1-full `
  --retrieved-date 2026-09-05 `
  --write-full-exclusions
```

**Observed full import/API result:**

```text
Track rows: 80,584
TrackFeatures rows: 80,584
Import result: successful
Import time: 160.366 seconds
Recommendation HTTP status: 200
Returned recommendations: 5
Relevance model: history_mood_cbf
Resolved algorithm: context_mmr
Mood model: va-informed-8-feature-heuristic-v1
Service processing time: 7,490.469 ms
Client wall time: 7,635.128 ms
```

**Retained 20-track sample re-verification:**

```text
Track rows: 20
TrackFeatures rows: 20
Recommendation HTTP status: 200
Returned recommendations: 5
Resolved algorithm: context_mmr
Service processing time: 4.272 ms
```

**Verification:**

```text
78 tests found
78 tests passed
Django system check: no issues
Model migration drift: none
All manifest output checksums: matched
All smoke-test history/recommendation IDs: present in their catalogue
```

**Generated full artefacts:**

- `data/processed/spotify-tracks-kaggle-v1-full/catalogue.json`
- `data/processed/spotify-tracks-kaggle-v1-full/dataset-summary.json`
- `data/processed/spotify-tracks-kaggle-v1-full/excluded-rows-summary.json`
- `data/processed/spotify-tracks-kaggle-v1-full/excluded-rows.json`
- `data/processed/spotify-tracks-kaggle-v1-full/manifest.json`
- `data/processed/spotify-tracks-kaggle-v1-full/smoke-test-result.json`

**Known limitation:** The full catalogue is functionally usable but the current
row-by-row importer and exhaustive candidate scoring are slow at this size.
These measurements are smoke baselines rather than a controlled performance
experiment. Bulk import and candidate/vector retrieval optimisation should be
completed before large offline experiment runs or production deployment.

**Next action:** Prepare full-catalogue performance (bulk import and candidate
vector retrieval/caching or fixed evaluation candidate pools), then run the
repeatable Random vs Basic CBF vs Context+MMR offline evaluation.
