# NextTrack data source

## Selected raw source

NextTrack currently selects MaharshiPandya's **Spotify Tracks Dataset**, version
1, as its only catalogue source.

- Dataset page: <https://www.kaggle.com/datasets/maharshipandya/-spotify-tracks-dataset>
- Pinned copy: <https://huggingface.co/datasets/maharshipandya/spotify-tracks-dataset/resolve/c4609440b24ac4075899f6e60b33775acbe00827/dataset.csv>
- Pinned revision: `c4609440b24ac4075899f6e60b33775acbe00827`
- Source last updated: `2022-10-22T14:40:15.3Z`
- Retrieved for NextTrack: `2026-09-04`
- Local raw file: `data/raw/spotify-tracks-kaggle/dataset.csv`
- Raw bytes: `20,118,244`
- Raw SHA-256: `b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd`

The raw file is immutable and Git-ignored. A downloaded copy is accepted only
when its SHA-256 matches the value above.

## Licence boundary

The Kaggle metadata declares **Database: Open Database, Contents: © Original
Authors** and identifies the Open Database Licence 1.0:
<https://opendatacommons.org/licenses/odbl/1-0/>.

Preserve source attribution and review ODbL obligations before distributing an
adapted database. Track and artist names are not claimed as project-owned. This
record documents the declared upstream terms and is not legal advice.

The dataset description states that its audio features were collected using the
Spotify Web API. NextTrack does not call Spotify or scrape Spotify webpages at
recommendation time.

## Current field contract

| NextTrack field | Source column | Hard-validity rule |
|---|---|---|
| `id` | `track_id` | Non-empty; maximum 100 characters; deduplication key |
| `title` | `track_name` | Non-empty; maximum 255 characters |
| `artist` | `artists` | Non-empty; maximum 255 characters |
| `genres` | `track_genre` | Column required; blank allowed; duplicate labels merged into a sorted list |
| `explicit` | `explicit` | Required boolean; stored as metadata; does not exclude the track |
| `year` | — | Stored as `null` because the source has no release year |
| `tempo` | `tempo` | Required finite number greater than zero |
| `energy` | `energy` | Required finite number in `[0, 1]` |
| `valence` | `valence` | Required finite number in `[0, 1]` |
| `danceability` | `danceability` | Required finite number in `[0, 1]` |
| `acousticness` | `acousticness` | Required finite number in `[0, 1]` |
| `instrumentalness` | `instrumentalness` | Required finite number in `[0, 1]` |
| `loudness` | `loudness` | Required finite number |
| `speechiness` | `speechiness` | Required finite number in `[0, 1]` |

## Preprocessing boundary

The offline implementation lives in `backend/catalogue_preprocess/` and performs:

1. Source-column validation.
2. Row-level hard validation.
3. Deduplication by `track_id`, keeping the first hard-valid occurrence.
4. Deterministic full selection in track-ID order.
5. Generation of `catalogue.json`, `preprocessing-report.json`, and
   `manifest.json` in a new empty output directory.

The pipeline stores but does not exclude explicit tracks. It also does not
exclude comedy, sleep, or high-speechiness tracks. Those are possible content-
policy choices, not invalid data.

Raw values are stored in the catalogue and database. Normalization is a runtime
model operation defined in `backend/recommendations/audio_features.py`.

The 20- and 500-track test catalogues must be generated from the frozen full
catalogue with `sample_catalogue`, not independently from the raw CSV. Their
manifests record the parent catalogue checksum and selection seed.

## Frozen catalogue versions

| Version | Tracks | Catalogue SHA-256 | Purpose |
|---|---:|---|---|
| `spotify-tracks-kaggle-full` | 89,566 | `82bd95b1e5d4e983f172af116904740bb43eb599f5d7e37cd6e0f558f84de65b` | Formal full catalogue |
| `spotify-tracks-kaggle-test-20` | 20 | `9966891bbeae7b20d756a17012f6977431f1f53face0ba05ddd9c6d8f4779616` | Fast import/API smoke test |
| `spotify-tracks-kaggle-test-500` | 500 | `b679f39c76eb8e14a9dd16fec999125d966cdc64342af4e0c7100d0e3702c36d` | Development algorithm test pool |

The samples use seed `221611`. The subset relationship was verified as
`20 ⊂ 500 ⊂ full`, and every generated output checksum matches its manifest.

## Other downloaded data

MusicOSet remains under `data/raw/musicoset/` but is not selected, joined, or
used by the current pipeline. It should be removed separately if the project no
longer needs it as a source-comparison candidate.
