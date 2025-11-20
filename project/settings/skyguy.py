# project/settings/skyguy.py
"""SkyGuy deployment configuration.

This is a Suite deployment (Money + FlightPlan) with the
CLIENT fixed to "skyguy".
"""

import os

os.environ.setdefault("CLIENT", "skyguy")

from .suite import *  # noqa

CLIENT = "skyguy"
