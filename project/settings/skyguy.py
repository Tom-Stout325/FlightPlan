# project/settings/skyguy.py
"""SkyGuy deployment (Money + FlightPlan)."""

import os

os.environ.setdefault("CLIENT", "skyguy")

from .base import *  # noqa

CLIENT = "skyguy"

DEBUG = True

ALLOWED_HOSTS = [
    "skyguy.example.com",

]

