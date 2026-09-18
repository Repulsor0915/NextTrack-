import json
from dataclasses import replace

from django.test import SimpleTestCase

from recommendations.audio_features import FEATURE_NAMES
from recommendations.domain.algorithm_config import (
    ALGORITHM_CONFIG_SCHEMA_VERSION,
    CURRENT_FEATURE_WEIGHTS,
    DEFAULT_ALGORITHM_CONFIG,
    EQUAL_FEATURE_WEIGHTS,
    LITERATURE_INFORMED_FEATURE_WEIGHTS,
    AlgorithmConfig,
)


class AlgorithmConfigTests(SimpleTestCase):
    def test_default_config_preserves_the_current_baseline(self):
        config = DEFAULT_ALGORITHM_CONFIG

        self.assertEqual(config.name, "baseline-current-v1")
        self.assertEqual(dict(config.feature_weights), CURRENT_FEATURE_WEIGHTS)
        self.assertEqual(config.relevance_similarity_metric, "weighted_cosine")
        self.assertEqual(config.diversity_similarity_metric, "weighted_cosine")
        self.assertEqual(config.history_window_size, 5)
        self.assertEqual(config.context_history_strategy, "linear_recency")
        self.assertEqual(config.history_relevance_weight, 0.65)
        self.assertEqual(config.mood_relevance_weight, 0.35)
        self.assertIsNone(config.mood_feature_weights)
        self.assertEqual(config.default_diversity_strength, 0.2)

    def test_config_snapshot_is_json_serialisable(self):
        snapshot = DEFAULT_ALGORITHM_CONFIG.to_dict()

        self.assertEqual(
            snapshot["schema_version"],
            ALGORITHM_CONFIG_SCHEMA_VERSION,
        )
        self.assertIn("baseline-current-v1", json.dumps(snapshot))

    def test_weight_mappings_are_immutable(self):
        with self.assertRaises(TypeError):
            DEFAULT_ALGORITHM_CONFIG.feature_weights["tempo"] = 1.0

    def test_rejects_incomplete_or_non_normalised_weights(self):
        with self.assertRaises(ValueError):
            AlgorithmConfig(feature_weights={"energy": 1.0})

        invalid_total = dict(CURRENT_FEATURE_WEIGHTS)
        invalid_total["tempo"] = 0.5
        with self.assertRaises(ValueError):
            AlgorithmConfig(feature_weights=invalid_total)

    def test_rejects_invalid_context_and_diversity_ratios(self):
        with self.assertRaises(ValueError):
            replace(
                DEFAULT_ALGORITHM_CONFIG,
                history_relevance_weight=0.7,
                mood_relevance_weight=0.4,
            )
        with self.assertRaises(ValueError):
            replace(DEFAULT_ALGORITHM_CONFIG, default_diversity_strength=1.1)

    def test_feature_weight_presets_are_complete_and_normalised(self):
        for weights in (
            CURRENT_FEATURE_WEIGHTS,
            EQUAL_FEATURE_WEIGHTS,
            LITERATURE_INFORMED_FEATURE_WEIGHTS,
        ):
            self.assertEqual(set(weights), set(FEATURE_NAMES))
            self.assertAlmostEqual(sum(weights.values()), 1.0)
