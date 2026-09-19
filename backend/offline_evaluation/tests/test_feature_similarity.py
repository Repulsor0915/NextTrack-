from types import SimpleNamespace

from django.test import SimpleTestCase

from offline_evaluation.feature_similarity import (
    concentration,
    factorial_comparisons,
    leave_out_weights,
    percentile,
    run_study,
    study_configs,
    summarize_study,
    top10_comparison,
)
from recommendations.domain.algorithm_config import (
    CURRENT_FEATURE_WEIGHTS,
    DEFAULT_ALGORITHM_CONFIG,
    LITERATURE_INFORMED_FEATURE_WEIGHTS,
)


class FeatureSimilarityTests(SimpleTestCase):
    def test_six_primary_cells_and_three_sensitivity_configs(self):
        configs = study_configs(DEFAULT_ALGORITHM_CONFIG)
        self.assertEqual(len(configs), 9)
        self.assertEqual(
            dict(configs["current_cosine"].feature_weights),
            CURRENT_FEATURE_WEIGHTS,
        )
        self.assertEqual(
            dict(configs["literature_euclidean"].feature_weights),
            LITERATURE_INFORMED_FEATURE_WEIGHTS,
        )
        for config in configs.values():
            self.assertAlmostEqual(sum(config.feature_weights.values()), 1.0)
        self.assertEqual(configs["without_energy_cosine"].feature_weights["energy"], 0)
        self.assertEqual(
            configs["without_energy_valence_cosine"].feature_weights["valence"], 0
        )
        self.assertEqual(DEFAULT_ALGORITHM_CONFIG.relevance_similarity_metric,
                         "weighted_cosine")

    def test_leave_out_weights_preserves_relative_remaining_weights(self):
        weights = leave_out_weights(CURRENT_FEATURE_WEIGHTS, {"energy"})
        self.assertAlmostEqual(sum(weights.values()), 1)
        self.assertEqual(weights["energy"], 0)
        self.assertAlmostEqual(weights["valence"], 0.25 / 0.75)
        with self.assertRaises(ValueError):
            leave_out_weights(CURRENT_FEATURE_WEIGHTS, set())

    def test_percentile_and_concentration_definitions(self):
        self.assertAlmostEqual(percentile([0, 1, 2, 3], 0.5), 1.5)
        tracks = [
            SimpleNamespace(artist="A", genres=["pop", "rock"]),
            SimpleNamespace(artist="A", genres=["pop"]),
            SimpleNamespace(artist="B", genres=[]),
        ]
        result = concentration(tracks)
        self.assertAlmostEqual(result["artist_hhi"], 5 / 9)
        self.assertAlmostEqual(result["artist_max_share"], 2 / 3)
        self.assertAlmostEqual(result["genre_hhi"], 14 / 36)

    def test_top10_comparison_handles_entries_exits_and_rank_changes(self):
        result = top10_comparison(["a", "b", "c"], ["b", "d", "a"])
        self.assertEqual(result["top10_overlap_count"], 2)
        self.assertEqual(result["top10_jaccard"], 0.5)
        self.assertEqual(result["mean_absolute_rank_change_common"], 1.5)
        self.assertTrue(result["top1_changed"])
        changes = {row["track_id"]: row for row in result["rank_changes"]}
        self.assertIsNone(changes["c"]["variant_rank"])
        self.assertIsNone(changes["d"]["baseline_rank"])

    def test_study_uses_same_candidates_and_returns_all_raw_scores(self):
        tracks = {"history": self._track("history", 0)}
        for index in range(10):
            track_id = f"candidate-{index:02d}"
            tracks[track_id] = self._track(track_id, index + 1)
        pool = {"track_ids": sorted(set(tracks) - {"history"})}
        scenarios = {
            "scenarios": [
                {
                    "scenario_id": "example",
                    "category": "single_track_history",
                    "applicable_algorithms": ["cbf"],
                    "request_template": {
                        "history": ["history"],
                        "limit": 10,
                        "context": {"mood": "happy"},
                    },
                }
            ]
        }
        config = {
            "algorithms": {
                "algorithm_config": DEFAULT_ALGORITHM_CONFIG.to_dict(),
                "eligible_scenario_counts": {"cbf": 1},
            }
        }
        configurations, runs, metrics, comparisons = run_study(
            protocol_config=config,
            pool=pool,
            scenarios=scenarios,
            tracks=tracks,
            latency_repetitions=1,
        )
        self.assertEqual(len(configurations), 9)
        self.assertEqual(len(runs), 9)
        self.assertEqual(len(metrics), 9)
        self.assertEqual(len(comparisons), 9)
        self.assertEqual(len(summarize_study(metrics, comparisons)), 18)
        paired, paired_summary = factorial_comparisons(runs)
        self.assertEqual(len(paired), 7)
        self.assertEqual(len(paired_summary), 14)
        for run in runs:
            self.assertEqual(len(run["candidate_scores_ranked"]), 10)
            self.assertEqual(len(run["top10"]), 10)
            self.assertEqual(run["requested_mood_ignored_by_cbf"], "happy")
            self.assertTrue(all(0 <= row["score"] <= 1
                                for row in run["candidate_scores_ranked"]))

    @staticmethod
    def _track(track_id, index):
        features = SimpleNamespace(
            tempo=80 + index * 10,
            energy=min(0.1 + index * 0.08, 1),
            valence=min(0.2 + index * 0.07, 1),
            danceability=0.5,
            acousticness=0.4,
            instrumentalness=0.1,
            loudness=-12,
            speechiness=0.05,
        )
        return SimpleNamespace(
            id=track_id,
            title=f"Title {track_id}",
            artist=f"Artist {index}",
            genres=["pop"],
            features=features,
        )
