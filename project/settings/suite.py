# project/settings/suite.py
from .base import *  # noqa
from ._client import (
    CURRENT_CLIENT,
    FEATURES,
    BRAND,
    CLIENT_TEMPLATE_DIR,
    CLIENT_STATIC_DIR,
)

TEMPLATES[0]["DIRS"] = [str(CLIENT_TEMPLATE_DIR)] + list(TEMPLATES[0].get("DIRS", []))
TEMPLATES[0]["OPTIONS"]["context_processors"] += [
    "project.context_processors.brand_context",
]

STATICFILES_DIRS = [
    *(STATICFILES_DIRS if "STATICFILES_DIRS" in globals() else []),
    str(CLIENT_STATIC_DIR),
]

CLIENT          = CURRENT_CLIENT
CLIENT_FEATURES = FEATURES
BRAND_NAME      = BRAND["NAME"]
BRAND_TAGLINE   = BRAND.get("TAGLINE", "")
CLIENT_SLUG     = BRAND["SLUG"]

INSTALLED_APPS += [
    "accounts",
    "clients",
    "documents",
    "equipment",
    "flightlogs",
    "operations",
    "pilot",
    "help",
    "money",
]
