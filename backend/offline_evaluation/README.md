# Offline Evaluation

This Django app runs the reproducible offline experiments used to inspect the
NextTrack recommendation system. It creates machine-readable results, report
figures, and the compact snapshot displayed on the Analytics page.

The measurements in this package are diagnostic proxies. They describe how the
algorithms behave on controlled scenarios; they are not human relevance labels
or recommendation accuracy scores.

## 1. Scope and directory boundary

Two similarly named directories have different responsibilities:

- `backend/offline_evaluation/` contains Python code, Django commands, and
  automated tests.
- `evaluation/` contains experiment configuration and generated artifacts.

The recommendation algorithms remain under `backend/recommendations/`. The
evaluation package calls those production algorithms so that an experiment does
not maintain a second recommendation implementation.

## 2. End-to-end flow

```text
active catalogue database
        |
        v
run_evaluation
        |
        +-- protocol.json
        +-- results/catalogue/
        +-- results/configuration/
        +-- results/comparison/
        +-- results/performance/
        +-- manifest.json
                |
                v
build_evaluation_graphs
        |
        +-- figures/*.svg
        +-- figures/manifest.json
                |
                v
publish_analytics_snapshot
        |
        +-- frontend/static/frontend/analytics/snapshot.json
        +-- frontend/static/frontend/analytics/figures/*.svg
```

Each stage reads and verifies the artifacts created by the previous stage.

## 3. Package structure

### Experiment code

| Path | Responsibility |
| --- | --- |
| `experiments/config.py` | Defines the V2 configuration schema, defaults, and JSON loader. |
| `experiments/protocol.py` | Reads the active catalogue and builds deterministic histories, scenarios, and the candidate pool. |
| `experiments/metrics.py` | Computes recommendation quality proxies and grouped summaries. |
| `experiments/artifacts.py` | Writes JSON, JSONL, and CSV atomically; calculates checksums; verifies output files. |
| `experiments/runner.py` | Coordinates selected studies and writes the final run manifest. |
| `experiments/studies/catalogue.py` | Audits catalogue completeness, feature ranges, sources, and mood coverage. |
| `experiments/studies/configuration.py` | Compares algorithm parameter configurations. |
| `experiments/studies/comparison.py` | Compares the four recommendation methods on the fixed protocol. |
| `experiments/studies/performance.py` | Measures fixed-pool and full-catalogue latency. |
| `experiments/studies/common.py` | Shares study helpers for running methods and calculating metrics. |

### Visualization code

| Path | Responsibility |
| --- | --- |
| `visualization/loader.py` | Loads a completed run and verifies its schema and checksums. |
| `visualization/charts.py` | Converts verified summaries into the five report charts. |
| `visualization/svg.py` | Provides the dependency-free SVG drawing helpers. |
| `visualization/publisher.py` | Builds the figures and their checksum manifest. |
| `visualization/analytics_snapshot.py` | Produces the compact frontend snapshot and copies verified figures. |

### Django commands and tests

| Path | Responsibility |
| --- | --- |
| `management/commands/run_evaluation.py` | Command entry point for the experiment runner. |
| `management/commands/build_evaluation_graphs.py` | Command entry point for figure generation. |
| `management/commands/publish_analytics_snapshot.py` | Command entry point for Analytics publication. |
| `tests/` | Tests configuration, protocol generation, metrics, artifact checks, SVG output, and snapshot publication. |

## 4. Requirements and active catalogue

Run commands from the repository root with the project virtual environment.
The active database must have:

- one consistent `CatalogueState`;
- matching `Track` and `TrackFeatures` rows;
- valid values for all eight runtime audio features;
- enough suitable tracks to create the scenario histories and candidate pool.

In Windows CMD, explicitly select the current database before running an
evaluation:

```bat
set "NEXTTRACK_DB_PATH=%CD%\backend\db.schema-final.sqlite3"
.\.venv\Scripts\python.exe backend\manage.py catalogue_status
```

In PowerShell, use:

```powershell
$env:NEXTTRACK_DB_PATH = "$PWD\backend\db.schema-final.sqlite3"
.\.venv\Scripts\python.exe backend\manage.py catalogue_status
```

The committed V2 snapshot was produced from catalogue version
`spotify-merged-v2`, containing 964,224 tracks and 964,224 feature rows. Its
catalogue SHA-256 is recorded in `evaluation/v2/protocol.json` and
`evaluation/v2/manifest.json`.

## 5. V2 experiment configuration

The committed configuration is `evaluation/v2-config.json`.

