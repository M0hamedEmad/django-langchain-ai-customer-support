"""Thin chatbot shell: graph wiring + entrypoints over nodes/ and services/.

Node logic lives in :mod:`apps.ai.nodes` (pure ``(state, *, company, deps)``
functions); shared resources come from :mod:`apps.ai.services`. These methods
exist only so the LangGraph wiring below keeps working unchanged until P3-4
moves it into :mod:`apps.ai.graph`.
"""

import logging
from datetime import datetime
from typing import Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from apps.ai.nodes import booking as booking_nodes
from apps.ai.nodes import complaint, inquiry, intake, response
from apps.ai.prompts import (
    build_booking_confirm_prompt,
    build_intent_classifier_prompt,
    build_response_generator_prompt,
    build_service_matching_prompt,
)
from apps.ai.services import get_deps
from apps.ai.state import ConversationState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CustomerServiceChatbot:
    """Advanced customer-service chatbot (LangGraph)."""

    def __init__(self, company=None):
        self.company = company

        # Heavy resources (LLMs, vector store, catalog snapshot) are shared
        # per company via services.cache; only graph compilation stays local
        # until P3-4. hardness is copied, never shared: nodes mutate it.
        self.deps = get_deps(company)
        self.llm = self.deps.llm
        self.pm_llm = self.deps.pm_llm
        self.vectorstore = self.deps.vectorstore
        self.services_db = self.deps.services_qs
        self.services_info = self.deps.services_info
        self.hardness = self.deps.hardness

        self.setup_templates()

        self.setup_conversation_graph()

    def setup_templates(self):
        # Prompt copy lives in apps.ai.prompts (Arabic product language).
        self.intent_classifier_template = build_intent_classifier_prompt()
        self.response_generator_template = build_response_generator_prompt()
        self.matching_prompt = build_service_matching_prompt()
        self.booking_confirm_prompt = build_booking_confirm_prompt()

    def setup_conversation_graph(self):
        """
        Build a LangGraph StateGraph using the node functions.
        Some nodes require company/conversation context, supplied via closures.
        """
        workflow = StateGraph(ConversationState)

        workflow.add_node("receive_message", self.receive_message)
        workflow.add_node("analyze_intent", self.analyze_intent)

        workflow.add_node("handle_general_inquiry", self.handle_general_inquiry)

        workflow.add_node("handle_service_booking", self.handle_service_booking)
        workflow.add_node("confirm_booking", self.confirm_booking)
        workflow.add_node("execute_create_booking", self.execute_create_booking)

        workflow.add_node("handle_service_information", self.handle_service_information)

        workflow.add_node(
            "handle_booking_modification", self.handle_booking_modification
        )
        workflow.add_node("handle_complaint", self.handle_complaint)
        workflow.add_node("clarify_intent", self.clarify_intent)

        workflow.add_node("generate_response", self.generate_response)

        workflow.set_entry_point("receive_message")
        workflow.add_edge("receive_message", "analyze_intent")

        workflow.add_conditional_edges(
            "analyze_intent",
            self.route_by_intent,
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
            self.route_after_collection,
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

        memory = MemorySaver()
        self.app = workflow.compile(checkpointer=memory)

        return self.app

    def generate_response(self, state: ConversationState) -> ConversationState:
        return response.generate_response(state, company=self.company, deps=self.deps)

    def receive_message(self, state: ConversationState) -> ConversationState:
        return intake.receive_message(state, company=self.company, deps=self.deps)

    def analyze_intent(self, state: ConversationState) -> ConversationState:
        return intake.analyze_intent(state, company=self.company, deps=self.deps)

    def handle_general_inquiry(self, state: ConversationState) -> ConversationState:
        return inquiry.handle_general_inquiry(state, company=self.company, deps=self.deps)

    def handle_service_information(self, state: ConversationState) -> ConversationState:
        return inquiry.handle_service_information(
            state, company=self.company, deps=self.deps
        )

    def handle_service_booking(self, state: ConversationState) -> ConversationState:
        return booking_nodes.handle_service_booking(
            state, company=self.company, deps=self.deps
        )

    def confirm_booking(self, state: ConversationState) -> ConversationState:
        return booking_nodes.confirm_booking(state, company=self.company, deps=self.deps)

    def execute_create_booking(self, state: ConversationState) -> ConversationState:
        return booking_nodes.execute_create_booking(
            state, company=self.company, deps=self.deps
        )

    def handle_complaint(self, state: ConversationState) -> ConversationState:
        return complaint.handle_complaint(state, company=self.company, deps=self.deps)

    def clarify_intent(self, state: ConversationState) -> ConversationState:
        return complaint.clarify_intent(state, company=self.company, deps=self.deps)

    def route_by_intent(self, state: ConversationState) -> str:
        return intake.route_by_intent(state, company=self.company, deps=self.deps)

    def route_general_inquiry(self, state):
        return intake.route_general_inquiry(state, company=self.company, deps=self.deps)

    def route_service_booking(self, state):
        return intake.route_service_booking(state, company=self.company, deps=self.deps)

    def route_after_collection(self, state):
        return intake.route_after_collection(state, company=self.company, deps=self.deps)

    def handle_booking_modification(self, state: ConversationState):
        return booking_nodes.handle_booking_modification(
            state, company=self.company, deps=self.deps
        )

    def analyze_request(self, state: ConversationState) -> ConversationState:
        return booking_nodes.analyze_request(state, company=self.company, deps=self.deps)

    def handle_message(
        self,
        message: str,
        session_id: str,
        customer_id: Optional[str] = None,
        init_state: Optional[ConversationState] = None,
    ) -> str:
        """Handle a new incoming message."""
        try:
            # Initialize state
            config = {"configurable": {"thread_id": session_id}}

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
            result = self.app.invoke(init_state or current_state, config)
            return result

        except Exception as e:
            import traceback

            logger.error("Failed to process message: %s\n%s", e, traceback.format_exc())
            return "عذراً، حدث خطأ تقني. يرجى المحاولة مرة أخرى لاحقاً."


def handle_chat(message, session_id, customer_id, company, init_state=None):
    """
    Minimal orchestrator that mimics the LangGraph flow described in ARCHITECTURE.md.
    It executes nodes in sequence with conditional routing.

    Later this can be replaced with a real LangGraph StateGraph app.
    """
    try:
        chatbot = CustomerServiceChatbot(company=company)

        final_state = chatbot.handle_message(
            message, session_id, customer_id, init_state=init_state
        )
        return final_state  # includes answer/debug/intent/booking
    except Exception as e:  # safety net
        logger.exception("handle_chat failed")
        return e
