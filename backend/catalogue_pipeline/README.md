# Catalogue preprocessing

This package is the offline boundary between the immutable raw Spotify Tracks
CSV and the catalogue that can later be imported into Django. It deliberately
contains no recommendation ranking, mood analysis, MMR, API, or evaluation
logic.

## 1. Pipeline overview

The complete data flow is:

```text
data/raw/spotify-tracks-kaggle/dataset.csv
                    |
                    | prepare_catalogue
                    v
data/processed/spotify-tracks-kaggle-full/
                    |
                    | sample_catalogue, seed 221611
                    +--------------------------+
                    v                          v
spotify-tracks-kaggle-test-20/   spotify-tracks-kaggle-test-500/
                    |
                    | optional import_catalogue
                    v
              Django database
```

The full catalogue must be prepared first. The 20- and 500-track catalogues are
then sampled from that same frozen full catalogue, never independently from the
raw CSV.

When the same parent catalogue and seed are used, the selection method ensures:

```text
20-track IDs are a subset of 500-track IDs,
and 500-track IDs are a subset of full-catalogue IDs.
```

## 2. Responsibility of each module

| File | Responsibility |
|---|---|
| `catalogue_pipeline/schema.py` | Declares source-column mappings and the hard-validation policy. |
| `catalogue_pipeline/validation.py` | Validates and converts one raw CSV row. |
| `catalogue_pipeline/pipeline.py` | Builds the full catalogue, deterministic samples, reports, manifests, and checksums. |
| `recommendations/audio_features.py` | Shares the eight-feature names and runtime normalization ranges with the recommender. |
| `recommendations/management/commands/prepare_catalogue.py` | Django CLI wrapper for full preprocessing. |
| `recommendations/management/commands/sample_catalogue.py` | Django CLI wrapper for deterministic sample creation. |
| `recommendations/management/commands/import_catalogue.py` | Optional ingestion step that loads a processed JSON catalogue into Django. |

`prepare_catalogue` and `sample_catalogue` are preprocessing commands.
`import_catalogue` does not clean or sample data; it only imports an already
processed `catalogue.json` into the database.

## 3. Path behaviour

The commands do not contain a hard-coded route to `NextTrack/data`. Every input
and output path is supplied as a positional command-line argument.

The commands below work because they are run from the project root:

```text
C:\Yu Heng\SIM\Year 3 Sem 2\FYP\NextTrack
```

From that working directory, the relative path
`data\raw\spotify-tracks-kaggle\dataset.csv` resolves to the raw CSV inside
this project. Running the same command from another directory would require
adjusted relative paths or absolute paths.

## 4. Prerequisites

Open PowerShell and move to the project root:

```powershell
cd "C:\Yu Heng\SIM\Year 3 Sem 2\FYP\NextTrack"
```

Confirm that the virtual environment and raw file exist:

```powershell
Test-Path .\.venv\Scripts\python.exe
Test-Path data\raw\spotify-tracks-kaggle\dataset.csv
```

Both commands should return `True`.

Verify the immutable raw input:

```powershell
Get-FileHash `
  data\raw\spotify-tracks-kaggle\dataset.csv `
  -Algorithm SHA256
```

Expected SHA-256:

```text
b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd
```

## 5. Generate the three catalogues

### 5.1 Generate the complete filtered catalogue

PowerShell multi-line version:

```powershell
.\.venv\Scripts\python.exe backend\manage.py prepare_catalogue `
  data\raw\spotify-tracks-kaggle\dataset.csv `
  data\processed\spotify-tracks-kaggle-full `
  --catalogue-version spotify-tracks-kaggle-full `
  --retrieved-date 2026-09-04
```

Single-line copy-and-paste version:

```powershell
.\.venv\Scripts\python.exe backend\manage.py prepare_catalogue data\raw\spotify-tracks-kaggle\dataset.csv data\processed\spotify-tracks-kaggle-full --catalogue-version spotify-tracks-kaggle-full --retrieved-date 2026-09-04
```