| Setting | Current value | Meaning |
| --- | ---: | --- |
| `schema_version` | `nexttrack-offline-evaluation-v2` | Artifact schema identifier. |
| `seed` | `221611` | Makes scenario and candidate selection repeatable. |
| `candidate_count` | `500` | Size of the fixed candidate pool. |
| `top_n` | `10` | Number of recommendations evaluated in each run. |
| `random_repetitions` | `30` | Repetitions for the random baseline per scenario. |
| `candidate_artist_policy` | `allow_missing` | Allows candidates whose artist metadata is null. |
| `history_windows` | `1, 5` | History lengths used in the configuration study. |
| `history_mood_ratios` | `1:0, 0.65:0.35, 0.5:0.5, 0:1` | History and mood relevance weights. |
| `mmr_strengths` | `0, 0.2, 0.4` | Diversity strengths used in the MMR study. |
| `performance_fresh_repetitions` | `5` | New service instances timed per method and scope. |
| `performance_warm_repetitions` | `10` | Same-process calls timed per method and scope. |

`candidate_artist_policy=allow_missing` keeps tracks with complete audio
features eligible even when artist metadata is unavailable. Artist-based
metrics therefore report metadata coverage separately. Use `require_known` in
another configuration only when the experiment requires artist metadata for
every candidate.

## 6. Protocol and scenarios

The protocol is created once for a run and shared by the configuration and
method-comparison studies.

1. The runner loads the active catalogue and its eight-feature vectors.
2. It selects five high-fit history tracks for each supported mood. Known,
   distinct artists are used for these histories when available.
3. It creates 12 controlled scenarios:
   - four coherent-history scenarios;
   - four mood-transition scenarios;
   - four mood-only scenarios.
4. It excludes history tracks from the candidate pool.
5. It selects 500 candidates using a stable SHA-256 ordering based on the seed
   and track ID.
6. It writes the catalogue identity, histories, scenarios, candidate IDs, and
   configuration into `protocol.json`.

The fixed candidate pool lets algorithm variants see the same tracks. The
performance study also evaluates the full catalogue to expose database and
candidate-loading cost.

## 7. Studies

### 7.1 Catalogue audit

The `catalogue` study checks the data used by the experiments:

- database, catalogue-state, and feature-row counts;
- missing artist, album, and audio-feature data;
- multi-artist track count;
- source counts stored by the imported catalogue;
- distributions and runtime-range counts for the eight audio features;
- the number of tracks matching each mood profile.

“Values outside runtime ranges” counts source feature values that the runtime
normalizer would clamp before similarity calculations. It is a data-quality and
normalization diagnostic, rather than a rejected-track count.

### 7.2 Configuration study

The `configuration` study changes one group of recommendation settings while
keeping the protocol fixed. It covers:

- current feature weights versus equal weights;
- weighted cosine versus weighted Euclidean relevance;
- a one-track history versus a five-track history;
- equal history aggregation versus linear recency weighting;
- different history-to-mood relevance ratios;
- MMR diversity strengths of 0, 0.2, and 0.4.

The output identifies how each design choice changes the proxy metrics. It does
not automatically declare one configuration universally best.

### 7.3 Method comparison

The `comparison` study evaluates:

1. `random`: random selection from the fixed pool;
2. `cbf`: basic content-based filtering from listening history;
3. `context_no_mmr`: history and mood relevance without MMR reranking;
4. `context_mmr`: history and mood relevance followed by MMR reranking.

Random selection is repeated 30 times per scenario. Basic CBF is evaluated only
on scenarios with history. The two context methods also support mood-only
scenarios. Pairwise output records Top-10 overlap and Jaccard similarity between
methods.

### 7.4 Performance study

The `performance` study measures all four methods under two candidate scopes:

- `fixed_pool`: the same 500 candidates used by the controlled experiments;
- `full_catalogue`: all eligible catalogue tracks except history items.

It records fresh-service and same-process warm timings and reports the minimum,
maximum, median (`p50`), and 95th percentile (`p95`). A fresh service instance
is not a cold Python process, so these measurements do not include server
startup, browser rendering, HTTP transfer, or concurrent-user load.

## 8. Metrics

