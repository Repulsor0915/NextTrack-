from django.core.exceptions import ValidationError
from django.test import TestCase

from recommendations.models import Track, TrackFeatures


class TrackModelTests(TestCase):
    def setUp(self):
        self.track = Track.objects.create(
            id="test-track-001",
            title="Test Song",
            artist="Test Artist",
            genres=["pop"],
            year=2024,
            data_source="test-fixture",
        )
        self.features = TrackFeatures.objects.create(
            track=self.track,
            tempo=120,
            energy=0.8,
            valence=0.7,
            danceability=0.6,
            acousticness=0.1,
            instrumentalness=0.0,
            loudness=-6.0,
            speechiness=0.05,
            feature_source="test-fixture",
        )

    def test_track_exposes_its_features(self):
        self.assertEqual(self.track.features, self.features)

    def test_track_string_contains_title_and_artist(self):
        self.assertEqual(str(self.track), "Test Song — Test Artist")

    def test_normalized_feature_rejects_value_above_one(self):
        self.features.energy = 1.1

        with self.assertRaises(ValidationError):
            self.features.full_clean()

    def test_deleting_track_also_deletes_features(self):
        self.track.delete()

        self.assertFalse(TrackFeatures.objects.exists())
