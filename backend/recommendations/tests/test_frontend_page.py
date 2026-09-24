from django.contrib.staticfiles import finders
from django.test import SimpleTestCase
from django.urls import reverse


class FrontendPageTests(SimpleTestCase):
    def test_home_serves_the_recommendation_page(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Find my next tracks")
        self.assertContains(response, "Advanced algorithm options")
        self.assertContains(response, "Can't find a song? Suggest it")
        self.assertContains(response, 'id="suggestion-form"')
        self.assertContains(response, 'name="album_name"')
        self.assertContains(response, 'name="reference_url"')
        self.assertNotContains(response, 'name="note"')
        self.assertNotContains(response, "/api/v1/docs/swagger/")
        self.assertContains(response, "Surprise me · random mix")
        self.assertNotContains(response, '<option value="random">')
        self.assertContains(response, "/static/frontend/js/discover/main.js")

    def test_frontend_assets_are_discoverable(self):
        for name in (
            "frontend/css/base.css",
            "frontend/css/discover.css",
            "frontend/js/api.js",
            "frontend/js/model.js",
            "frontend/js/discover/main.js",
            "frontend/js/discover/search.js",
            "frontend/js/discover/history.js",
            "frontend/js/discover/results.js",
            "frontend/js/discover/suggestions.js",
        ):
            self.assertIsNotNone(finders.find(name), name)
