# project/settings/skyguy.py
"""SkyGuy deployment (Money + FlightPlan)."""

import os

os.environ.setdefault("CLIENT", "skyguy")

from .base import *  

CLIENT = "skyguy"

DEBUG = True

ALLOWED_HOSTS = [
    ".herokuapp.com",

]


ENABLED_REPORTS = [
    "profit_loss",
    "form_4797",
    "category_summary",
    "travel_summary",
    "schedule_c",
    "tax_profit_loss",
    "tax_category_summary",
    "drone_safety_profile_list",
]