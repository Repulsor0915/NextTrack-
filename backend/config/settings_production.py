"""PostgreSQL settings for a separately provisioned public deployment."""

import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403,F401


def _required_env(name):
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(f"{name} must be set for production.")
    return value


DEBUG = False
SECRET_KEY = _required_env("NEXTTRACK_SECRET_KEY")
ALLOWED_HOSTS = [
    host.strip() for host in _required_env("NEXTTRACK_ALLOWED_HOSTS").split(",")
    if host.strip()
]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("NEXTTRACK_ALLOWED_HOSTS must contain a host.")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _required_env("NEXTTRACK_DB_NAME"),
        "USER": _required_env("NEXTTRACK_DB_USER"),
        "PASSWORD": _required_env("NEXTTRACK_DB_PASSWORD"),
        "HOST": _required_env("NEXTTRACK_DB_HOST"),
        "PORT": os.environ.get("NEXTTRACK_DB_PORT", "5432"),
        "OPTIONS": {
            "sslmode": os.environ.get("NEXTTRACK_DB_SSLMODE", "require"),
        },
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": _required_env("NEXTTRACK_REDIS_URL"),
    }
}

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = int(os.environ.get("NEXTTRACK_HSTS_SECONDS", "0"))

if os.environ.get("NEXTTRACK_TRUSTED_PROXY") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
