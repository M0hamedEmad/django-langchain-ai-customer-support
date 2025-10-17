"""Shared DB/LLM lookups used by nodes and booking tools.

All functions take explicit arguments (no graph state internals, no chatbot
instance) so they stay callable from views, tools, and commands.
"""

from __future__ import annotations

import json
import logging

from apps.core.models import Booking, Customer, Service

logger = logging.getLogger(__name__)


def resolve_customer(state) -> Customer | None:
    """Fetch the customer object for a conversation state (id, then phone)."""
    customer_id = state.get("customer_id", None)

    if customer_id:
        try:
            return Customer.objects.get(id=customer_id)
        except Exception as e:
            logger.error("Error fetching customer details: %s", e)
            return None

    customer_phone = state.get("customer_phone", None)

    if customer_phone:
        try:
            return Customer.objects.get(phone=customer_phone)
        except Exception as e:
            logger.error("Error fetching customer details: %s", e)
            return None

    return None


def fetch_user_bookings(company, customer) -> list:
    """Fetch all bookings for a user as plain dicts (empty list on failure)."""
    try:
        bookings = Booking.objects.filter(customer=customer, company=company).order_by(
            "-created_at"
        )

        if not bookings.exists():
            return []

        booking_list = []
        for booking in bookings:
            customer_id = None if booking.customer is None else booking.customer.id
            service = None if not booking.service else booking.service.id

            booking_list.append(
                {
                    "id": booking.id,
                    "customer": customer_id,
                    "service": service,
                    "service_text": booking.service_text,
                    "status": booking.status,
                    "date": booking.date,
                    "notes": booking.notes,
                    "source": booking.source,
                    "created_at": booking.created_at,
                    "is_cancellable": booking.status not in ["completed", "cancelled"],
                }
            )

        return booking_list

    except Exception as e:
        logger.error("Error fetching user bookings: %s", e)
        return []


def match_service(*, company, deps, state) -> Service | None:
    """Resolve the requested service to a catalog object.

    Fuzzy catalog match first (>=70), LLM matcher as fallback. Returns the
    ``Service`` or ``None``. Replaces the old split brain where a fuzzy hit
    left the ``service`` variable unbound and crashed the node.
    """
    selected_service = state.get("selected_service", None)
    last_message = state.get("original_message", "")

    names = list(deps.services_qs.values_list("name", flat=True))
    if names:
        try:
            from rapidfuzz import fuzz, process  # type: ignore

            best = process.extractOne(
                selected_service or last_message, names, scorer=fuzz.partial_ratio
            )
            if best and best[1] >= 70:
                matched = Service.objects.filter(company=company, name=best[0]).first()
                if matched is not None:
                    if not selected_service:
                        state["selected_service"] = matched.name
                    return matched
        except Exception as e:
            logger.error("Fuzzy service match failed: %s", e)

    if not selected_service:
        return None

    prompt = deps.matching_prompt.format_messages(
        query=selected_service, formatted_services=deps.services_info
    )

    response = deps.llm.invoke(prompt)
    response_text = response.content.strip()

    try:
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1
        if json_start != -1 and json_end > json_start:
            json_text = response_text[json_start:json_end]
            service_data = json.loads(json_text)

            service = service_data.get("service_id", "")
            confidence_score = service_data.get("confidence_score", 0)

            if service and confidence_score > 0.5:
                return Service.objects.filter(id=service, company=company).first()

            return None
    except Exception:
        import traceback

        logger.error(
            "Error parsing JSON response in service booking: %s",
            traceback.format_exc(),
        )
        return None
    return None
