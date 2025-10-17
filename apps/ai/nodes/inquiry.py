"""Inquiry nodes: knowledge-base answers, optionally with the catalog."""

from __future__ import annotations

import logging

from apps.ai.state import ConversationState

logger = logging.getLogger(__name__)


def _inquiry(
    state: ConversationState, *, company, deps, include_services: bool, step: str
) -> ConversationState:
    state["current_step"] = step

    if not state.get("messages"):
        return state

    query = state["original_message"]

    # Search the knowledge base
    if deps.vectorstore:
        relevant_docs = deps.vectorstore.similarity_search(query)
        context = "\n\n".join([doc.page_content for doc in relevant_docs])
        state["rag_context"] = context
    else:
        state["rag_context"] = "معلومات عامة عن النادي الرياضي"

    if include_services:
        services_info = "\n".join(
            [
                f"- {s['name']} : {s['price']} جنيه - {s['description']}"
                for s in deps.services_qs.values()
            ]
        )

        state["rag_context"] = f"""
            {state["rag_context"]}

            الخدمات المتاحة: {services_info}
        """

    logger.info("Handled general inquiry")
    return state


def handle_general_inquiry(
    state: ConversationState, *, company, deps
) -> ConversationState:
    return _inquiry(
        state,
        company=company,
        deps=deps,
        include_services=False,
        step="handle_general_inquiry",
    )


def handle_service_information(
    state: ConversationState, *, company, deps
) -> ConversationState:
    return _inquiry(
        state,
        company=company,
        deps=deps,
        include_services=True,
        step="handle_service_information",
    )
