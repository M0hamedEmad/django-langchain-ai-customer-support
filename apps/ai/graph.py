from __future__ import annotations

import logging
from typing import Any, Dict

from .state import GraphState
# from .workflow import compile_workflow

logger = logging.getLogger(__name__)


def run_chat(*, state: Dict[str, Any], company, conversation) -> Dict[str, Any]:
    """
    Minimal orchestrator that mimics the LangGraph flow described in ARCHITECTURE.md.
    It executes nodes in sequence with conditional routing.

    Later this can be replaced with a real LangGraph StateGraph app.
    """
    try:
        s: GraphState = state  # type: ignore
        # app = compile_workflow(company=company, conversation=conversation)
        final_state = app.invoke(s)
        return final_state  # includes answer/debug/intent/booking
    except Exception as e:  # safety net
        # Minimal fallback without importing nodes here
        s = state
        s.setdefault("errors", []).append(str(e))
        # User-facing Arabic fallback (product language).
        s.setdefault("answer", {})["text"] = "عذرًا، حصل خطأ بسيط. خلّينا نجرب كمان مرة."
        s.setdefault("debug", {})["node"] = "error_handler"
        logger.exception("LangGraph orchestration failed; returning fallback answer")
        return s
