import random

from django.test import SimpleTestCase

from recommendations.domain.cbf_ranker import rank_cbf
from recommendations.domain.context_ranker import (
    ContextRanking,
    score_context_candidates,
)
from recommendations.domain.feature_vectors import (
    FEATURE_WEIGHTS,
    build_recency_weighted_profile,
    build_session_profile,
    weighted_cosine_similarity,
)
from recommendations.domain.mmr import rerank_mmr
from recommendations.domain.mood_model import (
    MOOD_MODEL_VERSION,
    MOOD_PROFILES,
    calculate_mood_fit,
    score_mood,
)
from recommendations.domain.random_ranker import rank_random
from recommendations.audio_features import (
    FEATURE_NAMES,
    build_feature_vector,
    normalize_feature,
)


class RandomRankerTests(SimpleTestCase):
    def test_returns_requested_number_of_unique_candidates(self):
        candidates = ["track-a", "track-b", "track-c", "track-d"]

        results = rank_random(
            candidates,
            3,
            random_source=random.Random(42),
        )

        self.assertEqual(len(results), 3)
        self.assertEqual(len(set(results)), 3)
        self.assertTrue(set(results).issubset(candidates))

    def test_returns_all_candidates_when_limit_is_larger_than_pool(self):
        candidates = ["track-a", "track-b"]

        results = rank_random(
            candidates,
            5,
            random_source=random.Random(42),
        )

        self.assertCountEqual(results, candidates)

    def test_seeded_source_makes_result_repeatable(self):
        candidates = ["track-a", "track-b", "track-c", "track-d"]

        first = rank_random(candidates, 2, random_source=random.Random(7))
        second = rank_random(candidates, 2, random_source=random.Random(7))

        self.assertEqual(first, second)

    def test_does_not_modify_input_candidates(self):
        candidates = ["track-a", "track-b", "track-c"]
        original = candidates.copy()

        rank_random(candidates, 2, random_source=random.Random(42))

        self.assertEqual(candidates, original)

    def test_rejects_limit_below_one(self):
        with self.assertRaises(ValueError):
            rank_random(["track-a"], 0)


class FeatureVectorTests(SimpleTestCase):
    @staticmethod
    def _uniform_vector(value):
        return {feature_name: value for feature_name in FEATURE_NAMES}

    def test_feature_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(FEATURE_WEIGHTS.values()), 1.0)

    def test_normalization_maps_range_and_clamps_outliers(self):
        self.assertEqual(normalize_feature("tempo", 40), 0.0)
        self.assertEqual(normalize_feature("tempo", 220), 1.0)
        self.assertEqual(normalize_feature("tempo", 130), 0.5)
        self.assertEqual(normalize_feature("tempo", 20), 0.0)
        self.assertEqual(normalize_feature("tempo", 240), 1.0)
        self.assertEqual(normalize_feature("loudness", -15), 0.5)

    def test_build_feature_vector_normalizes_all_eight_features(self):
        vector = build_feature_vector(
            {
                "tempo": 130,
                "energy": 0.8,
                "valence": 0.7,
                "danceability": 0.6,
                "acousticness": 0.1,
                "instrumentalness": 0.0,
                "loudness": -15,
                "speechiness": 0.05,
            }
        )

        self.assertEqual(set(vector), set(FEATURE_NAMES))
        self.assertEqual(vector["tempo"], 0.5)
        self.assertEqual(vector["loudness"], 0.5)

    def test_identical_vectors_have_similarity_one(self):
        vector = self._uniform_vector(0.6)

        self.assertAlmostEqual(weighted_cosine_similarity(vector, vector), 1.0)

    def test_zero_vector_similarity_is_zero(self):
        zero_vector = self._uniform_vector(0.0)
        other_vector = self._uniform_vector(0.6)

        self.assertEqual(
            weighted_cosine_similarity(zero_vector, other_vector),
            0.0,
        )

    def test_session_profile_uses_only_the_most_recent_window(self):
        history_vectors = [
            self._uniform_vector(value) for value in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
        ]

        profile = build_session_profile(history_vectors, window_size=5)

        for value in profile.values():
            self.assertAlmostEqual(value, 0.6)

    def test_session_profile_requires_history(self):
        with self.assertRaises(ValueError):
            build_session_profile([])

    def test_recency_profile_gives_more_weight_to_later_history(self):
        oldest = self._uniform_vector(0.0)
        newest = self._uniform_vector(1.0)

        profile = build_recency_weighted_profile([oldest, newest])

        for value in profile.values():
            self.assertAlmostEqual(value, 2 / 3)


