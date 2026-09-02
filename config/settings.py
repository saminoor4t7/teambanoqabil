"""
Medical Panda 2.0 — Django settings.

Architecture note (see docs/ARCHITECTURE.md):
Three role-facing apps — `customer`, `medical_store` (pharmacy), and `rider` —
are interconnected through two shared apps:
  - `accounts`: a single custom User model with a `role` field, so every
    profile (CustomerProfile, PharmacyProfile, RiderProfile) is a 1:1
    extension of the same auth identity.
  - `orders`: the hub model (Order/OrderItem/Delivery) that each of the
    three apps reads and writes to via ForeignKeys, instead of the three
    apps depending on each other directly. This keeps them loosely coupled
    while still fully interconnected through one source of truth.
"""

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "b3(8^+9_=k(dm#5xunov7g6azn%a!qd@kp=yj6hl*gl-5)y!9g"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    # Medical Panda apps
    "apps.accounts",
    "apps.catalog",
    "apps.customer",
    "apps.medical_store",
    "apps.rider",
    "apps.orders",
    # AI Agent (local NLP + semantic search + Ollama)
    "apps.ai_agent",
    "apps.ai_assistant",

]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
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
        "DIRS": [BASE_DIR / "frontend"],
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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "frontend" / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"  # prescription images/PDFs land here (or AWS S3 in prod)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
}

CORS_ALLOW_ALL_ORIGINS = True

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
DEFAULT_FROM_EMAIL = "sussbhoo@gmail.com"
DELIVERY_FEE = 20
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_HOST_USER = "sussbhoo@gmail.com"
EMAIL_HOST_PASSWORD = "eozjmshobprvhzwd"
EMAIL_USE_TLS = True

# Async job queue (OCR, forecasting, notifications) per architecture doc.
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = CELERY_BROKER_URL

# Base URL of the separate AI microservice (Vision/OCR + LLM/RAG), called
# by apps.customer.services.ai_client — never called directly from models.
AI_SERVICE_BASE_URL = "http://localhost:9000"


# ── AI Agent settings (local models — no external API keys needed) ────
OLLAMA_BASE_URL = "http://localhost:11434"  # locally running Ollama server
OLLAMA_MODEL = "llama3.2:3b"                # small, fast model for chat
OLLAMA_TIMEOUT = 30                          # seconds before fallback

# ── Google Gemini AI Assistant ──
# Get a free API key from https://aistudio.google.com/apikey
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()  # set via environment variable
GEMINI_MODEL = "gemini-3.6-flash"

