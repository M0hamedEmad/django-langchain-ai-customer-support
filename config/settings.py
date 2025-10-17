from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load <repo>/.env. Legacy config/.env is deprecated and no longer loaded.
load_dotenv(BASE_DIR / ".env")


def _get_env(
    name: str, default: str | None = None, required: bool = False
) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise ImproperlyConfigured(f"{name} is required but not set in environment")
    return value


SECRET_KEY = (
    _get_env("DJANGO_SECRET_KEY", required=False)
    or "change-me-generate-a-strong-random-value-AADJTds-skl"
)
DEBUG = True
if DEBUG and SECRET_KEY in {
    "change-me",
    "change-me-generate-a-strong-random-value",
    "dev-secret-key-change-me",
}:
    raise ImproperlyConfigured(
        "Insecure DJANGO_SECRET_KEY with DJANGO_DEBUG=1. Set a strong key."
    )

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
    "apps.api.middleware.RequestIDMiddleware",
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

DATABASES: dict[str, dict[str, Any]] = {
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

# Structured logging (structlog -> stdlib bridge, so logging.getLogger keeps working).
# LOG_FORMAT=console (local) or json (prod). Request ids come from
# apps.api.middleware.RequestIDMiddleware via contextvars.
LOG_FORMAT = os.environ.get("LOG_FORMAT", "console" if DEBUG else "json")

import structlog  # noqa: E402  (configured right here, before first use)

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structlog": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processors": [
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                (
                    structlog.dev.ConsoleRenderer()
                    if LOG_FORMAT == "console"
                    else structlog.processors.JSONRenderer()
                ),
            ],
            "foreign_pre_chain": [
                structlog.contextvars.merge_contextvars,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.stdlib.add_log_level,
            ],
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structlog",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}

# Sentry (optional; sentry-sdk is intentionally not a hard dependency).
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.0)
    except ImportError:
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "SENTRY_DSN is set but sentry-sdk is not installed; skipping."
        )
