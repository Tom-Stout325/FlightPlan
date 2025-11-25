# project/settings/demo.py
"""Demo deployment (Money + FlightPlan) with generic branding."""

import os

os.environ.setdefault("CLIENT", "demo")

from .base import *  # noqa

CLIENT = "demo"

DEBUG = True
ALLOWED_HOSTS = ["*"]
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
