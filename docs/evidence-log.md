# NextTrack Evidence Log

## 2026-09-18 — Catalogue preprocessing baseline

### Scope

This entry freezes the catalogue state immediately before evaluation protocol 2.1.
It records preprocessing and smoke-test evidence only; it is not an algorithm
evaluation result.

### Source

- File: `data/raw/spotify-tracks-kaggle/dataset.csv`
- Rows: 114,000
- Bytes: 20,118,244
- SHA-256: `b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd`

### Frozen hard-validation policy

- Require non-empty `track_id`, `track_name`, and `artists` within model limits.
- Require all eight recommendation features to be finite numbers.
- Require `tempo > 0`.
- Require `energy`, `valence`, `danceability`, `acousticness`,
  `instrumentalness`, and `speechiness` to be within `[0, 1]`.
- Allow any finite source `loudness`; normalization/clamping is a runtime concern.
- Allow blank genre; merge, de-duplicate, and sort available genre labels.
- Require `explicit` to be a valid boolean and retain explicit tracks.
- De-duplicate by `track_id`, keeping the first hard-valid row while merging genres.
- Apply no recommendation/content-policy exclusions during preprocessing.

### Full catalogue result

- Version: `spotify-tracks-kaggle-full`
- Hard-valid unique tracks: 89,566
- Rejected source rows: 24,434
- Catalogue SHA-256: `82bd95b1e5d4e983f172af116904740bb43eb599f5d7e37cd6e0f558f84de65b`
- Catalogue bytes: 39,414,578

Rejection reason counts (a row can have more than one reason):

- `duplicate_track_id`: 24,258
- `duplicate_conflicting_genres`: 23,808
- `out_of_range_tempo`: 157
- `too_long_artists`: 18
- `too_long_track_name`: 1
- `missing_artists`: 1
- `missing_track_name`: 1

### Deterministic test catalogues

Both samples were selected from the frozen full catalogue using the lowest
SHA-256 priority of `221611:track_id`.

| Version | Tracks | Catalogue SHA-256 |
| --- | ---: | --- |
| `spotify-tracks-kaggle-test-20` | 20 | `9966891bbeae7b20d756a17012f6977431f1f53face0ba05ddd9c6d8f4779616` |
| `spotify-tracks-kaggle-test-500` | 500 | `b679f39c76eb8e14a9dd16fec999125d966cdc64342af4e0c7100d0e3702c36d` |

Verified relationship: 20-track IDs are a subset of the 500-track IDs, and
the 500-track IDs are a subset of the full catalogue IDs.

### Verification performed

- A second full preprocessing run produced byte-identical catalogue, report,
  and manifest hashes.
- Every full-catalogue record has exactly eight audio features, a boolean
  `explicit` value, and sorted unique `genres`.
- The 20- and 500-track files each imported into a temporary SQLite database.
- Random, Basic CBF, and Context+MMR each returned recommendations from both
  temporary databases.
- The full catalogue imported into the project database with 89,566 `Track`
  rows and 89,566 `TrackFeatures` rows; no feature row is missing.
- A fixed 500-track candidate-pool smoke test returned ten results for Random,
  Basic CBF, and Context+MMR.
- Django checks passed, no uncreated migrations were detected, and all 81 tests
  passed.

### Status

The preprocessing baseline is ready. Formal scenario construction, experiment
configuration, repeated runs, metric aggregation, and performance comparison
belong to evaluation protocol 2.1 and have not been claimed here.

## 2026-09-18 — Recommendation algorithm baseline

### Frozen explicit modes

- `random`: seedable sample without replacement; history and mood do not alter
  its ranking.
- `cbf`: equal profile of at most five recent history events, current
  eight-feature heuristic weights, and weighted cosine similarity; no mood or
  MMR contribution.
- `context_mmr`: linearly recency-weighted history and/or mood relevance,
  followed by MMR diversification.
- `auto` remains request routing and is not counted as a fourth algorithm.

### Baseline configuration

The immutable configuration is named `baseline-current-v1`. It preserves the
existing defaults: weighted cosine relevance, 65:35 history:mood relevance,
equal weights within each mood profile, and MMR diversity strength 0.20
(standard MMR lambda 0.80).

The algorithm layer now permits controlled offline comparisons without source
edits: feature-weight presets, weighted cosine versus normalized weighted
Euclidean relevance, mood feature weights, history:mood ratio, history strategy,
and MMR similarity/default strength. The public API does not accept the complete
configuration object.

### Verification performed

- All 92 recommendation tests passed, including the existing API/service
  regression suite and new configuration, Euclidean-distance, mood-weight, and
  parameter-injection tests.
- Django system checks passed.
- `makemigrations --check --dry-run` reported no model changes.
- Formal offline evaluation has not started; passing regression tests is not
  reported as evidence that one algorithm has better recommendation quality.
