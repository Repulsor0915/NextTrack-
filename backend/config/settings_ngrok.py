"""Hosted settings for the Windows Waitress and ngrok deployment."""

import os
import secrets

from .settings import *  # noqa: F401,F403


def _local_secret_key():
    """Return the environment key or create a private key for this checkout."""

    configured_key = os.environ.get("NEXTTRACK_SECRET_KEY", "").strip()
    if configured_key:
        return configured_key

    key_path = BASE_DIR / ".nexttrack-secret-key"  # noqa: F405
    if key_path.exists():
        saved_key = key_path.read_text(encoding="utf-8").strip()
        if saved_key:
            return saved_key

    generated_key = secrets.token_urlsafe(64)
    key_path.write_text(generated_key, encoding="utf-8")
    return generated_key


DEBUG = False
SECRET_KEY = _local_secret_key()

PUBLIC_HOST = os.environ.get(
    "NEXTTRACK_PUBLIC_HOST",
    "breeding-gusty-grower.ngrok-free.dev",
).strip()
ALLOWED_HOSTS = ["127.0.0.1", "localhost", PUBLIC_HOST]
CSRF_TRUSTED_ORIGINS = [f"https://{PUBLIC_HOST}"]

INSTALLED_APPS.remove("offline_evaluation.apps.OfflineEvaluationConfig")  # noqa: F405

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.schema-final.sqlite3",  # noqa: F405
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "nexttrack-ngrok-cache",
    }
}

MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
