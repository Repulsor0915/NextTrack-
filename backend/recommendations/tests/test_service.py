import random

from django.test import TestCase

from recommendations.models import Track, TrackFeatures
from recommendations.services.recommendation_service import (
    MissingTrackFeaturesError,
    NoCandidatesError,
    RecommendationService,
    UnknownTrackIdsError,
)


class RecommendationServiceTests(TestCase):
    def setUp(self):
        self._create_track("track-a", tempo=80)
        self._create_track("track-b", tempo=110)
        self._create_track("track-c", tempo=130)
        self._create_track("track-d", tempo=160)
        self.service = RecommendationService(random_source=random.Random(42))

    @staticmethod
    def _create_track(
        track_id,
        *,
        tempo,
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
            genre="test",
            year=2024,
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

    @staticmethod
    def _request(**overrides):
        request = {
            "history": [],
            "algorithm": "random",
            "limit": 2,
            "context": {},
        }
        request.update(overrides)
        return request

    def test_random_recommendations_exclude_history_and_respect_limit(self):
        result = self.service.recommend(
            self._request(history=["track-a"], limit=2)
        )

        result_ids = {
            recommendation["track"]["id"]
            for recommendation in result["recommendations"]
        }
        self.assertEqual(len(result_ids), 2)
        self.assertNotIn("track-a", result_ids)
        self.assertEqual(result["meta"]["candidate_count"], 3)
        self.assertEqual(result["meta"]["returned_count"], 2)

    def test_candidate_ids_restrict_the_pool(self):
        result = self.service.recommend(
            self._request(candidate_ids=["track-a", "track-c"], limit=5)
        )

        result_ids = {
            recommendation["track"]["id"]
            for recommendation in result["recommendations"]
        }
        self.assertEqual(result_ids, {"track-a", "track-c"})

    def test_duplicate_candidate_ids_do_not_duplicate_results(self):
        result = self.service.recommend(
            self._request(
                candidate_ids=["track-a", "track-a", "track-c"],
                limit=5,
            )
        )

        result_ids = [
            recommendation["track"]["id"]
            for recommendation in result["recommendations"]
        ]
        self.assertCountEqual(result_ids, ["track-a", "track-c"])
        self.assertEqual(len(result_ids), len(set(result_ids)))

    def test_history_order_and_repeated_play_events_are_preserved(self):
        tracks = self.service._get_history_tracks(
            ["track-a", "track-b", "track-a"]
        )

        self.assertEqual(
            [track.id for track in tracks],
            ["track-a", "track-b", "track-a"],
        )

    def test_bpm_range_is_applied_as_a_hard_candidate_filter(self):
        result = self.service.recommend(
            self._request(context={"bpm": {"min": 100, "max": 140}}, limit=5)
        )

        result_ids = {
            recommendation["track"]["id"]
            for recommendation in result["recommendations"]
        }
        self.assertEqual(result_ids, {"track-b", "track-c"})
        self.assertEqual(result["meta"]["candidate_count"], 2)

    def test_mood_does_not_influence_the_random_baseline(self):
        without_mood = RecommendationService(
            random_source=random.Random(7)
        ).recommend(self._request(limit=3))
        with_mood = RecommendationService(random_source=random.Random(7)).recommend(
            self._request(context={"mood": "happy"}, limit=3)
        )

        without_mood_ids = [
            recommendation["track"]["id"]
            for recommendation in without_mood["recommendations"]
        ]
        with_mood_ids = [
            recommendation["track"]["id"]
            for recommendation in with_mood["recommendations"]
        ]
        self.assertEqual(without_mood_ids, with_mood_ids)

    def test_unknown_track_id_is_rejected(self):
        with self.assertRaises(UnknownTrackIdsError) as context:
            self.service.recommend(self._request(history=["missing-track"]))

        self.assertEqual(context.exception.details["ids"], ["missing-track"])

    def test_no_unplayed_candidates_is_reported(self):
        with self.assertRaises(NoCandidatesError):
            self.service.recommend(
                self._request(
                    candidate_ids=["track-a"],
                    history=["track-a"],
                )
            )

    def test_result_uses_the_frozen_response_shape(self):
        result = self.service.recommend(self._request(limit=1))
        recommendation = result["recommendations"][0]

        self.assertEqual(result["algorithm"], "random")
        self.assertEqual(recommendation["rank"], 1)
        self.assertIsNone(recommendation["score"])
        self.assertEqual(recommendation["components"], {})
        self.assertIn("summary", recommendation["explanation"])
        self.assertEqual(result["meta"]["catalogue_version"], "test-catalogue-v1")
        self.assertIsInstance(result["meta"]["processing_ms"], float)
        self.assertEqual(result["meta"]["requested_algorithm"], "random")
        self.assertEqual(result["meta"]["resolved_algorithm"], "random")

    def test_cbf_ranks_the_closest_history_match_first(self):
        result = self.service.recommend(
            self._request(
                algorithm="cbf",
                history=["track-b"],
                candidate_ids=["track-a", "track-c", "track-d"],
                limit=3,
            )
        )

        self.assertEqual(
            result["recommendations"][0]["track"]["id"],
            "track-c",
        )
        scores = [item["score"] for item in result["recommendations"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_cbf_uses_at_most_five_recent_history_entries(self):
        result = self.service.recommend(
            self._request(
                algorithm="cbf",
                history=[
                    "track-a",
                    "track-b",
                    "track-a",
                    "track-b",
                    "track-a",
                    "track-b",
                ],
                candidate_ids=["track-c", "track-d"],
            )
        )

        self.assertEqual(result["meta"]["history_count_used"], 5)
        self.assertEqual(result["meta"]["history_window_size"], 5)

    def test_mood_does_not_influence_basic_cbf(self):
        request = self._request(
            algorithm="cbf",
            history=["track-b"],
            limit=3,
        )
        without_mood = self.service.recommend(request)
        with_mood = self.service.recommend(
            {**request, "context": {"mood": "happy"}}
        )

        self.assertEqual(
            [item["track"]["id"] for item in without_mood["recommendations"]],
            [item["track"]["id"] for item in with_mood["recommendations"]],
        )
        self.assertEqual(
            [item["score"] for item in without_mood["recommendations"]],
            [item["score"] for item in with_mood["recommendations"]],
        )

    def test_cbf_result_contains_similarity_components_and_evidence(self):
        result = self.service.recommend(
            self._request(algorithm="cbf", history=["track-b"], limit=1)
        )
        recommendation = result["recommendations"][0]

        self.assertEqual(result["algorithm"], "cbf")
        self.assertIsInstance(recommendation["score"], float)
        self.assertGreaterEqual(recommendation["score"], 0)
        self.assertLessEqual(recommendation["score"], 1)
        self.assertIn("history_similarity", recommendation["components"])
        self.assertEqual(
            len(recommendation["components"]["feature_closeness"]),
            8,
        )
        self.assertTrue(recommendation["explanation"]["evidence"])
        self.assertIsNone(result["meta"]["reranker"])

    def test_cbf_rejects_history_track_without_features(self):
        Track.objects.create(
            id="track-without-features",
            title="Incomplete Track",
            artist="Test Artist",
            data_source="test-catalogue-v1",
        )

        with self.assertRaises(MissingTrackFeaturesError):
            self.service.recommend(
                self._request(
                    algorithm="cbf",
                    history=["track-without-features"],
                )
            )

    def test_context_mmr_supports_mood_without_history(self):
        self._create_track(
            "happy-track",
            tempo=130,
            energy=0.70,
            valence=0.85,
            danceability=0.65,
        )
        self._create_track(
            "low-mood-track",
            tempo=70,
            energy=0.10,
            valence=0.10,
            danceability=0.20,
        )

        result = self.service.recommend(
            self._request(
                algorithm="context_mmr",
                history=[],
                candidate_ids=["happy-track", "low-mood-track"],
                context={"mood": "happy", "diversity_strength": 0},
            )
        )

        self.assertEqual(
            result["recommendations"][0]["track"]["id"],
            "happy-track",
        )
        self.assertIsNone(
            result["recommendations"][0]["components"]["history_similarity"]
        )
        self.assertEqual(result["meta"]["history_count_used"], 0)

    def test_context_result_exposes_mood_and_mmr_components(self):
        result = self.service.recommend(
            self._request(
                algorithm="context_mmr",
                history=["track-b"],
                context={
                    "mood": "happy",
                    "bpm": {"min": 100, "max": 140},
                    "diversity_strength": 0.4,
                },
                limit=2,
            )
        )
        recommendation = result["recommendations"][0]
        components = recommendation["components"]

        self.assertEqual(result["algorithm"], "context_mmr")
        self.assertEqual(result["meta"]["mood"], "happy")
        self.assertEqual(
            result["meta"]["mood_model"],
            "va-informed-8-feature-heuristic-v1",
        )
        self.assertEqual(result["meta"]["diversity_strength"], 0.4)
        self.assertEqual(result["meta"]["mmr_lambda"], 0.6)
        self.assertIsNotNone(components["history_similarity"])
        self.assertIsNotNone(components["mood_fit"])
        self.assertTrue(components["mood_feature_closeness"])
        self.assertIs(components["bpm_constraint_satisfied"], True)
        self.assertIn("context_relevance", components)
        self.assertIn("diversity_penalty", components)
        self.assertIn("mmr_score", components)
        self.assertEqual(recommendation["score"], components["context_relevance"])
        self.assertTrue(recommendation["explanation"]["evidence"])
        self.assertTrue(
            any(
                item.startswith("closest mood-profile cues:")
                for item in recommendation["explanation"]["evidence"]
            )
        )

    def test_auto_history_uses_cbf_relevance_with_default_mmr(self):
        result = self.service.recommend(
            self._request(
                algorithm="auto",
                history=["track-b"],
                limit=2,
            )
        )

        self.assertEqual(result["algorithm"], "auto")
        self.assertEqual(result["meta"]["resolved_algorithm"], "cbf")
        self.assertEqual(result["meta"]["relevance_model"], "history_cbf")
        self.assertEqual(result["meta"]["reranker"], "mmr")
        self.assertEqual(result["meta"]["diversity_strength"], 0.2)
        self.assertEqual(result["meta"]["mmr_lambda"], 0.8)
        for recommendation in result["recommendations"]:
            self.assertEqual(
                recommendation["score"],
                recommendation["components"]["context_relevance"],
            )

    def test_high_diversity_strength_promotes_diversity_after_first_result(self):
        feature_values = {
            "tempo": 220,
            "energy": 1.0,
            "valence": 1.0,
            "danceability": 1.0,
            "acousticness": 0.0,
            "instrumentalness": 0.0,
            "loudness": 0.0,
            "speechiness": 0.0,
        }
        self._create_track("ctx-history", **feature_values)
        self._create_track("ctx-a", **feature_values)
        self._create_track(
            "ctx-b",
            tempo=215,
            energy=0.95,
            valence=0.95,
            danceability=0.95,
            acousticness=0.05,
            instrumentalness=0.05,
            loudness=-1.0,
            speechiness=0.05,
        )
        self._create_track(
            "ctx-c",
            tempo=40,
            energy=0.0,
            valence=0.0,
            danceability=0.0,
            acousticness=1.0,
            instrumentalness=1.0,
            loudness=-30.0,
            speechiness=1.0,
        )
        base_request = self._request(
            algorithm="context_mmr",
            history=["ctx-history"],
            candidate_ids=["ctx-a", "ctx-b", "ctx-c"],
            limit=2,
        )

        relevance_result = self.service.recommend(
            {**base_request, "context": {"diversity_strength": 0}}
        )
        diversity_result = self.service.recommend(
            {**base_request, "context": {"diversity_strength": 0.9}}
        )

        self.assertEqual(
            [item["track"]["id"] for item in relevance_result["recommendations"]],
            ["ctx-a", "ctx-b"],
        )
        self.assertEqual(
            [item["track"]["id"] for item in diversity_result["recommendations"]],
            ["ctx-a", "ctx-c"],
        )

    def test_context_uses_recency_weighted_history_profile(self):
        result = self.service.recommend(
            self._request(
                algorithm="context_mmr",
                history=["track-a", "track-b", "track-c"],
                candidate_ids=["track-d"],
                context={"diversity_strength": 0.2},
            )
        )

        self.assertEqual(result["meta"]["history_count_used"], 3)
        self.assertEqual(result["meta"]["history_window_size"], 5)
