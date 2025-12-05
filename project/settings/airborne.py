# project/settings/airborne.py
"""Airborne Images deployment (Money + FlightPlan)."""

import os

os.environ.setdefault("CLIENT", "airborne")

from .base import *  # noqa

CLIENT = "airborne"

DEBUG = True  # or True while you're still debugging

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",")

print(">>> USING ALLOWED_HOSTS:", ALLOWED_HOSTS)


ENABLED_REPORTS = [
    "financial_statement",
    "form_4797",
    "category_summary",
    "nhra_summary",
    "nhra_summary_report",
    "travel_expense_analysis",
    "schedule_c",
    "receipts",
    "invoice_summary",
    "travel_expenses",
]