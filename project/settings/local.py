# project/settings/local.py
"""Local development settings (Money + FlightPlan)."""

import os

# Pick a default client for local dev
os.environ.setdefault("CLIENT", "airborne")

from .base import *  # noqa

CLIENT = os.getenv("CLIENT", "airborne")

DEBUG = True
ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
