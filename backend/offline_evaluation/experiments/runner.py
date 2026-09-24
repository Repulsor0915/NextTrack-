"""Run selected studies against one shared and frozen experiment context."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

import django
from django.conf import settings
from django.db import connection

from .artifacts import (
    file_metadata,
    require_empty_directory,
    write_csv,
    write_json,
    write_jsonl,
)
from .config import EvaluationConfig, SCHEMA_VERSION, STUDY_NAMES
from .protocol import build_context
from .studies import catalogue, comparison, configuration, performance


STUDIES = {
    "catalogue": catalogue.run,
    "configuration": configuration.run,
    "comparison": comparison.run,
    "performance": performance.run,
}


def _write_study(output_dir: Path, name: str, result) -> dict:
    study_dir = output_dir / "results" / name
    study_dir.mkdir(parents=True, exist_ok=False)
    summary_path = study_dir / "summary.json"
    write_json(summary_path, result.summary)
    if result.runs:
        write_jsonl(study_dir / "runs.jsonl", result.runs)
    for table_name, rows in result.tables.items():
        if table_name != "summary":
            write_json(study_dir / f"{table_name}.json", {"rows": rows})
        write_csv(study_dir / f"{table_name}.csv", rows)
    for detail_name, value in result.details.items():
        write_json(study_dir / f"{detail_name}.json", value)
    return {
        str(path.relative_to(output_dir)).replace("\\", "/"): file_metadata(path)
        for path in sorted(study_dir.iterdir())
        if path.is_file()
    }


def run_evaluation(
    *, config: EvaluationConfig, output_dir: Path, selected_studies: tuple[str, ...],
    progress=None,
) -> Path:
    """Run a complete snapshot without allowing accidental result replacement."""

    unknown = sorted(set(selected_studies) - set(STUDY_NAMES))
    if unknown:
        raise ValueError(f"Unknown studies: {unknown}.")
    require_empty_directory(output_dir)
    if progress:
        progress("Preparing the active catalogue, fixed pool, and 12 scenarios...")
    context = build_context(config)
    protocol_path = output_dir / "protocol.json"
    write_json(protocol_path, context.protocol_document())

    outputs = {
        "protocol.json": file_metadata(protocol_path),
    }
    run_counts = {}
    for study_name in selected_studies:
        if progress:
            progress(f"Running {study_name} study...")
        result = STUDIES[study_name](context)
        outputs.update(_write_study(output_dir, study_name, result))
        run_counts[study_name] = len(result.runs)

    source_root = Path(settings.BASE_DIR) / "offline_evaluation" / "experiments"
    source_files = sorted(source_root.rglob("*.py"))
    manifest_path = output_dir / "manifest.json"
    write_json(
        manifest_path,
        {
            "schema_version": SCHEMA_VERSION,
            "catalogue": context.catalogue_state,
            "selected_studies": list(selected_studies),
            "run_counts": run_counts,
            "environment": {
                "python": sys.version.split()[0],
                "django": django.get_version(),
                "platform": platform.platform(),
                "database_engine": connection.settings_dict["ENGINE"],
            },
            "source_sha256": {
                str(path.relative_to(Path(settings.BASE_DIR).parent)).replace("\\", "/"): file_metadata(path)["sha256"]
                for path in source_files
            },
            "outputs": outputs,
        },
    )
    if progress:
        progress("All requested studies and checksums were written.")
    return manifest_path
