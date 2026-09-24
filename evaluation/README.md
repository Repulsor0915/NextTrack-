# Offline evaluation artifacts

This directory contains the current offline evaluation configuration and its
generated results for the active catalogue.

## Current files

- `v2-config.json` defines the experiment settings.
- `v2/protocol.json` records the catalogue snapshot and resolved settings.
- `v2/results/` contains the four study outputs, including raw and summarized
  latency measurements under `v2/results/performance/`.
- `v2/figures/` contains the generated SVG figures.
- `v2/manifest.json` records output counts and checksums.

Tracks with missing artist metadata remain eligible. Artist diversity is
calculated over tracks with a known artist and is accompanied by artist
metadata coverage. Results are not grouped by catalogue source.

## Run the experiments

From the repository root:

```powershell
.\.venv\Scripts\python.exe backend\manage.py run_evaluation `
  --config evaluation\v2-config.json `
  --output-dir evaluation\v2
```

The output directory must be empty before a new full run.

## Build the figures

```powershell
.\.venv\Scripts\python.exe backend\manage.py build_evaluation_graphs `
  --input-dir evaluation\v2
```

The figures are generated from the verified result files. This command does
not rerun the recommendation experiments.
