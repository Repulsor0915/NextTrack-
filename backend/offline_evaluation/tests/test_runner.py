from types import SimpleNamespace

from django.test import SimpleTestCase

from offline_evaluation.runner import (
    comparison_configs,
    diagnostic_metrics,
    summarize_runs,
)
from recommendations.domain.algorithm_config import DEFAULT_ALGORITHM_CONFIG


class RunnerTests(SimpleTestCase):
    def test_comparisons_change_only_the_named_parameter(self):
        baseline = DEFAULT_ALGORITHM_CONFIG
        variants = comparison_configs(baseline)
        self.assertEqual(len(variants), 4)
        baseline_fields = baseline.to_dict()
        for name, variant in variants.items():
            changed = {
                field
                for field, value in variant.to_dict().items()
                if value != baseline_fields[field] and field != "name"
            }
            expected = {
                "equal_feature_weights": {"feature_weights"},
                "euclidean_relevance": {"relevance_similarity_metric"},
                "equal_history_mood_ratio": {
                    "history_relevance_weight",
                    "mood_relevance_weight",
                },
                "mmr_60_40": {"default_diversity_strength"},
            }
            self.assertEqual(changed, expected[name])

    def test_diagnostic_metrics_are_bounded_and_not_algorithm_scores(self):
        vector_a = {
            "tempo": 0.2, "energy": 0.2, "valence": 0.2,
            "danceability": 0.2, "acousticness": 0.8,
            "instrumentalness": 0.1, "loudness": 0.2, "speechiness": 0.1,
        }
        vector_b = {**vector_a, "energy": 0.8, "valence": 0.8}
        vectors = {"history": vector_a, "a": vector_a, "b": vector_b}
        tracks = {
            "a": SimpleNamespace(artist="Artist A"),
            "b": SimpleNamespace(artist="Artist B"),
        }
        metrics = diagnostic_metrics(
            recommended_ids=["a", "b"],
            history_ids=["history"],
            mood="happy",
            tracks=tracks,
            vectors=vectors,
            reference_config=DEFAULT_ALGORITHM_CONFIG,
            processing_ms=12.0,
        )
        for name in (
            "history_match", "mood_match", "intra_list_diversity",
            "distinct_artist_fraction",
        ):
            self.assertGreaterEqual(metrics[name], 0)
            self.assertLessEqual(metrics[name], 1)
        self.assertEqual(metrics["distinct_artist_fraction"], 1.0)
        self.assertGreater(metrics["intra_list_diversity"], 0)

    def test_summary_counts_coverage_and_missing_mood_metrics(self):
        def run(seed, track_id):
            return {
                "algorithm": "random", "category": "single_track_history",
                "scenario_id": "single", "seed": seed,
                "recommendations": [{"track": {"id": track_id}}],
                "metrics": {
                    "history_match": 0.5,
                    "mood_match": None,
                    "intra_list_diversity": None,
                    "distinct_artist_fraction": 1.0,
                    "processing_ms": 2.0,
                },
            }
        summary = summarize_runs([run(1, "a"), run(2, "b")], pool_count=10)
        self.assertEqual(summary["run_count"], 2)
        row = summary["groups"][0]
        self.assertEqual(row["scenario_count"], 1)
        self.assertEqual(row["catalogue_coverage"], 0.2)
        self.assertIsNone(row["mean_mood_match"])
