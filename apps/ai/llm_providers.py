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
        return ChatOpenAI(
        api_key="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",
        base_url="https://openrouter.ai/api/v1",
        model=model_name or "deepseek/deepseek-chat-v3.1:free",
        temperature=0.3
        )

    # Default fallback
    if ChatOpenAI is None:
        raise RuntimeError("No LLM provider available")
    return ChatOpenAI(model=model_name, temperature=0.3)
