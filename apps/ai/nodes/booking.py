"""Booking nodes: collection, confirmation, execution, modification."""

from __future__ import annotations

import json
import logging
import re

from django.db import transaction
from langchain_core.messages import HumanMessage

from apps.ai.services.dates import parse_booking_date
from apps.ai.services.lookup import fetch_user_bookings, match_service, resolve_customer
from apps.ai.state import ConversationState
from apps.core.models import Booking, Service

logger = logging.getLogger(__name__)


def format_bookings_context(bookings) -> str:
    """Render the user-bookings block shared by modification flows."""
    bookings_context = "Current bookings for the user:\n"
    for idx, booking in enumerate(bookings, 1):
        bookings_context += f"\n{idx}. Booking #{booking['id']}:"
        bookings_context += f"\n   - Service: {booking['service']}"
        bookings_context += f"\n   - service_text: {booking['service_text']}"
        bookings_context += f"\n   - Date: {booking['date']}"
        bookings_context += f"\n   - Status: {booking['status']}"
        bookings_context += f"\n   - notes: {booking['notes']}"
        bookings_context += (
            f"\n   - Can Cancel: {'Yes' if booking['is_cancellable'] else 'No'}"
        )
    return bookings_context


def handle_service_booking(
    state: ConversationState, *, company, deps
) -> ConversationState:
    state["current_step"] = "handle_service_booking"

    # Check what information is missing
    missing = []
    if not state.get("customer_name"):
        missing.append("name")
    if not state.get("customer_phone"):
        missing.append("phone")
    if not state.get("selected_service"):
        missing.append("service")

    state["missing_info"] = missing

    last_message = state["original_message"]

    phone_pattern = re.compile(r"\b\d{10,11}\b")
    phone_match = phone_pattern.search(last_message)
    if phone_match and not state.get("customer_phone"):
        state["customer_phone"] = phone_match.group()
        if "phone" in missing:
            missing.remove("phone")

    if missing:
        services_info = "\n".join(
            [
                f"- {s['name']} : {s['price']} جنيه - {s['description']}"
                for s in deps.services_qs.values()
            ]
        )

        state["rag_context"] = f"""
        Missing information: {", ".join(missing)}

        Ask the customer politely for the missing information in a conversational way.
        If service is missing, list the available services with their numbers.

        الخدمات المتاحة: {services_info}
        """

    # Unified matcher (fuzzy first, LLM fallback). Previously a fuzzy hit left
    # `service` unbound and crashed the node; now it resolves to an object.
    service = match_service(company=company, deps=deps, state=state)
    if service is not None:
        state["selected_service_id"] = service.id
    state["service_object"] = None if service is None else service.id
    return state


def confirm_booking(state: ConversationState, *, company, deps) -> ConversationState:
    """Ask for booking confirmation"""
    service = state.get("service_object", None)

    if service:
        service = Service.objects.filter(id=service).first()

    customer_name = state.get("customer_name", "")
    customer_phone = state.get("customer_phone", "")
    customer_address = state.get("customer_address", "")
    booking_date = state.get("booking_date", "")
    booking_id = state.get("booking_id", "")
    selected_service = state.get("selected_service", "")

    name = ""
    description = ""
    price = ""

    if service:
        name = service.name or selected_service
        description = service.description or ""
        price = service.price

    formatted_context = f"""
        أنت مساعد آلي دقيق ومحترف. مهمتك هي عرض تفاصيل الحجز التالية للحصول على تأكيد نهائي من العميل. يجب عليك إتباع القواعد الشرطية الصارمة: لا تُدرج أي سطر أو جزء معلومات عن متغير فارغ.

        من المهم جدا ان تكون رسالتك بغرض طلب تأكيد الحجز من العميل وتتم بصيغة السؤال دائما

        تأكد من موضوع الاسم والرقم اذا وجدوا في رساله الرد .
        لا تسأل عن اي عنصر عير موجود في رساله الرد
        اجعل رساله الرد قصيرة

        1. رسالة البداية المخصصة:
        اختر رسالة بداية مناسبة

        2. ملخص تفاصيل الحجز والخدمة:
        نحن على وشك تأكيد حجزك رقم . يرجى مراجعة التفاصيل أدناه قبل التأكيد النهائي:

        أ. معلومات العميل والحجز:
        {"- رقم الحجز:" if booking_id else ""} {booking_id}
        {"- العميل:" if customer_name else ""} {customer_name}
        {"- رقم التواصل:" if customer_phone else ""} {customer_phone}
        {"- التاريخ والوقت:" if booking_date else ""} {booking_date}
        {"- موقع الخدمة:" if customer_address else ""} {customer_address}

        ب. تفاصيل الخدمة:
        - الخدمة المحجوزة: {name}
        - [إذا كانت description]: وصف الخدمة: {description}
        - [إذا كانت price]: التكلفة: {price}

        3. السؤال النهائي للتأكيد:
        "هل المعلومات المذكورة أعلاه صحيحة وتؤكد المضي قدماً في الحجز؟ (يرجى الرد بنعم للتأكيد)"

        4. رسالة الختام المخصصة:
        اختر رسالة نهاية مناسبة
    """
    state["rag_context"] = formatted_context

    return state


