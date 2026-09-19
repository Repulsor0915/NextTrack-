# Feature/similarity study versions

`feature-similarity-v1/` is an initial local generated draft (ignored by Git).
It contains the six
primary configurations and three sensitivity checks but no fixed-weight /
fixed-metric paired-comparison tables. It is retained, not the final 2.2
deliverable.

`feature-similarity-v2/` is the versioned, complete 2.2 study, including the 3x2 matrix,
energy/valence sensitivity checks, candidate-score distributions, Top-10
comparisons, factorial paired comparisons, checksums, and interpretation.
It is generated into a new directory so neither the draft nor the earlier
offline baseline is overwritten.

The main six cells are current/equal/literature-informed feature weights x
weighted cosine/weighted Euclidean similarity. Three additional cosine runs
exclude energy, valence, or both and re-normalize remaining weights. The
literature-informed preset is for experimental comparison only; it comes
from another prediction task and is not a proven optimum for NextTrack.

`runs.json` contains all 500 raw candidate scores plus Top-10 explanations for
each run. `scenario-metrics.*` contains score distributions, artist/genre
concentration, fixed-reference history match, and ranking-only latency.
`comparisons.*` compares every run with current+cosine. The
`factorial-comparisons.*` and `factorial-summary.*` files compare weights while
holding the metric fixed, and compare metrics while holding weights fixed.
`summary.*` aggregates by scenario category and over all 17 histories.
