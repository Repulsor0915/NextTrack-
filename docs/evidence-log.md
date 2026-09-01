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
