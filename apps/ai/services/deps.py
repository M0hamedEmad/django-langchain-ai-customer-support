"""Per-company chatbot dependencies (LLMs, vector store, service catalog).

Built once per company and shared across requests; see ``cache.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from apps.ai.llm_providers import get_chat_model
from apps.ai.prompts import (
    build_booking_confirm_prompt,
    build_intent_classifier_prompt,
    build_response_generator_prompt,
    build_service_matching_prompt,
)
from apps.ai.retrieval.chroma_store import get_vectorstore
from apps.core.models import Service, WebSiteConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatbotDeps:
    """Expensive, shareable chatbot resources for one company.

    ``services_qs`` is an *unevaluated* queryset, so every ``.values()`` call
    still hits the database fresh. ``hardness`` is a starting value only:
    nodes mutate per-request hardness on the chatbot instance, never here.
    """

    llm: Any
    pm_llm: Any
    vectorstore: Any | None
    services_qs: Any
    services_info: str
    hardness: int = 5
    intent_classifier_template: Any = None
    response_generator_template: Any = None
    matching_prompt: Any = None
    booking_confirm_prompt: Any = None


def build_deps(company) -> ChatbotDeps:
    """Construct (never cached here) the deps for ``company``.

    Mirrors the old ``CustomerServiceChatbot.__init__`` failure semantics:
    LLM misconfiguration raises, vector-store failure degrades to ``None``.
    """
    web_config = WebSiteConfig.objects.filter().first()
    llm_provider = None
    llm_model = None
    p_llm_provider = None
    p_llm_model = None
    hardness = 5

    if web_config:
        llm_provider = web_config.llm_provider
        llm_model = web_config.get_llm_model()
        p_llm_provider = web_config.premium_llm_provider
        p_llm_model = web_config.get_pm_llm_model()
        hardness = web_config.hardness_score

    llm = get_chat_model(provider=llm_provider, model_name=llm_model)
    pm_llm = get_chat_model(provider=p_llm_provider, model_name=p_llm_model)

    try:
        vectorstore = get_vectorstore(company)
        logger.info("RAG system initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize RAG system: %s", e)
        vectorstore = None

    services_qs = Service.objects.filter(company=company, is_active=True)
    # iterator(): evaluate without populating the queryset cache, so the
    # stored services_qs keeps hitting the database fresh on later use.
    services_info = "\n".join(
        [
            f"id: {s.id}, name:{s.name}, price: {s.price}, description: {s.description}"
            for s in services_qs.iterator()
        ]
    )

    return ChatbotDeps(
        llm=llm,
        pm_llm=pm_llm,
        vectorstore=vectorstore,
        services_qs=services_qs,
        services_info=services_info,
        hardness=hardness,
        intent_classifier_template=build_intent_classifier_prompt(),
        response_generator_template=build_response_generator_prompt(),
        matching_prompt=build_service_matching_prompt(),
        booking_confirm_prompt=build_booking_confirm_prompt(),
    )
