"""Complaint handling and clarification nodes."""

from __future__ import annotations

import logging
from datetime import datetime

from apps.ai.state import ConversationState

logger = logging.getLogger(__name__)


def handle_complaint(state: ConversationState, *, company, deps) -> ConversationState:
    """Handle complaints."""
    state["current_step"] = "handle_complaint"

    if not state.get("messages"):
        return state

    complaint_text = state["original_message"]

    # Assess complaint severity
    severity_keywords = {
        "عالية": ["خطر", "إصابة", "طبي", "طوارئ", "تسمم", "حريق"],
        "متوسطة": ["سوء معاملة", "خطأ", "تأخير", "رد أموال", "إلغاء"],
        "منخفضة": ["اقتراح", "تحسين", "ملاحظة", "استفسار"],
    }

    severity = "متوسطة"
    for level, keywords in severity_keywords.items():
        if any(keyword in complaint_text for keyword in keywords):
            severity = level
            break

    complaint_id = f"COM{datetime.now().strftime('%Y%m%d%H%M%S')}"

    if severity == "عالية":
        state["requires_escalation"] = True
        state["rag_context"] = (
            f"تم تسجيل شكواك برقم {complaint_id} وسيتم التواصل معك خلال ساعة واحدة من قبل الإدارة."
        )
    elif severity == "متوسطة":
        state["rag_context"] = (
            f"تم تسجيل شكواك برقم {complaint_id} وسيتم الرد عليك خلال 24 ساعة."
        )
    else:
        state["rag_context"] = (
            f"شكراً لك على ملاحظتك. تم تسجيلها برقم {complaint_id} وسنعمل على تحسين خدماتنا."
        )

    logger.info("Complaint recorded with severity %s - id %s", severity, complaint_id)
    return state


def clarify_intent(state: ConversationState, *, company, deps) -> ConversationState:
    """Ask the customer for clarification."""
    state["current_step"] = "clarify_intent"

    state["rag_context"] = (
        "عذراً، لم أتمكن من فهم طلبك بوضوح. يمكنني مساعدتك في:\n\n"
        "1️⃣ الإجابة على الاستفسارات العامة عن النادي\n"
        "2️⃣ حجز الخدمات المختلفة\n"
        "3️⃣ تعديل أو إلغاء الحجوزات الموجودة\n"
        "4️⃣ تسجيل الشكاوى والملاحظات\n"
        "5️⃣ الاستفسار عن معلومات العضوية\n\n"
        "يرجى إخباري كيف يمكنني مساعدتك اليوم؟"
    )

    logger.info("Requested clarification from customer")
    return state
