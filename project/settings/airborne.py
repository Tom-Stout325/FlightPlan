# project/settings/airborne.py
"""Airborne Images deployment (Money + FlightPlan)."""

import os

os.environ.setdefault("CLIENT", "airborne")

from .base import *  # noqa

CLIENT = "airborne"

DEBUG = False  # or True while you're still debugging

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",")

print(">>> USING ALLOWED_HOSTS:", ALLOWED_HOSTS)
