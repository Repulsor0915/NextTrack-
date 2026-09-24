import hashlib
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from recommendations.catalogue_import.snapshot import _validate_records
from recommendations.models import (
    Album,
    Artist,
    CatalogueState,
    Track,
    TrackArtist,
    TrackFeatures,
    TrackGenre,
)


class ImportCatalogueCommandTests(TestCase):
    def test_validates_nullable_display_fields_without_legacy_artist(self):
        record = self._track("track-a")
        record.pop("artist")
        record["artist_display"] = None
        record["album_display"] = None

        _validate_records([record])

        record["artist_display"] = 123
        with self.assertRaisesRegex(CommandError, "invalid artist_display"):
            _validate_records([record])

    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.catalogue_path = Path(self.temporary_directory.name) / "catalogue.json"

    def _write_catalogue(self, catalogue, *, version="test-fixture"):
        with self.catalogue_path.open("w", encoding="utf-8") as catalogue_file:
            json.dump(catalogue, catalogue_file)
        raw = self.catalogue_path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        manifest = {
            "catalogue_version": version,
            "outputs": {
                "catalogue.json": {"bytes": len(raw), "sha256": checksum}
            },
        }
        self.catalogue_path.with_name("manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return checksum

    def _preview_token(self, *, replace=False, prune=False):
        output = StringIO()
        call_command(
            "import_catalogue", self.catalogue_path,
            replace=replace, prune=prune, dry_run=True, stdout=output,
        )
        return json.loads(output.getvalue())["preview_token"]

    @staticmethod
    def _track(track_id, *, title="Test Song", energy=0.8):
        return {
            "id": track_id,
            "title": title,
            "artist": "Test Artist",
            "artist_display": "Test Artist",
            "album_display": "Test Album",
            "genres": ["pop"],
            "explicit": False,
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
        self.assertEqual(TrackGenre.objects.count(), 2)
        self.assertEqual(Track.objects.get(pk="track-a").data_source, "test-fixture")
        self.assertEqual(
            Track.objects.get(pk="track-b").features.feature_source,
            "test-fixture",
        )
        self.assertIn("2 created, 0 updated", output.getvalue())
        self.assertEqual(CatalogueState.objects.get(pk=1).version, "test-fixture")
        self.assertEqual(CatalogueState.objects.get(pk=1).record_count, 2)

    def test_imports_all_artists_and_preserves_display_text(self):
        track = self._track("track-zh")
        track.pop("artist")
        track["artist_display"] = "周杰伦; 蔡依林; 周杰伦"
        track["album_display"] = "合作专辑"
        self._write_catalogue([track])

        call_command("import_catalogue", self.catalogue_path, stdout=StringIO())

        stored = Track.objects.select_related("primary_artist", "album").get(pk="track-zh")
        self.assertEqual(stored.artist_display, "周杰伦; 蔡依林; 周杰伦")
        self.assertEqual(stored.artist, "周杰伦")
        self.assertEqual(stored.primary_artist.name, "周杰伦")
        self.assertEqual(stored.album_display, "合作专辑")
        self.assertEqual(stored.album.name, "合作专辑")
        self.assertEqual(stored.album.artist_id, stored.primary_artist_id)
        self.assertEqual(
            list(
                stored.track_artists.order_by("position").values_list(
                    "artist__name", flat=True
                )
            ),
            ["周杰伦", "蔡依林"],
        )
        self.assertEqual(TrackFeatures.objects.count(), Track.objects.count())

    def test_missing_artist_and_album_remain_null(self):
        track = self._track("track-unknown")
        track.pop("artist")
        track["artist_display"] = None
        track["album_display"] = "Album Without Known Artist"
        self._write_catalogue([track])

        call_command("import_catalogue", self.catalogue_path, stdout=StringIO())

        stored = Track.objects.get(pk="track-unknown")
        self.assertIsNone(stored.artist)
        self.assertIsNone(stored.primary_artist_id)
        self.assertIsNone(stored.album_id)
        self.assertEqual(stored.album_display, "Album Without Known Artist")
        self.assertFalse(Artist.objects.exists())
        self.assertFalse(Album.objects.exists())
        self.assertFalse(TrackArtist.objects.exists())

    def test_same_album_name_for_different_artists_stays_separate(self):
        first = self._track("track-a")
        second = self._track("track-b")
        first["artist_display"] = "First Artist"
        second["artist_display"] = "Second Artist"
        first["album_display"] = second["album_display"] = "Greatest Hits"
        self._write_catalogue([first, second])

        call_command("import_catalogue", self.catalogue_path, stdout=StringIO())

        self.assertEqual(Album.objects.count(), 2)
        self.assertNotEqual(
            Track.objects.get(pk="track-a").album_id,
            Track.objects.get(pk="track-b").album_id,
        )

    def test_reimport_replaces_artist_links_and_can_remove_album(self):
        first = self._track("track-a")
        first.pop("artist")
        first["artist_display"] = "First Artist; Second Artist"
        self._write_catalogue([first], version="first")
        call_command("import_catalogue", self.catalogue_path, stdout=StringIO())

        updated = self._track("track-a")
        updated.pop("artist")
        updated["artist_display"] = "Second Artist; Third Artist"
        updated["album_display"] = None
        checksum = self._write_catalogue([updated], version="second")
        call_command(
            "import_catalogue",
            self.catalogue_path,
            prune=True,
            confirm_version="second",
            confirm_sha256=checksum,
            confirm_plan=self._preview_token(prune=True),
            stdout=StringIO(),
        )

        stored = Track.objects.get(pk="track-a")
        self.assertEqual(stored.artist, "Second Artist")
        self.assertEqual(stored.primary_artist.name, "Second Artist")
        self.assertIsNone(stored.album_id)
        self.assertIsNone(stored.album_display)
        self.assertFalse(Album.objects.exists())
        self.assertFalse(Artist.objects.filter(name="First Artist").exists())
        self.assertEqual(
            list(
                stored.track_artists.order_by("position").values_list(
                    "artist__name", flat=True
                )
            ),
            ["Second Artist", "Third Artist"],
        )

    def test_reimport_updates_existing_tracks_without_duplicates(self):
        self._write_catalogue([self._track("track-a")], version="first-source")
        call_command(
            "import_catalogue",
            self.catalogue_path,
            data_source="first-source",
            stdout=StringIO(),
        )
        checksum = self._write_catalogue(
            [self._track("track-a", title="Updated Song", energy=0.4)],
            version="updated-source",
        )
        output = StringIO()

        call_command(
            "import_catalogue",
            self.catalogue_path,
            data_source="updated-source",
            prune=True,
            confirm_version="updated-source",
            confirm_sha256=checksum,
            confirm_plan=self._preview_token(prune=True),
            stdout=output,
        )

        track = Track.objects.get(pk="track-a")
        self.assertEqual(Track.objects.count(), 1)
        self.assertEqual(track.title, "Updated Song")
        self.assertEqual(track.features.energy, 0.4)
        self.assertEqual(track.data_source, "updated-source")
        self.assertIn("0 created, 1 updated", output.getvalue())
        self.assertEqual(CatalogueState.objects.get(pk=1).version, "updated-source")

    def test_prune_refreshes_the_exact_genre_index(self):
        self._write_catalogue([self._track("track-a")], version="first")
        call_command("import_catalogue", self.catalogue_path, stdout=StringIO())
        revised = self._track("track-a")
        revised["genres"] = ["synth-pop"]
        checksum = self._write_catalogue([revised], version="second")

        call_command(
            "import_catalogue", self.catalogue_path, prune=True,
            confirm_version="second", confirm_sha256=checksum,
            confirm_plan=self._preview_token(prune=True), stdout=StringIO(),
        )

        self.assertEqual(
            list(TrackGenre.objects.values_list("normalized_name", flat=True)),
            ["synth-pop"],
        )

    def test_rejects_genre_whose_casefolded_index_exceeds_column_limit(self):
        track = self._track("track-a")
        track["genres"] = ["\ufb03" * 100]
        self._write_catalogue([track])

        with self.assertRaisesMessage(CommandError, "invalid genres"):
            call_command("import_catalogue", self.catalogue_path, stdout=StringIO())

        self.assertEqual(Track.objects.count(), 0)

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

    def test_manifest_checksum_is_required(self):
        self._write_catalogue([self._track("track-a")])
        self.catalogue_path.write_text("[]", encoding="utf-8")

        with self.assertRaisesMessage(CommandError, "checksum or byte size"):
            call_command("import_catalogue", self.catalogue_path, stdout=StringIO())
        self.assertFalse(Track.objects.exists())

    def test_dry_run_reports_counts_without_writing(self):
        self._write_catalogue([self._track("track-a"), self._track("track-b")])
        output = StringIO()

        call_command(
            "import_catalogue", self.catalogue_path, dry_run=True, stdout=output
        )

        summary = json.loads(output.getvalue())
        self.assertEqual(summary["created"], 2)
        self.assertEqual(summary["deleted"], 0)
        self.assertFalse(Track.objects.exists())
        self.assertFalse(CatalogueState.objects.exists())

    def test_different_snapshot_requires_an_explicit_sync_mode(self):
        self._write_catalogue([self._track("track-a")], version="first")
        call_command("import_catalogue", self.catalogue_path, stdout=StringIO())
        self._write_catalogue([self._track("track-a", title="Changed")], version="second")

        with self.assertRaisesMessage(CommandError, "different snapshot"):
            call_command("import_catalogue", self.catalogue_path, stdout=StringIO())
        self.assertEqual(Track.objects.get(pk="track-a").title, "Test Song")
        self.assertEqual(CatalogueState.objects.get(pk=1).version, "first")

    def test_prune_requires_confirmation_and_syncs_complete_snapshot(self):
        self._write_catalogue(
            [self._track(f"track-{index}") for index in range(20)], version="first"
        )
        call_command("import_catalogue", self.catalogue_path, stdout=StringIO())
        checksum = self._write_catalogue(
            [self._track(f"track-{index}", title="Updated") for index in range(19)]
            + [self._track("track-new")],
            version="second",
        )
        preview = StringIO()
        call_command(
            "import_catalogue", self.catalogue_path, prune=True,
            dry_run=True, stdout=preview,
        )
        self.assertEqual(json.loads(preview.getvalue())["deleted"], 1)
        self.assertEqual(Track.objects.count(), 20)

        with self.assertRaisesMessage(CommandError, "requires --confirm-version"):
            call_command(
                "import_catalogue", self.catalogue_path, prune=True,
                stdout=StringIO(),
            )
        call_command(
            "import_catalogue", self.catalogue_path, prune=True,
            confirm_version="second", confirm_sha256=checksum,
            confirm_plan=json.loads(preview.getvalue())["preview_token"],
            stdout=StringIO(),
        )

        self.assertEqual(Track.objects.count(), 20)
        self.assertEqual(TrackFeatures.objects.count(), 20)
        self.assertFalse(Track.objects.filter(pk="track-19").exists())
        self.assertEqual(Track.objects.get(pk="track-0").title, "Updated")
        self.assertTrue(Track.objects.filter(pk="track-new").exists())
        self.assertEqual(CatalogueState.objects.get(pk=1).catalogue_sha256, checksum)

    def test_large_prune_needs_extra_override(self):
        self._write_catalogue(
            [self._track(f"track-{index}") for index in range(10)], version="first"
        )
        call_command("import_catalogue", self.catalogue_path, stdout=StringIO())
        checksum = self._write_catalogue([self._track("track-0")], version="second")

        with self.assertRaisesMessage(CommandError, "--allow-large-prune"):
            call_command(
                "import_catalogue", self.catalogue_path, prune=True,
                confirm_version="second", confirm_sha256=checksum,
                confirm_plan=self._preview_token(prune=True),
                stdout=StringIO(),
            )
        self.assertEqual(Track.objects.count(), 10)

        call_command(
            "import_catalogue", self.catalogue_path, prune=True,
            confirm_version="second", confirm_sha256=checksum,
            confirm_plan=self._preview_token(prune=True),
            allow_large_prune=True, stdout=StringIO(),
        )
        self.assertEqual(Track.objects.count(), 1)
        self.assertEqual(TrackFeatures.objects.count(), 1)

    def test_destructive_sync_rejects_an_unconfirmed_preview(self):
        self._write_catalogue([self._track("track-a")], version="first")
        call_command("import_catalogue", self.catalogue_path, stdout=StringIO())
        checksum = self._write_catalogue([self._track("track-b")], version="second")

        with self.assertRaisesMessage(CommandError, "--confirm-plan"):
            call_command(
                "import_catalogue", self.catalogue_path, replace=True,
                confirm_version="second", confirm_sha256=checksum,
                confirm_plan="incorrect-token", stdout=StringIO(),
            )
        self.assertTrue(Track.objects.filter(pk="track-a").exists())

    def test_replace_rebuilds_legacy_rows_after_confirmation(self):
        Track.objects.create(id="legacy", title="Legacy", artist="Test")
        checksum = self._write_catalogue([self._track("new")], version="new-snapshot")

        call_command(
            "import_catalogue", self.catalogue_path, replace=True,
            confirm_version="new-snapshot", confirm_sha256=checksum,
            confirm_plan=self._preview_token(replace=True),
            stdout=StringIO(),
        )

        self.assertEqual(set(Track.objects.values_list("id", flat=True)), {"new"})
        self.assertEqual(TrackFeatures.objects.count(), 1)
        self.assertEqual(CatalogueState.objects.get(pk=1).version, "new-snapshot")

    def test_prune_rejects_legacy_rows_without_active_state(self):
        Track.objects.create(id="legacy", title="Legacy", artist="Test")
        checksum = self._write_catalogue([self._track("new")], version="new-snapshot")

        with self.assertRaisesMessage(CommandError, "no verified active state"):
            call_command(
                "import_catalogue", self.catalogue_path, prune=True,
                confirm_version="new-snapshot", confirm_sha256=checksum,
                stdout=StringIO(),
            )
        self.assertTrue(Track.objects.filter(pk="legacy").exists())

    def test_transaction_rolls_back_after_batch_write_failure(self):
        self._write_catalogue([self._track("track-a")], version="first")
        call_command("import_catalogue", self.catalogue_path, stdout=StringIO())
        checksum = self._write_catalogue([self._track("track-b")], version="second")

        with patch(
            "recommendations.catalogue_import.writer.TrackFeatures.objects.bulk_create",
            side_effect=RuntimeError("injected failure"),
        ):
            with self.assertRaisesMessage(RuntimeError, "injected failure"):
                call_command(
                    "import_catalogue", self.catalogue_path, replace=True,
                    confirm_version="second", confirm_sha256=checksum,
                    confirm_plan=self._preview_token(replace=True),
                    stdout=StringIO(),
                )

        self.assertTrue(Track.objects.filter(pk="track-a").exists())
        self.assertFalse(Track.objects.filter(pk="track-b").exists())
        self.assertEqual(CatalogueState.objects.get(pk=1).version, "first")

    def test_import_over_multiple_batches(self):
        self._write_catalogue([self._track(f"track-{i}") for i in range(501)])
        call_command("import_catalogue", self.catalogue_path, stdout=StringIO())

        self.assertEqual(Track.objects.count(), 501)
        self.assertEqual(TrackFeatures.objects.count(), 501)
        self.assertEqual(CatalogueState.objects.get(pk=1).record_count, 501)

    def test_adopt_matching_legacy_rows_without_replacing_them(self):
        self._write_catalogue([self._track("track-a")], version="legacy-source")
        Track.objects.create(
            id="track-a", title="Test Song", artist="Test Artist",
            genres=["pop"], explicit=False, year=2024,
            data_source="legacy-source",
        )
        TrackFeatures.objects.create(
            track_id="track-a", tempo=120, energy=0.8, valence=0.7,
            danceability=0.6, acousticness=0.1, instrumentalness=0.0,
            loudness=-6.0, speechiness=0.05, feature_source="legacy-source",
        )

        call_command("adopt_catalogue", self.catalogue_path, stdout=StringIO())

        self.assertEqual(Track.objects.count(), 1)
        self.assertEqual(CatalogueState.objects.get(pk=1).import_mode, "adopt")

    def test_adopt_rejects_any_mismatch_without_writing_state(self):
        self._write_catalogue([self._track("track-a")], version="legacy-source")
        Track.objects.create(
            id="track-a", title="Different", artist="Test Artist",
            genres=["pop"], explicit=False, year=2024,
            data_source="legacy-source",
        )
        TrackFeatures.objects.create(
            track_id="track-a", tempo=120, energy=0.8, valence=0.7,
            danceability=0.6, acousticness=0.1, instrumentalness=0.0,
            loudness=-6.0, speechiness=0.05, feature_source="legacy-source",
        )

        with self.assertRaisesMessage(CommandError, "metadata differs"):
            call_command("adopt_catalogue", self.catalogue_path, stdout=StringIO())
        self.assertFalse(CatalogueState.objects.exists())
