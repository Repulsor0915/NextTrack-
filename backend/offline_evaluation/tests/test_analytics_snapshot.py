from django.test import SimpleTestCase

from offline_evaluation.visualization.analytics_snapshot import aggregate_pairwise


class AnalyticsSnapshotTests(SimpleTestCase):
    def test_pairwise_rows_are_weighted_by_comparison_count(self):
        result = aggregate_pairwise(
            [
                {
                    "left_method": "random",
                    "right_method": "cbf",
                    "comparison_count": 1,
                    "mean_jaccard": 0.2,
                    "mean_overlap": 2.0,
                    "top1_same_fraction": 0.0,
                },
                {
                    "left_method": "random",
                    "right_method": "cbf",
                    "comparison_count": 3,
                    "mean_jaccard": 0.6,
                    "mean_overlap": 6.0,
                    "top1_same_fraction": 1.0,
                },
            ]
        )[0]

        self.assertEqual(result["scenario_count"], 2)
        self.assertEqual(result["comparison_count"], 4)
        self.assertAlmostEqual(result["mean_top10_jaccard"], 0.5)
        self.assertAlmostEqual(result["mean_overlap_count"], 5.0)
        self.assertAlmostEqual(result["top1_same_fraction"], 0.75)
