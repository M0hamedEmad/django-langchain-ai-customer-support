from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict
from dotenv import load_dotenv

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# Load <repo>/.env. Legacy config/.env is deprecated and no longer loaded.
load_dotenv(BASE_DIR / ".env")


def _get_env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise ImproperlyConfigured(f"{name} is required but not set in environment")
    return value


SECRET_KEY = _get_env("DJANGO_SECRET_KEY", required=False) or "change-me-generate-a-strong-random-value-AADJTds-skl"
DEBUG = True
if DEBUG and SECRET_KEY in {"change-me", "change-me-generate-a-strong-random-value", "dev-secret-key-change-me"}:
    raise ImproperlyConfigured("Insecure DJANGO_SECRET_KEY with DJANGO_DEBUG=1. Set a strong key.")

_allowed_hosts_raw = _get_env("DJANGO_ALLOWED_HfOSTS", "*" if DEBUG else "")
ALLOWED_HOSTS = [h.strip() for h in (_allowed_hosts_raw or "").split(",") if h.strip()]
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS is required when DJANGO_DEBUG=0")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "rest_framework",
    

    # Local apps
    "apps.core",
    "apps.api",
    "apps.ai",
    "apps.ingestion",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES: Dict[str, Dict[str, Any]] = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            "timeout": 20,
        },
    }
}

# SQLite + long-lived connections = write-lock footgun. Keep 0 for dev/SQLite.
CONN_MAX_AGE = 0

LANGUAGE_CODE = "en"
TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
}

# Channels (using in-memory layer for dev)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# Chroma
CHROMA_DB_DIR = os.environ.get("CHROMA_DB_DIR", str(BASE_DIR / ".chroma"))

# LLM provider selection (openai | gemini | deepseek). No secrets here — keys come from env.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-2.5-flash")

# Basic structlog setup (optional; can be elaborated later)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
