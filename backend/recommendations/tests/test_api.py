from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from recommendations.models import Track, TrackFeatures


class RecommendationApiTests(APITestCase):
    def setUp(self):
        self.url = reverse("recommendations:recommendations")

    @staticmethod
    def _create_track(
        track_id,
        *,
        tempo=120,
        energy=0.5,
        valence=0.5,
        danceability=0.5,
        acousticness=0.5,
        instrumentalness=0.0,
        loudness=-8.0,
        speechiness=0.05,
    ):
        track = Track.objects.create(
            id=track_id,
            title=f"Song {track_id}",
            artist="Test Artist",
            data_source="test-catalogue-v1",
        )
        TrackFeatures.objects.create(
            track=track,
            tempo=tempo,
            energy=energy,
            valence=valence,
            danceability=danceability,
            acousticness=acousticness,
            instrumentalness=instrumentalness,
            loudness=loudness,
            speechiness=speechiness,
            feature_source="test-catalogue-v1",
        )

    def test_valid_cbf_request_returns_ranked_recommendations(self):
        self._create_track(
            "track-history",
            tempo=120,
            energy=0.8,
            valence=0.8,
            acousticness=0.1,
        )
        self._create_track(
            "track-similar",
            tempo=122,
            energy=0.79,
            valence=0.81,
            acousticness=0.1,
        )
        self._create_track(
            "track-different",
            tempo=60,
            energy=0.1,
            valence=0.1,
            acousticness=0.9,
        )

        response = self.client.post(
            self.url,
            {
                "history": ["track-history"],
                "algorithm": "cbf",
                "limit": 2,
                "context": {
                    "mood": "happy",
                    "bpm": {"min": 50, "max": 140},
                    "exploration": 0.25,
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["algorithm"], "cbf")
        self.assertEqual(len(response.data["recommendations"]), 2)
        self.assertEqual(
            response.data["recommendations"][0]["track"]["id"],
            "track-similar",
        )
        self.assertIsInstance(response.data["recommendations"][0]["score"], float)
        self.assertEqual(response.data["meta"]["history_count_used"], 1)

    def test_algorithm_defaults_to_cbf(self):
        self._create_track("track-history", tempo=100)
        self._create_track("track-candidate", tempo=105)

        response = self.client.post(
            self.url,
            {"history": ["track-history"]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["algorithm"], "cbf")
        self.assertEqual(len(response.data["recommendations"]), 1)

    def test_invalid_algorithm_returns_400(self):
        response = self.client.post(
            self.url,
            {"history": ["track-001"], "algorithm": "ai_agent"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("algorithm", response.data)

    def test_limit_above_maximum_returns_400(self):
        response = self.client.post(
            self.url,
            {"history": ["track-001"], "limit": 11},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("limit", response.data)

    def test_cbf_requires_non_empty_history(self):
        response = self.client.post(
            self.url,
            {"history": [], "algorithm": "cbf"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("history", response.data)

    def test_random_allows_empty_history(self):
        self._create_track("track-a")
        self._create_track("track-b")

        response = self.client.post(
            self.url,
            {"history": [], "algorithm": "random", "limit": 2},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["algorithm"], "random")
        self.assertEqual(len(response.data["recommendations"]), 2)
        self.assertEqual(response.data["meta"]["returned_count"], 2)
        for rank, recommendation in enumerate(
            response.data["recommendations"], start=1
        ):
            self.assertEqual(recommendation["rank"], rank)
            self.assertIsNone(recommendation["score"])
            self.assertIn("track", recommendation)
            self.assertIn("explanation", recommendation)

    def test_random_excludes_history_and_honours_candidate_ids(self):
        self._create_track("track-a")
        self._create_track("track-b")
        self._create_track("track-c")

        response = self.client.post(
            self.url,
            {
                "history": ["track-a"],
                "algorithm": "random",
                "limit": 5,
                "candidate_ids": ["track-a", "track-b"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["recommendations"]), 1)
        self.assertEqual(
            response.data["recommendations"][0]["track"]["id"],
            "track-b",
        )

    def test_random_unknown_track_returns_error_schema(self):
        self._create_track("track-a")

        response = self.client.post(
            self.url,
            {
                "history": ["missing-track"],
                "algorithm": "random",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "UNKNOWN_TRACK_ID")
        self.assertEqual(
            response.data["error"]["details"]["ids"],
            ["missing-track"],
        )

    def test_random_no_eligible_candidate_returns_422(self):
        self._create_track("track-a")

        response = self.client.post(
            self.url,
            {
                "history": ["track-a"],
                "algorithm": "random",
                "candidate_ids": ["track-a"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.data["error"]["code"], "NO_CANDIDATES")

    def test_context_mmr_returns_ranked_component_scores(self):
        self._create_track("track-history", energy=0.8, valence=0.7)
        self._create_track("track-a", energy=0.75, valence=0.8)
        self._create_track("track-b", energy=0.2, valence=0.1)

        response = self.client.post(
            self.url,
            {
                "history": ["track-history"],
                "algorithm": "context_mmr",
                "limit": 2,
                "context": {
                    "mood": "happy",
                    "exploration": 0.3,
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["algorithm"], "context_mmr")
        self.assertEqual(len(response.data["recommendations"]), 2)
        components = response.data["recommendations"][0]["components"]
        self.assertIn("history_similarity", components)
        self.assertIn("mood_fit", components)
        self.assertIn("diversity_penalty", components)
        self.assertIn("mmr_score", components)

    def test_context_mmr_allows_mood_without_history(self):
        self._create_track(
            "happy-track",
            energy=0.70,
            valence=0.85,
            danceability=0.65,
        )
        self._create_track(
            "sad-track",
            energy=0.15,
            valence=0.10,
            danceability=0.20,
        )

        response = self.client.post(
            self.url,
            {
                "history": [],
                "algorithm": "context_mmr",
                "limit": 1,
                "context": {"mood": "happy", "exploration": 0},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["recommendations"][0]["track"]["id"],
            "happy-track",
        )
        self.assertEqual(response.data["meta"]["history_count_used"], 0)

    def test_context_mmr_without_history_or_mood_returns_400(self):
        response = self.client.post(
            self.url,
            {
                "history": [],
                "algorithm": "context_mmr",
                "context": {"exploration": 0.5},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("history", response.data)

    def test_invalid_bpm_range_returns_400(self):
        response = self.client.post(
            self.url,
            {
                "history": ["track-001"],
                "context": {"bpm": {"min": 140, "max": 90}},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("context", response.data)

    def test_malformed_json_returns_400(self):
        response = self.client.generic(
            "POST",
            self.url,
            "{",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)
