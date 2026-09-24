# NextTrack

NextTrack is an explainable music recommendation system built as a final-year
project. A user can provide recent tracks, a target mood, an optional BPM
range, and a diversity preference. The Django service returns ranked tracks
with the evidence used to produce each result.

The application is stateless from the listener's perspective. It does not
require a public user account and does not store listening sessions. Selected
history is sent with each recommendation request and is cleared when the page
is refreshed.

## 1. Project goals and main features

NextTrack is intended to demonstrate a complete and reproducible recommendation
workflow rather than operate as a streaming platform. It includes:

- title and artist search over an imported catalogue;
- ordered listening history of up to five tracks;
- Happy, Energetic, Calm, and Sad mood targets;
- optional BPM filtering and MMR diversity control;
- Random, Basic CBF, and contextual recommendation paths;
- deterministic, evidence-based explanations for ranked results;
- a public track-suggestion form with staff review in Django Admin;
- a read-only Analytics page generated from verified offline experiments;
- reproducible CSV preprocessing, catalogue import, evaluation, and deployment
  commands.

## 2. Technology stack

| Area | Technology |
|---|---|
| Backend | Python, Django 6.1, Django REST Framework |
| Recommendation code | NumPy and project-owned ranking modules |
| Local database | SQLite |
| Hosted user testing | Waitress, ngrok, WhiteNoise, and SQLite |
| Frontend | Django templates, HTML, CSS, dependency-free JavaScript modules |
| API schema | drf-spectacular |
| Offline evaluation | Django management commands with JSON, JSONL, CSV, and SVG artifacts |
| Tests | Django test runner and Node's built-in test runner |

Python 3.12 or newer is required by the pinned Django version. The verified V2
experiment snapshot was produced with Python 3.14.4 on Windows 11 and SQLite.

## 3. Repository structure

```text
NextTrack/
├── backend/
│   ├── catalogue_preprocess/   CSV validation, merging, and output manifests
│   ├── config/                 Django development and ngrok host settings
│   ├── offline_evaluation/     V2 experiment and visualization code
│   └── recommendations/        Models, API, services, rankers, and import code
├── data/
│   ├── raw/                    Local source CSV files; Git-ignored
│   └── processed/              Manifests, reports, and local catalogue output
├── deploy/ngrok/               Waitress and ngrok startup instructions
├── evaluation/v2/              Verified experiment results and figures
├── frontend/                   Templates, styles, JavaScript, and frontend tests
├── requirements.txt            Local application dependencies
└── requirements-production.txt Additional deployment dependencies
```

More detailed component notes are kept in:

- [catalogue preprocessing](backend/catalogue_preprocess/README.md)
- [recommendation domain](backend/recommendations/domain/README.md)
- [offline evaluation](backend/offline_evaluation/README.md)
- [evaluation artifacts](evaluation/README.md)
- [frontend](frontend/README.md)
- [ngrok hosting](deploy/ngrok/README.md)

## 4. Python environment and dependency installation

Run the following commands from the repository root in CMD:

