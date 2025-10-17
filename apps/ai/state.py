from __future__ import annotations

from enum import Enum
from typing import Any, NotRequired, TypedDict


class IntentType(Enum):
    """Intent type enumeration."""

    GENERAL_INQUIRY = "استفسار_عام"
    SERVICE_BOOKING = "حجز_خدمة"
    BOOKING_MODIFICATION = "تعديل_حجز"
    COMPLAINT = "شكوى"
    MEMBERSHIP_INQUIRY = "استفسار_عضوية"
    UNCLEAR = "غير_واضح"


class IntentSubType(Enum):
    """Intent subtype enumeration."""

    # General inquiry
    GENERAL_INFO_REQUEST = "طلب_معلومات_عامة"
    SERVICE_INFO_REQUEST = "طلب_معلومات_خدمة"

    # Service booking
    BOOKING_REQUEST = "طلب_حجز"
    BOOKING_INFO_REQUEST = "طلب_معلومات_حجز"
    BOOKING_CONFIRMATION = "تأكيد_طلب_الحجز"

    # Booking modification
    BOOKING_CANCEL = "إلغاء_حجز"
    BOOKING_RESCHEDULE = "تعديل_معلومات_الحجز"

    # Complaint
    COMPLAINT_INQUIRY = "استفسار_شكوى"
    COMPLAINT_SUBMISSION = "تقديم_شكوى"

    # Membership inquiry
    MEMBERSHIP_INFO = "معلومات_عضوية"
    MEMBERSHIP_RENEWAL = "تجديد_عضوية"

    # Unclear
    UNCLEAR = "غير_واضح"


class ConversationState(TypedDict):
    """Conversation state."""

    company_id: str
    session_id: str
    messages: list[dict[str, Any]]
    original_message: str

    current_intent: str | None
    intent_type: str | None  # Intent subtype
    intent_confidence: float | None  # Confidence score from 0 to 1

    customer_id: str | None
    customer_name: str | None
    customer_phone: str | None
    customer_address: str | None

    selected_service_id: str | None
    selected_service: str | None
    service_object: Any | None
    booking_date: str | None
    booking_id: str | None
    missing_info: list[str] | None

    booking_context: dict[str, Any] | None
    user_bookings: list[dict]

    conversation_history: list[dict[str, Any]]
    history: list[dict[str, Any]]
    rag_context: str | None
    requires_escalation: bool
    satisfaction_score: int | None
    language: str
    current_step: str
    hardness: NotRequired[float]

    errors: list[str]
    debug: dict[str, Any]
