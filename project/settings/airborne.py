# project/settings/airborne.py
"""Airborne Images deployment configuration.

This is a Suite deployment (Money + FlightPlan) with the
CLIENT fixed to "airborne".
"""

import os

# Ensure the CLIENT env var is set early so _client.py sees it.
os.environ.setdefault("CLIENT", "airborne")

from .suite import *  # noqa

# Optional: make it very explicit in settings which client this is.
CLIENT = "airborne"
