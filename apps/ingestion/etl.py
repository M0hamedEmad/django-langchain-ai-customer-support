from __future__ import annotations

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from apps.ai.retrieval.arabic_preprocess import normalize_arabic
from apps.ai.retrieval.chroma_store import collection_name, get_vectorstore
from apps.core.models import Company


def _field(item, key: str, default=""):
    """Read dict keys and model attributes through one accessor."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _as_faq_dict(item, index: int) -> dict:
    """Accept API dicts and FAQ model instances (bulk/reindex pass models)."""

    def text(key: str) -> str:
        return str(_field(item, key, "") or "").strip()

    tags = _field(item, "tags", "")
    if isinstance(tags, (list, tuple)):
        tags = ",".join(str(t) for t in tags)

    return {
        "id": _field(item, "id", ""),
        "question": text("question"),
        "answer": text("answer"),
        "informal_answer": text("informal_answer"),
        "category": _field(item, "category", "") or "",
        "tags": tags,
        "example_dialogue": _field(item, "example_dialogue", "") or "",
        "rag_tips": _field(item, "rag_tips", "") or "",
        "json_faq_id": str(_field(item, "json_faq_id", "")),
        "row": index,
    }


def handle_faq_questions(data, company_id):
    docs: list[Document] = []
    ids: list[str] = []
    if isinstance(data, list):
        for i, raw in enumerate(data):
            item = _as_faq_dict(raw, i)
            q = item["question"]
            a = item["answer"]
            informal_answer = item["informal_answer"]

            content = f"سؤال: {q}\nإجابة: {a}"
            if informal_answer:
                content += f"\nإجابة اخري: {informal_answer}"

            docs.append(
                Document(
                    page_content=content,
                    metadata={
                        "question": q,
                        "answer": a,
                        "source": "faq",
                        "company_id": str(company_id),
                        "faq_id": str(item["id"]),
                        "category": item["category"],
                        "tags": item["tags"],
                        "example_dialogue": item["example_dialogue"],
                        "rag_tips": item["rag_tips"],
                        "row": i,
                        "json_faq_id": item["json_faq_id"],
                    },
                )
            )
            ids.append(f"faq:{item['id']}")
    return docs, ids


def upsert_faqs(company, faq_records):
    """Upsert FAQs into Chroma collection for the company, replacing existing vectors for those IDs."""
    try:
        raw_docs, ids = handle_faq_questions(faq_records, company.id)
        if not raw_docs:
            raise Exception(
                "No KB documents found (supporting CSV and JSON with question/answer fields)."
            )

        # Normalize content for better Arabic retrieval
        for d in raw_docs:
            d.page_content = normalize_arabic(d.page_content)

        splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=50)
        chunks = splitter.split_documents(raw_docs)

        vs = get_vectorstore(company)

        if ids:
            try:
                vs.delete(
                    where={
                        "$and": [
                            {"company_id": str(company.id)},
                            {"faq_id": {"$in": ids}},
                        ]
                    }
                )
            except Exception as e:
                print(e)

        vs.add_documents(chunks)
        print(f"Upserted {len(ids)} FAQs for company {company.id}")
        return {"upserted": len(ids), "collection": collection_name(company)}
    except Exception as e:
        print(e)
        raise e


def delete_faq_id(company, faq_id):
    """Upsert FAQs into Chroma collection for the company, replacing existing vectors for those IDs."""
    try:
        vs = get_vectorstore(company)
        d = vs.delete(
            where={
                "$and": [{"company_id": str(company.id)}, {"faq_id": {"$in": faq_id}}]
            }
        )
        print(f"Deleted {len(faq_id)} FAQs for company {company.id} - {d}")
        return {"deleted": len(faq_id), "collection": collection_name(company)}
    except Exception as e:
        print(e)
        raise e


def delete_json_faq(company, json_faq_pk):
    """Delete all vectors sourced from one JSONFAQ record (by json_faq_id)."""
    try:
        vs = get_vectorstore(company)
        d = vs.delete(where={"json_faq_id": str(json_faq_pk)})
        print(f"Deleted JSONFAQ {json_faq_pk} vectors for company {company.id} - {d}")
        return {"deleted_json_faq": json_faq_pk, "collection": collection_name(company)}
    except Exception as e:
        print(e)
        raise e


def upsert_company_info(company_id):
    """Upsert company info into Chroma collection for the company, replacing existing vectors for those IDs."""
    try:
        company = Company.objects.get(id=company_id)
        data = company.get_company_info()

        docs = [
            Document(
                page_content=data,
                metadata={"source": "company_info", "company_info_id": str(company_id)},
            )
        ]

        if not docs:
            raise Exception(
                "No KB documents found (supporting CSV and JSON with question/answer fields)."
            )

        # Normalize content for better Arabic retrieval
        for d in docs:
            d.page_content = normalize_arabic(d.page_content)

        splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)
        chunks = splitter.split_documents(docs)

        vs = get_vectorstore(company)

        vs.delete(
            where={
                "$and": [
                    {"company_info_id": str(company_id)},
                    {"source": "company_info"},
                ]
            }
        )

        vs.add_documents(chunks)

        return {"upserted": len(chunks), "collection": collection_name(company)}
    except Exception as e:
        print(e)
        raise e


# def upsert_faqs(company: Company, faq_records: Iterable[FAQ]) -> Dict[str, Any]:
#     """Upsert FAQs into Chroma collection for the company, replacing existing vectors for those IDs."""
#     vs = get_vectorstore(company)
#     ids: List[str] = []
#     texts: List[str] = []
#     metadatas: List[Dict[str, Any]] = []

#     for faq in faq_records:
#         _id = f"faq:{faq.id}"
#         ids.append(_id)
#         # Combine question + answer as content; answer is the ground truth.
#         content = f"سؤال: {faq.question}\nإجابة: {faq.answer}"
#         texts.append(content)
#         metadatas.append({
#             "company_id": str(company.id),
#             "faq_id": str(faq.id),
#             "category": faq.category or "",
#             "tags": faq.tags or [],
#             "source": "faq",
#         })

#     # delete old vectors by ids, then add updated
#     if ids:
#         try:
#             vs.delete(ids=ids)
#         except Exception:
#             # ignore if not existing
#             pass
#         vs.add_texts(texts=texts, metadatas=metadatas, ids=ids)
#         try:
#             vs.persist()
#         except Exception:
#             pass

#     return {"upserted": len(ids), "collection": collection_name(company)}
