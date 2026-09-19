from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from offline_evaluation.freeze import freeze_scenarios
from offline_evaluation.protocol import (
    ProtocolValidationError,
    load_json,
    sha256_file,
    write_json,
    write_text,
)


class FreezeTests(SimpleTestCase):
    def test_freeze_records_provisional_approval_and_refuses_repeat(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            evaluation = root / "evaluation-v2"
            evaluation.mkdir()
            pool = {"track_ids": ["candidate"], "track_count": 1}
            draft = {
                "status": "draft_requires_human_review",
                "source": {
                    "candidate_pool_sha256": None,
                    "catalogue_sha256": "catalogue-sha",
                },
                "scenario_count": 1,
                "scenarios": [
                    {
                        "scenario_id": "one",
                        "request_template": {
                            "history": ["history"], "limit": 1, "context": {}
                        },
                        "expected_candidate_count": 1,
                    }
                ],
            }
            write_json(evaluation / "candidate-pool.json", pool)
            draft["source"]["candidate_pool_sha256"] = sha256_file(
                evaluation / "candidate-pool.json"
            )
            write_json(evaluation / "scenarios.draft.json", draft)
            write_text(
                evaluation / "scenario-review.md",
                "Status: **awaiting human approval**\n"
                "- [ ] Approve all scenarios as written.\n"
                "Do not run or freeze the evaluation while any checkbox decision is\n"
                "unresolved.",
            )
            config = {
                "protocol_status": "awaiting_human_scenario_review",
                "catalogue": {"sha256": "catalogue-sha"},
                "candidate_pool": {
                    "sha256": sha256_file(evaluation / "candidate-pool.json")
                },
                "scenarios": {"sha256": sha256_file(evaluation / "scenarios.draft.json")},
                "ranking": {"history_max_length": 5, "top_n": 1},
            }
            write_json(evaluation / "experiment-config.json", config)
            sources = (
                "experiment-config.json", "candidate-pool.json",
                "scenarios.draft.json", "scenario-review.md",
            )
            write_json(
                evaluation / "protocol-manifest.json",
                {
                    "outputs": {
                        name: {"sha256": sha256_file(evaluation / name)}
                        for name in sources
                    }
                },
            )

            result = freeze_scenarios(
                project_root=root,
                evaluation_dir=evaluation,
                approval_date="2026-09-19",
            )
            frozen = load_json(evaluation / "scenarios.json")
            self.assertEqual(result["scenario_count"], 1)
            self.assertEqual(frozen["status"], "frozen_after_user_acceptance")
            self.assertEqual(frozen["approval_record"], "evaluation-v2/scenario-approval.md")
            self.assertEqual(
                load_json(evaluation / "experiment-config.json")["scenarios"]["path"],
                "evaluation-v2/scenarios.json",
            )
            self.assertIn(
                "accepted provisionally",
                (evaluation / "scenario-review.md").read_text(encoding="utf-8"),
            )
            with self.assertRaises(ProtocolValidationError):
                freeze_scenarios(
                    project_root=root,
                    evaluation_dir=evaluation,
                    approval_date="2026-09-19",
                )
