# project/settings/demo.py
"""Demo deployment configuration.

This is typically a FlightPlan-only deployment with generic branding.
"""

import os

os.environ.setdefault("CLIENT", "demo")

from .flightplan import *  # noqa

CLIENT = "demo"
