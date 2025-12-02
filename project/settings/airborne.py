# project/settings/airborne.py
"""Airborne Images deployment (Money + FlightPlan)."""

import os

# Ensure CURRENT_CLIENT is set before base imports _client.py
os.environ.setdefault("CLIENT", "airborne")

from .base import *  # noqa

CLIENT = "airborne"

# Production-ish overrides live here:
DEBUG = False

ALLOWED_HOSTS = [
    "12bytes.airborne-images.net",
    "airborne-images.net",
    "www.airborne-images.net",
    "serene-parrot-plxxk4ab6u3sadwd5h494x3u.herokudns.com"
]
