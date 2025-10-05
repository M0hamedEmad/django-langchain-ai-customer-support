from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document


from apps.ai.retrieval.chroma_store import get_vectorstore, collection_name
from apps.ai.retrieval.arabic_preprocess import normalize_arabic

from apps.core.models import Company

def handle_faq_questions(data, company_id):
    docs: List[Document] = []
    ids: List[str] = []
    if isinstance(data, list):
        for i, item in enumerate(data):
            q = (item.get("question") or "").strip()
            a = (item.get("answer") or "").strip()
            informal_answer = (item.get("informal_answer") or "").strip()
            
            content = f"سؤال: {q}\nإجابة: {a}"
            if informal_answer:
                content += f"\nإجابة اخري: {informal_answer}"
            
            docs.append(Document(page_content=content, metadata={"question": q, "answer": a, "source": "faq", "company_id": str(company_id), "faq_id": str(item.get("id", "")), "category": item.get("category", ""), "tags": item.get("tags", ""), "example_dialogue": item.get("example_dialogue", ""), "rag_tips": item.get("rag_tips", ""), "row": i, "json_faq_id": str(item.get("json_faq_id", ""))}))
            ids.append(f"faq:{item.get("id", "")}")
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
                vs.delete(where={"$and": [
                {"company_id": str(company.id)},
                {"faq_id": {"$in": ids}}
                ]})
            except Exception as e:
                print(e)

        vs = get_vectorstore(company)
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
        d = vs.delete(where={"$and": [
                {"company_id": str(company.id)},
                {"faq_id": {"$in": faq_id}}
                ]})
        print(f"Deleted {len(faq_id)} FAQs for company {company.id} - {d}")
        return {"deleted": len(faq_id), "collection": collection_name(company)}
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
        
        vs.delete(where={"$and": [
                {"company_info_id": str(company_id)},
                {"source": "company_info"}
                ]}
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


