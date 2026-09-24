from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from recommendations.models import (
    CatalogueState, Track, TrackFeatures, TrackGenre, TrackSuggestion,
)


class PublicApiAndStaffAccessTests(APITestCase):
    def setUp(self):
        cache.clear()

    @staticmethod
    def create_track(track_id, *, title, artist, genre, tempo):
        track = Track.objects.create(
            id=track_id, title=title, artist=artist,
            genres=[genre] if genre else [], data_source="fixture-v1",
        )
        TrackFeatures.objects.create(
            track=track, tempo=tempo, energy=0.6, valence=0.7,
            danceability=0.5, acousticness=0.2, instrumentalness=0.0,
            loudness=-7.0, speechiness=0.05, feature_source="fixture-v1",
        )
        if genre:
            TrackGenre.objects.create(
                track=track, name=genre, normalized_name=genre.casefold(),
            )
        return track

    def test_health_does_not_require_a_catalogue(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"status": "ok"})

    def test_catalogue_status_requires_active_state(self):
        url = reverse("recommendations:catalogue")
        missing = self.client.get(url)
        self.assertEqual(missing.status_code, 503)
        self.assertEqual(missing.data["error"]["code"], "CATALOGUE_UNAVAILABLE")

        CatalogueState.objects.create(
            pk=1, version="fixture-v1", catalogue_sha256="a" * 64,
            record_count=4, import_mode="initial",
        )
        present = self.client.get(url)
        self.assertEqual(present.status_code, 200)
        self.assertEqual(present.data["version"], "fixture-v1")
        self.assertEqual(present.data["catalogue_sha256"], "a" * 64)

    def test_tracks_filter_exact_genre_and_paginate(self):
        self.create_track("a", title="Alpha", artist="Artist A", genre="pop", tempo=90)
        self.create_track(
            "b", title="Beta", artist="Artist B", genre="synth-pop", tempo=100
        )
        self.create_track("c", title="Gamma", artist="Artist C", genre="POP", tempo=110)
        self.create_track("d", title="Delta", artist="Artist D", genre="rock", tempo=120)
        url = reverse("recommendations:tracks")

        page = self.client.get(url, {"page_size": 2})
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.data["count"], 4)
        self.assertEqual([item["id"] for item in page.data["results"]], ["a", "b"])
        self.assertIsNotNone(page.data["next"])
        second = self.client.get(url, {"page": 2, "page_size": 2})
        self.assertEqual([item["id"] for item in second.data["results"]], ["c", "d"])

        pop = self.client.get(url, {"genre": "PoP"})
        self.assertEqual([item["id"] for item in pop.data["results"]], ["a", "c"])
        filtered = self.client.get(
            url, {"q": "Gamma", "artist": "Artist C", "bpm_min": 105,
                  "bpm_max": 115},
        )
        self.assertEqual(filtered.data["count"], 1)
        self.assertEqual(filtered.data["results"][0]["id"], "c")

    def test_tracks_reject_invalid_filters_and_return_detail(self):
        self.create_track("a", title="Alpha", artist="Artist", genre="pop", tempo=90)
        url = reverse("recommendations:tracks")
        for query in (
            {"page_size": 101},
            {"bpm_min": 120, "bpm_max": 100},
            {"unknown": "value"},
        ):
            response = self.client.get(url, query)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

        detail = self.client.get(reverse("recommendations:track-detail", args=["a"]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.data["features"]), 8)
        missing = self.client.get(
            reverse("recommendations:track-detail", args=["missing"])
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.data["error"]["code"], "NOT_FOUND")
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 405)
        self.assertEqual(
            self.client.delete(reverse("recommendations:track-detail", args=["a"])).status_code,
            405,
        )

    def test_suggestion_is_queued_without_adding_a_track(self):
        url = reverse("recommendations:track-suggestions")
        response = self.client.post(
            url,
            {"title": "Suggested Song", "artist": "New Artist",
             "album_name": "Suggested Album",
             "reference_url": "https://example.com/track"},
            format="json",
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(response.data["album_name"], "Suggested Album")
        self.assertEqual(TrackSuggestion.objects.count(), 1)
        suggestion = TrackSuggestion.objects.get()
        self.assertEqual(suggestion.album_name, "Suggested Album")
        self.assertEqual(suggestion.reference_url, "https://example.com/track")
        self.assertEqual(Track.objects.count(), 0)
        invalid = self.client.post(
            url, {"title": "Song", "artist": "Artist", "unexpected": 1},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)

    def test_product_recommendation_request_accepts_top_level_mood(self):
        self.create_track("a", title="Alpha", artist="A", genre="pop", tempo=90)
        self.create_track("b", title="Beta", artist="B", genre="pop", tempo=100)
        response = self.client.post(
            reverse("recommendations:recommendations"),
            {"history": ["a"], "mood": "happy", "bpm": {"min": 80, "max": 110},
             "limit": 1},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["recommendations"][0]["track"]["id"], "b")
        self.assertEqual(response.data["meta"]["mood"], "happy")
        self.assertIn("explanation_evidence", response.data["recommendations"][0])

        conflict = self.client.post(
            reverse("recommendations:recommendations"),
            {"mood": "happy", "context": {"mood": "sad"}},
            format="json",
        )
        self.assertEqual(conflict.status_code, 400)
        self.assertIn("mood", conflict.data["error"]["details"])

    def test_suggestion_rate_limit_returns_standard_error(self):
        url = reverse("recommendations:track-suggestions")
        for number in range(3):
            response = self.client.post(
                url, {"title": f"Song {number}", "artist": "Artist"},
                format="json",
            )
            self.assertEqual(response.status_code, 202)
        limited = self.client.post(
            url, {"title": "Song 4", "artist": "Artist"}, format="json"
        )
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.data["error"]["code"], "THROTTLED")
        self.assertEqual(TrackSuggestion.objects.count(), 3)

    def test_recommendation_rate_limit_is_independent_of_track_reads(self):
        self.create_track("a", title="Alpha", artist="A", genre="pop", tempo=90)
        url = reverse("recommendations:recommendations")
        for _ in range(12):
            self.assertEqual(self.client.post(url, {}, format="json").status_code, 200)
        limited = self.client.post(url, {}, format="json")
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.data["error"]["code"], "THROTTLED")
        self.assertEqual(
            self.client.get(reverse("recommendations:tracks")).status_code, 200
        )

    def test_oversized_request_uses_standard_error_without_writing(self):
        response = self.client.post(
            reverse("recommendations:track-suggestions"),
            {"title": "Song", "artist": "Artist", "note": "x" * 70000},
            format="json",
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"]["code"], "REQUEST_TOO_LARGE")
        self.assertEqual(TrackSuggestion.objects.count(), 0)

    def test_staff_token_is_required_to_review_suggestions(self):
        suggestion = TrackSuggestion.objects.create(title="Song", artist="Artist")
        listing = reverse("recommendations:staff-track-suggestions")
        detail = reverse(
            "recommendations:staff-track-suggestion-detail", args=[suggestion.pk]
        )
        self.assertEqual(self.client.get(listing).status_code, 401)

        user_model = get_user_model()
        regular = user_model.objects.create_user("regular", password="password")
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=regular).key}"
        )
        self.assertEqual(self.client.get(listing).status_code, 403)

        staff = user_model.objects.create_user(
            "staff", password="password", is_staff=True
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=staff).key}"
        )
        result = self.client.get(listing)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["count"], 1)
        reviewed = self.client.patch(detail, {"decision": "reviewed"}, format="json")
        self.assertEqual(reviewed.status_code, 200)
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.status, "reviewed")
        self.assertIsNotNone(suggestion.reviewed_at)
        self.assertEqual(Track.objects.count(), 0)

    @override_settings(CORS_ALLOWED_ORIGINS=["https://frontend.example"])
    def test_cors_only_allows_configured_origin(self):
        url = reverse("recommendations:tracks")
        allowed = self.client.get(url, HTTP_ORIGIN="https://frontend.example")
        denied = self.client.get(url, HTTP_ORIGIN="https://other.example")
        self.assertEqual(
            allowed.headers.get("Access-Control-Allow-Origin"),
            "https://frontend.example",
        )
        self.assertIsNone(denied.headers.get("Access-Control-Allow-Origin"))
        preflight = self.client.options(
            reverse("recommendations:track-suggestions"),
            HTTP_ORIGIN="https://frontend.example",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        self.assertEqual(preflight.status_code, 200)
        self.assertEqual(
            preflight.headers.get("Access-Control-Allow-Origin"),
            "https://frontend.example",
        )

    def test_schema_and_documentation_require_a_superuser_session(self):
        routes = ("schema", "swagger", "redoc")
        for name in routes:
            self.assertEqual(
                self.client.get(reverse(f"recommendations:{name}")).status_code,
                403,
            )

        user_model = get_user_model()
        regular = user_model.objects.create_user("docs-regular", password="password")
        staff = user_model.objects.create_user(
            "docs-staff", password="password", is_staff=True
        )
        superuser = user_model.objects.create_superuser(
            "docs-admin", password="password"
        )
        for user in (regular, staff):
            self.client.force_login(user)
            for name in routes:
                self.assertEqual(
                    self.client.get(reverse(f"recommendations:{name}")).status_code,
                    403,
                )

        self.client.force_login(superuser)
        schema = self.client.get(reverse("recommendations:schema"))
        self.assertEqual(schema.status_code, 200)
        self.assertIn("/api/v1/tracks/", str(schema.data))
        self.assertEqual(
            self.client.get(reverse("recommendations:swagger")).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("recommendations:redoc")).status_code, 200
        )
        self.client.logout()
        self.assertEqual(self.client.get(reverse("recommendations:schema")).status_code, 403)
        self.assertEqual(self.client.get(reverse("recommendations:tracks")).status_code, 200)