class CbfRankerTests(SimpleTestCase):
    @staticmethod
    def _uniform_vector(value):
        return {feature_name: value for feature_name in FEATURE_NAMES}

    def test_ranks_more_similar_candidate_first(self):
        profile = {
            "tempo": 0.7,
            "energy": 0.9,
            "valence": 0.8,
            "danceability": 0.7,
            "acousticness": 0.1,
            "instrumentalness": 0.0,
            "loudness": 0.8,
            "speechiness": 0.1,
        }
        candidates = [
            (
                "far-track",
                {
                    "tempo": 0.1,
                    "energy": 0.1,
                    "valence": 0.1,
                    "danceability": 0.2,
                    "acousticness": 0.9,
                    "instrumentalness": 1.0,
                    "loudness": 0.2,
                    "speechiness": 0.9,
                },
            ),
            (
                "close-track",
                {
                    "tempo": 0.68,
                    "energy": 0.88,
                    "valence": 0.82,
                    "danceability": 0.69,
                    "acousticness": 0.12,
                    "instrumentalness": 0.01,
                    "loudness": 0.78,
                    "speechiness": 0.11,
                },
            ),
            ("medium-track", self._uniform_vector(0.5)),
        ]

        results = rank_cbf(candidates, profile, limit=3)

        self.assertEqual(results[0].candidate, "close-track")
        self.assertEqual(results[-1].candidate, "far-track")
        self.assertGreaterEqual(results[0].score, results[1].score)
        self.assertGreaterEqual(results[1].score, results[2].score)

    def test_respects_limit(self):
        profile = self._uniform_vector(0.5)
        candidates = [
            (f"track-{index}", self._uniform_vector(index / 10))
            for index in range(1, 6)
        ]

        results = rank_cbf(candidates, profile, limit=2)

        self.assertEqual(len(results), 2)

    def test_reports_per_feature_closeness(self):
        profile = self._uniform_vector(0.5)
        vector = self._uniform_vector(0.5)

        result = rank_cbf([("track-a", vector)], profile, limit=1)[0]

        self.assertEqual(set(result.feature_closeness), set(FEATURE_NAMES))
        self.assertTrue(all(value == 1.0 for value in result.feature_closeness.values()))

    def test_rejects_limit_below_one(self):
        with self.assertRaises(ValueError):
            rank_cbf([], self._uniform_vector(0.5), limit=0)


