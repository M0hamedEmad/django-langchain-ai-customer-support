"""Shared chatbot resources: per-company cached deps with signal invalidation."""

from apps.ai.services.cache import get_deps, invalidate_all, invalidate_company
from apps.ai.services.deps import ChatbotDeps, build_deps

__all__ = [
    "ChatbotDeps",
    "build_deps",
    "get_deps",
    "invalidate_all",
    "invalidate_company",
]
