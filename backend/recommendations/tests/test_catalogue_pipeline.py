import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from catalogue_pipeline import (
    CataloguePreparationError,
    prepare_catalogue,
    sample_catalogue,
)
from catalogue_pipeline.schema import REQUIRED_SOURCE_COLUMNS
from catalogue_pipeline.validation import validate_source_row


class CatalogueValidationTests(SimpleTestCase):
    @staticmethod
    def _row(**overrides):
        row = {
            "track_id": "track-1",
            "track_name": "Song",
            "artists": "Artist",
            "track_genre": "",
            "explicit": "true",
            "tempo": "120",
            "energy": "0.8",
            "valence": "0.7",
            "danceability": "0.6",
            "acousticness": "0.1",
            "instrumentalness": "0.0",
            "loudness": "-8",
            "speechiness": "0.05",
        }
        row.update(overrides)
        return row

    def test_accepts_blank_genre_and_stores_explicit_boolean(self):
        result = validate_source_row(self._row())

        self.assertEqual(result.reasons, ())
        self.assertEqual(result.record["genres"], [])
        self.assertIs(result.record["explicit"], True)

    def test_rejects_invalid_explicit_value(self):
        result = validate_source_row(self._row(explicit="unknown"))

        self.assertIn("invalid_explicit", result.reasons)

    def test_requires_strictly_positive_tempo(self):
        result = validate_source_row(self._row(tempo="0"))

        self.assertIn("out_of_range_tempo", result.reasons)

    def test_accepts_extreme_finite_loudness_but_rejects_non_finite(self):
        finite = validate_source_row(self._row(loudness="-100"))
        non_finite = validate_source_row(self._row(loudness="nan"))

        self.assertEqual(finite.reasons, ())
        self.assertIn("non_finite_loudness", non_finite.reasons)


class CataloguePipelineTests(SimpleTestCase):
    def test_keeps_first_valid_duplicate_and_reports_conflicts(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_path = root / "source.csv"
            output_directory = root / "output"
            first = CatalogueValidationTests._row()
            second = CatalogueValidationTests._row(
                track_genre="rock",
                explicit="false",
                energy="0.6",
            )
            with source_path.open("w", encoding="utf-8", newline="") as source:
                writer = csv.DictWriter(source, fieldnames=REQUIRED_SOURCE_COLUMNS)
                writer.writeheader()
                writer.writerows([first, second])

            prepare_catalogue(
                source_path,
                output_directory,
                catalogue_version="test-v1",
                retrieved_date="2026-09-18",
            )

            with (output_directory / "catalogue.json").open(encoding="utf-8") as file:
                catalogue = json.load(file)
            with (output_directory / "preprocessing-report.json").open(
                encoding="utf-8"
            ) as file:
                report = json.load(file)

            self.assertEqual(len(catalogue), 1)
            self.assertEqual(catalogue[0]["genres"], ["rock"])
            self.assertIs(catalogue[0]["explicit"], True)
            self.assertEqual(report["rejection_reason_counts"]["duplicate_track_id"], 1)
            self.assertEqual(
                report["rejection_reason_counts"]["duplicate_conflicting_genres"],
                1,
            )
            self.assertEqual(
                report["rejection_reason_counts"]["duplicate_conflicting_explicit"],
                1,
            )
            self.assertEqual(
                report["rejection_reason_counts"]["duplicate_conflicting_features"],
                1,
            )

    def test_refuses_to_mix_outputs_in_a_non_empty_directory(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_path = root / "source.csv"
            output_directory = root / "output"
            output_directory.mkdir()
            (output_directory / "old.json").write_text("{}", encoding="utf-8")
            with source_path.open("w", encoding="utf-8", newline="") as source:
                writer = csv.DictWriter(source, fieldnames=REQUIRED_SOURCE_COLUMNS)
                writer.writeheader()
                writer.writerow(CatalogueValidationTests._row())

            with self.assertRaises(CataloguePreparationError):
                prepare_catalogue(
                    source_path,
                    output_directory,
                    catalogue_version="test-v1",
                    retrieved_date="2026-09-18",
                )

    def test_sample_is_derived_from_the_frozen_parent_catalogue(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_path = root / "source.csv"
            full_directory = root / "full"
            sample_directory = root / "sample"
            rows = [
                CatalogueValidationTests._row(
                    track_id=f"track-{index}",
                    track_name=f"Song {index}",
                )
                for index in range(1, 4)
            ]
            with source_path.open("w", encoding="utf-8", newline="") as source:
                writer = csv.DictWriter(source, fieldnames=REQUIRED_SOURCE_COLUMNS)
                writer.writeheader()
                writer.writerows(rows)

            prepare_catalogue(
                source_path,
                full_directory,
                catalogue_version="full-v1",
                retrieved_date="2026-09-18",
            )
            sample_catalogue(
                full_directory / "catalogue.json",
                sample_directory,
                catalogue_version="sample-v1",
                limit=2,
                seed=7,
            )

            with (sample_directory / "catalogue.json").open(encoding="utf-8") as file:
                sample = json.load(file)
            with (sample_directory / "manifest.json").open(encoding="utf-8") as file:
                manifest = json.load(file)

            self.assertEqual(len(sample), 2)
            self.assertEqual(manifest["parent"]["catalogue_version"], "full-v1")
            self.assertEqual(manifest["selection"]["seed"], 7)
