# Evaluation artifacts

This directory contains versioned offline-evaluation inputs and results. The
source catalogue remains under `data/processed`.

Frozen protocol:

1. `experiment-config.json` records fixed inputs, algorithm settings, seeds,
   environment, and planned outputs.
2. `candidate-pool.json` freezes the 500 candidate track IDs.
3. `scenarios.draft.json` is the deterministic original proposal.
4. `scenario-review.md` is the retained review checklist; `scenario-approval.md`
   records provisional acceptance and the two known caveats.
5. `scenarios.json` is the accepted, frozen copy used for evaluation.
6. `protocol-manifest.json` records checksums for all protocol files.

The accepted draft was frozen on 2026-09-19, without track substitutions. This
is permission to run a first experiment, not evidence that the scenarios or
parameters are optimal. A later replacement requires a new protocol version;
do not overwrite the baseline.

Run from the NextTrack root after importing the full catalogue into SQLite:

```powershell
.\.venv\Scripts\python.exe backend\manage.py run_offline_evaluation --mode baseline
.\.venv\Scripts\python.exe backend\manage.py run_offline_evaluation --mode compare
```

The baseline contains 668 runs: 21 scenarios x 30 seeded random repetitions,
17 CBF runs, and 21 Context+MMR runs. Each parameter variant contains 38
CBF/Context+MMR runs. The runner refuses to overwrite existing result files.
`results/manifest.json` and the comparison manifests record checksums. Wall
time is recorded but can change between runs; track ranking should be stable.

`results/recommendation-runs.json` contains each Top-10 playlist and score
components. `results/summary.json` and `.csv` summarize diagnostic proxies:
history fit, requested-mood fit, within-list audio-feature diversity, distinct
artist fraction, catalogue coverage, and processing time. These are **not**
ground-truth user preferences or recommendation accuracy.

The four comparisons change one dimension at a time: equal eight-feature
weights; Euclidean rather than cosine relevance; history:mood 50:50 rather
than 65:35; and MMR relevance:diversity 60:40 rather than 80:20. MMR changes
do not affect Basic CBF. History:mood ratio only matters when both are present.
All comparisons use the same 500 candidates and 21 scenarios. Random uses the
same 30 seed values for each scenario; because random ignores history and mood,
one seed selects the same playlist in every scenario. Its repetitions measure
sampling variability, not 30 independent user preferences.

`results/interpretation.zh-CN.md` records the first numeric observations and
their limitations in Chinese. The production algorithm remains on the frozen
65:35 context ratio and 80:20 MMR ratio; comparisons do not silently change it.

## Step 2.2: feature weights and similarity metric

The Basic CBF-only 3x2 study is under `studies/feature-similarity-v2/`.
It uses the same 17 frozen history scenarios and 500 candidates, ignores
requested mood (as Basic CBF does), and leaves the production defaults alone.
To reproduce it into a **new empty directory** from the NextTrack root:

```powershell
.\.venv\Scripts\python.exe backend\manage.py run_feature_similarity_study --output-dir evaluation/studies/feature-similarity-reproduction
```

The command refuses to overwrite an existing study and verifies that
`current_cosine` reproduces the previous baseline Top-10 for every scenario.
It writes raw scores for all 500 candidates, Top-10 playlists, per-scenario
metrics, paired 3x2 comparisons, summary JSON/CSV, and a checksum manifest.
Ranking latency is measured after warm-up for five repetitions and excludes
database loading and serialization. The Chinese provisional interpretation
is in `studies/feature-similarity-v2/interpretation.zh-CN.md`.
