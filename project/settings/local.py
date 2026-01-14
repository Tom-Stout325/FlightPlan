# project/settings/local.py
"""Local development settings (Money + FlightPlan)."""

import os

# Pick a default client for local dev
os.environ.setdefault("CLIENT", "airborne")

from .base import *  

CLIENT = os.getenv("CLIENT", "airborne")

DEBUG = True
ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"



ENABLED_REPORTS = [
    "profit_loss",
    "form_4797",
    "category_summary",
    "nhra_summary",
    "nhra_summary_report",
    "travel_expense_analysis",
    "receipts",
    "travel_summary",
    "travel_expenses",
    "schedule_c",
    "tax_profit_loss",
    "tax_category_summary",
    "drone_safety_profile_list",
]