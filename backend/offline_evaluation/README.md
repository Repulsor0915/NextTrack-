# Offline evaluation application

This Django application is an offline research tool. It does not expose API
endpoints, store user sessions, or duplicate the regression tests under
`recommendations/tests`.

Its responsibilities are:

- create and validate reproducible experiment inputs;
- generate deterministic scenario drafts for human review;
- freeze accepted scenarios with an explicit acceptance record;
- run recommendation configurations after protocol approval; and
- calculate and export offline metrics and manifests.

The implementation covers protocol steps 6-12. The frozen inputs are in
`evaluation/` and results in `evaluation/results/`. The evaluation measures
diagnostic audio-feature proxies only; it does not provide human relevance
labels or prove that a parameter setting is universally best.

Management commands (from the NextTrack root):

```powershell
.\.venv\Scripts\python.exe backend\manage.py prepare_evaluation_protocol --protocol-date 2026-09-19
.\.venv\Scripts\python.exe backend\manage.py freeze_evaluation_scenarios --approval-date 2026-09-19
.\.venv\Scripts\python.exe backend\manage.py run_offline_evaluation --mode baseline
.\.venv\Scripts\python.exe backend\manage.py run_offline_evaluation --mode compare
```

The first two commands are historical for this version; rerunning them in the
same directory is intentionally rejected. Create a new evaluation directory
for a revised protocol, review it again, and keep the present outputs intact.