Argument meanings:

- First positional argument: raw source CSV.
- Second positional argument: new output directory.
- `--catalogue-version`: stable provenance label written to the manifest.
- `--retrieved-date`: date on which this raw source copy was retrieved, not the
  date on which the command happens to be rerun.

Expected output structure:

```text
data/processed/spotify-tracks-kaggle-full/
|-- catalogue.json
|-- preprocessing-report.json
`-- manifest.json
```

The command reads every raw row, applies hard validation, deduplicates by
`track_id`, merges genre labels for duplicate IDs, sorts accepted records by
track ID, and writes all hard-valid unique tracks.

### 5.2 Generate the 20-track smoke-test catalogue

PowerShell multi-line version:

```powershell
.\.venv\Scripts\python.exe backend\manage.py sample_catalogue `
  data\processed\spotify-tracks-kaggle-full\catalogue.json `
  data\processed\spotify-tracks-kaggle-test-20 `
  --limit 20 `
  --seed 221611 `
  --catalogue-version spotify-tracks-kaggle-test-20
```

Single-line copy-and-paste version:

```powershell
.\.venv\Scripts\python.exe backend\manage.py sample_catalogue data\processed\spotify-tracks-kaggle-full\catalogue.json data\processed\spotify-tracks-kaggle-test-20 --limit 20 --seed 221611 --catalogue-version spotify-tracks-kaggle-test-20
```

Expected output structure:

```text
data/processed/spotify-tracks-kaggle-test-20/
|-- catalogue.json
|-- sample-report.json
`-- manifest.json
```

Use this small catalogue for quick import, API, and algorithm smoke tests. It is
not large enough for recommendation-quality conclusions.

### 5.3 Generate the 500-track development catalogue

PowerShell multi-line version:

```powershell
.\.venv\Scripts\python.exe backend\manage.py sample_catalogue `
  data\processed\spotify-tracks-kaggle-full\catalogue.json `
  data\processed\spotify-tracks-kaggle-test-500 `
  --limit 500 `
  --seed 221611 `
  --catalogue-version spotify-tracks-kaggle-test-500
```

Single-line copy-and-paste version:

```powershell
.\.venv\Scripts\python.exe backend\manage.py sample_catalogue data\processed\spotify-tracks-kaggle-full\catalogue.json data\processed\spotify-tracks-kaggle-test-500 --limit 500 --seed 221611 --catalogue-version spotify-tracks-kaggle-test-500
```

Expected output structure:

