from django.contrib.staticfiles import finders
from django.test import SimpleTestCase
from django.urls import reverse


class AnalyticsPageTests(SimpleTestCase):
    def test_public_analytics_page_uses_the_frozen_snapshot(self):
        response = self.client.get(reverse("analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "VERIFIED V2 OFFLINE EXPERIMENTS")
        self.assertContains(response, "What the results actually say")
        self.assertContains(response, "Which settings were retained?")
        self.assertContains(response, "/static/frontend/js/analytics/analytics.js")
        self.assertNotContains(response, "recommendation-runs.json")

    def test_main_page_links_to_analytics(self):
        self.assertContains(self.client.get(reverse("home")), 'href="/analytics/"')

    def test_analytics_assets_are_discoverable(self):
        for name in (
            "frontend/css/base.css",
            "frontend/css/analytics.css",
            "frontend/js/analytics/analytics.js",
            "frontend/analytics/snapshot.json",
            "frontend/analytics/figures/01-catalogue-clamping.svg",
            "frontend/analytics/figures/05-latency.svg",
        ):
            with self.subTest(name=name):
                self.assertIsNotNone(finders.find(name))