| Metric | Interpretation |
| --- | --- |
| `history_match` | Mean similarity between selected tracks and the recency-weighted history profile. |
| `mood_match` | Mean fit between selected tracks and the requested mood profile. |
| `intra_list_diversity` | Mean pairwise dissimilarity among selected tracks; a larger value means more varied audio features. |
| `artist_diversity` | Unique known artists divided by recommendations with known artist metadata. |
| `artist_metadata_coverage` | Recommendations with known artist metadata divided by all selected recommendations. |
| `mean_relevance` | Mean relevance score emitted by the recommendation method; unavailable for random results. |
| `pool_coverage` | Unique recommended tracks across grouped runs divided by the candidate-pool size. |
| `processing_ms` | Time measured inside the evaluated recommendation operation. |
| `top_n_jaccard` | Intersection divided by union for two methods' Top-10 track sets. |

History match, mood match, and intra-list diversity use the same normalized
eight-feature representation. These metrics are suitable for controlled system
comparison, but they cannot replace user testing.

## 9. Run a new evaluation

Every output directory must be new or empty. Keep `evaluation/v2/` unchanged as
the committed, verified snapshot and write development runs elsewhere.

Run all four studies:

```powershell
.\.venv\Scripts\python.exe backend\manage.py run_evaluation `
  --config evaluation\v2-config.json `
  --output-dir evaluation\v2-local
```

Run selected studies during development:

```powershell
.\.venv\Scripts\python.exe backend\manage.py run_evaluation `
  --config evaluation\v2-config.json `
  --output-dir evaluation\v2-check `
  --study catalogue configuration
```

Do not reuse either example output directory for a second run unless its old
contents have been intentionally moved or removed.

## 10. Generated artifacts

A complete run has this layout:

```text
evaluation/v2-local/
|-- protocol.json
|-- manifest.json
`-- results/
    |-- catalogue/
    |   |-- summary.json
    |   |-- source-counts.json
    |   |-- source-counts.csv
    |   |-- feature-distributions.json
    |   |-- feature-distributions.csv
    |   |-- mood-coverage.json
    |   `-- mood-coverage.csv
    |-- configuration/
    |   |-- configurations.json
    |   |-- runs.jsonl
    |   |-- summary.json
    |   `-- summary.csv
    |-- comparison/
    |   |-- runs.jsonl
    |   |-- summary.json
    |   |-- summary.csv
    |   |-- pairwise.json
    |   `-- pairwise.csv
    `-- performance/
        |-- runs.jsonl
        |-- summary.json
        `-- summary.csv
```

`manifest.json` records the configuration, catalogue identity, environment,
experiment source checksums, artifact checksums, and run counts. The current
verified V2 snapshot contains 124 configuration runs, 392 comparison runs, and
120 performance runs.

## 11. Build figures

Generate figures only after `run_evaluation` has completed and its manifest is
present:

```powershell
.\.venv\Scripts\python.exe backend\manage.py build_evaluation_graphs `
  --input-dir evaluation\v2-local
```

The command verifies the run and writes:

1. `01-catalogue-clamping.svg`;
2. `02-cbf-configuration.svg`;
3. `03-context-configuration.svg`;
4. `04-method-comparison.svg`;
5. `05-latency.svg`;
6. `figures/manifest.json`.

## 12. Publish the Analytics snapshot

After reviewing the new manifest and figures, publish them to the frontend:

```powershell
.\.venv\Scripts\python.exe backend\manage.py publish_analytics_snapshot `
  --input-dir evaluation\v2-local
```

The command verifies both manifests before replacing the frontend snapshot and
figure copies under `frontend/static/frontend/analytics/`. The Analytics page
reads these static published files; it does not run experiments in the browser.

## 13. Tests

Run the evaluation package tests from the repository root:

```powershell
.\.venv\Scripts\python.exe backend\manage.py test offline_evaluation.tests --noinput
```

Run Django's system check separately:

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
```

The tests cover deterministic configuration and protocol behavior, metric
calculations, atomic artifact handling, checksum verification, SVG escaping and
rendering, and Analytics snapshot publication. They use small fixtures and do
not reproduce the full 964,224-track experiment.

## 14. Reproducibility and limitations

- The seed, catalogue version, catalogue checksum, protocol, source checksums,
  environment, and output checksums are recorded in the run artifacts.
- Changing the database, configuration, or experiment code creates a different
  run and should use a new output directory.
- The imported merged catalogue stores one merged `data_source` value, so the
  catalogue study cannot reconstruct per-input-source counts.
- Artist metrics are less representative when artist metadata coverage is low;
  use `artist_metadata_coverage` when interpreting them.
- Offline similarity and diversity measures show controlled algorithm behavior.
  Conclusions about usefulness and satisfaction require the separate user test.
- Performance results describe the machine and database used for that run and
  should not be presented as universal production latency.
