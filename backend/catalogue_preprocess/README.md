# Catalogue preprocessing

`catalogue_preprocess` converts two raw Spotify metadata CSV files into one
deterministic catalogue snapshot that can be verified and imported into
Django. It is an offline data-preparation package. It does not perform
recommendation ranking, mood scoring, MMR reranking, API work, or offline
evaluation.

## Data flow

```text
data/raw/spotify-tracks-kaggle/dataset.csv ─┐
                                             ├─ validate and merge
data/raw/tracks.csv ─────────────────────────┘
                         │
                         ▼
              processed catalogue directory
              ├── catalogue.json
              ├── preprocessing-report.json
              └── manifest.json
                         │
                         ▼
               import_catalogue command
                         │
                         ▼
              db.schema-final.sqlite3
```

The raw files and the generated full `catalogue.json` are Git-ignored. Source
URLs, licences, byte sizes, and checksums are documented in
[`data/SOURCES.md`](../../data/SOURCES.md).

## Package structure

| File | Responsibility |
|---|---|
| `schema.py` | Declares source columns, required fields, feature ranges, and the preprocessing policy. |
| `validation.py` | Validates one normalized source row and creates the shared catalogue record. |
| `sources.py` | Reads CSV files, adapts `tracks.csv`, parses genres and release years, deduplicates each source, and merges the two sources. |
| `process.py` | Coordinates a full build, writes reports and manifests, calculates checksums, and optionally creates deterministic samples. |
| `__init__.py` | Exposes the package's public functions and error class. |

The Django entry points are outside this package:

| Command module | Responsibility |
|---|---|
| `recommendations/management/commands/prepare_catalogue.py` | Calls the two-source preprocessing package. |
| `recommendations/management/commands/sample_catalogue.py` | Creates an optional deterministic subset of a processed catalogue. |
| `recommendations/management/commands/import_catalogue.py` | Verifies and writes a processed snapshot into the database. |
| `recommendations/management/commands/catalogue_status.py` | Reports the active version and database consistency. |

## Input sources

The current merged build uses:

```text
Kaggle: data/raw/spotify-tracks-kaggle/dataset.csv
Zenodo: data/raw/tracks.csv
```

The two files contain different column names. `sources.py` adapts both to the
same validation contract.

| Catalogue value | Kaggle column | Zenodo column |
|---|---|---|
| ID | `track_id` | `track_id` |
| Title | `track_name` | `name` |
| Artist text | `artists` | `track_artists` |
| Album text | `album_name` | `album_name` |
| Genres | `track_genre` | `genres` |
| Release year | Not available | Derived from `album_release_date` |
| Explicit flag | `explicit` | `explicit` |
| Audio features | Same eight feature names | Same eight feature names |

## Unified catalogue record

Every accepted CSV row is converted into this shape:

```json
{
  "id": "spotify-track-id",
  "title": "Track title",
  "artist_display": "Artist A; Artist B",
  "album_display": "Album title",
  "genres": ["pop", "rock"],
  "explicit": false,
  "year": 2024,
  "features": {
    "tempo": 120.0,
    "energy": 0.8,
    "valence": 0.6,
    "danceability": 0.7,
    "acousticness": 0.1,
    "instrumentalness": 0.0,
    "loudness": -6.5,
    "speechiness": 0.05
  }
}
```

`artist_display` and `album_display` preserve the available source text. They
are `null` when the source value is missing. The preprocessing layer does not
create `Unknown Artist` or `Unknown Album` values.

The `year` value is `null` for the Kaggle source. For `tracks.csv`, the pipeline
accepts `YYYY`, `YYYY-MM`, or `YYYY-MM-DD` and stores a year between 1800 and
2100. A missing or invalid date produces `null` rather than rejecting an
otherwise usable track.

## Hard-validation rules

A row must have:

- a non-empty track ID;
- a non-empty title;
- a Boolean `explicit` value;
- all eight audio features;
- numeric and finite feature values;
- a tempo greater than zero;
- energy, valence, danceability, acousticness, instrumentalness, and
  speechiness inside `[0, 1]`.

Loudness may be any finite value at preprocessing time. Artist, album, genre,
and release year are allowed to be missing. The pipeline stores explicit tracks
and does not reject particular genres or high-speechiness content.

Text length rules are applied before import. IDs are limited to 100 characters,
titles to 255 characters, and each genre label to 100 characters.

## Deduplication and source precedence

Within each CSV source:

1. rows are processed in source order;
2. the first hard-valid row for an ID is retained;
3. later rows with the same ID are recorded as duplicates;
4. additional valid genre labels are merged into the retained record;
5. conflicting features, genres, or explicit flags are reported but do not
   replace the first record's other values.

After both sources are processed, records are merged by track ID. When the same
ID exists in both sources, the Kaggle record is kept unchanged. IDs found only
in `tracks.csv` are added. The final list is sorted by track ID so the same
inputs and code produce the same record ordering.

## Build the current catalogue

Run from the repository root. The output directory must not exist or must be
empty:

```powershell
.\.venv\Scripts\python.exe backend\manage.py prepare_catalogue data\raw\spotify-tracks-kaggle\dataset.csv data\processed\spotify-merged-v2-rebuild --catalogue-version spotify-merged-v2 --retrieved-date 2026-09-23 --tracks-csv data\raw\tracks.csv
```

The equivalent command from the `backend` directory is:

```powershell
..\.venv\Scripts\python.exe manage.py prepare_catalogue ..\data\raw\spotify-tracks-kaggle\dataset.csv ..\data\processed\spotify-merged-v2-rebuild --catalogue-version spotify-merged-v2 --retrieved-date 2026-09-23 --tracks-csv ..\data\raw\tracks.csv
```

Argument meanings:

- `source_csv`: Kaggle CSV path;
- `output_directory`: a new directory for the three generated files;
- `--catalogue-version`: stable version stored in the manifest and database;
- `--retrieved-date`: provenance date recorded in the manifest;
- `--tracks-csv`: optional second-source path; supplying it enables the merged
  two-source build.

Without `--tracks-csv`, the command still supports a Kaggle-only catalogue.
That mode is retained for controlled tests and historical reproduction; it is
not the current production catalogue.

## Generated artifacts

### `catalogue.json`

Contains the complete sorted list of unified records. The current file is about
466 MB, so it is stored locally rather than in Git.

### `preprocessing-report.json`

Records total rows, accepted records, rejection counts, up to 100 rejection
examples per source, duplicate conflicts, overlap count, and the merge policy.

### `manifest.json`

Records:

- catalogue version and retrieval date;
- both source filenames, byte sizes, and SHA-256 checksums;
- validation, deduplication, genre, and source-precedence policies;
- the eight required features and runtime normalization ranges;
- output file byte sizes and SHA-256 checksums.

Files are first written to a `.tmp` path and then renamed. This prevents a
partially written JSON file from being mistaken for a completed artifact.
The pipeline also refuses to write into a non-empty directory, preventing a
new run from silently overwriting a frozen version.

## Current verified output

| Measure | Value |
|---|---:|
| Total source rows | 1,013,702 |
| Kaggle hard-valid unique rows | 89,582 |
| Zenodo hard-valid unique rows | 898,206 |
| Rejected source rows | 25,914 |
| Cross-source overlapping IDs | 23,564 |
| Final records | 964,224 |
| Catalogue version | `spotify-merged-v2` |
| Catalogue SHA-256 | `45652c01108cdce20454d71cc51351b0e3d6e1bef4e47d5219642e55f001e2e2` |

These values come from the committed manifest and preprocessing report under
`data/processed/spotify-merged-v2/`.

## Database import

Preprocessing and importing are separate operations. `prepare_catalogue`
creates a portable snapshot; `import_catalogue` verifies that snapshot and
writes it to the active database.

The local development database is:

```text
backend/db.schema-final.sqlite3
```

For a new empty database:

```powershell
.\.venv\Scripts\python.exe backend\manage.py migrate
.\.venv\Scripts\python.exe backend\manage.py import_catalogue data\processed\spotify-merged-v2-rebuild\catalogue.json --dry-run
.\.venv\Scripts\python.exe backend\manage.py import_catalogue data\processed\spotify-merged-v2-rebuild\catalogue.json
.\.venv\Scripts\python.exe backend\manage.py catalogue_status
```

For a populated database, preview a full synchronization first:

```powershell
.\.venv\Scripts\python.exe backend\manage.py import_catalogue data\processed\spotify-merged-v2-rebuild\catalogue.json --prune --dry-run
```

The preview supplies the version, catalogue SHA-256, and plan token required by
the confirmed `--prune` or `--replace` command. Pruning more than 10% requires
the additional `--allow-large-prune` flag. Investigate the deletion count
before using it.

The importer writes `Track`, `TrackFeatures`, `Artist`, `Album`, and
`TrackArtist` records in batches. It preserves `artist_display`, treats the
first parsed artist as `primary_artist`, stores collaborator links in
`TrackArtist`, and leaves missing artists or albums as database `NULL` values.

## Optional deterministic samples

`sample_catalogue` can create a small deterministic subset from a completed
catalogue:

```powershell
.\.venv\Scripts\python.exe backend\manage.py sample_catalogue data\processed\spotify-merged-v2-rebuild\catalogue.json data\processed\spotify-merged-smoke-20 --limit 20 --seed 221611 --catalogue-version spotify-merged-smoke-20
```

The sampler orders every track by the SHA-256 of `<seed>:<track_id>`, takes the
requested number, and records the parent checksum, seed, limit, and method in a
new manifest. It is useful for import smoke tests. The current V2 evaluation
creates its own fixed 500-track candidate pool and does not depend on these old
20/500 catalogue directories.

## Verification

After changing preprocessing code:

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend\manage.py test --noinput
```

After generating or importing a catalogue:

```powershell
.\.venv\Scripts\python.exe backend\manage.py catalogue_status
```

For the current database, `track_count`, `feature_count`, and `record_count`
must all equal 964,224, the only data source must be `spotify-merged-v2`, and
`state_consistent` must be `true`.

There is currently no dedicated automated test module for raw CSV
preprocessing. The test suite covers the verified JSON importer and database
relationships, but a future preprocessing change should add focused tests for
both source adapters, deduplication, merge precedence, and artifact checksums.

## Known boundaries

- Preprocessing loads the accepted catalogue into memory before writing JSON;
  the full two-source build therefore requires substantial memory.
- There is no audit-only flag. To inspect a new run without affecting the
  database, generate into a new empty directory and review its report and
  manifest without calling `import_catalogue`.
- The build records rejection reasons but stores only a limited number of
  example rows in the report.
- Raw feature values may fall outside the narrower runtime normalization ranges.
  The recommender clamps during vector construction; preprocessing only applies
  the hard validity ranges described above.
- Source files and processed snapshots are immutable inputs. Use a new version
  label and output directory when either source or preprocessing policy changes.