class ContextRankerTests(SimpleTestCase):
    @staticmethod
    def _vector(**overrides):
        vector = {feature_name: 0.5 for feature_name in FEATURE_NAMES}
        vector.update(overrides)
        return vector

    def test_happy_mood_prefers_high_valence_and_energy(self):
        happy_vector = self._vector(
            valence=0.85,
            energy=0.70,
            danceability=0.65,
        )
        low_mood_vector = self._vector(
            valence=0.10,
            energy=0.15,
            danceability=0.20,
        )

        self.assertGreater(
            calculate_mood_fit(happy_vector, "happy"),
            calculate_mood_fit(low_mood_vector, "happy"),
        )

    def test_mood_model_is_explicitly_versioned_and_uses_audio_features_only(self):
        self.assertEqual(
            MOOD_MODEL_VERSION,
            "va-informed-8-feature-heuristic-v1",
        )
        for profile in MOOD_PROFILES.values():
            self.assertTrue(set(profile).issubset(FEATURE_NAMES))
            self.assertNotIn("arousal", profile)
            self.assertNotIn("dominance", profile)

    def test_mood_score_returns_feature_level_evidence(self):
        score = score_mood(
            self._vector(valence=0.85, energy=0.70, danceability=0.65),
            "happy",
        )

        self.assertAlmostEqual(score.fit, 1.0)
        self.assertEqual(
            set(score.feature_closeness),
            {"valence", "energy", "danceability"},
        )

    def test_mood_only_context_can_rank_without_history(self):
        candidates = [
            (
                "low-mood-track",
                self._vector(valence=0.1, energy=0.1, danceability=0.2),
            ),
            (
                "happy-track",
                self._vector(valence=0.85, energy=0.7, danceability=0.65),
            ),
        ]

        results = score_context_candidates(candidates, mood="happy")

        self.assertEqual(results[0].candidate, "happy-track")
        self.assertIsNone(results[0].history_similarity)
        self.assertIsNotNone(results[0].mood_fit)
        self.assertEqual(
            set(results[0].mood_feature_closeness),
            {"valence", "energy", "danceability"},
        )

    def test_history_and_mood_are_combined_into_context_relevance(self):
        profile = self._vector(energy=0.8, valence=0.8)
        candidate = self._vector(energy=0.7, valence=0.85, danceability=0.65)

        result = score_context_candidates(
            [("track-a", candidate)],
            session_profile=profile,
            mood="happy",
        )[0]

        expected = 0.65 * result.history_similarity + 0.35 * result.mood_fit
        self.assertAlmostEqual(result.relevance, expected)

    def test_bpm_constraint_is_reported_as_hard_fit(self):
        result = score_context_candidates(
            [("track-a", self._vector())],
            mood="calm",
            bpm_constraint_applied=True,
        )[0]

        self.assertIs(result.bpm_constraint_satisfied, True)

    def test_rejects_request_without_history_profile_or_mood(self):
        with self.assertRaises(ValueError):
            score_context_candidates([("track-a", self._vector())])


class MmrTests(SimpleTestCase):
    @staticmethod
    def _vector(high_group, low_group):
        return {
            "tempo": high_group,
            "energy": high_group,
            "valence": high_group,
            "danceability": high_group,
            "acousticness": low_group,
            "instrumentalness": low_group,
            "loudness": high_group,
            "speechiness": low_group,
        }

    def _ranking(self, candidate, relevance, vector):
        return ContextRanking(
            candidate=candidate,
            vector=vector,
            relevance=relevance,
            history_similarity=relevance,
            mood_fit=None,
            bpm_constraint_satisfied=None,
            feature_closeness={},
        )

    def setUp(self):
        self.relevant = self._ranking(
            "track-a",
            0.95,
            self._vector(1.0, 0.0),
        )
        self.similar = self._ranking(
            "track-b",
            0.90,
            self._vector(0.95, 0.05),
        )
        self.diverse = self._ranking(
            "track-c",
            0.70,
            self._vector(0.0, 1.0),
        )
        self.rankings = [self.relevant, self.similar, self.diverse]

    def test_zero_diversity_strength_preserves_relevance_order(self):
        results = rerank_mmr(self.rankings, 2, diversity_strength=0)

        self.assertEqual(
            [result.context.candidate for result in results],
            ["track-a", "track-b"],
        )

    def test_high_diversity_strength_promotes_a_different_second_track(self):
        results = rerank_mmr(self.rankings, 2, diversity_strength=0.9)

        self.assertEqual(
            [result.context.candidate for result in results],
            ["track-a", "track-c"],
        )
        self.assertGreater(results[1].diversity_gain, 0.9)

    def test_first_selection_is_most_relevant_at_any_diversity_strength(self):
        results = rerank_mmr(self.rankings, 1, diversity_strength=1)

        self.assertEqual(results[0].context.candidate, "track-a")
        self.assertEqual(results[0].diversity_penalty, 0)

    def test_does_not_modify_input_rankings(self):
        original = self.rankings.copy()

        rerank_mmr(self.rankings, 2, diversity_strength=0.5)

        self.assertEqual(self.rankings, original)

    def test_rejects_diversity_strength_outside_zero_to_one(self):
        with self.assertRaises(ValueError):
            rerank_mmr(self.rankings, 2, diversity_strength=1.1)
