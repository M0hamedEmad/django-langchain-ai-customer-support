"""Intent routing: pure decision tables, no DB, no LLM."""

from apps.ai import nodes as N


def _route(intent, intent_type=""):
    return N.route_by_intent(
        {"current_intent": intent, "intent_type": intent_type},
        company=None,
        deps=None,
    )


def test_general_inquiry_routes():
    assert _route("استفسار_عام", "طلب_معلومات_عامة") == "general_inquiry"


def test_service_info_routes():
    assert _route("استفسار_عام", "طلب_معلومات_خدمة") == "service_information"


def test_booking_request_routes():
    assert _route("حجز_خدمة", "طلب_حجز") == "service_booking"


def test_booking_info_routes_to_service_information():
    assert _route("حجز_خدمة", "طلب_معلومات_حجز") == "service_information"


def test_modification_routes():
    assert _route("تعديل_حجز") == "booking_modification"


def test_complaint_routes():
    assert _route("شكوى") == "complaint"


def test_membership_falls_back_to_general_inquiry():
    # No dedicated membership node exists; must not raise KeyError downstream.
    assert _route("استفسار_عضوية") == "general_inquiry"


def test_unknown_intent_clarifies():
    assert _route("???") == "unclear"


def test_route_after_collection():
    kw = {"company": None, "deps": None}
    assert (
        N.route_after_collection({"missing_info": ["x"]}, **kw) == "generate_response"
    )
    assert (
        N.route_after_collection(
            {"missing_info": [], "intent_type": "تأكيد_طلب_الحجز"}, **kw
        )
        == "execute_create_booking"
    )
    assert N.route_after_collection({"missing_info": []}, **kw) == "confirm_booking"
