# project/settings/local.py
"""Local development settings.

Intended for running the Suite variant locally with relaxed security.
You can point DJANGO_SETTINGS_MODULE here while developing.
"""

from .suite import *  # noqa

DEBUG = True

# Allow everything in local dev
ALLOWED_HOSTS = ["*"]

# Local email: console backend
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