```cmd
py -3.14 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Python 3.12 or 3.13 may be used when compatible wheels are available. Node.js
is optional and is only needed to run the small frontend test suite. There is
no frontend build step and no runtime npm dependency.

For public user testing through ngrok, also install the host dependencies:

```cmd
python -m pip install -r requirements-production.txt
```

## 5. Default database

Local development uses:

```text
backend/db.schema-final.sqlite3
```

SQLite files are Git-ignored. A fresh clone therefore starts without the
populated development database. The current schema separates catalogue data
into `Track`, `TrackFeatures`, `Artist`, `Album`, and `TrackArtist`, with
`CatalogueState` recording the active verified snapshot.

Create or update the schema and inspect the active catalogue with:

```cmd
python backend\manage.py migrate
python backend\manage.py catalogue_status
```

The current verified database should report catalogue version
`spotify-merged-v2`, 964,224 tracks, 964,224 feature rows, and
`state_consistent: true`.

## 6. Obtaining or generating the catalogue

The full processed `catalogue.json` is approximately 466 MB and is not stored
in Git. To reproduce it, place these source files locally:

```text
data/raw/spotify-tracks-kaggle/dataset.csv
data/raw/tracks.csv
```

Their expected SHA-256 values are recorded in the committed
`data/processed/spotify-merged-v2/manifest.json`. Generate a fresh copy into an
empty output directory:

```cmd
python backend\manage.py prepare_catalogue data\raw\spotify-tracks-kaggle\dataset.csv data\processed\spotify-merged-v2-rebuild --catalogue-version spotify-merged-v2 --retrieved-date 2026-09-23 --tracks-csv data\raw\tracks.csv
```

The command writes:

```text
catalogue.json
preprocessing-report.json
manifest.json
```

It validates the required fields and eight audio features, removes duplicate
track IDs within each source, keeps the Kaggle record when the two sources
share an ID, and adds new IDs from `tracks.csv`. Missing artist and album data
remain `null`; display fallbacks belong to the UI rather than the database.

For a new empty database, import the verified output with:

```cmd
python backend\manage.py migrate
python backend\manage.py import_catalogue data\processed\spotify-merged-v2-rebuild\catalogue.json
python backend\manage.py catalogue_status
```

For a populated database, preview the synchronization first:

```cmd
python backend\manage.py import_catalogue data\processed\spotify-merged-v2-rebuild\catalogue.json --prune --dry-run
```

Review `created`, `updated`, and `deleted`, then use the reported version,
checksum, and preview token with the command's confirmation options. Do not add
`--allow-large-prune` until an unexpectedly large deletion has been explained.

## 7. Starting the application locally

After the schema and catalogue are ready:

```cmd
python backend\manage.py catalogue_status
python backend\manage.py runserver
```

Open <http://127.0.0.1:8000/>. Useful local pages are:

- Discover: <http://127.0.0.1:8000/>
- Analytics: <http://127.0.0.1:8000/analytics/>
- Django Admin: <http://127.0.0.1:8000/admin/>

Create a local administrator when needed:

```cmd
python backend\manage.py createsuperuser
```

`runserver` is only for local development. Stop it before starting the public
Waitress host because both commands use port 8000.

## 8. Web and API routes

### Public routes

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/health/` | Service health |
| `GET` | `/api/v1/catalogue/` | Active catalogue metadata |
| `GET` | `/api/v1/tracks/` | Search and filter tracks |
| `GET` | `/api/v1/tracks/{id}/` | Retrieve one track |
| `POST` | `/api/v1/recommendations/` | Generate recommendations |
| `POST` | `/api/v1/track-suggestions/` | Submit a track for review |

Track search supports partial title or artist text, exact artist and genre
filters, BPM bounds, and page-number pagination. Public routes cannot edit the
active catalogue.

Staff catalogue status and suggestion-review endpoints live under
`/api/v1/staff/` and require staff token authentication. The schema, Swagger,
and ReDoc routes require a superuser session after login through `/admin/`.

## 9. Recommendation methods

| Method | Input | Behaviour |
|---|---|---|
| Random | Optional BPM and exclusions | Samples eligible tracks without a relevance score |
| Basic CBF | At least one history track | Ranks by weighted cosine similarity to recent history |
| Context | History and/or mood | Combines history similarity with mood-feature fit |
| Context + MMR | Context relevance | Reranks to balance relevance and intra-list diversity |

All content-based methods use tempo, energy, valence, danceability,
acousticness, instrumentalness, loudness, and speechiness. History is ordered
oldest to newest and uses at most the five most recent events. The current
combined relevance baseline weights history at 0.65 and mood at 0.35. The
default diversity strength is 0.2, equivalent to an MMR relevance weight of
0.8.

The API's `auto` mode selects a method from the supplied signals. The Discover
page asks for history or mood before using Auto and presents Random as the
separate **Surprise me** action. Recommendation explanations are deterministic
and use recorded scoring evidence; they do not call an LLM.

## 10. V2 offline evaluation

The current evaluation is divided into four studies:

1. catalogue completeness, feature ranges, and mood coverage;
2. configuration sensitivity for CBF, history, context, and MMR settings;
3. comparison of Random, Basic CBF, Context, and Context + MMR;
4. fixed-pool and full-catalogue service latency.

