from django.test import SimpleTestCase

from offline_evaluation.visualization.svg import grouped_bar_chart


class SvgTests(SimpleTestCase):
    def test_chart_escapes_user_visible_text(self):
        value = grouped_bar_chart(
            title="A & B",
            subtitle="<summary>",
            rows=[{"label": "x < y", "value": 0.5}],
            series=[("value", "#000000")],
            maximum=1.0,
        )

        self.assertIn("A &amp; B", value)
        self.assertIn("&lt;summary&gt;", value)
        self.assertIn("x &lt; y", value)
