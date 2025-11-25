# project/settings/airborne.py
"""Airborne Images deployment (Money + FlightPlan)."""

import os

# Ensure CURRENT_CLIENT is set before base imports _client.py
os.environ.setdefault("CLIENT", "airborne")

from .base import *  # noqa

CLIENT = "airborne"

# Production-ish overrides live here:
DEBUG = True

ALLOWED_HOSTS = [
    "airborne-images.net",
    "www.airborne-images.net",
    # add Heroku domain etc.
]


