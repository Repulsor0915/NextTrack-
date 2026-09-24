from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from recommendations.models import CatalogueState, Track, TrackFeatures, TrackSuggestion


class AdminOperationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.track = Track.objects.create(
            id="admin-track", title="Admin Test Song", artist="Test Artist",
            genres=["pop"], year=2024, data_source="admin-test-v1",
        )
        TrackFeatures.objects.create(
            track=cls.track, tempo=120, energy=0.8, valence=0.7,
            danceability=0.6, acousticness=0.1, instrumentalness=0.0,
            loudness=-6.0, speechiness=0.05, feature_source="admin-test-v1",
        )
        CatalogueState.objects.create(
            version="admin-test-v1", catalogue_sha256="a" * 64,
            record_count=1, import_mode="initial",
        )
        cls.suggestion = TrackSuggestion.objects.create(
            title="Suggested Song", artist="Suggested Artist",
            album_name="Suggested Album",
            reference_url="https://example.com/track", note="Please review.",
        )
        cls.superuser = get_user_model().objects.create_superuser(
            username="admin-test", password="test-password", email="admin@example.com"
        )

    def test_public_page_needs_no_login_but_admin_does(self):
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        login_redirect = self.client.get(reverse("admin:index"))
        self.assertEqual(login_redirect.status_code, 302)
        self.assertIn("/admin/login/", login_redirect.url)

        regular = get_user_model().objects.create_user(
            username="regular-test", password="test-password"
        )
        self.client.force_login(regular)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)

    def test_admin_login_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            reverse("admin:login"),
            {"username": "admin-test", "password": "test-password"},
        )
        self.assertEqual(response.status_code, 403)

    def test_catalogue_admin_shows_version_and_live_counts(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse("admin:recommendations_cataloguestate_changelist")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "admin-test-v1")
        self.assertContains(response, "Track rows")
        self.assertContains(response, "Feature rows")
        self.assertContains(response, "Snapshot consistent")
        model_admin = admin.site._registry[CatalogueState]
        state = CatalogueState.objects.get(pk=1)
        self.assertEqual(model_admin.actual_track_count(state), 1)
        self.assertEqual(model_admin.actual_feature_count(state), 1)
        self.assertTrue(model_admin.snapshot_consistent(state))

    def test_track_admin_supports_search_and_filters(self):
        self.client.force_login(self.superuser)
        url = reverse("admin:recommendations_track_changelist")
        matching = self.client.get(url, {"q": "Admin Test Song", "explicit__exact": "0"})
        self.assertEqual(matching.status_code, 200)
        self.assertEqual(matching.context["cl"].result_count, 1)
        missing = self.client.get(url, {"q": "Different Song"})
        self.assertEqual(missing.context["cl"].result_count, 0)

    def test_catalogue_models_cannot_be_edited_in_admin(self):
        self.client.force_login(self.superuser)
        model_urls = (
            ("track", self.track.pk, {"title": "Changed"}),
            ("trackfeatures", self.track.pk, {"energy": "0.1"}),
            ("cataloguestate", 1, {"version": "changed-v2"}),
        )
        for model_name, pk, payload in model_urls:
            with self.subTest(model=model_name):
                base = f"admin:recommendations_{model_name}"
                detail = reverse(f"{base}_change", args=[pk])
                self.assertEqual(self.client.get(detail).status_code, 200)
                self.assertEqual(self.client.post(detail, payload).status_code, 403)
                self.assertEqual(
                    self.client.get(reverse(f"{base}_add")).status_code, 403
                )
                self.assertEqual(
                    self.client.post(reverse(f"{base}_delete", args=[pk])).status_code,
                    403,
                )
        self.track.refresh_from_db()
        self.assertEqual(self.track.title, "Admin Test Song")
        self.assertEqual(TrackFeatures.objects.get(pk=self.track.pk).energy, 0.8)
        self.assertEqual(CatalogueState.objects.get(pk=1).version, "admin-test-v1")

    def test_staff_with_suggestion_permission_can_review_without_importing(self):
        staff = get_user_model().objects.create_user(
            username="reviewer-test", password="test-password", is_staff=True
        )
        staff.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="recommendations",
                codename="change_tracksuggestion",
            )
        )
        self.client.force_login(staff)
        detail = reverse(
            "admin:recommendations_tracksuggestion_change",
            args=[self.suggestion.pk],
        )
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertContains(self.client.get(detail), "Suggested Album")
        self.assertEqual(
            self.client.post(
                detail,
                {"status": "reviewed", "title": "Tampered", "_save": "Save"},
            ).status_code,
            302,
        )
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, "reviewed")
        self.assertIsNotNone(self.suggestion.reviewed_at)
        self.assertEqual(Track.objects.count(), 1)
        self.assertEqual(
            self.client.post(detail, {"status": "pending", "_save": "Save"}).status_code,
            302,
        )
        self.suggestion.refresh_from_db()
        self.assertIsNone(self.suggestion.reviewed_at)
        self.assertEqual(self.suggestion.title, "Suggested Song")
        self.assertEqual(
            self.client.get(reverse("admin:recommendations_track_changelist")).status_code,
            403,
        )

    def test_staff_without_model_permission_cannot_review_suggestions(self):
        staff = get_user_model().objects.create_user(
            username="unprivileged-staff", password="test-password", is_staff=True
        )
        self.client.force_login(staff)
        self.assertEqual(
            self.client.get(
                reverse("admin:recommendations_tracksuggestion_changelist")
            ).status_code,
            403,
        )
