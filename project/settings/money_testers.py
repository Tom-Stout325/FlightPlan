# project/settings/money_testers.py
"""Money-only deployment for external testers (Heroku)."""

from __future__ import annotations

import os

from .base import *  # noqa


# ---------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------
os.environ.setdefault("CLIENT", "money-testers")
CLIENT = "money-testers"
ENVIRONMENT = "money-testers"


# ---------------------------------------------------------------------
# Security / runtime
# ---------------------------------------------------------------------
DEBUG = False

SECRET_KEY = os.environ.get("SECRET_KEY", SECRET_KEY)

# Heroku app hostnames (add custom domain later if you want)
ALLOWED_HOSTS = [
    "money-12bytes-8c73d89f4a22.herokuapp.com",
    "money-12bytes.herokuapp.com",
]

CSRF_TRUSTED_ORIGINS = [
    "https://money-12bytes-8c73d89f4a22.herokuapp.com",
    "https://money-12bytes.herokuapp.com",
]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Keep HSTS off until you’re confident you won’t serve over http anywhere
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True


# ---------------------------------------------------------------------
# Apps: keep shared + money stack, drop non-money business apps
# ---------------------------------------------------------------------
INSTALLED_APPS = [
    # Storage (you already rely on it in base; safe to keep even if not used yet)
    "storages",

    # Django core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sites",

    # Shared project utilities used across templates/context processors
    "project.common",

    # UI / forms dependencies your Money templates likely expect
    "crispy_forms",
    "crispy_bootstrap5",
    "fontawesomefree",
    "bootstrap5",
    "dal",
    "dal_select2",
    "formtools",

    # Auth/accounts (your project uses this rather than the older "app" name)
    "accounts",

    # Business app: Money only
    "money",
]

# Middleware: keep same as base (works well on Heroku)
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Route only money + accounts URLs
ROOT_URLCONF = "project.urls_money_testers"


# ---------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------
# Leave DATABASES untouched:
# Heroku Postgres injects DATABASE_URL, and base.py should already parse it.
# This environment will automatically use the Heroku Postgres add-on.


# ---------------------------------------------------------------------
# Optional: reduce noise / keep logs sane
# ---------------------------------------------------------------------
LOGGING = globals().get(
    "LOGGING",
    {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {"console": {"class": "logging.StreamHandler"}},
        "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    },
)





