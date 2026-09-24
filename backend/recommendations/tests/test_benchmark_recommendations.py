import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import CommandError, call_command
from django.test import TestCase

from recommendations.models import Track, TrackFeatures


class BenchmarkRecommendationsCommandTests(TestCase):
    def setUp(self):
        for track_id in ("track-a", "track-b"):
            track = Track.objects.create(
                id=track_id, title=track_id, artist="Artist", data_source="test-v1"
            )
            TrackFeatures.objects.create(
                track=track, tempo=120, energy=0.7, valence=0.6,
                danceability=0.5, acousticness=0.2, instrumentalness=0.0,
                loudness=-8, speechiness=0.1, feature_source="test-v1",
            )

    def test_writes_reproducible_report(self):
        with TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "benchmark.json"
            call_command(
                "benchmark_recommendations", algorithm="random",
                candidate_limit=2, top_n=1, warmup=0, repeat=2,
                output=output_path, stdout=StringIO(),
            )
            report = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(report["candidate_count"], 2)
        self.assertEqual(len(report["wall_times_ms"]), 2)
        self.assertEqual(report["returned_ids"], ["track-a"])
        self.assertEqual(len(report["candidate_ids_sha256"]), 64)

    def test_rejects_nonpositive_candidate_limit(self):
        with self.assertRaises(CommandError):
            call_command(
                "benchmark_recommendations", algorithm="random",
                candidate_limit=0, stdout=StringIO(),
            )
