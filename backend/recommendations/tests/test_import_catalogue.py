import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import CommandError, call_command
from django.test import TestCase

from recommendations.models import Track, TrackFeatures


class ImportCatalogueCommandTests(TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.catalogue_path = Path(self.temporary_directory.name) / "catalogue.json"

    def _write_catalogue(self, catalogue):
        with self.catalogue_path.open("w", encoding="utf-8") as catalogue_file:
            json.dump(catalogue, catalogue_file)

    @staticmethod
    def _track(track_id, *, title="Test Song", energy=0.8):
        return {
            "id": track_id,
            "title": title,
            "artist": "Test Artist",
            "genre": "pop",
            "year": 2024,
            "features": {
                "tempo": 120,
                "energy": energy,
                "valence": 0.7,
                "danceability": 0.6,
                "acousticness": 0.1,
                "instrumentalness": 0.0,
                "loudness": -6.0,
                "speechiness": 0.05,
            },
        }

    def test_imports_multiple_tracks_and_features(self):
        self._write_catalogue(
            [self._track("track-a"), self._track("track-b", title="Second Song")]
        )
        output = StringIO()

        call_command(
            "import_catalogue",
            self.catalogue_path,
            data_source="test-fixture",
            stdout=output,
        )

        self.assertEqual(Track.objects.count(), 2)
        self.assertEqual(TrackFeatures.objects.count(), 2)
        self.assertEqual(Track.objects.get(pk="track-a").data_source, "test-fixture")
        self.assertEqual(
            Track.objects.get(pk="track-b").features.feature_source,
            "test-fixture",
        )
        self.assertIn("2 created, 0 updated", output.getvalue())

    def test_reimport_updates_existing_tracks_without_duplicates(self):
        self._write_catalogue([self._track("track-a")])
        call_command(
            "import_catalogue",
            self.catalogue_path,
            data_source="first-source",
            stdout=StringIO(),
        )
        self._write_catalogue(
            [self._track("track-a", title="Updated Song", energy=0.4)]
        )
        output = StringIO()

        call_command(
            "import_catalogue",
            self.catalogue_path,
            data_source="updated-source",
            stdout=output,
        )

        track = Track.objects.get(pk="track-a")
        self.assertEqual(Track.objects.count(), 1)
        self.assertEqual(track.title, "Updated Song")
        self.assertEqual(track.features.energy, 0.4)
        self.assertEqual(track.data_source, "updated-source")
        self.assertIn("0 created, 1 updated", output.getvalue())

    def test_invalid_feature_rolls_back_the_whole_import(self):
        self._write_catalogue(
            [self._track("track-a"), self._track("track-b", energy=1.1)]
        )

        with self.assertRaises(CommandError):
            call_command(
                "import_catalogue",
                self.catalogue_path,
                data_source="test-fixture",
                stdout=StringIO(),
            )

        self.assertFalse(Track.objects.exists())
        self.assertFalse(TrackFeatures.objects.exists())
