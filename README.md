# NextTrack

Stateless Django REST Framework API for session-informed music recommendation.
The client supplies track history and optional mood/context in every request; the
server does not require a user account or store a listening session.

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

Example Random baseline request:

```json
{
  "history": ["mbid-001"],
  "algorithm": "random",
  "limit": 2,
  "candidate_ids": ["mbid-001", "mbid-002", "mbid-003"]
}
```

Random selection excludes history, honours `candidate_ids`, `limit`, and the BPM
hard filter, but deliberately does not use mood or audio similarity for ranking.
Its `score` is therefore `null`, and its explanation identifies it as a baseline.

Example Basic CBF request:

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

Basic CBF normalizes eight audio features, averages at most the five most recent
history entries into a session profile, and ranks candidates using weighted cosine
similarity. It excludes history and honours the same candidate and BPM constraints
as Random, but deliberately leaves mood and exploration to Context+MMR.

Example Context+MMR request:

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

Context+MMR uses a linearly recency-weighted profile of at most five history
entries. When both history and mood are supplied, contextual relevance is 65%
history similarity and 35% heuristic mood fit. MMR then uses `exploration` to
trade relevance against dissimilarity to tracks already selected for the Top-N
list. A mood-only request is supported when history is empty. Mood targets are
configurable project heuristics and require evaluation; they are not presented as
psychologically validated boundaries.

The current 25-track catalogue is provisional prototype data for development and
parity testing. It must not be presented as the final research dataset or as
verified Spotify data. A documented research dataset will replace it before the
final evaluation.
