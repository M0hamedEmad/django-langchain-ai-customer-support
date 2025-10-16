"""Booking operations as plain functions (no graph state, no chatbot instance).

Previously mis-declared as ``@tool`` methods taking ``(self, state, ...)``
that LangChain could never bind (``bind_tools`` is never called) and that
nothing ever invoked. The logic is preserved verbatim; only the calling
convention changed to explicit ``company``/``customer`` arguments so nodes,
views, and commands can use them. ``get_booking_details`` additionally
returns its payload instead of writing into a ``state["state"]`` key that
never existed.
"""

from __future__ import annotations

from typing import Optional

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from apps.ai.services.dates import parse_booking_date
from apps.core.models import Booking


def get_booking_details(*, company, customer, booking_id: int) -> dict:
    """Booking details for one user-owned booking."""
    try:
        booking = Booking.objects.get(
            id=booking_id, customer=customer, company=company
        )

        return {
            "success": True,
            "booking": {
                "id": booking.id,
                "customer": booking.customer,
                "service": booking.service,
                "service_text": booking.service_text,
                "status": booking.status,
                "date": booking.date,
                "notes": booking.notes,
                "source": booking.source,
                "created_at": booking.created_at,
                "is_editable": booking.status
                in ["created", "confirmed", "cancelled"],
                "is_cancellable": booking.status not in ["completed", "cancelled"],
            },
        }
    except ObjectDoesNotExist:
        return {
            "success": False,
            "message": f"Booking #{booking_id} not found or doesn't belong to you.",
            "booking": None,
        }


def cancel_booking(
    *, company, customer, booking_id: int, reason: Optional[str] = None
) -> dict:
    """Cancel one non-completed booking."""
    try:
        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(
                id=booking_id, customer=customer
            )

            if booking.status in ["completed", "cancelled"]:
                return {
                    "success": False,
                    "message": f"Cannot cancel booking #{booking_id}. Status: {booking.status}",
                }

            # Store previous status for rollback if needed
            previous_status = booking.status

            booking.status = "cancelled"
            booking.save()

            return {
                "success": True,
                "message": f"Booking #{booking_id} has been successfully cancelled.",
                "previous_status": previous_status,
                "booking_id": booking_id,
            }
    except ObjectDoesNotExist:
        return {
            "success": False,
            "message": f"Booking #{booking_id} not found or doesn't belong to you.",
        }
    except Exception as e:
        return {"success": False, "message": f"Error cancelling booking: {str(e)}"}


def cancel_all_bookings(*, company, customer) -> dict:
    """Cancel all active bookings for one user."""
    try:
        with transaction.atomic():
            active_bookings = (
                Booking.objects.select_for_update()
                .filter(
                    customer=customer,
                    company=company,
                )
                .exclude(status__in=["completed", "cancelled"])
            )

            if not active_bookings.exists():
                return {
                    "success": False,
                    "message": "You don't have any active bookings to cancel.",
                    "cancelled_count": 0,
                }

            count = active_bookings.count()
            booking_ids = list(active_bookings.values_list("id", flat=True))

            active_bookings.update(
                status="cancelled",
            )

            return {
                "success": True,
                "message": f"Successfully cancelled {count} active booking(s).",
                "cancelled_count": count,
                "booking_ids": booking_ids,
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error cancelling bookings: {str(e)}",
            "cancelled_count": 0,
        }


def edit_booking(
    *,
    company,
    customer,
    booking_id: int,
    date: Optional[str] = None,
    notes: Optional[str] = None,
    service: Optional[str] = None,
) -> dict:
    """Edit one booking after confirmation; only editable fields change."""
    try:
        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(
                id=booking_id, customer=customer
            )

            if booking.status not in [Booking.Status.CREATED, Booking.Status.CONFIRMED]:
                return {
                    "success": False,
                    "message": f"Cannot edit booking #{booking_id}. Current status: {booking.status}",
                }

            changes = {}

            # Update fields if provided
            if date:
                parsed = parse_booking_date(date)
                if parsed is None:
                    return {
                        "success": False,
                        "message": "Invalid date format. Use YYYY-MM-DD.",
                    }
                booking.date = parsed
                changes["date"] = date

            if notes is not None:
                booking.notes = notes
                changes["notes"] = notes

            if service is not None:
                booking.service = service
                changes["service"] = service

            if changes:
                booking.save()

                return {
                    "success": True,
                    "message": f"Booking #{booking_id} has been successfully updated.",
                    "changes": changes,
                    "booking_id": booking_id,
                }
            else:
                return {"success": False, "message": "No changes were provided."}

    except ObjectDoesNotExist:
        return {
            "success": False,
            "message": f"Booking #{booking_id} not found or doesn't belong to you.",
        }
    except Exception as e:
        return {"success": False, "message": f"Error updating booking: {str(e)}"}
