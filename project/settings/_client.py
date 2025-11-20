# project/settings/_client.py
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

CURRENT_CLIENT = os.getenv("CLIENT", "airborne").lower()

FEATURE_MATRIX = {
    "airborne": {"NHRA": True},
    "skyguy":   {"NHRA": False},
    "demo":     {"NHRA": False},
}
FEATURES = FEATURE_MATRIX.get(CURRENT_CLIENT, {})

BRANDS = {
    "airborne": {
        "NAME": "Airborne Images",
        "SLUG": "airborne-images",
        "TAGLINE": "Views From Above",
    },
    "skyguy": {
        "NAME": "SkyGuy",
        "SLUG": "skyguy",
        "TAGLINE": "Views with Altitude",
    },
    "demo": {
        "NAME": "FlightPlan Demo",
        "SLUG": "demo",
        "TAGLINE": "Demo environment – not for production use",
    },
}

BRAND = BRANDS.get(
    CURRENT_CLIENT,
    {
        "NAME": CURRENT_CLIENT.title(),
        "SLUG": CURRENT_CLIENT,
        "TAGLINE": "",
    },
)

CLIENT_TEMPLATE_DIR = BASE_DIR / "clients" / CURRENT_CLIENT / "templates"
CLIENT_STATIC_DIR   = BASE_DIR / "clients" / CURRENT_CLIENT / "static"
