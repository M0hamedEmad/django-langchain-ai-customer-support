"""Shared pytest fixtures. Env defaults are test-only (fail-fast settings)."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-key-not-a-secret")
os.environ.setdefault("DJANGO_DEBUG", "1")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "testserver,localhost")
os.environ.setdefault("OPENAI_API_KEY", "dummy-test-key")
os.environ.setdefault("GOOGLE_API_KEY", "dummy-test-key")

import pytest

from apps.core.models import Company


@pytest.fixture
def company(db):
    return Company.objects.create(business_name="Test Co", api_key="test-key")


@pytest.fixture
def api_key(company):
    return {"HTTP_X_COMPANY_KEY": company.api_key}
