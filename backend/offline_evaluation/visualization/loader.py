"""Load only verified summaries produced by the experiment layer."""

from __future__ import annotations

from pathlib import Path

from offline_evaluation.experiments.artifacts import (
    ArtifactError,
    load_json,
    verify_outputs,
)
from offline_evaluation.experiments.config import SCHEMA_VERSION


def load_verified_run(run_dir: Path) -> dict:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ArtifactError(f"Missing evaluation manifest: {manifest_path}.")
    manifest = load_json(manifest_path)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ArtifactError("The evaluation manifest schema is not supported.")
    verify_outputs(run_dir, manifest["outputs"])
    return manifest


def load_summary(run_dir: Path, study_name: str):
    path = run_dir / "results" / study_name / "summary.json"
    if not path.is_file():
        raise ArtifactError(f"Study summary is missing: {path}.")
    return load_json(path)


def load_table(run_dir: Path, study_name: str, table_name: str) -> list[dict]:
    path = run_dir / "results" / study_name / f"{table_name}.json"
    if not path.is_file():
        raise ArtifactError(f"Study table is missing: {path}.")
    return load_json(path)["rows"]
