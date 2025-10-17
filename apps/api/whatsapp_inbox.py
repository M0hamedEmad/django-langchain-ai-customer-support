"""WhatsApp inbox worker logic: unprocessed rows -> AI reply -> send -> mark.

Single-attempt processing: a row that cannot be answered (no company, dead
LLM, dead gateway) is marked processed with an empty reply and a log line,
never retried in a poison loop. Requeue from the admin by clearing
`is_processed`. Shares nothing with HTTP handling; the webhook only stores.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from apps.ai.graph import handle_chat
from apps.core.models import Conversation, Customer, Message, WhatsAppMessage

logger = logging.getLogger(__name__)


def _get_gateway():
    from apps.api.whatsapp_service import WhatsAppService

    return WhatsAppService()


def _ensure_customer_and_conversation(company, phone: str, sender_name: str = ""):
    customer, _ = Customer.objects.get_or_create(
        company=company,
        phone=phone,
        defaults={"name": sender_name or "", "email": ""},
    )
    conv, _ = Conversation.objects.get_or_create(
        company=company,
        session_id=phone,
    )
    if conv.customer_id != customer.id:
        conv.customer = customer
        conv.save(update_fields=["customer"])
    return customer, conv


def _build_state(company, conv, customer, message: str) -> Dict[str, Any]:
    # Mirrors ChatStreamView.post(): last-8 history + current message.
    recent: List[Message] = list(
        Message.objects.filter(conversation=conv).order_by("-created_at")[:8]
    )
    history = [{"role": m.role, "content": m.content} for m in reversed(recent)]
    return {
        "company_id": str(company.id),
        "session_id": conv.session_id,
        "original_message": message,
        "messages": [{"role": "user", "content": message}],
        "lang": company.language or "ar",
        "customer_id": customer.id,
        "customer_name": customer.name,
        "customer_phone": customer.phone,
        "conversation_history": history,
    }


def _mark(wm: WhatsAppMessage, reply: str = "") -> None:
    wm.reply_text = reply
    wm.is_processed = True
    wm.save(update_fields=["reply_text", "is_processed"])


def process_one(wm: WhatsAppMessage, gateway=None) -> bool:
    """Answer one inbound message. Returns True if a reply was sent."""
    company = wm.company
    if company is None:
        logger.warning("WhatsApp %s has no company; skipping", wm.message_id)
        _mark(wm)
        return False

    customer, conv = _ensure_customer_and_conversation(
        company, wm.phone_number, wm.sender_name or ""
    )
    Message.objects.create(
        conversation=conv,
        role=Message.Role.USER,
        content=wm.message_body,
        meta={"lang": company.language or "ar", "whatsapp_id": wm.message_id},
    )
    state = _build_state(company, conv, customer, wm.message_body)
    result = handle_chat(
        wm.message_body, conv.session_id, customer.id, company, init_state=state
    )
    try:
        final_text: str = result["messages"][-1]["content"]
    except (KeyError, IndexError, TypeError, AttributeError):
        logger.exception("WhatsApp %s: pipeline produced no reply", wm.message_id)
        _mark(wm)
        return False

    Message.objects.create(
        conversation=conv,
        role=Message.Role.ASSISTANT,
        content=final_text,
        meta={"lang": company.language or "ar", "whatsapp_id": wm.message_id},
    )
    try:
        gateway = gateway if gateway is not None else _get_gateway()
        gateway.send_message(f"+{wm.phone_number}", final_text)
    except Exception:
        logger.exception("WhatsApp %s: reply send failed", wm.message_id)
        _mark(wm)
        return False
    _mark(wm, final_text)
    return True


def process_inbox(limit: int | None = None, gateway=None) -> dict:
    """Process unprocessed rows oldest-first. Returns a summary dict."""
    qs = WhatsAppMessage.objects.filter(is_processed=False).order_by(
        "received_at", "pk"
    )
    if limit is not None:
        qs = qs[:limit]
    sent = failed = 0
    for wm in qs:
        try:
            if process_one(wm, gateway=gateway):
                sent += 1
            else:
                failed += 1
        except Exception:
            logger.exception("WhatsApp %s: unexpected worker error", wm.message_id)
            try:
                _mark(wm)
            except Exception:
                pass
            failed += 1
    return {"sent": sent, "failed": failed}
