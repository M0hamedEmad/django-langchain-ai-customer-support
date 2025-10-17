"""Booking nodes needing deps (LLM clients built with dummy keys, never called)."""

import pytest

from apps.ai import nodes as N
from apps.ai.services import get_deps
from apps.core.models import Booking, Customer, Service


@pytest.fixture
def ctx(db, company, tmp_path, settings):
    settings.CHROMA_DB_DIR = str(tmp_path / "chroma")
    deps = get_deps(company)
    customer = Customer.objects.create(company=company, phone="6000", name="C")
    service = Service.objects.create(company=company, name="تدريب شخصي")
    return company, deps, customer, service


def _state(company, customer, **kw):
    base = {
        "company_id": str(company.id),
        "customer_id": customer.id,
        "customer_name": "C",
        "customer_phone": "6000",
        "customer_address": "",
        "booking_date": "2024-05-06",
        "booking_id": "",
        "selected_service": "تدريب شخصي",
        "service_object": None,
    }
    base.update(kw)
    return base


def test_fuzzy_match_resolves_object(ctx):
    company, deps, customer, service = ctx
    out = N.handle_service_booking(
        _state(
            company,
            customer,
            original_message="عايز تدريب",
            selected_service="تدريب",
            missing_info=[],
        ),
        company=company,
        deps=deps,
    )
    assert out["service_object"] == service.id


def test_execute_double_submit_reuses(ctx):
    company, deps, customer, service = ctx
    st = _state(company, customer, original_message="x", service_object=service.id)
    N.execute_create_booking(dict(st), company=company, deps=deps)
    N.execute_create_booking(dict(st), company=company, deps=deps)
    assert Booking.objects.filter(customer=customer, service=service).count() == 1


def test_confirm_renders(ctx):
    company, deps, customer, service = ctx
    out = N.confirm_booking(
        _state(company, customer, service_object=service.id),
        company=company,
        deps=deps,
    )
    assert "المضي قدماً" in out["rag_context"]


def test_modification_without_bookings_survives(ctx):
    company, deps, customer, _ = ctx
    out = N.handle_booking_modification(
        {"original_message": "اريد تعديل", "customer_id": 424242},
        company=company,
        deps=deps,
    )
    assert "rag_context" in out
