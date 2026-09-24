from django.test import TestCase

from recommendations.audio_features import build_feature_vector
from recommendations.domain.feature_vectors import calculate_similarity
from recommendations.domain.mood_model import MOOD_PROFILES
from recommendations.models import Track, TrackFeatures
from recommendations.services.recommendation_service import RecommendationService


class ExplanationEvidenceTests(TestCase):
    @staticmethod
    def create_track(track_id, **features):
        values = {
            "tempo": 120,
            "energy": 0.5,
            "valence": 0.5,
            "danceability": 0.5,
            "acousticness": 0.5,
            "instrumentalness": 0.0,
            "loudness": -8.0,
            "speechiness": 0.05,
        }
        values.update(features)
        track = Track.objects.create(
            id=track_id,
            title=track_id,
            artist="Evidence Artist",
            data_source="evidence-fixture",
        )
        TrackFeatures.objects.create(
            track=track,
            feature_source="evidence-fixture",
            **values,
        )
        return track

    def setUp(self):
        self.service = RecommendationService()

    @staticmethod
    def request(*, algorithm, history=None, mood=None, strength=None, limit=3):
        context = {}
        if mood is not None:
            context["mood"] = mood
        if strength is not None:
            context["diversity_strength"] = strength
        return {
            "algorithm": algorithm,
            "history": history or [],
            "limit": limit,
            "context": context,
        }

    def test_random_does_not_invent_history_or_mood_evidence(self):
        self.create_track("candidate")

        result = self.service.recommend(
            self.request(algorithm="random", mood="happy")
        )
        item = result["recommendations"][0]
        evidence = item["explanation_evidence"]

        self.assertEqual(evidence["path"], "random")
        self.assertIsNone(evidence["base_score"])
        self.assertIsNone(evidence["base_rank"])
        self.assertIsNone(evidence["rank_change"])
        self.assertIsNone(evidence["history"])
        self.assertIsNone(evidence["mood"])
        self.assertIsNone(evidence["mmr"])
        self.assertNotIn("mood", str(item["explanation"]).lower())
        self.assertEqual(
            result["meta"]["explanation_model_version"],
            "evidence-grounded-explanation-v1",
        )

    def test_basic_cbf_exposes_profile_and_nearest_used_play(self):
        old = self.create_track("old", energy=0.1, valence=0.1)
        recent = self.create_track("recent", energy=0.9, valence=0.9)
        candidate = self.create_track("candidate", energy=0.85, valence=0.85)

        result = self.service.recommend(
            self.request(
                algorithm="cbf",
                history=[old.id, recent.id],
                mood="sad",
                limit=1,
            )
        )
        item = result["recommendations"][0]
        evidence = item["explanation_evidence"]
        actual = build_feature_vector(candidate.features)
        old_vector = build_feature_vector(old.features)
        recent_vector = build_feature_vector(recent.features)
        target = evidence["history"]["features"]
        profile = {name: values["target"] for name, values in target.items()}

        self.assertEqual(evidence["path"], "basic_cbf")
        self.assertIsNone(evidence["mood"])
        self.assertIsNone(evidence["mood_fit"])
        self.assertIsNone(evidence["mmr"])
        self.assertEqual(evidence["base_rank"], evidence["final_rank"])
        self.assertEqual(evidence["rank_change"], 0)
        self.assertEqual(evidence["history"]["profile_method"], "equal")
        self.assertAlmostEqual(profile["energy"], 0.5)
        for name, values in target.items():
            self.assertEqual(values["actual"], actual[name])
            self.assertAlmostEqual(
                values["closeness"], 1 - abs(actual[name] - values["target"])
            )
        expected = calculate_similarity(
            profile,
            actual,
            metric=evidence["history"]["similarity_metric"],
            weights=evidence["history"]["feature_weights"],
        )
        self.assertAlmostEqual(evidence["base_score"], expected)
        self.assertEqual(item["score"], round(expected, 4))
        closest = evidence["history"]["closest_track"]
        self.assertEqual(closest["track_id"], recent.id)
        self.assertEqual(closest["request_index"], 1)
        self.assertAlmostEqual(
            closest["similarity"],
            calculate_similarity(
                actual,
                recent_vector,
                metric=evidence["history"]["similarity_metric"],
                weights=evidence["history"]["feature_weights"],
            ),
        )
        self.assertNotEqual(old_vector, recent_vector)
        self.assertNotIn("sad", str(item["explanation"]).lower())

    def test_mood_only_scores_candidates_without_random_selection(self):
        matching = self.create_track(
            "matching", energy=0.70, valence=0.85, danceability=0.65
        )
        self.create_track("different", energy=0.1, valence=0.1)

        result = self.service.recommend(
            self.request(algorithm="context_mmr", mood="happy", strength=0)
        )
        item = result["recommendations"][0]
        evidence = item["explanation_evidence"]
        mood_evidence = evidence["mood"]

        self.assertEqual(item["track"]["id"], matching.id)
        self.assertEqual(evidence["path"], "mood_mmr")
        self.assertIsNone(evidence["history"])
        self.assertIsNone(evidence["history_similarity"])
        self.assertEqual(set(mood_evidence["features"]), set(MOOD_PROFILES["happy"]))
        self.assertAlmostEqual(sum(mood_evidence["active_feature_weights"].values()), 1)
        actual = build_feature_vector(matching.features)
        for name, values in mood_evidence["features"].items():
            self.assertEqual(values["actual"], actual[name])
            self.assertEqual(values["target"], MOOD_PROFILES["happy"][name])
            self.assertAlmostEqual(
                values["closeness"], 1 - abs(values["actual"] - values["target"])
            )
        expected = sum(
            mood_evidence["active_feature_weights"][name] * values["closeness"]
            for name, values in mood_evidence["features"].items()
        )
        self.assertAlmostEqual(evidence["mood_fit"], expected)
        self.assertAlmostEqual(evidence["base_score"], expected)
        self.assertEqual(item["score"], round(expected, 4))
        self.assertNotIn("history", str(item["explanation"]).lower())
        self.assertFalse(evidence["mmr"]["ranking_changed"])

    def test_combined_relevance_uses_separate_profile_targets_and_weights(self):
        self.create_track("old", energy=0.2, valence=0.2)
        self.create_track("recent", energy=0.8, valence=0.8)
        self.create_track("candidate", energy=0.7, valence=0.85)

        result = self.service.recommend(
            self.request(
                algorithm="context_mmr",
                history=["old", "recent"],
                mood="happy",
                strength=0,
                limit=1,
            )
        )
        item = result["recommendations"][0]
        evidence = item["explanation_evidence"]

        self.assertEqual(evidence["path"], "combined_mmr")
        self.assertEqual(evidence["history"]["profile_method"], "linear_recency")
        self.assertAlmostEqual(
            evidence["history"]["features"]["energy"]["target"],
            (0.2 + 2 * 0.8) / 3,
        )
        self.assertEqual(evidence["mood"]["features"]["energy"]["target"], 0.7)
        weights = evidence["relevance_weights"]
        self.assertAlmostEqual(
            evidence["base_score"],
            weights["history"] * evidence["history_similarity"]
            + weights["mood"] * evidence["mood_fit"],
        )
        self.assertEqual(item["score"], round(evidence["base_score"], 4))

    def test_mmr_evidence_tracks_greedy_selection_and_rank_direction(self):
        high = {
            "tempo": 220,
            "energy": 1,
            "valence": 1,
            "danceability": 1,
            "acousticness": 0,
            "instrumentalness": 0,
            "loudness": 0,
            "speechiness": 0,
        }
        low = {
            "tempo": 40,
            "energy": 0,
            "valence": 0,
            "danceability": 0,
            "acousticness": 1,
            "instrumentalness": 1,
            "loudness": -30,
            "speechiness": 1,
        }
        self.create_track("history", **high)
        self.create_track("first", **high)
        similar_features = {
            name: value
            for name, value in high.items()
            if name not in {"energy", "valence"}
        }
        self.create_track(
            "similar", energy=0.95, valence=0.95, **similar_features
        )
        self.create_track("diverse", **low)
        request = self.request(
            algorithm="context_mmr", history=["history"], strength=0.9, limit=2
        )
        result = self.service.recommend(request)
        first, second = result["recommendations"]
        first_evidence = first["explanation_evidence"]
        second_evidence = second["explanation_evidence"]

        self.assertEqual(
            [first["track"]["id"], second["track"]["id"]],
            ["first", "diverse"],
        )
        self.assertEqual(first_evidence["base_rank"], 1)
        self.assertEqual(first_evidence["rank_change"], 0)
        self.assertIsNone(first_evidence["mmr"]["supporting_track"])
        self.assertIsNone(first_evidence["mmr"]["diversity_gain"])
        self.assertNotIn("MMR changed", str(first["explanation"]))
        self.assertEqual(second_evidence["base_rank"], 3)
        self.assertEqual(second_evidence["final_rank"], 2)
        self.assertEqual(second_evidence["rank_change"], 1)
        self.assertTrue(second_evidence["mmr"]["ranking_changed"])
        support = second_evidence["mmr"]["supporting_track"]
        self.assertEqual(support["track_id"], "first")
        self.assertIn(
            "maximum similarity to an earlier recommendation:",
            " ".join(second["explanation"]["evidence"]),
        )
        self.assertNotIn("first", " ".join(second["explanation"]["evidence"]))
        first_vector = build_feature_vector(Track.objects.get(id="first").features)
        diverse_vector = build_feature_vector(Track.objects.get(id="diverse").features)
        self.assertAlmostEqual(
            support["similarity"],
            calculate_similarity(
                diverse_vector,
                first_vector,
                metric=second_evidence["mmr"]["similarity_metric"],
                weights=second_evidence["history"]["feature_weights"],
            ),
        )
        self.assertAlmostEqual(
            second_evidence["mmr"]["diversity_gain"],
            1 - support["similarity"],
        )
        self.assertAlmostEqual(
            second_evidence["mmr"]["selection_score"],
            0.1 * second_evidence["base_score"]
            + 0.9 * second_evidence["mmr"]["diversity_gain"],
        )
        self.assertEqual(
            second["components"]["mmr_score"],
            round(second_evidence["mmr"]["selection_score"], 4),
        )
        self.assertIn("MMR changed", str(second["explanation"]))

        zero = self.service.recommend({
            **request,
            "context": {"diversity_strength": 0},
        })
        self.assertEqual(
            [item["track"]["id"] for item in zero["recommendations"]],
            ["first", "similar"],
        )
        for item in zero["recommendations"]:
            evidence = item["explanation_evidence"]
            self.assertEqual(evidence["rank_change"], 0)
            self.assertFalse(evidence["mmr"]["ranking_changed"])
            self.assertIsNone(evidence["mmr"]["supporting_track"])
            self.assertNotIn("MMR changed", str(item["explanation"]))

    def test_auto_history_path_is_distinct_from_explicit_basic_cbf(self):
        self.create_track("history")
        self.create_track("candidate")

        auto = self.service.recommend(
            self.request(algorithm="auto", history=["history"], limit=1)
        )
        basic = self.service.recommend(
            self.request(algorithm="cbf", history=["history"], limit=1)
        )

        self.assertEqual(
            auto["recommendations"][0]["explanation_evidence"]["path"],
            "history_mmr",
        )
        self.assertEqual(
            basic["recommendations"][0]["explanation_evidence"]["path"],
            "basic_cbf",
        )
        self.assertIsNotNone(auto["recommendations"][0]["explanation_evidence"]["mmr"])
        self.assertIsNone(basic["recommendations"][0]["explanation_evidence"]["mmr"])

    def test_closest_history_track_is_selected_only_from_the_used_window(self):
        history = ["excluded_old"]
        self.create_track("excluded_old", energy=0.95, valence=0.95)
        for index in range(5):
            track_id = f"used_{index}"
            self.create_track(track_id, energy=0.1, valence=0.1)
            history.append(track_id)
        self.create_track("candidate", energy=0.95, valence=0.95)

        result = self.service.recommend(
            self.request(algorithm="cbf", history=history, limit=1)
        )
        closest = result["recommendations"][0]["explanation_evidence"]["history"][
            "closest_track"
        ]

        self.assertEqual(result["meta"]["history_count_used"], 5)
        self.assertEqual(closest["track_id"], "used_4")
        self.assertEqual(closest["request_index"], 5)
