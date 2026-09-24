from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase

from offline_evaluation.experiments.config import EvaluationConfig, STUDY_NAMES
from offline_evaluation.experiments.protocol import build_context
from offline_evaluation.experiments.runner import run_evaluation
from offline_evaluation.experiments.studies import comparison, configuration
from offline_evaluation.visualization.publisher import build_report_figures
from recommendations.models import CatalogueState, Track, TrackFeatures


class ProtocolTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        tracks = []
        for index in range(30):
            tracks.append(
                Track(
                    id=f"track-{index:02d}",
                    title=f"Track {index}",
                    artist=f"Artist {index}",
                    artist_display=f"Artist {index}",
                    genres=["test"],
                    data_source="test-source",
                )
            )
        Track.objects.bulk_create(tracks)
        TrackFeatures.objects.bulk_create(
            [
                TrackFeatures(
                    track=track,
                    tempo=60.0 + index * 4,
                    energy=(index % 10) / 10,
                    valence=((index * 3) % 10) / 10,
                    danceability=((index * 7) % 10) / 10,
                    acousticness=((index * 9) % 10) / 10,
                    instrumentalness=((index * 2) % 10) / 10,
                    loudness=-25.0 + index * 0.8,
                    speechiness=((index * 4) % 10) / 10,
                    feature_source="test",
                )
                for index, track in enumerate(tracks)
            ]
        )
        CatalogueState.objects.create(
            id=1,
            version="test-catalogue",
            catalogue_sha256="a" * 64,
            record_count=30,
            import_mode="test",
        )

    def test_builds_twelve_scenarios_and_a_disjoint_pool(self):
        config = EvaluationConfig(
            candidate_count=5,
            top_n=3,
            random_repetitions=1,
            performance_fresh_repetitions=1,
            performance_warm_repetitions=1,
        )

        first = build_context(config)
        second = build_context(config)

        history_ids = {
            track_id for scenario in first.scenarios for track_id in scenario["history"]
        }
        self.assertEqual(len(first.scenarios), 12)
        self.assertEqual(len(first.candidate_ids), 5)
        self.assertTrue(history_ids.isdisjoint(first.candidate_ids))
        self.assertEqual(first.candidate_ids, second.candidate_ids)

    def test_compact_configuration_and_comparison_studies_execute(self):
        config = EvaluationConfig(
            candidate_count=5,
            top_n=3,
            random_repetitions=1,
            performance_fresh_repetitions=1,
            performance_warm_repetitions=1,
        )
        context = build_context(config)

        configuration_result = configuration.run(context)
        comparison_result = comparison.run(context)

        self.assertEqual(len(configuration_result.runs), 124)
        self.assertEqual(len(comparison_result.runs), 44)
        self.assertTrue(configuration_result.tables["summary"])
        self.assertTrue(comparison_result.tables["pairwise"])

    def test_end_to_end_run_and_figure_build(self):
        config = EvaluationConfig(
            candidate_count=5,
            top_n=3,
            random_repetitions=1,
            performance_fresh_repetitions=1,
            performance_warm_repetitions=1,
        )
        with TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "evaluation"

            manifest = run_evaluation(
                config=config,
                output_dir=output_dir,
                selected_studies=STUDY_NAMES,
            )
            figure_manifest = build_report_figures(output_dir)

            self.assertTrue(manifest.is_file())
            self.assertTrue(figure_manifest.is_file())
            self.assertEqual(len(list((output_dir / "figures").glob("*.svg"))), 5)
