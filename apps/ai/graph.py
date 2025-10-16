"""Conversation graph: wiring, persistent checkpointer, and entrypoints.

Topology (unchanged since the god-file era): ``receive_message`` runs first,
``analyze_intent`` fans out to six handlers, everything converges on
``generate_response``. Node logic lives in :mod:`apps.ai.nodes`; shared
resources come from :mod:`apps.ai.services`.

Memory is a SQLite-backed LangGraph checkpointer (own file, never the Django
database), keyed per ``company + session`` so different companies sharing a
session id never collide.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from functools import partial
from typing import Any, Dict, Optional

from django.conf import settings
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from apps.ai.nodes import booking as booking_nodes
from apps.ai.nodes import complaint, inquiry, intake, response
from apps.ai.services import get_deps
from apps.ai.state import ConversationState

logger = logging.getLogger(__name__)

_checkpointer: SqliteSaver | None = None


def get_checkpointer() -> SqliteSaver:
    """Process-lifetime SQLite checkpointer (own file, WAL-friendly path)."""
    global _checkpointer
    if _checkpointer is None:
        path = getattr(
            settings,
            "LANGGRAPH_CHECKPOINT_DB",
            str(settings.BASE_DIR / "checkpointer.sqlite3"),
        )
        conn = sqlite3.connect(path, check_same_thread=False)
        _checkpointer = SqliteSaver(conn)
    return _checkpointer


def thread_id_for(company, session_id: str) -> str:
    """Isolate checkpoint threads per company + session."""
    return f"company:{getattr(company, 'id', 'none')}:session:{session_id}"


def build_graph(*, company, deps):
    """Compile the conversation graph with company-bound node closures."""
    workflow = StateGraph(ConversationState)

    workflow.add_node(
        "receive_message", partial(intake.receive_message, company=company, deps=deps)
    )
    workflow.add_node(
        "analyze_intent", partial(intake.analyze_intent, company=company, deps=deps)
    )

    workflow.add_node(
        "handle_general_inquiry",
        partial(inquiry.handle_general_inquiry, company=company, deps=deps),
    )

    workflow.add_node(
        "handle_service_booking",
        partial(booking_nodes.handle_service_booking, company=company, deps=deps),
    )
    workflow.add_node(
        "confirm_booking",
        partial(booking_nodes.confirm_booking, company=company, deps=deps),
    )
    workflow.add_node(
        "execute_create_booking",
        partial(booking_nodes.execute_create_booking, company=company, deps=deps),
    )

    workflow.add_node(
        "handle_service_information",
        partial(inquiry.handle_service_information, company=company, deps=deps),
    )

    workflow.add_node(
        "handle_booking_modification",
        partial(booking_nodes.handle_booking_modification, company=company, deps=deps),
    )
    workflow.add_node(
        "handle_complaint",
        partial(complaint.handle_complaint, company=company, deps=deps),
    )
    workflow.add_node(
        "clarify_intent", partial(complaint.clarify_intent, company=company, deps=deps)
    )

    workflow.add_node(
        "generate_response",
        partial(response.generate_response, company=company, deps=deps),
    )

    workflow.set_entry_point("receive_message")
    workflow.add_edge("receive_message", "analyze_intent")

    workflow.add_conditional_edges(
        "analyze_intent",
        partial(intake.route_by_intent, company=company, deps=deps),
        {
            "general_inquiry": "handle_general_inquiry",
            "service_booking": "handle_service_booking",
            "service_information": "handle_service_information",
            "booking_modification": "handle_booking_modification",
            "complaint": "handle_complaint",
            "unclear": "clarify_intent",
        },
    )
    workflow.add_conditional_edges(
        "handle_service_booking",
        partial(intake.route_after_collection, company=company, deps=deps),
        {
            "confirm_booking": "confirm_booking",
            "generate_response": "generate_response",
            "execute_create_booking": "execute_create_booking",
        },
    )

    workflow.add_edge("handle_general_inquiry", "generate_response")
    workflow.add_edge("handle_service_information", "generate_response")
    workflow.add_edge("confirm_booking", "generate_response")
    workflow.add_edge("execute_create_booking", "generate_response")

    workflow.add_edge("handle_booking_modification", "generate_response")
    workflow.add_edge("handle_complaint", "generate_response")
    workflow.add_edge("clarify_intent", "generate_response")

    workflow.add_edge("generate_response", END)

    return workflow.compile(checkpointer=get_checkpointer())


def handle_message(
    message: str,
    session_id: str,
    customer_id: Optional[str] = None,
    company=None,
    init_state: Optional[ConversationState] = None,
) -> Dict[str, Any]:
    """Run one message through the graph on its company+session thread."""
    try:
        deps = get_deps(company)
        app = build_graph(company=company, deps=deps)
        config = {"configurable": {"thread_id": thread_id_for(company, session_id)}}

        # Load current state or create a new one
        current_state = {
            "messages": [
                {
                    "role": "user",
                    "content": message,
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "session_id": session_id,
            "customer_id": customer_id,
            "language": "ar",
            "current_step": "start",
            "requires_escalation": False,
        }
        return app.invoke(init_state or current_state, config)

    except Exception as e:
        import traceback

        logger.error("Failed to process message: %s\n%s", e, traceback.format_exc())
        return "عذراً، حدث خطأ تقني. يرجى المحاولة مرة أخرى لاحقاً."


def handle_chat(message, session_id, customer_id, company, init_state=None):
    """Chat entrypoint used by the API, WhatsApp worker, and demos."""
    try:
        return handle_message(
            message, session_id, customer_id, company=company, init_state=init_state
        )
    except Exception as e:  # safety net
        logger.exception("handle_chat failed")
        return e


# Backwards-compatible alias for the old orchestrator name.
run_chat = handle_chat
