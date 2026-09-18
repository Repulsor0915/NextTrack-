from django.test import SimpleTestCase

from offline_evaluation.protocol import (
    DEFAULT_COHERENT_GENRES,
    build_scenario_review,
    generate_scenario_draft,
)
from recommendations.domain.mood_model import MOOD_PROFILES


class ScenarioGeneratorTests(SimpleTestCase):
    def test_generates_deterministic_reviewable_scenario_families(self):
        records = self._catalogue()
        candidate_ids = {f"candidate-{index:03d}" for index in range(10)}

        first = generate_scenario_draft(
            records,
            candidate_ids=candidate_ids,
            catalogue_version="test-full",
            catalogue_sha256="full-sha",
            candidate_pool_sha256="pool-sha",
            top_n=10,
        )
        second = generate_scenario_draft(
            records,
            candidate_ids=candidate_ids,
            catalogue_version="test-full",
            catalogue_sha256="full-sha",
            candidate_pool_sha256="pool-sha",
            top_n=10,
        )

        self.assertEqual(first, second)
        self.assertEqual(first["status"], "draft_requires_human_review")
        self.assertEqual(first["scenario_count"], 21)
        self.assertEqual(
            first["category_counts"],
            {
                "coherent_multi_track_history": 9,
                "mood_only": 4,
                "single_track_history": 4,
                "transition_conflicting_history": 4,
            },
        )

        for scenario in first["scenarios"]:
            history = set(scenario["request_template"]["history"])
            self.assertTrue(history.isdisjoint(candidate_ids))
            self.assertEqual(scenario["request_template"]["limit"], 10)

    def test_coherent_histories_are_nested_and_use_distinct_artists(self):
        draft = generate_scenario_draft(
            self._catalogue(),
            candidate_ids={f"candidate-{index:03d}" for index in range(10)},
            catalogue_version="test-full",
            catalogue_sha256="full-sha",
            candidate_pool_sha256="pool-sha",
            top_n=10,
        )
        scenarios = {
            scenario["scenario_id"]: scenario for scenario in draft["scenarios"]
        }

        for genre in DEFAULT_COHERENT_GENRES:
            slug = genre.replace("-", "_")
            h1 = scenarios[f"coherent_{slug}_h1"]
            h3 = scenarios[f"coherent_{slug}_h3"]
            h5 = scenarios[f"coherent_{slug}_h5"]
            ids1 = set(h1["request_template"]["history"])
            ids3 = set(h3["request_template"]["history"])
            ids5 = set(h5["request_template"]["history"])
            self.assertTrue(ids1.issubset(ids3))
            self.assertTrue(ids3.issubset(ids5))
            artists = [track["artist"] for track in h5["history_tracks"]]
            self.assertEqual(len(artists), len(set(artists)))

    def test_review_document_contains_each_scenario_and_approval_gate(self):
        draft = generate_scenario_draft(
            self._catalogue(),
            candidate_ids={f"candidate-{index:03d}" for index in range(10)},
            catalogue_version="test-full",
            catalogue_sha256="full-sha",
            candidate_pool_sha256="pool-sha",
            top_n=10,
        )

        review = build_scenario_review(draft, draft_sha256="draft-sha")

        self.assertIn("awaiting human approval", review)
        self.assertIn("draft-sha", review)
        self.assertIn("single_happy_anchor", review)
        self.assertIn("coherent_pop", review)
        self.assertIn("transition_calm_to_energetic", review)
        self.assertIn("mood_only_sad", review)
        self.assertIn("Approve all scenarios as written", review)

    @classmethod
    def _catalogue(cls):
        records = [
            cls._record(
                f"candidate-{index:03d}",
                artist=f"Candidate Artist {index}",
                genre="candidate",
                energy=0.5,
                valence=0.5,
                acousticness=0.5,
            )
            for index in range(10)
        ]

        for genre_index, genre in enumerate(DEFAULT_COHERENT_GENRES):
            for index in range(12):
                records.append(
                    cls._record(
                        f"{genre.replace('-', '_')}-{index:03d}",
                        artist=f"{genre} Artist {index}",
                        genre=genre,
                        energy=0.35 + genre_index * 0.2 + index * 0.002,
                        valence=0.4 + genre_index * 0.1 + index * 0.002,
                        acousticness=0.55 - genre_index * 0.15,
                    )
                )

        for mood, profile in MOOD_PROFILES.items():
            for index in range(10):
                overrides = dict(profile)
                records.append(
                    cls._record(
                        f"mood-{mood}-{index:03d}",
                        artist=f"Mood {mood} Artist {index}",
                        genre=f"mood-{mood}",
                        **overrides,
                    )
                )
        return records

    @staticmethod
    def _record(
        track_id,
        *,
        artist,
        genre,
        tempo=120.0,
        energy=0.5,
        valence=0.5,
        danceability=0.5,
        acousticness=0.5,
        instrumentalness=0.1,
        loudness=-10.0,
        speechiness=0.05,
    ):
        return {
            "id": track_id,
            "title": f"Track {track_id}",
            "artist": artist,
            "genres": [genre],
            "features": {
                "tempo": tempo,
                "energy": energy,
                "valence": valence,
                "danceability": danceability,
                "acousticness": acousticness,
                "instrumentalness": instrumentalness,
                "loudness": loudness,
                "speechiness": speechiness,
            },
        }
