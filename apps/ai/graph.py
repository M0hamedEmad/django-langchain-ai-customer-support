"""LangGraph orchestration entrypoint.

Single re-export of the live chatbot pipeline in :mod:`apps.ai.workflow`.
Kept as a stable import path so callers never import workflow internals.
"""

from __future__ import annotations

from .workflow import handle_chat

__all__ = ["handle_chat"]

# Backwards-compatible alias for the old orchestrator name.
run_chat = handle_chat