The verified snapshot uses 12 synthetic scenarios, a fixed 500-track candidate
pool, Top-10 lists, and 30 fixed Random seeds per scenario. These metrics are
diagnostic audio-feature proxies, not listener ratings or recommendation
accuracy.

Run a new evaluation into an empty directory:

```cmd
python backend\manage.py run_evaluation --config evaluation\v2-config.json --output-dir evaluation\v2-local
python backend\manage.py build_evaluation_graphs --input-dir evaluation\v2-local
```

After verifying a completed run and its manifest, publish it to the Analytics
page with:

```cmd
python backend\manage.py publish_analytics_snapshot --input-dir evaluation\v2-local
```

The committed verified results remain under `evaluation/v2/`.

## 11. Tests

Run the backend checks and complete Django test suite:

```cmd
python backend\manage.py check
python backend\manage.py test --noinput
```

Run the dependency-free frontend tests:

```cmd
node --test frontend\tests\analytics.test.js frontend\tests\model.test.js
```

The tests cover API validation, ranking behaviour, explanations, catalogue
imports, staff access, evaluation artifacts, page templates, and frontend
request/display helpers. Browser layout and real multi-user performance still
require manual checks.

## 12. Public user testing with ngrok

The hosted FYP profile runs Django through Waitress on the Windows development
machine and publishes it through ngrok. It uses `config.settings_ngrok`,
WhiteNoise, and the existing `backend/db.schema-final.sqlite3` database.

Install `requirements-production.txt` and authenticate the ngrok agent once:

```cmd
ngrok config add-authtoken YOUR_TOKEN
```

Then open two CMD windows from the repository root:

```cmd
deploy\ngrok\start-waitress.cmd
```

```cmd
ngrok http 8000
```

The first command checks Django, collects static assets, and starts Waitress.
The second command maintains the public HTTPS tunnel. Do not run Django's
development server at the same time. The current public address is
<https://breeding-gusty-grower.ngrok-free.dev>.

The hosted settings use `backend/db.schema-final.sqlite3` and create a private,
Git-ignored key at `backend/.nexttrack-secret-key`. Both CMD windows and the
computer must remain running during a user test. See the
[ngrok hosting guide](deploy/ngrok/README.md) for domain changes.

## 13. Data sources and boundaries

The merged catalogue was produced from 1,013,702 source rows:

| Source | Rows read | Hard-valid unique rows | Rejected rows |
|---|---:|---:|---:|
| Kaggle `dataset.csv` | 114,000 | 89,582 | 24,418 |
| `tracks.csv` | 899,702 | 898,206 | 1,496 |

After cross-source overlap handling, the final catalogue contains 964,224
tracks. The pipeline applies hard data validation only. Explicit tracks and
particular genres are retained. Raw feature values are stored, while model
normalization happens at recommendation time.

The sources are MaharshiPandya's Spotify Tracks Dataset and Oleg Fostenko's
Almost a million Spotify tracks. Their attribution, licences, file metadata,
and pinned checksums are recorded in [data/SOURCES.md](data/SOURCES.md). Raw CSV
files, generated full catalogues, and SQLite databases are intentionally
excluded from Git.

## 14. Current limitations

- The synthetic offline scenarios do not provide human relevance labels or
  prove recommendation accuracy.
- Normalized Artist and Album relationships are unavailable for 777,524
  catalogue rows, although the source album display text is preserved for all
  but two tracks. Missing artist relationships still limit artist search,
  collaboration analysis, and artist-diversity interpretation.
- Full-catalogue content scoring on SQLite can take several seconds, especially
  for Context + MMR and larger result sets.
- SQLite with one local Waitress process is suitable for demonstrations and
  small user tests, not horizontal scaling or high write concurrency.
- Spotify playback embeds depend on third-party availability and may be hidden
  by browser content-filtering extensions.
- Track suggestions enter a review queue and are not automatically added to the
  active catalogue.
- The repository does not include raw data, the 466 MB processed catalogue, or
  a populated SQLite database. They must be generated or transferred
  separately.
