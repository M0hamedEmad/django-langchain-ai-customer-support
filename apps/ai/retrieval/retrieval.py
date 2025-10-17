from __future__ import annotations

from functools import lru_cache
from typing import Any

try:
    from langchain_community.docstore.document import Document
    from langchain_community.retrievers import BM25Retriever
    from langchain_community.vectorstores import Chroma
except Exception:  # pragma: no cover
    Chroma = None  # type: ignore
    BM25Retriever = None  # type: ignore
    Document = None  # type: ignore

from apps.core.models import FAQ, Company
from apps.ingestion.etl import get_vectorstore


@lru_cache(maxsize=32)
def _bm25_corpus_stats(company_id: int) -> tuple[int, list[dict[str, Any]]]:
    """Cache the raw corpus for BM25 (count + items). Invalidates when count changes."""
    qs = FAQ.objects.filter(company_id=company_id).only(
        "id", "question", "answer", "category", "tags"
    )
    items: list[dict[str, Any]] = []
    for f in qs:
        content = f"سؤال: {f.question}\nإجابة: {f.answer}"
        items.append(
            {
                "id": str(f.id),
                "text": content,
                "metadata": {
                    "company_id": str(company_id),
                    "faq_id": str(f.id),
                    "category": f.category or "",
                    "tags": f.tags or [],
                    "source": "faq",
                },
            }
        )
    return (qs.count(), items)


def _get_bm25_retriever(company: Company):
    if BM25Retriever is None:
        return None, 0
    count, items = _bm25_corpus_stats(company.id)
    texts = [i["text"] for i in items]
    metadatas = [i["metadata"] for i in items]
    retriever = BM25Retriever.from_texts(texts=texts, metadatas=metadatas)
    retriever.k = 10
    return retriever, count


def better_retrieve(
    company: Company, query: str, *, top_k: int = 6, fetch_k: int = 24
) -> list[dict[str, Any]]:
    """Hybrid retrieval: vector similarity + BM25, with simple score fusion.
    Returns a list of {id, score, metadata, text} sorted by score desc.
    """
    results: list[dict[str, Any]] = []

    # Vector search using Chroma (with scores)
    try:
        vs = get_vectorstore(company)
        vec_hits = vs.similarity_search_with_score(query, k=fetch_k)
    except Exception:
        vec_hits = []

    vec_map: dict[str, float] = {}
    vec_meta: dict[str, dict[str, Any]] = {}
    vec_text: dict[str, str] = {}
    for doc, score in vec_hits:
        fid = doc.metadata.get("faq_id") or doc.metadata.get("id") or ""
        if not fid:
            continue
        # Convert distance-like score to affinity (smaller distance -> higher score)
        affinity = 1.0 / (1.0 + float(score))
        vec_map[fid] = max(vec_map.get(fid, 0.0), affinity)
        vec_meta[fid] = doc.metadata
        vec_text[fid] = doc.page_content

    # BM25 retrieval on FAQ corpus
    bm25_rank: dict[str, int] = {}
    try:
        retriever, count = _get_bm25_retriever(company)
        if retriever is not None:
            bm25_docs: list[Document] = retriever.get_relevant_documents(query)  # type: ignore
            for idx, doc in enumerate(bm25_docs):
                fid = (doc.metadata or {}).get("faq_id") or ""
                if not fid:
                    continue
                if fid not in bm25_rank:
                    bm25_rank[fid] = idx
                if fid not in vec_meta:  # fill in text/meta if vector search missed it
                    vec_meta[fid] = doc.metadata or {}
                    vec_text[fid] = doc.page_content
    except Exception:
        pass

    # Score fusion
    fused: list[tuple[str, float]] = []
    all_ids = set(vec_map.keys()) | set(bm25_rank.keys())
    for fid in all_ids:
        v = vec_map.get(fid, 0.0)
        r = bm25_rank.get(fid)
        rscore = 0.0 if r is None else 1.0 / (1.0 + r)
        score = 0.7 * v + 0.3 * rscore
        fused.append((fid, score))

    fused.sort(key=lambda x: x[1], reverse=True)
    for fid, score in fused[:top_k]:
        results.append(
            {
                "id": fid,
                "score": score,
                "metadata": vec_meta.get(fid, {"faq_id": fid}),
                "text": vec_text.get(fid, ""),
            }
        )

    return results
