# NextTrack catalogue source and processing record

Last verified: 2026-09-04

## Selected source

The runtime catalogue is derived from MaharshiPandya's **Spotify Tracks
Dataset**, version 1:

- Canonical dataset page:
  <https://www.kaggle.com/datasets/maharshipandya/-spotify-tracks-dataset>
- Kaggle metadata API:
  <https://www.kaggle.com/api/v1/datasets/view/maharshipandya/-spotify-tracks-dataset>
- Pinned retrieval copy:
  <https://huggingface.co/datasets/maharshipandya/spotify-tracks-dataset/resolve/c4609440b24ac4075899f6e60b33775acbe00827/dataset.csv>
- Pinned retrieval revision: `c4609440b24ac4075899f6e60b33775acbe00827`
- Source version: `1`
- Source last updated: `2022-10-22T14:40:15.3Z`
- Retrieved for this project: `2026-09-04`
- Raw filename: `dataset.csv`
- Raw bytes: `20,118,244`
- Raw SHA-256:
  `b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd`

The raw CSV is deliberately Git-ignored. It can be reconstructed from the
pinned URL and verified against the recorded hash. NextTrack does not call the
Spotify API at recommendation time and does not scrape Spotify webpages.

## Licence and attribution boundary

The Kaggle metadata declares: **Database: Open Database, Contents: © Original
Authors**. The applicable database licence is the Open Database Licence 1.0:
<https://opendatacommons.org/licenses/odbl/1-0/>.

For this project, retain this source record, the licence notice, version, and
checksums with every processed catalogue. ODbL attribution, share-alike, and
database-access obligations should be reviewed before publishing an adapted
database. Track names, artist names, and other individual contents are not
claimed as project-owned. This record documents the declared licence; it is not
legal advice and does not guarantee that every upstream content right is
covered.

The dataset description says its audio features were collected using the
Spotify Web API. Consequently, the processed catalogue supports a reproducible
engineering evaluation, but it must not be described as a first-party Spotify
release or as features calculated by NextTrack.

## Field mapping

One source row is transformed into the existing Django schema as follows:

| NextTrack field | Source column | Rule |
|---|---|---|
| `id` | `track_id` | Required; deduplication key |
| `title` | `track_name` | Required |
| `artist` | `artists` | Required; source text retained |
| `genre` | `track_genre` | Required; source label retained |
| `year` | — | Stored as `null`; source has no release-year column |
| `tempo` | `tempo` | Required finite number, `(0, 300]` BPM |
| `energy` | `energy` | Required finite number in `[0, 1]` |
| `valence` | `valence` | Required finite number in `[0, 1]` |
| `danceability` | `danceability` | Required finite number in `[0, 1]` |
| `acousticness` | `acousticness` | Required finite number in `[0, 1]` |
| `instrumentalness` | `instrumentalness` | Required finite number in `[0, 1]` |
| `loudness` | `loudness` | Required finite number in `[-60, 5]` dB |
| `speechiness` | `speechiness` | Required finite number in `[0, 1]` |

The unnamed CSV index column and unused fields are ignored. The source supplies
all eight features already used by `TrackFeatures`, so no `0002` migration is
needed. No `arousal` or `dominance` column is derived.

## Quality rules and observed results

The pipeline reads all 114,000 rows before selecting a catalogue. It retains
80,598 valid unique tracks and excludes 33,402 source rows. A row may have more
than one reason, so reason counts need not sum exactly to excluded rows.

| Exclusion reason | Count | Rule |
|---|---:|---|
| Duplicate `track_id` | 22,207 | Keep the first valid occurrence |
| Source `explicit=true` | 9,747 | Exclude from this project catalogue |
| `comedy` or `sleep` genre | 2,000 | Exclude obvious non-song categories |
| `speechiness > 0.66` | 91 | Exclude likely spoken-word recordings |
| Tempo outside `(0, 300]` | 19 | Exclude invalid range |
| Missing artist | 1 | Required field |
| Missing title | 1 | Required field |

No required audio-feature value is missing. The existing robust normalisation
ranges cover 99.976% of valid tempo values and 99.454% of valid loudness values;
the current normaliser clamps the small number of more extreme values. All six
other feature ranges cover every retained value. This behaviour must be stated
as clamping rather than silently described as lossless normalisation.

Known limitations:

- Source-provided `explicit` and genre labels may be incomplete or imperfect.
- Track and artist text is retained as supplied and is not a content-safety
  guarantee.
- Keeping the first valid duplicate is deterministic but may discard a later
  genre assignment for the same track.
- The 500-track catalogue is a deterministic random-like sample for this FYP,
  not a popularity-balanced or user-personalised corpus.
- DEAM informs the valence/arousal literature and mood rationale only; no DEAM
  audio or annotations are merged into this catalogue.

## Generated catalogue versions

| Version | Tracks | Artists | Genres | Purpose |
|---|---:|---:|---:|---|
| `spotify-tracks-kaggle-v1-spike-20` | 20 | 20 | 19 | Schema/import/API spike |
| `spotify-tracks-kaggle-v1-500` | 500 | 477 | 107 | Formal FYP catalogue baseline |

Selection is reproducible: candidates are ordered by the SHA-256 value of
`20260904:<track_id>` and the lowest priorities are selected. Output order is
then sorted by track ID. Each version contains:

- `catalogue.json`: importable processed data;
- `dataset-summary.json`: source shape, missing values, feature distributions,
  and selection coverage;
- `excluded-rows-summary.json`: reason totals and the first 100 examples;
- `excluded-rows.json` in the 500-track version: all excluded source rows and
  their reasons;
- `manifest.json`: source identity, raw checksum, transform policy, and SHA-256
  checksum for every generated JSON artefact;
- `smoke-test-result.json`: observed import/API result.

## Reproduction

Run from the `NextTrack` directory in PowerShell after downloading the pinned
CSV to `data/raw/spotify-tracks-kaggle-v1/dataset.csv`:

```powershell
Get-FileHash -Algorithm SHA256 data\raw\spotify-tracks-kaggle-v1\dataset.csv

.\.venv\Scripts\python.exe backend\manage.py prepare_catalogue `
  data\raw\spotify-tracks-kaggle-v1\dataset.csv `
  data\processed\spotify-tracks-kaggle-v1-500 `
  --limit 500 `
  --seed 20260904 `
  --catalogue-version spotify-tracks-kaggle-v1-500 `
  --retrieved-date 2026-09-04 `
  --write-full-exclusions

$env:NEXTTRACK_DB_PATH = "data\processed\spotify-tracks-kaggle-v1-500\verification.sqlite3"
.\.venv\Scripts\python.exe backend\manage.py migrate --noinput
.\.venv\Scripts\python.exe backend\manage.py import_catalogue `
  data\processed\spotify-tracks-kaggle-v1-500\catalogue.json `
  --data-source spotify-tracks-kaggle-v1-500
```

`NEXTTRACK_DB_PATH` keeps verification separate from the developer database.
Generated SQLite files are ignored and are not research artefacts.

## Candidate not selected

MusicOSet was inspected because it exposes all eight required fields and states
that the dataset has open, unrestricted access:
<https://marianaossilva.github.io/DSW2019/>. It was not selected because the
available project page did not identify a sufficiently clear standard licence
for the files. It remains a literature/data comparison candidate, not a mixed
source for the final catalogue.
