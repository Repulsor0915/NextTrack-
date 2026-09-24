# Offline evaluation

This Django app contains the current reproducible offline evaluation.

## Structure

- `experiments/` loads one active catalogue snapshot, runs the studies, computes
  metrics once, and writes checksummed JSON/JSONL/CSV artifacts.
- `visualization/` reads verified summary artifacts and creates report figures.
- `management/commands/` contains thin Django command entry points.

The four studies are:

1. `catalogue`: schema completeness, source counts, feature ranges, and mood
   coverage.
2. `configuration`: compact CBF, history profile, history/mood ratio, and MMR
   parameter comparisons.
3. `comparison`: Random, Basic CBF, Context without MMR, and Context with MMR.
4. `performance`: fixed-pool and full-catalogue service latency.

The quality metrics are diagnostic proxies. They are not human relevance
labels and are not reported as recommendation accuracy.

## Run

From the repository root:

```powershell
.\.venv\Scripts\python.exe backend\manage.py run_evaluation `
  --config evaluation\v2-config.json `
  --output-dir evaluation\v2
```

Run only selected studies while developing:

```powershell
.\.venv\Scripts\python.exe backend\manage.py run_evaluation `
  --output-dir evaluation\v2-check `
  --study catalogue configuration
```

Every output directory must be empty. A run writes `protocol.json`, study
results under `results/`, and a final `manifest.json` with file and source-code
checksums.

`candidate_artist_policy` defaults to `allow_missing`, so tracks with valid
audio features remain eligible when artist metadata is null. Set it to
`require_known` in a JSON config if artist-level diversity is part of the main
comparison. Either choice is recorded in `protocol.json`.

Build the report figures from a completed run:

```powershell
.\.venv\Scripts\python.exe backend\manage.py build_evaluation_graphs `
  --input-dir evaluation\v2
```

Publish the verified compact snapshot and figure copies used by the public
Analytics page:

```powershell
.\.venv\Scripts\python.exe backend\manage.py publish_analytics_snapshot `
  --input-dir evaluation\v2
```
