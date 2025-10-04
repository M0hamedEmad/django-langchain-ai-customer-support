from __future__ import annotations
import re
from typing import Any, Dict
import json

from django.utils import timezone

from apps.core.models import Service, Booking, EscalationTicket
from apps.ai.retrieval.retrieval import better_retrieve
from .state import GraphState
from .prompts import GROUNDED_ANSWER_PROMPT_AR, INTENT_PROMPT_AR
from .llm_providers import get_chat_model
try:
    from langchain_core.messages import SystemMessage, HumanMessage
except Exception:  # pragma: no cover
    SystemMessage = None  # type: ignore
    HumanMessage = None  # type: ignore


def _normalize_arabic(text: str) -> str:
    text = text.replace("ـ", "").strip()
    text = re.sub(r"[\u0622\u0623\u0625]", "ا", text)  # unify alef
    return text


def _within_working_hours(company, start_dt, duration_minutes: int) -> bool:
    try:
        hours = getattr(company, "working_hours", {}) or {}
        # Normalize weekday key, e.g., 'mon', 'tue', ...
        key = start_dt.strftime("%a").lower()  # Mon->mon
        intervals = hours.get(key) or []
        if not intervals:
            return False
        end_dt = start_dt + timezone.timedelta(minutes=duration_minutes or 60)
        for interval in intervals:
            # interval like ["09:00","17:00"]
            if not isinstance(interval, (list, tuple)) or len(interval) != 2:
                continue
            s, e = interval
            sh, sm = map(int, s.split(":"))
            eh, em = map(int, e.split(":"))
            start_window = start_dt.replace(hour=sh, minute=sm, second=0, microsecond=0)
            end_window = start_dt.replace(hour=eh, minute=em, second=0, microsecond=0)
            # Check full containment
            if start_dt >= start_window and end_dt <= end_window:
                return True
        return False
    except Exception:
        return True  # be permissive if bad config


def preprocess_ar(state: GraphState) -> GraphState:
    state["message"] = _normalize_arabic(state.get("message", ""))
    state.setdefault("debug", {})["node"] = "preprocess_ar"
    return state


def customer_identifier(state: GraphState) -> GraphState:
    # API layer sets customer info when available
    state.setdefault("debug", {})["node"] = "customer_identifier"
    return state


def classify_intent(state: GraphState) -> GraphState:
    text = state.get("message", "")
    intent: Dict[str, Any] = {"label": None, "operation": None, "confidence": 0.5, "rationale": "heuristic"}
    # First try LLM JSON classification
    try:
        chat = get_chat_model()
        prompt = INTENT_PROMPT_AR + "\n\n" + text
        res = chat.invoke(prompt)
        content = getattr(res, "content", None) or str(res)
        # Extract JSON
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            data = json.loads(content[start:end+1])
            intent.update({
                "label": data.get("intent"),
                "operation": data.get("operation"),
                "confidence": float(data.get("confidence", 0.5)),
                "rationale": data.get("rationale", "llm"),
            })
        else:
            raise ValueError("No JSON found in LLM output")
    except Exception:
        # Heuristic fallback
        if any(k in text for k in ["حجز", "احجز", "موعد", "اشتراك", "reservation"]):
            intent.update({"label": "BOOKING", "operation": "create", "confidence": 0.8})
        elif any(k in text for k in ["مرحبا", "أهلا", "اهلا", "سلام", "ازيك", "كيفك"]):
            intent.update({"label": "SMALL_TALK", "confidence": 0.7})
        elif any(k in text for k in ["بشري", "انسان", "موظف", "تواصل مع شخص", "مش راضي"]):
            intent.update({"label": "ESCALATE", "confidence": 0.9})
        else:
            intent.update({"label": "FAQ", "confidence": 0.6})

    # Flag low confidence for clarifying question
    intent["low_conf"] = bool(intent.get("confidence", 0.0) < 0.55)
    state["intent"] = intent
    state.setdefault("debug", {})["node"] = "classify_intent"
    return state


def retrieve(state: GraphState, *, company=None) -> GraphState:
    query = state.get("message", "")
    docs: list[dict[str, Any]] = []
    try:
        if company is not None and query:
            docs = better_retrieve(company, query, top_k=6, fetch_k=24)
    except Exception:
        docs = []
    state["retrieval"] = {"query": query, "docs": docs}
    state.setdefault("debug", {})["node"] = "retrieve"
    return state


