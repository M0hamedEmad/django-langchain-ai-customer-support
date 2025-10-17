"""Booking tools: plain-function flows on sqlite (no LLM, no vectors)."""

import pytest

from apps.ai.tools import booking as tools
from apps.core.models import Booking, Customer, Service


@pytest.fixture
def setup(db, company):
    customer = Customer.objects.create(company=company, phone="5000")
    service = Service.objects.create(company=company, name="Massage")
    return company, customer, service


def _create(company, customer, service, **kw):
    return Booking.objects.create(
        company=company,
        customer=customer,
        service=service,
        service_text="Massage",
        status=Booking.Status.CREATED,
        **kw,
    )


def test_get_details(setup):
    company, customer, service = setup
    b = _create(company, customer, service)
    result = tools.get_booking_details(
        company=company, customer=customer, booking_id=b.pk
    )
    assert result["success"] and result["booking"]["id"] == b.pk


def test_get_details_wrong_customer(company, setup):
    _, customer, _ = setup
    other = Customer.objects.create(company=company, phone="5001")
    b = Booking.objects.create(company=company, customer=other, status="created")
    result = tools.get_booking_details(
        company=company, customer=customer, booking_id=b.pk
    )
    assert not result["success"]


def test_cancel_twice(setup):
    company, customer, service = setup
    b = _create(company, customer, service)
    assert tools.cancel_booking(company=company, customer=customer, booking_id=b.pk)[
        "success"
    ]
    second = tools.cancel_booking(company=company, customer=customer, booking_id=b.pk)
    assert not second["success"]


def test_cancel_all(setup):
    company, customer, service = setup
    _create(company, customer, service)
    _create(company, customer, service)
    result = tools.cancel_all_bookings(company=company, customer=customer)
    assert result["success"] and result["cancelled_count"] == 2
    again = tools.cancel_all_bookings(company=company, customer=customer)
    assert not again["success"] and again["cancelled_count"] == 0


def test_edit_valid_and_invalid(setup):
    company, customer, service = setup
    b = _create(company, customer, service)
    ok = tools.edit_booking(
        company=company, customer=customer, booking_id=b.pk, date="2024-06-01"
    )
    assert ok["success"] and ok["changes"] == {"date": "2024-06-01"}
    bad = tools.edit_booking(
        company=company, customer=customer, booking_id=b.pk, date="not-a-date"
    )
    assert not bad["success"]
