from pathlib import Path
import environ
import os
from django.contrib.messages import constants as messages



# Set base directory first
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Initialize environment
env = environ.Env()

environ.Env.read_env()
# ---- Brand configuration ----
BRAND_NAME   = env("BRAND_NAME", default="Airborne Images")
BRAND_DOMAIN = env("BRAND_DOMAIN", default="airborne-images.com")
BRAND_TAGLINE= env("BRAND_TAGLINE", default="")
BRAND_EMAIL  = env("BRAND_EMAIL", default=env("DEFAULT_FROM_EMAIL", default="no-reply@example.com"))
BRAND_BCC    = env.list("BRAND_BCC", default=[])

DEFAULT_FROM_EMAIL   = env("DEFAULT_FROM_EMAIL", default=BRAND_EMAIL)
SERVER_EMAIL         = env("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)
EMAIL_SUBJECT_PREFIX = env("EMAIL_SUBJECT_PREFIX", default=f"[{BRAND_NAME}] ")


ADMIN_BRANDING_ENABLED = env.bool("ADMIN_BRANDING_ENABLED", default=True)

# Load environment variables from the correct .env file
ENV_FILE = os.environ.get('ENV_FILE', '.env')
environ.Env.read_env(os.path.join(BASE_DIR, ENV_FILE))

CLIENT_SLUG = env('CLIENT_SLUG', default='default')
BRAND_NAME  = env('BRAND_NAME',  default='12bytes')

SECRET_KEY = env('DJANGO_SECRET_KEY')
DEBUG = env.bool('DEBUG', default=True)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])

INSTALLED_APPS = [
   'storages',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.sites',

    'crispy_bootstrap5',
    'crispy_forms',
    'fontawesomefree',
    'bootstrap5',
    
    'accounts',
    'clients',
    'documents',
    'equipment',
    'flightlogs',
    'operations',
    'pilot',
    'help',
    'money',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'project.urls'
WSGI_APPLICATION = 'project.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages', 
                'django.template.context_processors.static',
                'project.context_processors.brand_context',
                'django.template.context_processors.media',
                'django.template.context_processors.i18n',
                'django.template.context_processors.tz',
                "money.context_processors.client_profile",

            ],
        },
    },
]



DATABASES = {
    'default': env.db(default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')
}

if DEBUG:
    db = DATABASES['default']
    if (db.get('HOST') or '').strip() not in ('', '127.0.0.1', 'localhost'):
        raise RuntimeError("Refusing remote DB while DEBUG=False")

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

STATICFILES_STORAGE = (
    'whitenoise.storage.CompressedManifestStaticFilesStorage'
    if not DEBUG else 'django.contrib.staticfiles.storage.StaticFilesStorage'
)

from ._client import (
    CURRENT_CLIENT,
    FEATURES,
    BRAND,
    CLIENT_TEMPLATE_DIR,
    CLIENT_STATIC_DIR,
)

# 1) Per-client template directory first in search path
TEMPLATES[0]["DIRS"] = [str(CLIENT_TEMPLATE_DIR)] + list(
    TEMPLATES[0].get("DIRS", [])
)

# 2) Add per-client static folder
STATICFILES_DIRS = [
    *(STATICFILES_DIRS if "STATICFILES_DIRS" in globals() else []),
    str(CLIENT_STATIC_DIR),
]

# 3) Expose branding + features to settings
CLIENT          = CURRENT_CLIENT
CLIENT_FEATURES = FEATURES
BRAND_NAME      = BRAND["NAME"]
BRAND_TAGLINE   = BRAND.get("TAGLINE", "")
CLIENT_SLUG     = BRAND["SLUG"]


USE_S3 = env.bool("USE_S3", default=False)
if USE_S3:
    DEFAULT_FILE_STORAGE      = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_STORAGE_BUCKET_NAME   = env("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME        = env("AWS_S3_REGION_NAME", default="us-east-2")
    AWS_ACCESS_KEY_ID         = env("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY     = env("AWS_SECRET_ACCESS_KEY")
    AWS_S3_ADDRESSING_STYLE   = "virtual"
    AWS_S3_SIGNATURE_VERSION  = "s3v4"
    AWS_DEFAULT_ACL           = None
    AWS_QUERYSTRING_AUTH      = True
    AWS_S3_OBJECT_PARAMETERS  = {
        "CacheControl": "max-age=86400, s-maxage=86400, public"
    }
    AWS_S3_FILE_OVERWRITE     = False




redis_url = env('REDISCLOUD_URL', default=env('REDIS_URL', default=None))
if redis_url:
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': redis_url,
            'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'}
        }
    }
else:
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'


MESSAGE_TAGS = {
    messages.ERROR: 'danger',
}

EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='smtp.office365.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default=None)
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default=None)
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='webmaster@localhost')



if not DEBUG:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_SSL_REDIRECT = True




LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'ERROR',
    },
}

SITE_ID = 1

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:home"
LOGOUT_REDIRECT_URL = "accounts:login"

FORMAT_MODULE_PATH = 'app.formats'

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

SESSION_COOKIE_AGE = 60 * 60 * 24 * 7
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"


# Custom Terminology (can be overridden per client via env)
# TERM_EVENT_SINGULAR = env('TERM_EVENT_SINGULAR', default=None)
# TERM_EVENT_PLURAL   = env('TERM_EVENT_PLURAL',   default=None)
# CLIENT_SLUG         = env('CLIENT_SLUG', default='default') 
# BRAND_NAME          = env('BRAND_NAME',  default='12bytes')
