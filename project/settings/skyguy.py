# project/settings/skyguy.py
"""SkyGuy deployment (Money + FlightPlan)."""

import os

os.environ.setdefault("CLIENT", "skyguy")

from .base import *  # noqa

CLIENT = "skyguy"

DEBUG = True

ALLOWED_HOSTS = [
    ".herokuapp.com",

]


ENABLED_REPORTS = [
    "financial_statement",
    "form_4797",
    "category_summary",
    "schedule_c",
    "invoice_summary",
]