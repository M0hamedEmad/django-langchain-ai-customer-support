"""Process-level cache of per-company chatbot deps.

Invalidation is signal-driven (see ``signals.py``): any ``WebSiteConfig``
change drops everything (the singleton config feeds all companies), while
``Service``/``Company`` writes drop only their company. Failures are never
cached, so a misconfigured company retries the build on the next request
instead of poisoning the cache.

Benign races only: two threads may build the same company twice; the last
write wins and both results are equivalent.
"""

from __future__ import annotations

from typing import Dict, Optional

from apps.ai.services.deps import ChatbotDeps, build_deps

_cache: Dict[object, ChatbotDeps] = {}


def _key(company) -> object:
    return getattr(company, "id", None)


def get_deps(company) -> ChatbotDeps:
    """Return cached deps for ``company``, building on first use."""
    key = _key(company)
    deps = _cache.get(key)
    if deps is None:
        deps = build_deps(company)
        _cache[key] = deps
    return deps


def invalidate_company(company_id: Optional[int]) -> None:
    _cache.pop(company_id, None)


def invalidate_all() -> None:
    _cache.clear()
