from __future__ import annotations
from typing import Iterable, List, Dict, Any

from django.conf import settings
import os

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

try:
    from langchain_community.vectorstores import Chroma
except Exception:  # pragma: no cover
    Chroma = None  # type: ignore

try:
    from langchain_openai import OpenAIEmbeddings  # type: ignore
except Exception:  # pragma: no cover
    OpenAIEmbeddings = None  # type: ignore

try:
    from langchain_google_genai import GoogleGenerativeAIEmbeddings  # type: ignore
except Exception:  # pragma: no cover
    GoogleGenerativeAIEmbeddings = None  # type: ignore


from apps.core.models import Company, FAQ
from apps.ai.retrieval.arabic_preprocess import normalize_arabic
from apps.ai.retrieval.chroma_store import get_vectorstore, collection_name



def handle_faq_questions(data, company_id):
    docs: List[Document] = []
    ids: List[str] = []
    if isinstance(data, list):
        for i, item in enumerate(data):
            q = (item.question or "").strip()
            a = (item.answer or "").strip()
            informal_answer = (item.informal_answer or "").strip()
            
            content = f"سؤال: {q}\nإجابة: {a}"
            if informal_answer:
                content += f"\nإجابة اخري: {informal_answer}"
            
            docs.append(Document(page_content=content, metadata={"source": "faq", "company_id": str(company_id), "faq_id": str(item.id), "category": item.category or "", "tags": item.tags or "", "example_dialogue": item.example_dialogue or "", "rag_tips": item.rag_tips or "", "row": i}))
            ids.append(f"faq:{item.id}")
    return docs, ids



def upsert_faqs(company, faq_records):
    """Upsert FAQs into Chroma collection for the company, replacing existing vectors for those IDs."""
    try:
        raw_docs, ids = handle_faq_questions(faq_records, company.id)
        if not raw_docs:
            raise Exception("No KB documents found (supporting CSV and JSON with question/answer fields).")

        # Normalize content for better Arabic retrieval
        for d in raw_docs:
            d.page_content = normalize_arabic(d.page_content)

        splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=50)
        chunks = splitter.split_documents(raw_docs)

        if ids:
            try:
                vs.delete(ids=ids)
            except Exception as e:
                print(e)

        vs = get_vectorstore(company)
        vs.add_documents(chunks)

        return {"upserted": len(ids), "collection": collection_name(company)}
    except Exception as e:
        print(e)
        raise e


def upsert_company_info(company_id):
    """Upsert company info into Chroma collection for the company, replacing existing vectors for those IDs."""
    try:
        company = Company.objects.get(id=company_id)
        data = company.get_company_info()
        
        docs = [
            Document(page_content=data, metadata={"source": "company_info", "company_info_id": str(company_id)})
            ]

        if not docs:
            raise Exception("No KB documents found (supporting CSV and JSON with question/answer fields).")

        # Normalize content for better Arabic retrieval
        for d in docs:
            d.page_content = normalize_arabic(d.page_content)

        splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)
        chunks = splitter.split_documents(docs)

        vs = get_vectorstore(company)
        
        vs.delete(where={'company_info_id': str(company_id)})

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


