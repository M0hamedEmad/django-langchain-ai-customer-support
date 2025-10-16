"""Intake nodes: message receipt, intent analysis, and routing."""

from __future__ import annotations

import json
import logging

from apps.ai.retrieval.arabic_preprocess import normalize_arabic
from apps.ai.state import ConversationState, IntentSubType, IntentType

logger = logging.getLogger(__name__)


def receive_message(state: ConversationState, *, company, deps) -> ConversationState:
    messages = (
        state.get("messages", [])[-1] if state.get("messages") else "no messages"
    )

    try:
        messages = normalize_arabic(messages["content"])
    except Exception as e:
        logger.error("Failed to normalize incoming message: %s", e)

    logger.info("Received new message: %s", messages)
    state["current_step"] = "receive_message"

    return state


def analyze_intent(state: ConversationState, *, company, deps) -> ConversationState:
    if not state.get("messages"):
        state["current_intent"] = IntentType.UNCLEAR.value
        state["intent_type"] = IntentSubType.UNCLEAR.value
        state["intent_confidence"] = 0.0
        return state

    last_message = state["original_message"]
    info = company.get_company_general_info()

    try:
        chat_history = state.get("conversation_history", [])
        prompt = deps.intent_classifier_template.format_messages(
            message=last_message, company_info=info, chat_history=chat_history
        )
        response = deps.llm.invoke(prompt)
        response_text = response.content.strip()

        try:
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                json_text = response_text[json_start:json_end]
                intent_data = json.loads(json_text)

                intent = intent_data.get("intent", "")
                intent_type = intent_data.get("intent_type", "")
                customer = intent_data.get("customer", {})
                confidence = float(intent_data.get("confidence", 0.5))
                state["hardness"] = float(intent_data.get("hardness", 5))

                valid_intents = [e.value for e in IntentType]
                valid_intent_types = [e.value for e in IntentSubType]

                if intent in valid_intents:
                    state["current_intent"] = intent
                else:
                    state["current_intent"] = IntentType.UNCLEAR.value

                if intent_type in valid_intent_types:
                    state["intent_type"] = intent_type
                else:
                    state["intent_type"] = IntentSubType.UNCLEAR.value

                state["intent_confidence"] = max(0.0, min(1.0, confidence))

                if customer:
                    state["customer_name"] = customer.get("name") or state.get(
                        "customer_name", None
                    )
                    state["customer_phone"] = customer.get("phone") or state.get(
                        "customer_phone", None
                    )
                    # state["customer_address"] = customer.get("address") or state.get("customer_address", None)
                    state["selected_service"] = customer.get(
                        "service"
                    ) or state.get("selected_service", None)
                    state["booking_date"] = customer.get(
                        "booking_date"
                    ) or state.get("booking_date", None)
                    state["booking_id"] = customer.get("booking_id") or state.get(
                        "booking_id", None
                    )

            else:
                raise ValueError("لم يتم العثور على JSON في الاستجابة")

        except (json.JSONDecodeError, ValueError) as json_error:
            logger.warning(
                "JSON parse failed, falling back to legacy parser: %s", json_error
            )
            # Fall back to the legacy parser
            intent = response_text
            valid_intents = [e.value for e in IntentType]
            if intent in valid_intents:
                state["current_intent"] = intent
            else:
                state["current_intent"] = IntentType.UNCLEAR.value
            state["intent_type"] = IntentSubType.UNCLEAR.value
            state["intent_confidence"] = 0.5

    except Exception as e:
        import traceback

        traceback.print_exc()
        logger.error("Failed to analyze intent: %s", e)
        state["current_intent"] = IntentType.UNCLEAR.value
        state["intent_type"] = IntentSubType.UNCLEAR.value
        state["intent_confidence"] = 0.0

    state["current_step"] = "analyze_intent"
    logger.info(
        "Intent determined: %s | type: %s | confidence: %.2f | hardness: %s",
        state["current_intent"],
        state.get("intent_type"),
        state.get("intent_confidence", 0),
        state.get("hardness", deps.hardness),
    )
    return state


def route_by_intent(state: ConversationState, *, company, deps) -> str:
    """Route the conversation by intent."""
    intent = state.get("current_intent", "")

    if intent == IntentType.GENERAL_INQUIRY.value:
        return route_general_inquiry(state, company=company, deps=deps)
    elif intent == IntentType.SERVICE_BOOKING.value:
        return route_service_booking(state, company=company, deps=deps)
    elif intent == IntentType.BOOKING_MODIFICATION.value:
        return "booking_modification"
    elif intent == IntentType.COMPLAINT.value:
        return "complaint"
    elif intent == IntentType.MEMBERSHIP_INQUIRY.value:
        # No dedicated membership node exists; membership questions are
        # answered as general inquiries (previously a graph KeyError).
        return route_general_inquiry(state, company=company, deps=deps)
    else:
        return "unclear"


def route_general_inquiry(state, *, company, deps):
    intent_type = state.get("intent_type", "")

    if intent_type == IntentSubType.GENERAL_INFO_REQUEST.value:
        return "general_inquiry"
    elif intent_type == IntentSubType.SERVICE_INFO_REQUEST.value:
        return "service_information"

    return "general_inquiry"


def route_service_booking(state, *, company, deps):
    intent_type = state.get("intent_type", "")

    if intent_type == IntentSubType.BOOKING_REQUEST.value:
        return "service_booking"
    elif intent_type == IntentSubType.BOOKING_INFO_REQUEST.value:
        return "service_information"
    elif intent_type == IntentSubType.BOOKING_CONFIRMATION.value:
        return "service_booking"

    return "service_booking"


def route_after_collection(state, *, company, deps):
    missing = state.get("missing_info", [])

    if missing:
        return "generate_response"
    elif state.get("intent_type", "") == IntentSubType.BOOKING_CONFIRMATION.value:
        return "execute_create_booking"

    return "confirm_booking"
