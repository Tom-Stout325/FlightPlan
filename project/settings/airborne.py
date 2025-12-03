# project/settings/airborne.py
"""Airborne Images deployment (Money + FlightPlan)."""

import os

# Ensure CURRENT_CLIENT is set before base imports _client.py
os.environ.setdefault("CLIENT", "airborne")

from .base import *  # noqa

CLIENT = "airborne"

# Production-ish overrides live here:
DEBUG = True

if DEBUG:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]