```text
data/processed/spotify-tracks-kaggle-test-500/
|-- catalogue.json
|-- sample-report.json
`-- manifest.json
```

Use this catalogue as the fixed development candidate pool when comparing
Random, Basic CBF, and Context+MMR under the same inputs. Full-catalogue
performance testing remains a separate experiment.

## 6. Seed behaviour

The sample seed is configurable. It is not a learned recommendation parameter
and it has no effect on audio-feature similarity, mood scoring, or MMR.

For every parent track, the sampler calculates:

```text
SHA-256("<seed>:<track_id>")
```

It sorts tracks by that value and takes the first `limit` tracks. Therefore:

- same parent checksum + same seed + same limit = same selected tracks;
- changing the seed creates a different deterministic sample;
- using one seed for both limits makes the 20-track sample a subset of the
  500-track sample;
- once formal experiments begin, the seed must be frozen and recorded rather
  than changed between algorithms.

`221611` is the current project catalogue-sampling seed. It is an explicit engineering
choice, not a default supplied by Spotify or Django.

## 7. Hard-validation rules

Full preprocessing currently applies only data-validity rules:

- `track_id`, `track_name`, `artists`, and `explicit` must be present.
- Text must fit the Django model limits.
- All eight recommendation features must be present, numeric, and finite.
- `tempo` must be greater than zero.
- `energy`, `valence`, `danceability`, `acousticness`, `instrumentalness`, and
  `speechiness` must be within `[0, 1]`.
- Any finite `loudness` is valid at preprocessing time.
- Blank genre is allowed.
- Duplicate `track_id` values keep the first hard-valid row and merge unique
  non-empty genre labels.
- `explicit` is stored as metadata but does not exclude a track.
- No genre, mood, speechiness, or other content-policy filter is applied.

The catalogue stores validated raw feature values. Min-max normalization and
clamping occur later, when the recommendation system builds feature vectors.

## 8. Output safety and reproducibility

An output directory must either not exist or be empty. The pipeline refuses a
non-empty output directory so that a rerun cannot silently mix or overwrite a
frozen catalogue.

For an experimental rerun, use a new directory and version label. Do not delete
an official frozen version unless that deletion is intentional.

Every full run records:

- raw filename, byte size, and SHA-256;
- validation and deduplication policy;
- eight required features;
- normalization ranges used later at runtime;
- generated-file byte sizes and SHA-256 values.

Every sample run records:

- parent catalogue version and SHA-256;
- seed and limit;
- deterministic selection method;
- generated-file byte sizes and SHA-256 values.

The sampler also checks that its parent `catalogue.json` still matches the
checksum in the parent's `manifest.json`.

## 9. Optional database import

Generating processed data and importing it are separate actions. To replace the
current Django catalogue with the 20-track version:

```powershell
.\.venv\Scripts\python.exe backend\manage.py import_catalogue `
  data\processed\spotify-tracks-kaggle-test-20\catalogue.json `
  --data-source spotify-tracks-kaggle-test-20 `
  --replace
```

For 500 tracks, change both occurrences of the version name to
`spotify-tracks-kaggle-test-500`. For the full catalogue, change them to
`spotify-tracks-kaggle-full`.

`--replace` deletes existing `Track` rows inside the configured database before
the import. It does not delete raw or processed files. Without `--replace`,
matching IDs are updated and new IDs are created, which is not suitable when an
experiment requires one isolated catalogue version.

## 10. Verification commands

After changing preprocessing code, run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend\manage.py test recommendations.tests
```

After generating data, inspect each `manifest.json` and keep its checksums with
the experiment configuration. Do not begin evaluation protocol 2.1 until the
chosen full catalogue and 500-track candidate pool are frozen.

## 11. Code-level execution flow

Running `manage.py prepare_catalogue` makes Django discover the `Command` class
in `recommendations/management/commands/prepare_catalogue.py`. Its `handle()`
method passes the supplied paths and metadata to
`catalogue_pipeline.pipeline.prepare_catalogue()`.

That function performs the following calls and operations:

```text
prepare_catalogue(...)
  |-- resolve and validate the supplied paths
  |-- _require_empty_output_directory(...)
  |-- _read_valid_unique_rows(...)
  |     |-- csv.DictReader(...)
  |     |-- validate_source_row(...) for every source row
  |     `-- deduplicate by track_id and merge genres
  |-- sort all accepted records by track_id
  |-- _write_json(catalogue.json)
  |-- _write_json(preprocessing-report.json)
  `-- _write_json(manifest.json)
```

Running `manage.py sample_catalogue` similarly calls
`catalogue_pipeline.pipeline.sample_catalogue()`. Its central selection is
equivalent to:

```python
selected = sorted(
    parent_catalogue,
    key=lambda track: sha256(f"{seed}:{track['id']}"),
)[:limit]
```

The real implementation uses `hashlib.sha256(...).hexdigest()`, validates the
parent JSON and manifest first, and sorts the selected records by track ID
before writing them. The final track-ID sort affects file ordering only; it
does not change which tracks were selected.

Running `manage.py import_catalogue` follows a different path. It reads the
selected `catalogue.json`, validates each Django model, writes `Track` and
`TrackFeatures`, and labels the rows with `--data-source`. It never calls the
raw-CSV validation or sampling functions.
