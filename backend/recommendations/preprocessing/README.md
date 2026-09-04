# Catalogue preprocessing

This package owns the reproducible boundary between a raw downloadable CSV and
the values consumed by the recommendation algorithms.

## Modules

- `schema.py`: the canonical eight input feature names.
- `catalogue.py`: source-column validation, database-length validation,
  exclusion rules, deduplication, deterministic sampling/all-valid selection,
  distribution summaries, provenance manifest, and checksums.
- `normalization.py`: min-max conversion of raw feature values into the `[0, 1]`
  vector space used by CBF, mood scoring, and MMR.

## Data boundary

`catalogue.json` intentionally stores the validated raw source values. Tempo
therefore remains in BPM and loudness remains in dB. Keeping the raw values
allows auditing and human-readable filters such as BPM.

At feature-vector construction time, each value is transformed with:

```text
normalized = (raw_value - configured_minimum)
             / (configured_maximum - configured_minimum)
normalized = clamp(normalized, 0, 1)
```

This avoids storing two competing feature copies in SQLite. The exact bounds
are defined once in `normalization.py` and written into each newly generated
manifest. The catalogue summary reports how many source values fall outside
the robust tempo and loudness bounds and are therefore clamped.

## Full catalogue command

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe backend\manage.py prepare_catalogue `
  data\raw\spotify-tracks-kaggle-v1\dataset.csv `
  data\processed\spotify-tracks-kaggle-v1-full `
  --all-valid `
  --catalogue-version spotify-tracks-kaggle-v1-full `
  --retrieved-date 2026-09-05 `
  --write-full-exclusions
```

`--all-valid` is distinct from `--limit N`: it retains every row that survives
validation and deduplication, then sorts the result by `track_id`.
