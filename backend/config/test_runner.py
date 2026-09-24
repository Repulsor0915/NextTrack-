"""Make the project-root test command discover both application suites."""

from django.test.runner import DiscoverRunner


class NextTrackTestRunner(DiscoverRunner):
    def build_suite(self, test_labels=None, **kwargs):
        labels = test_labels or ("recommendations", "offline_evaluation")
        return super().build_suite(labels, **kwargs)
