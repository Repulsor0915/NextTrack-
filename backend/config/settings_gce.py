"""Production settings for one Google Compute Engine VM with SQLite.

This profile is intended for a small FYP deployment, not horizontal scaling.
The SQLite file must live on the VM's persistent disk and must be backed up.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403,F401


def _required_env(name):
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(f"{name} must be set for GCE deployment.")
    return value


DEBUG = False
SECRET_KEY = _required_env("NEXTTRACK_SECRET_KEY")
INSTALLED_APPS.remove("offline_evaluation.apps.OfflineEvaluationConfig")
ALLOWED_HOSTS = [
    host.strip()
    for host in _required_env("NEXTTRACK_ALLOWED_HOSTS").split(",")
    if host.strip()
]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("NEXTTRACK_ALLOWED_HOSTS must contain a host.")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("NEXTTRACK_DB_PATH", BASE_DIR / "db.sqlite3"),
    }
}

# A single VM does not need Redis. This cache is per-process and is only a
# basic development-scale throttle/cache; use shared Redis for multi-instance
# deployment.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "nexttrack-gce-cache",
    }
}

MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = os.environ.get("NEXTTRACK_HTTPS", "0") == "1"
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
if os.environ.get("NEXTTRACK_HTTPS", "0") == "1":
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("NEXTTRACK_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
