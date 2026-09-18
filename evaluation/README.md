# Evaluation artifacts

This directory contains versioned offline-evaluation inputs and, later,
generated results. The source catalogue remains under `data/processed`.

Current protocol stage:

1. `experiment-config.json` records fixed inputs, algorithm settings, seeds,
   environment, and planned outputs.
2. `candidate-pool.json` freezes the 500 candidate track IDs.
3. `scenarios.draft.json` is deterministic but not yet approved.
4. `scenario-review.md` provides the human approval checklist.
5. `protocol-manifest.json` records checksums for the generated protocol files.

Do not rename or copy the draft to `scenarios.json` without human review. Once
approved, a freeze step will update the config and manifest before any baseline
evaluation is run.
