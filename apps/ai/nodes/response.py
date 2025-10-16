"""Terminal node: render the final assistant reply from accumulated context."""

from __future__ import annotations

import logging
from datetime import datetime

from apps.ai.state import ConversationState

logger = logging.getLogger(__name__)


def generate_response(state: ConversationState, *, company, deps) -> ConversationState:
    if not state.get("messages"):
        return state

    query = state["original_message"]
    context = state.get("rag_context", "")
    additional_info = f"الخطوة الحالية: {state.get('current_step', 'غير محدد')}"
    info = company.get_company_general_info()

    try:
        prompt = deps.response_generator_template.format_messages(
            chat_history=state["conversation_history"],
            context=context,
            query=query,
            additional_info=additional_info,
            company_info=info,
            intent=state.get("current_intent", "غير محدد"),
            language=state.get("language", "ar"),
            current_step=state.get("current_step", "غير محدد"),
        )

        hardness = state.get("hardness", deps.hardness)
        if hardness > 4 or state["intent_confidence"] < 0.7:
            response = deps.pm_llm.invoke(prompt)
        else:
            response = deps.llm.invoke(prompt)

        # Append the reply to the conversation
        if "messages" not in state:
            state["messages"] = []

        state["messages"].append(
            {
                "role": "assistant",
                "content": response.content,
                "timestamp": datetime.now().isoformat(),
            }
        )

        logger.info("Response generated successfully")

    except Exception as e:
        logger.error("Failed to generate response: %s", e)
        error_response = (
            "عذراً، حدث خطأ تقني. يرجى المحاولة مرة أخرى أو التواصل مع فريق الدعم."
        )

        state["messages"].append(
            {
                "role": "assistant",
                "content": error_response,
                "timestamp": datetime.now().isoformat(),
            }
        )

    return state
