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
                    "diversity_strength": 0.25,
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

    def test_algorithm_defaults_to_auto_and_resolves_history_to_cbf(self):
        self._create_track("track-history", tempo=100)
        self._create_track("track-candidate", tempo=105)

        response = self.client.post(
            self.url,
            {"history": ["track-history"]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["algorithm"], "auto")
        self.assertEqual(response.data["meta"]["resolved_algorithm"], "cbf")
        self.assertEqual(response.data["meta"]["reranker"], "mmr")
        self.assertIsNone(response.data["meta"]["mood_model"])
        self.assertEqual(response.data["meta"]["diversity_strength"], 0.2)
        self.assertEqual(len(response.data["recommendations"]), 1)

    def test_auto_without_history_or_mood_resolves_to_random(self):
        self._create_track("track-a")
        self._create_track("track-b")

        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["algorithm"], "auto")
        self.assertEqual(response.data["meta"]["resolved_algorithm"], "random")
        self.assertEqual(response.data["meta"]["relevance_model"], "random")
        self.assertIsNone(response.data["meta"]["reranker"])
        self.assertIsNone(response.data["recommendations"][0]["score"])

    def test_auto_with_mood_resolves_to_mood_cbf_and_default_mmr(self):
        self._create_track(
            "happy-track",
            energy=0.70,
            valence=0.85,
            danceability=0.65,
        )
        self._create_track("other-track", energy=0.1, valence=0.1)

        response = self.client.post(
            self.url,
            {"context": {"mood": "happy"}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["algorithm"], "auto")
        self.assertEqual(
            response.data["meta"]["resolved_algorithm"],
            "context_mmr",
        )
        self.assertEqual(response.data["meta"]["relevance_model"], "mood_cbf")
        self.assertEqual(response.data["meta"]["reranker"], "mmr")
        self.assertEqual(
            response.data["meta"]["mood_model"],
            "va-informed-8-feature-heuristic-v1",
        )
        self.assertEqual(response.data["meta"]["diversity_strength"], 0.2)
        self.assertEqual(response.data["meta"]["mmr_lambda"], 0.8)

    def test_auto_with_history_and_mood_uses_combined_context_model(self):
        self._create_track("track-history", energy=0.7, valence=0.7)
        self._create_track("track-candidate", energy=0.8, valence=0.8)

        response = self.client.post(
            self.url,
            {
                "history": ["track-history"],
                "context": {"mood": "happy"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["meta"]["resolved_algorithm"],
            "context_mmr",
        )
        self.assertEqual(
            response.data["meta"]["relevance_model"],
            "history_mood_cbf",
        )
        components = response.data["recommendations"][0]["components"]
        self.assertIsNotNone(components["history_similarity"])
        self.assertIsNotNone(components["mood_fit"])

    def test_auto_with_only_bpm_filters_then_resolves_to_random(self):
        self._create_track("inside-range", tempo=120)
        self._create_track("outside-range", tempo=160)

        response = self.client.post(
            self.url,
            {"context": {"bpm": {"min": 100, "max": 140}}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["meta"]["resolved_algorithm"], "random")
        self.assertEqual(
            response.data["recommendations"][0]["track"]["id"],
            "inside-range",
        )

    def test_renamed_exploration_field_returns_specific_error(self):
        response = self.client.post(
            self.url,
            {"context": {"mood": "happy", "exploration": 0.2}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn(
            "diversity_strength",
            str(response.data["error"]["details"]["context"]["exploration"]),
        )

    def test_invalid_algorithm_returns_400(self):
        response = self.client.post(
            self.url,
            {"history": ["track-001"], "algorithm": "ai_agent"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("algorithm", response.data["error"]["details"])

    def test_limit_above_maximum_returns_400(self):
        response = self.client.post(
            self.url,
            {"history": ["track-001"], "limit": 11},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("limit", response.data["error"]["details"])

    def test_cbf_requires_non_empty_history(self):
        response = self.client.post(
            self.url,
            {"history": [], "algorithm": "cbf"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("history", response.data["error"]["details"])

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
        self.assertTrue(
            response.data["error"]["details"]["candidate_ids_supplied"]
        )
        self.assertEqual(response.data["error"]["details"]["history_count"], 1)

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
                    "diversity_strength": 0.3,
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
        self.assertIn("mood_feature_closeness", components)
        self.assertIn("diversity_penalty", components)
        self.assertIn("mmr_score", components)
        self.assertEqual(
            response.data["recommendations"][0]["score"],
            components["context_relevance"],
        )

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
                "context": {"mood": "happy", "diversity_strength": 0},
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
                "context": {"diversity_strength": 0.5},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("history", response.data["error"]["details"])

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
        self.assertIn("context", response.data["error"]["details"])

    def test_malformed_json_returns_400(self):
        response = self.client.generic(
            "POST",
            self.url,
            "{",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "MALFORMED_JSON")
        self.assertIn("parse_error", response.data["error"]["details"])
