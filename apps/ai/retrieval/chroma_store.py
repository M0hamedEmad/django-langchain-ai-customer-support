import os
from typing import Any

from django.conf import settings
from langchain_community.vectorstores import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_openai import OpenAIEmbeddings

from apps.core.models import Company


def collection_name(company: Company) -> str:
    return f"company_{company.id}"


def get_embeddings() -> Any:
    provider = (
        getattr(settings, "LLM_PROVIDER", os.getenv("LLM_PROVIDER", "gemini"))
        or "gemini"
    ).lower()

    if (
        provider in ("gemini", "google", "google-genai", "deepseek")
        and GoogleGenerativeAIEmbeddings is not None
    ):
        # Prefer configurable embeddings model; default to text-embedding-004
        model_name = os.getenv("GOOGLE_EMBEDDINGS_MODEL", "models/gemini-embedding-001")
        if not os.getenv("GOOGLE_API_KEY"):
            raise RuntimeError("GOOGLE_API_KEY not set in environment")
        return GoogleGenerativeAIEmbeddings(model=model_name)

    # default to OpenAI
    return OpenAIEmbeddings(model="text-embedding-3-large")


def get_vectorstore(company: Company):
    embeddings = get_embeddings()
    vs = Chroma(
        collection_name=collection_name(company),
        embedding_function=embeddings,
        persist_directory=getattr(settings, "CHROMA_DB_DIR", ".chroma"),
    )
    return vs


def get_retriever(company: Company, top_k: int = 5):
    vs = get_vectorstore(company)
    return vs.as_retriever(search_kwargs={"k": top_k})
