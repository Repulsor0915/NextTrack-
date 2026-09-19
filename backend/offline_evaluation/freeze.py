"""Freeze a user-accepted scenario draft without regenerating its tracks."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .protocol import (
    ProtocolValidationError,
    load_json,
    sha256_file,
    _relative_path,
    write_json,
    write_text,
)


def freeze_scenarios(*, project_root: Path, evaluation_dir: Path, approval_date: str):
    date.fromisoformat(approval_date)
    project_root = project_root.resolve()
    evaluation_dir = evaluation_dir.resolve()
    config_path = evaluation_dir / "experiment-config.json"
    pool_path = evaluation_dir / "candidate-pool.json"
    draft_path = evaluation_dir / "scenarios.draft.json"
    review_path = evaluation_dir / "scenario-review.md"
    manifest_path = evaluation_dir / "protocol-manifest.json"
    frozen_path = evaluation_dir / "scenarios.json"
    approval_path = evaluation_dir / "scenario-approval.md"
    if frozen_path.exists() or approval_path.exists():
        raise ProtocolValidationError("Scenarios are already frozen; refusing overwrite.")

    config = load_json(config_path)
    pool = load_json(pool_path)
    draft = load_json(draft_path)
    manifest = load_json(manifest_path)
    if config["protocol_status"] != "awaiting_human_scenario_review":
        raise ProtocolValidationError("Protocol is not awaiting scenario approval.")
    for path in (config_path, pool_path, draft_path, review_path):
        expected = manifest["outputs"][path.name]["sha256"]
        if sha256_file(path) != expected:
            raise ProtocolValidationError(f"Protocol checksum mismatch: {path.name}.")
    if config["candidate_pool"]["sha256"] != sha256_file(pool_path):
        raise ProtocolValidationError("Candidate pool checksum differs from config.")
    if config["scenarios"]["sha256"] != sha256_file(draft_path):
        raise ProtocolValidationError("Draft checksum differs from config.")
    if draft["source"]["candidate_pool_sha256"] != sha256_file(pool_path):
        raise ProtocolValidationError("Draft refers to another candidate pool.")
    if draft["source"]["catalogue_sha256"] != config["catalogue"]["sha256"]:
        raise ProtocolValidationError("Draft refers to another full catalogue.")
    if draft["scenario_count"] != len(draft["scenarios"]):
        raise ProtocolValidationError("Draft scenario count is inconsistent.")

    pool_ids = set(pool["track_ids"])
    if len(pool_ids) != pool["track_count"]:
        raise ProtocolValidationError("Candidate pool has duplicate or missing IDs.")
    scenario_ids = set()
    for scenario in draft["scenarios"]:
        scenario_id = scenario["scenario_id"]
        if scenario_id in scenario_ids:
            raise ProtocolValidationError(f"Duplicate scenario ID: {scenario_id}.")
        scenario_ids.add(scenario_id)
        history = scenario["request_template"]["history"]
        if len(history) > config["ranking"]["history_max_length"]:
            raise ProtocolValidationError(f"History too long: {scenario_id}.")
        if len(history) != len(set(history)) or pool_ids.intersection(history):
            raise ProtocolValidationError(f"History/pool conflict: {scenario_id}.")
        if scenario["expected_candidate_count"] != len(pool_ids):
            raise ProtocolValidationError(f"Candidate count mismatch: {scenario_id}.")
        if scenario["request_template"]["limit"] != config["ranking"]["top_n"]:
            raise ProtocolValidationError(f"Top-N mismatch: {scenario_id}.")

    draft_sha = sha256_file(draft_path)
    frozen = dict(draft)
    frozen["status"] = "frozen_after_user_acceptance"
    frozen["human_review_required"] = False
    frozen["source_draft_sha256"] = draft_sha
    frozen["approval_date"] = approval_date
    frozen["approval_record"] = _relative_path(approval_path, project_root)
    frozen.pop("instructions", None)

    approval = f"""# Scenario acceptance record

Date: {approval_date}
Decision: accepted provisionally as written; no track substitutions.
Draft SHA-256: `{draft_sha}`
Frozen scenario count: {draft['scenario_count']}

中文备案：项目负责人表示尚未完全理解各情境的具体差别，但暂时接受现有 21 个情境，
不替换歌曲，并要求保留记录。本次接受仅允许建立第一版离线实验基线，
不代表逐首人工核实，也不代表参数已经最优。

The project owner accepted the proposed 21 scenarios while noting that the
practical differences were not fully clear yet. This approval permits the
first offline baseline and comparisons; it is not a claim that the scenarios
or parameter values are optimal or that every title was manually validated.

Known caveats retained in this frozen version:

- `coherent_pop` is numerically/genre-coherent but mixes language and cultural
  contexts (Indian film/pop tracks and GAYLE). Interpret it as an audio-feature
  test, not proof of semantic playlist coherence.
- `transition_energetic_to_calm` contains *The Wheels on the Bus* as a recent
  calm track. Its feature profile fits the selection rule, but it is a
  children's song and can make a real listening playlist feel inappropriate.

If a later qualitative review changes these tracks, create a new protocol
version and keep this baseline intact for reproducibility.
"""
    write_json(frozen_path, frozen)
    write_text(approval_path, approval)
    review = review_path.read_text(encoding="utf-8")
    review = review.replace(
        "Status: **awaiting human approval**",
        "Status: **accepted provisionally**; see `scenario-approval.md` for caveats",
    ).replace(
        "- [ ] Approve all scenarios as written.",
        "- [x] Accept all scenarios as written, provisionally.",
    ).replace(
        "Do not run or freeze the evaluation while any checkbox decision is\n"
        "unresolved.",
        "The accepted copy is `scenarios.json`; this draft checklist is kept "
        "for provenance.",
    )
    write_text(review_path, review)

    config["protocol_status"] = "frozen"
    config["scenarios"].update(
        path=_relative_path(frozen_path, project_root),
        sha256=sha256_file(frozen_path),
        status="frozen_after_user_acceptance",
        source_draft_sha256=draft_sha,
        approval_record=_relative_path(approval_path, project_root),
    )
    write_json(config_path, config)

    manifest["protocol_status"] = "frozen"
    manifest["outputs"] = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in (
            config_path,
            pool_path,
            draft_path,
            review_path,
            frozen_path,
            approval_path,
        )
    }
    write_json(manifest_path, manifest)
    return {
        "scenario_count": len(scenario_ids),
        "frozen_sha256": sha256_file(frozen_path),
        "approval_record": str(approval_path.relative_to(project_root)),
    }