def generate_answer(state: GraphState) -> GraphState:
    label = (state.get("intent") or {}).get("label")
    if (state.get("intent") or {}).get("low_conf"):
        state.setdefault("answer", {})["text"] = "ممكن توضّح قصدك؟ هل تسأل عن الحجز أم عن معلومة عامة؟"
        state.setdefault("debug", {})["node"] = "generate_answer"
        return state
    # Booking path keeps the structured flow; use templates instead of LLM to enforce confirmation
    if label == "BOOKING":
        booking = state.get("booking") or {}
        if booking.get("params_status") != "complete":
            missing = booking.get("missing", [])
            if missing:
                pretty = ", ".join(missing)
                text = f"تمام. محتاج منك معلومات: {pretty}."
            else:
                text = "خلّينا نكمّل الحجز، اسمك ورقم الهاتف والخدمة والوقت المناسب؟"
            state.setdefault("answer", {})["text"] = text
            state.setdefault("debug", {})["node"] = "generate_answer"
            return state
        summary = ((booking.get("confirmation") or {}).get("summary")) or "هذا ملخص الحجز. اكتب \"تأكيد\" لإتمام العملية."
        state.setdefault("answer", {})["text"] = summary
        state.setdefault("debug", {})["node"] = "generate_answer"
        return state

    # For FAQ/SMALL_TALK, attempt LLM grounded answer; fallback to simple responses
    retrieval = state.get("retrieval") or {}
    docs = retrieval.get("docs", [])
    history = state.get("history") or []
    user_msg = state.get("message", "")
    doc_snippets = "\n\n".join([d.get("text", "") for d in docs[:4]])
    history_snippets = "\n".join([f"{h['role']}: {h['content']}" for h in history[-6:]])

    text = ""
    try:
        chat = get_chat_model()
        if SystemMessage and HumanMessage:
            messages = [
                SystemMessage(content=GROUNDED_ANSWER_PROMPT_AR),
                HumanMessage(content=f"تاريخ المحادثة (مختصر):\n{history_snippets}" if history_snippets else ""),
                HumanMessage(content=f"مقاطع معرفة:\n{doc_snippets}" if doc_snippets else "لا توجد مقاطع معرفة كافية"),
                HumanMessage(content=f"رسالة العميل: {user_msg}"),
            ]
            ai_msg = chat.invoke(messages)
            text = getattr(ai_msg, "content", None) or str(ai_msg)
        else:
            # If message classes not available, call with raw prompt
            prompt = "\n\n".join([
                GROUNDED_ANSWER_PROMPT_AR,
                f"تاريخ:\n{history_snippets}" if history_snippets else "",
                f"معرفة:\n{doc_snippets}" if doc_snippets else "لا توجد معرفة كافية",
                f"سؤال:\n{user_msg}",
            ])
            ai_msg = chat.invoke(prompt)
            text = getattr(ai_msg, "content", None) or str(ai_msg)
    except Exception:
        # Fallbacks
        if label == "SMALL_TALK":
            text = "أهلاً وسهلاً! كيف أقدر أساعدك؟"
        else:
            text = "تمام، ممكن توضح سؤالك أكثر؟"

    ans = state.setdefault("answer", {})
    ans["text"] = text
    # Attach citations if available
    if docs:
        ans["citations"] = [d.get("metadata", {}).get("faq_id") for d in docs[:3] if d.get("metadata", {}).get("faq_id")]
    state.setdefault("debug", {})["node"] = "generate_answer"
    return state


def booking(state: GraphState) -> GraphState:
    booking = state.get("booking") or {}
    booking.setdefault("service_name", None)
    booking.setdefault("when", None)
    booking.setdefault("name", (state.get("customer") or {}).get("name"))
    booking.setdefault("phone", (state.get("customer") or {}).get("phone"))
    state["booking"] = booking
    state.setdefault("debug", {})["node"] = "booking"
    return state


def booking_params(state: GraphState, *, company=None) -> GraphState:
    b = state.get("booking") or {}
    # Try to auto-extract service from message if missing
    if company is not None and not b.get("service_name"):
        from rapidfuzz import process, fuzz  # type: ignore
        msg = state.get("message", "")
        names = list(company.services.filter(is_active=True).values_list("name", flat=True))
        if names:
            best = process.extractOne(msg, names, scorer=fuzz.partial_ratio)
            if best and best[1] >= 70:
                b["service_name"] = best[0]

    # Parse time using dateparser if available
    if not b.get("when"):
        b["when"] = state.get("message", "")
    if company is not None and b.get("when") and not b.get("start_at"):
        try:
            import dateparser  # type: ignore
            from django.utils import timezone as dj_tz
            tzname = getattr(company, "timezone", "UTC") or "UTC"
            dt = dateparser.parse(b.get("when") or "", settings={"PREFER_DATES_FROM": "future", "TIMEZONE": tzname})
            if dt is not None:
                start_at = dj_tz.make_aware(dt, dj_tz.get_current_timezone()) if dt.tzinfo is None else dt
                b["start_at"] = start_at.isoformat()
        except Exception:
            pass

    # Validate availability against working hours & conflicts
    availability_ok = True
    suggestion = None
    try:
        if company is not None and b.get("start_at") and b.get("service_name"):
            from dateutil import parser as dtparser  # type: ignore
            start_dt = dtparser.parse(b["start_at"])  # aware
            service = Service.objects.filter(company=company, name__iexact=b["service_name"], is_active=True).first()
            duration = (service.duration_minutes if service else 60) or 60
            if not _within_working_hours(company, start_dt, duration):
                availability_ok = False
            else:
                end_dt = start_dt + timezone.timedelta(minutes=duration)
                conflict = Booking.objects.filter(company=company, service=service, start_at__lt=end_dt, end_at__gt=start_dt).exists()
                if conflict:
                    availability_ok = False
            if not availability_ok:
                # naive suggestion: add 60 min
                suggestion = (start_dt + timezone.timedelta(minutes=60)).isoformat()
                b["suggested_when"] = suggestion
    except Exception:
        pass

    required = ["name", "phone", "service_name", "when"]
    missing = [k for k in required if not b.get(k)]
    if not availability_ok and "when" not in missing:
        missing.append("when")
    b["missing"] = missing
    b["params_status"] = "complete" if not missing else "incomplete"
    state["booking"] = b
    state.setdefault("debug", {})["node"] = "booking_params"
    return state


