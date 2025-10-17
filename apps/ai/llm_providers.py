from __future__ import annotations

import os
from typing import Any

# Optional providers via LangChain wrappers
try:
    from langchain_openai import ChatOpenAI  # type: ignore
except Exception:  # pragma: no cover
    ChatOpenAI = None  # type: ignore

try:
    from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
except Exception:  # pragma: no cover
    ChatGoogleGenerativeAI = None  # type: ignore


def get_chat_model(provider: str | None = None, model_name: str | None = None) -> Any:
    provider = (provider or os.getenv("LLM_PROVIDER", "openai")).lower()
    # generic default; may be overridden per provider below
    model_name = model_name or os.getenv("LLM_MODEL", "gpt-4o-mini")

    if provider in ("openai", "gpt", "gpt4", "gpt-4o"):
        if ChatOpenAI is None:
            raise RuntimeError("langchain-openai not installed")
        return ChatOpenAI(model=model_name, temperature=0.3)

    if provider in ("gemini", "google", "google-genai"):
        if ChatGoogleGenerativeAI is None:
            raise RuntimeError("langchain-google-genai not installed")
        # Prefer explicit Google model env var; fallback to provided model_name if it's a Gemini model, else default
        gen_model = model_name or os.getenv("GOOGLE_GENAI_MODEL")
        return ChatGoogleGenerativeAI(model=gen_model, temperature=0.3)

    if provider in ("deepseek", "deep_seek"):
        if ChatOpenAI is None:
            raise RuntimeError("langchain-openai not installed")
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set in environment")
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        return ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name
            or os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-chat-v3.1:free"),
            temperature=0.3,
        )

    # Default fallback
    if ChatOpenAI is None:
        raise RuntimeError("No LLM provider available")
    return ChatOpenAI(model=model_name, temperature=0.3)
