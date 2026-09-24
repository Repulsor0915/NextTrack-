"""Atomic result writing and checksum verification for every study."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path


class ArtifactError(ValueError):
    """Raised when an experiment artifact is missing or inconsistent."""


@dataclass
class StudyResult:
    """The storage contract returned by every study."""

    summary: dict | list[dict]
    runs: list[dict] = field(default_factory=list)
    tables: dict[str, list[dict]] = field(default_factory=dict)
    details: dict[str, dict | list] = field(default_factory=dict)


def json_bytes(value) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(json_bytes(value))
    temporary.replace(path)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fieldnames = list(rows[0])
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_metadata(path: Path) -> dict:
    return {"bytes": path.stat().st_size, "sha256": sha256_file(path)}


def verify_outputs(directory: Path, outputs: dict[str, dict]) -> None:
    for relative_name, expected in outputs.items():
        path = directory / relative_name
        if not path.is_file():
            raise ArtifactError(f"Missing artifact: {path}.")
        if path.stat().st_size != expected["bytes"]:
            raise ArtifactError(f"Artifact size differs: {path}.")
        if sha256_file(path) != expected["sha256"]:
            raise ArtifactError(f"Artifact checksum differs: {path}.")


def require_empty_directory(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise ArtifactError(f"Refusing to overwrite non-empty output: {path}.")
    path.mkdir(parents=True, exist_ok=True)
