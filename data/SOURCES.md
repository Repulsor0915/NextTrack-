# NextTrack data sources

NextTrack's current catalogue, `spotify-merged-v2`, combines two public Spotify
metadata datasets. Raw CSV files are kept locally under `data/raw/` and are not
committed to Git. The committed manifest records their file sizes and SHA-256
checksums so that a catalogue build can be tied to exact source files.

## Source 1: Spotify Tracks Dataset

MaharshiPandya's **Spotify Tracks Dataset** supplies the smaller genre-oriented
source.

- Dataset page: <https://www.kaggle.com/datasets/maharshipandya/-spotify-tracks-dataset>
- Pinned copy: <https://huggingface.co/datasets/maharshipandya/spotify-tracks-dataset/resolve/c4609440b24ac4075899f6e60b33775acbe00827/dataset.csv>
- Pinned revision: `c4609440b24ac4075899f6e60b33775acbe00827`
- Source last updated: `2022-10-22T14:40:15.3Z`
- Retrieved for NextTrack: `2026-09-04`
- Local file: `data/raw/spotify-tracks-kaggle/dataset.csv`
- Rows read: `114,000`
- File size: `20,118,244` bytes
- SHA-256: `b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd`
- Declared licence: Open Database Licence 1.0

The dataset page describes a database containing Spotify track metadata and
audio features; the pinned local CSV contains 114 distinct non-empty genre
labels. Its metadata declares **Database: Open
Database, Contents: © Original Authors** and links to the
[Open Database Licence 1.0](https://opendatacommons.org/licenses/odbl/1-0/).

## Source 2: Almost a million Spotify tracks

Oleg Fostenko's **Almost a million Spotify tracks** supplies the larger source.
The Zenodo record states that the metadata was sampled through the Spotify API
and that each track is identified by `track_id`.

- Creator: Oleg Fostenko
- Affiliation: Lomonosov Moscow State University
- Repository: Zenodo
- Version: `v1`
- Published: `2024-06-03`
- DOI: <https://doi.org/10.5281/zenodo.11453410>
- Dataset page: <https://zenodo.org/records/11453410>
- Retrieved for the merged NextTrack build: `2026-09-23`
- Local file: `data/raw/tracks.csv`
- Rows read: `899,702`
- File size: `931,386,809` bytes
- MD5: `c32dffb8f9a62fec8c5892b464d7ea42`
- SHA-256: `eeebc3b0a5ca488a823f82453b120088ab8bed970e54989c0b1328fac248acb9`
- Licence: Creative Commons Attribution 4.0

Zenodo publishes `tracks.csv` as a 931.4 MB file with MD5
`c32dffb8f9a62fec8c5892b464d7ea42`. The locally stored file has the same MD5,
which confirms that it is the file from this record rather than a similarly
named dataset.

Suggested citation:

> Fostenko, O. (2024). *Almost a million Spotify tracks* (Version v1)
> [Data set]. Zenodo. <https://doi.org/10.5281/zenodo.11453410>

The Zenodo metadata identifies the licence as
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), which requires
appropriate attribution when the material is shared or adapted.

## Field mapping

The two CSV files use different column names. Preprocessing converts both into
one catalogue record before merging them.

| Catalogue field | Kaggle `dataset.csv` | Zenodo `tracks.csv` | Output rule |
|---|---|---|---|
| `id` | `track_id` | `track_id` | Required; deduplication key |
| `title` | `track_name` | `name` | Required |
| `artist_display` | `artists` | `track_artists` | Original text preserved; blank becomes `null` |
| `album_display` | `album_name` | `album_name` | Original text preserved; blank becomes `null` |
| `genres` | `track_genre` | `genres` | Stored as a sorted list of unique non-empty labels |
| `explicit` | `explicit` | `explicit` | Required Boolean metadata |
| `year` | Not available | `album_release_date` | `null` for Kaggle; valid release year extracted from Zenodo |
| `tempo` | `tempo` | `tempo` | Required finite number greater than zero |
| `energy` | `energy` | `energy` | Required number in `[0, 1]` |
| `valence` | `valence` | `valence` | Required number in `[0, 1]` |
| `danceability` | `danceability` | `danceability` | Required number in `[0, 1]` |
| `acousticness` | `acousticness` | `acousticness` | Required number in `[0, 1]` |
| `instrumentalness` | `instrumentalness` | `instrumentalness` | Required number in `[0, 1]` |
| `loudness` | `loudness` | `loudness` | Required finite number |
| `speechiness` | `speechiness` | `speechiness` | Required number in `[0, 1]` |

Artist and album metadata are nullable. Their absence does not make an
otherwise valid track unusable by the recommendation algorithms. Display text
such as "Unknown Artist" belongs to the frontend and is not stored as a
sentinel database row.

## Validation and merge boundary

The implementation is under `backend/catalogue_preprocess/`. It performs:

1. required-column and row-level validation;
2. validation of the eight recommendation features;
3. within-source deduplication by `track_id`, keeping the first hard-valid row
   while merging additional valid genre labels;
4. cross-source merging, keeping the Kaggle record when both sources contain
   the same track ID;
5. deterministic sorting by track ID;
6. generation of `catalogue.json`, `preprocessing-report.json`, and
   `manifest.json` in a new empty directory.

The pipeline applies hard data-validity rules only. It does not remove explicit
tracks, high-speechiness tracks, or particular genres. Raw feature values are
stored in the catalogue and database. Runtime normalization is defined in
`backend/recommendations/audio_features.py`.

## Current merged catalogue

| Item | Value |
|---|---:|
| Catalogue version | `spotify-merged-v2` |
| Total source rows | 1,013,702 |
| Kaggle hard-valid unique rows | 89,582 |
| Zenodo hard-valid unique rows | 898,206 |
| Rejected rows | 25,914 |
| Cross-source overlapping IDs | 23,564 |
| Final catalogue records | 964,224 |
| `catalogue.json` size | 488,158,477 bytes |
| `catalogue.json` SHA-256 | `45652c01108cdce20454d71cc51351b0e3d6e1bef4e47d5219642e55f001e2e2` |

The detailed rejection counts and examples are stored in
`data/processed/spotify-merged-v2/preprocessing-report.json`. The source and
output checksums are stored in the sibling `manifest.json`.

## Distribution boundary

The two source licences and applicable upstream terms remain in effect. Source
attribution must be preserved when the data or an adapted database is shared.
Track, album, and artist metadata are not claimed as project-owned.

The raw CSV files, generated full `catalogue.json`, and SQLite databases are
Git-ignored. The smaller manifest and preprocessing report remain in the
repository so the build inputs, rules, counts, and output checksum can be
audited without committing the complete catalogue.
