# NextTrack Frontend

This directory contains the Django templates and static browser files for the
Discover and Analytics pages. It uses native JavaScript modules and the Django
API; there is no separate frontend server or build step.

## Pages

| Route | Template | Purpose |
| --- | --- | --- |
| `/` | `index.html` | Search the catalogue, set recommendation options, and inspect results. |
| `/analytics/` | `analytics.html` | Display the published V2 evaluation snapshot and figures. |

`base.html` provides the shared header, footer, metadata, and base stylesheet.

## Structure

```text
frontend/
|-- base.html
|-- index.html
|-- analytics.html
|-- static/frontend/
|   |-- css/
|   |   |-- base.css
|   |   |-- discover.css
|   |   `-- analytics.css
|   |-- js/
|   |   |-- api.js
|   |   |-- model.js
|   |   |-- discover/
|   |   |   |-- dom.js
|   |   |   |-- history.js
|   |   |   |-- main.js
|   |   |   |-- results.js
|   |   |   |-- search.js
|   |   |   `-- suggestions.js
|   |   `-- analytics/analytics.js
|   `-- analytics/
|       |-- snapshot.json
|       `-- figures/*.svg
`-- tests/
    |-- analytics.test.js
    `-- model.test.js
```

## Discover modules

| Module | Responsibility |
| --- | --- |
| `api.js` | Sends catalogue, search, recommendation, and suggestion requests. |
| `model.js` | Validates settings, builds API payloads, formats scores, and handles result pages. |
| `discover/main.js` | Owns page state and connects the other Discover modules. |
| `discover/history.js` | Adds, removes, reorders, and renders up to five history tracks. |
| `discover/search.js` | Debounces search, cancels stale requests, and supports keyboard selection. |
| `discover/results.js` | Renders loading, errors, recommendations, pagination, Spotify playback, and explanation evidence. |
| `discover/suggestions.js` | Submits track suggestions and shows the review-queue status. |

The Discover page supports Auto, Basic CBF, Context + MMR, and a separate
**Surprise me** Random action. Users can select a mood, optional BPM range,
variety strength, and 5, 10, or 20 results.

During recommendation requests, the buttons are disabled and the results area
shows a visible loading message. A 20-track response is returned in one request
and displayed in two pages of ten. Changing settings after a response marks the
old results as stale.

Listening history is stored only in browser memory. Refreshing the page clears
it. A submitted track suggestion enters the admin review queue and does not
change the active catalogue.

## API calls

| Endpoint | Use |
| --- | --- |
| `GET /api/v1/catalogue/` | Display the active catalogue version and size. |
| `GET /api/v1/tracks/?q=...` | Search by track title or artist. |
| `POST /api/v1/recommendations/` | Generate a recommendation list. |
| `POST /api/v1/track-suggestions/` | Submit a track for admin review. |

Known validation, rate-limit, catalogue, and no-candidate errors are converted
into short messages by `model.js` and `api.js`.

## Analytics assets

`analytics/analytics.js` reads
`static/frontend/analytics/snapshot.json` and renders the verified summary and
five SVG figures. It does not run an experiment or recalculate metrics in the
browser.

Publish a completed evaluation from the repository root with:

```powershell
.\.venv\Scripts\python.exe backend\manage.py publish_analytics_snapshot `
  --input-dir evaluation\v2
```

The publisher verifies the evaluation artifacts before replacing the frontend
snapshot and figure copies.

## Run and test

Start Django from the repository root:

```powershell
.\.venv\Scripts\python.exe backend\manage.py catalogue_status
.\.venv\Scripts\python.exe backend\manage.py runserver
```

Open `http://127.0.0.1:8000/` and
`http://127.0.0.1:8000/analytics/`.

Run the frontend tests:

```powershell
node --test frontend\tests\*.test.js

.\.venv\Scripts\python.exe backend\manage.py test `
  recommendations.tests.test_frontend_page `
  recommendations.tests.test_analytics_page `
  --noinput
```

Manual browser checks should cover English and Chinese search, all four
recommendation choices, 5/10/20 results, loading and error states, suggestion
confirmation, explanation panels, and desktop/mobile layouts.

## Production static files

Production deployment must run:

```bash
python backend/manage.py collectstatic --noinput
```

Django collects these assets into `backend/staticfiles/`. The GCE deployment
serves that directory at `/static/`.
