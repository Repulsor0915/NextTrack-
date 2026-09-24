from types import SimpleNamespace

from django.test import SimpleTestCase

from offline_evaluation.experiments.metrics import recommendation_metrics


class MetricTests(SimpleTestCase):
    def test_metrics_use_primary_artist_key_and_fixed_vectors(self):
        tracks = {
            "history": SimpleNamespace(
                vector={name: 0.5 for name in (
                    "tempo", "energy", "valence", "danceability",
                    "acousticness", "instrumentalness", "loudness", "speechiness",
                )},
                artist_key="history artist",
            ),
            "a": SimpleNamespace(
                vector={name: 0.5 for name in (
                    "tempo", "energy", "valence", "danceability",
                    "acousticness", "instrumentalness", "loudness", "speechiness",
                )},
                artist_key="artist a",
            ),
            "b": SimpleNamespace(
                vector={name: 0.4 for name in (
                    "tempo", "energy", "valence", "danceability",
                    "acousticness", "instrumentalness", "loudness", "speechiness",
                )},
                artist_key="artist b",
            ),
        }
        recommendations = [
            {"track": {"id": "a"}, "score": 0.9},
            {"track": {"id": "b"}, "score": 0.8},
        ]

        result = recommendation_metrics(
            recommendations=recommendations,
            history_ids=["history"],
            mood="happy",
            tracks=tracks,
            processing_ms=12.5,
        )

        self.assertEqual(result["artist_diversity"], 1.0)
        self.assertEqual(result["artist_metadata_coverage"], 1.0)
        self.assertAlmostEqual(result["mean_relevance"], 0.85)
        self.assertEqual(result["processing_ms"], 12.5)