def execute_create_booking(
    state: ConversationState, *, company, deps
) -> ConversationState:
    """Handle booking creation"""
    state["current_step"] = "execute_create_booking"
    service = state.get("service_object", None)

    if service:
        service = Service.objects.filter(id=service).first()

    customer = resolve_customer(state)

    customer_name = state.get("customer_name", "")
    customer_phone = state.get("customer_phone", "")
    customer_address = state.get("customer_address", "")
    booking_date = state.get("booking_date", "")
    selected_service = state.get("selected_service", "")

    notes = f"""
        اسم العميل : {customer_name}
        رقم الهاتف : {customer_phone}
        العنوان : {customer_address}
        تاريخ الحجز : {booking_date}
        الخدمة : {selected_service}
    """

    parsed_date = parse_booking_date(booking_date)

    with transaction.atomic():
        booking = None
        # Double-submit guard: an identical still-open booking is reused
        # instead of creating a duplicate. Skipped when the date is
        # unparseable (NULL dates never match each other).
        if parsed_date is not None:
            booking = (
                Booking.objects.select_for_update()
                .filter(
                    company_id=state["company_id"],
                    customer=customer,
                    service=service,
                    service_text=selected_service,
                    date=parsed_date,
                    status__in=[Booking.Status.CREATED, Booking.Status.CONFIRMED],
                )
                .first()
            )
        if booking is None:
            booking = Booking.objects.create(
                company_id=state["company_id"],
                customer=customer,
                service=service,
                service_text=selected_service,
                status=Booking.Status.CONFIRMED,
                notes=notes,
                source=Booking.Source.CHAT,
                date=parsed_date,
            )

    state["rag_context"] = f"""
        ارسال رساله لانها تم انشاء حجزك واضف هذه المعلومات.
        اذا كانت هناك معلومات فارغه لا تتضفها
        رقم الحجز : {booking.id}
        الخدمة : {selected_service if not service else service.name}
        تاريخ الحجز : {booking_date}
        العنوان : {customer_address}
        رقم الهاتف : {customer_phone}
        اسم العميل : {customer_name}

    """

    return state


def handle_booking_modification(state: ConversationState, *, company, deps):
    result = analyze_request(state, company=company, deps=deps)

    action_type = result.get("action_type")
    booking_id = result.get("booking_id")
    edit_fields = result.get("edit_fields")
    rag_context = ""

    bookings_context = format_bookings_context(state.get("user_bookings", []))

    if not action_type:
        rag_context = """
        مشكلة في تحدد نية العميل:
        لا أفهم الإجراء الذي تريد تنفيذه على حجوزاتك. هل يمكنك توضيحه أكثر واختيار أحد الخيارات التالية:
            تعديل حجز محدد، أو إلغاء حجز محدد، أو إلغاء حجز الحجوزات، أو المعلومات المتعلقة بحجوزاتك.

        """

    if not booking_id:
        rag_context += f"""
            تحديد الحجز المحدد:
            يمكنك اختيار أي من هذه الحجوزات.

            {bookings_context}

         """

    if not edit_fields and action_type == "edit":
        rag_context += """
            تحديد الحقل المحدد:
           الحقول التي تريد تعديلها

         """

    if rag_context:
        state["rag_context"] = rag_context
        return state

    return state


def analyze_request(state: ConversationState, *, company, deps) -> ConversationState:
    """
    Analyze user request and determine action type.
    Provides context of all user bookings to LLM.
    """
    state["current_step"] = "clarify_intent"

    # Fetch user bookings for context
    customer = resolve_customer(state)
    bookings = fetch_user_bookings(company, customer)

    if not bookings:
        state["rag_context"] = (
            "I see you don't have any bookings yet. Would you like to make a new booking?"
        )
        return state

    state["user_bookings"] = bookings

    # Build context message
    bookings_context = format_bookings_context(state["user_bookings"])

    user_messete = state["original_message"]

    analysis_prompt = f"""
    Analyze the user's request and determine the action needed.

    {bookings_context}

    User's last message: {user_messete}

    Determine:
    1. Action type: 'edit', 'cancel', 'cancel_all', 'info'  or 'confirm previous booking'
    2. Which booking ID if specific booking mentioned user can choose more than booking so make it list [1,2,3] if user choose all make it all id in the ilist
    3. What fields to edit if editing

    Respond in JSON format.
    {{
        "action_type": "edit",
        "booking_id": 123,
        "edit_fields": ["date", "time"]
    }}
    """

    response = deps.llm.invoke([HumanMessage(content=analysis_prompt)])

    # Parse LLM response and update state
    try:
        json_start = response.content.find("{")
        json_end = response.content.rfind("}") + 1
        if json_start != -1 and json_end > json_start:
            json_text = response.content[json_start:json_end]
            analysis = json.loads(json_text)

            state["action_type"] = analysis.get("action_type")
            if "booking_id" in analysis:
                state["selected_booking"] = next(
                    (
                        b
                        for b in state["user_bookings"]
                        if b["id"] == analysis["booking_id"]
                    ),
                    None,
                )
            if "edit_fields" in analysis:
                state["edit_fields"] = analysis["edit_fields"]
        else:
            state["rag_context"] = ""
    except Exception:
        logger.exception("Failed to parse booking-modification analysis")

    return state
