import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from recommendations.catalogue_pipeline import (
    CataloguePreparationError,
    prepare_catalogue,
)
from recommendations.catalogue_schema import FEATURE_FIELDS


class CataloguePipelineTests(SimpleTestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.source_path = self.root / "source.csv"
        self.output_directory = self.root / "processed"

    @staticmethod
    def _row(track_id, **overrides):
        row = {
            "track_id": track_id,
            "track_name": f"Song {track_id}",
            "artists": "Test Artist",
            "track_genre": "test",
            "explicit": "False",
            "tempo": "120",
            "energy": "0.6",
            "valence": "0.7",
            "danceability": "0.5",
            "acousticness": "0.2",
            "instrumentalness": "0.0",
            "loudness": "-8.0",
            "speechiness": "0.05",
        }
        row.update(overrides)
        return row

    def _write_rows(self, rows):
        field_names = [
            "track_id",
            "track_name",
            "artists",
            "track_genre",
            "explicit",
            *FEATURE_FIELDS,
        ]
        with self.source_path.open("w", encoding="utf-8", newline="") as source:
            writer = csv.DictWriter(source, fieldnames=field_names)
            writer.writeheader()
            writer.writerows(rows)

    def test_prepares_deterministic_import_catalogue_and_evidence_files(self):
        self._write_rows(
            [
                self._row("track-a"),
                self._row("track-b", energy="0.8"),
                self._row("track-c", valence="0.2"),
            ]
        )

        result = prepare_catalogue(
            self.source_path,
            self.output_directory,
            limit=2,
            seed=42,
            catalogue_version="test-v1",
            retrieved_date="2026-09-04",
        )

        with result["catalogue_path"].open(encoding="utf-8") as catalogue_file:
            catalogue = json.load(catalogue_file)
        with result["manifest_path"].open(encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)

        self.assertEqual(len(catalogue), 2)
        self.assertEqual(set(catalogue[0]["features"]), set(FEATURE_FIELDS))
        self.assertEqual(manifest["catalogue_version"], "test-v1")
        self.assertIn("catalogue.json", manifest["outputs"])

    def test_reports_duplicate_missing_and_out_of_range_rows(self):
        self._write_rows(
            [
                self._row("track-a"),
                self._row("track-a"),
                self._row("track-missing", energy=""),
                self._row("track-invalid", valence="1.2"),
                self._row("track-spoken", speechiness="0.9"),
                self._row("track-explicit", explicit="True"),
                self._row("track-non-song", track_genre="sleep"),
            ]
        )

        result = prepare_catalogue(
            self.source_path,
            self.output_directory,
            limit=1,
            seed=42,
            catalogue_version="test-v1",
            retrieved_date="2026-09-04",
        )

        with result["exclusions_summary_path"].open(
            encoding="utf-8"
        ) as report_file:
            report = json.load(report_file)

        self.assertEqual(report["excluded_source_row_count"], 6)
        self.assertEqual(report["reason_counts"]["duplicate_track_id"], 1)
        self.assertEqual(report["reason_counts"]["missing_energy"], 1)
        self.assertEqual(report["reason_counts"]["out_of_range_valence"], 1)
        self.assertEqual(report["reason_counts"]["likely_spoken_word"], 1)
        self.assertEqual(report["reason_counts"]["explicit_content"], 1)
        self.assertEqual(report["reason_counts"]["non_song_genre"], 1)

    def test_rejects_missing_required_source_column(self):
        with self.source_path.open("w", encoding="utf-8", newline="") as source:
            source.write("track_id,track_name\ntrack-a,Song A\n")

        with self.assertRaises(CataloguePreparationError):
            prepare_catalogue(
                self.source_path,
                self.output_directory,
                limit=1,
                seed=42,
                catalogue_version="test-v1",
                retrieved_date="2026-09-04",
            )
