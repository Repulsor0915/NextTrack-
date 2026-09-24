"""Write verified report figures without touching frontend Analytics assets."""

from __future__ import annotations

from pathlib import Path

from offline_evaluation.experiments.artifacts import (
    file_metadata,
    require_empty_directory,
    write_json,
)

from .charts import build_figures
from .loader import load_verified_run


def build_report_figures(run_dir: Path, output_dir: Path | None = None) -> Path:
    manifest = load_verified_run(run_dir)
    destination = output_dir or (run_dir / "figures")
    require_empty_directory(destination)
    figures = build_figures(run_dir)
    for name, contents in figures.items():
        (destination / name).write_text(contents, encoding="utf-8", newline="\n")
    figure_manifest = destination / "manifest.json"
    write_json(
        figure_manifest,
        {
            "schema_version": "nexttrack-evaluation-figures-v2",
            "catalogue": manifest["catalogue"],
            "source_evaluation_manifest": file_metadata(run_dir / "manifest.json"),
            "outputs": {
                name: file_metadata(destination / name) for name in sorted(figures)
            },
        },
    )
    return figure_manifest
