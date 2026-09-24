from django.test import SimpleTestCase

from offline_evaluation.experiments.config import EvaluationConfig


class EvaluationConfigTests(SimpleTestCase):
    def test_round_trip_preserves_tuple_fields(self):
        original = EvaluationConfig(candidate_count=40, top_n=5)

        restored = EvaluationConfig.from_dict(original.to_dict())

        self.assertEqual(restored, original)

    def test_rejects_invalid_history_mood_ratio(self):
        with self.assertRaisesRegex(ValueError, "sum to 1"):
            EvaluationConfig(history_mood_ratios=((0.7, 0.7),))