def booking_confirmation_handler(state: GraphState) -> GraphState:
    b = state.get("booking") or {}
    summary = (
        f"ملخص الحجز:\n- الخدمة: {b.get('service_name') or 'غير محددة'}\n"
        f"- الاسم: {b.get('name') or 'غير محدد'}\n- الهاتف: {b.get('phone') or 'غير محدد'}\n"
        f"- الموعد: {b.get('when') or 'غير محدد'}\n\nلو كل شيء تمام اكتب \"تأكيد\" لإتمام الحجز."
    )
    conf = b.get("confirmation") or {"required": True, "asked": True, "confirmed": False, "summary": summary}
    # If user already said "تأكيد"
    if "تاكيد" in _normalize_arabic(state.get("message", "")) or "تأكيد" in state.get("message", ""):
        conf["confirmed"] = True
    b["confirmation"] = conf
    state["booking"] = b
    state.setdefault("answer", {})["text"] = summary
    state.setdefault("debug", {})["node"] = "booking_confirmation_handler"
    return state


def booking_execute(state: GraphState, *, company=None, conversation=None) -> GraphState:
    b = state.get("booking") or {}
    conf = (b.get("confirmation") or {})
    if not conf.get("confirmed"):
        return state

    # Resolve service
    service_name = (b.get("service_name") or "").strip()
    service = None
    if company and service_name:
        service = Service.objects.filter(company=company, name__iexact=service_name, is_active=True).first()
    if not service:
        state.setdefault("answer", {})["text"] = "الخدمة غير متاحة حالياً. ممكن تختار خدمة من القائمة؟"
        return state

    # Determine start/end time
    start_at = None
    try:
        if b.get("start_at"):
            from dateutil import parser as dtparser  # type: ignore
            dt = dtparser.parse(b.get("start_at"))
            start_at = dt if dt.tzinfo else timezone.make_aware(dt, timezone.get_current_timezone())
    except Exception:
        start_at = None
    if start_at is None:
        start_at = timezone.now() + timezone.timedelta(hours=1)
    end_at = start_at + timezone.timedelta(minutes=service.duration_minutes or 60)

    booking = Booking.objects.create(
        company=company,
        customer=conversation.customer if conversation else None,
        service=service,
        start_at=start_at,
        end_at=end_at,
        notes="created via chat",
    )
    state.setdefault("answer", {})["text"] = f"تم تأكيد حجزك رقم #{booking.id} لخدمة {service.name} في {start_at:%Y-%m-%d %H:%M}."
    state.setdefault("debug", {})["node"] = "booking_execute"
    return state


def escalate(state: GraphState, *, company=None, conversation=None) -> GraphState:
    state.setdefault("escalation", {})["needed"] = True
    # Create a DB ticket for human follow-up when possible
    try:
        if company is not None and conversation is not None:
            EscalationTicket.objects.create(
                company=company,
                conversation=conversation,
                reason=state.get("intent", {}).get("rationale", "user requested escalation"),
                priority=EscalationTicket.Priority.MEDIUM,
            )
    except Exception:
        pass

    state.setdefault("answer", {})["text"] = "تم إحالة المحادثة لدعم بشري. شكراً لصبرك."
    state.setdefault("debug", {})["node"] = "escalate"
    return state


def error_handler(state: GraphState, error: Exception) -> GraphState:
    print(error)
    state.setdefault("errors", []).append(str(error))
    state.setdefault("answer", {})["text"] = "عذرًا، حصل خطأ بسيط. خلّينا نجرب كمان مرة."
    state.setdefault("debug", {})["node"] = "error_handler"
    return state
