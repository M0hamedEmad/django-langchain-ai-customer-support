"""Vector-sync outbox: enqueue from model saves, drain via `process_outbox`.

Jobs are idempotent by construction (Chroma upserts/deletes keyed on stable
ids), so an overlapping worker run can at worst repeat work, never corrupt.
Run a single worker in production.
"""

from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def enqueue_vector_sync(company, kind: str, ref_id: int, op: str = "upsert"):
    """Coalesce repeated saves into one pending row. Never raises."""
    from apps.core.models import VectorSyncJob

    try:
        with transaction.atomic():
            job, created = VectorSyncJob.objects.get_or_create(
                company=company,
                kind=kind,
                ref_id=ref_id,
                status=VectorSyncJob.Status.PENDING,
                defaults={"op": op},
            )
            if not created and job.op != op:
                # A delete supersedes a queued upsert for the same ref.
                job.op = op
                job.save(update_fields=["op", "updated_at"])
            return job
    except Exception:
        logger.warning(
            "VectorSync enqueue failed for %s/%s ref=%s", kind, op, ref_id,
            exc_info=True,
        )
        return None


def process_one(job) -> bool:
    """Execute one job; returns True on success. Never raises."""
    from apps.core.models import JSONFAQ, VectorSyncJob
    from apps.ingestion import etl

    try:
        if job.kind == VectorSyncJob.Kind.COMPANY_INFO:
            etl.upsert_company_info(job.ref_id)
        elif job.kind == VectorSyncJob.Kind.JSON_FAQ:
            if job.op == VectorSyncJob.Op.DELETE:
                etl.delete_json_faq(job.company, job.ref_id)
            else:
                faq = JSONFAQ.objects.filter(pk=job.ref_id).first()
                if faq is None:
                    logger.warning("VectorSync job %s: ref gone, skipping", job.pk)
                else:
                    etl.delete_json_faq(job.company, faq.pk)
                    docs = _json_faq_docs(faq)
                    if docs:
                        etl.upsert_faqs(job.company, docs)
        else:
            raise ValueError(f"Unknown vector job kind: {job.kind}")
        return True
    except Exception as e:
        logger.warning("VectorSync job %s failed: %s", job.pk, e, exc_info=True)
        job.attempts += 1
        job.last_error = str(e)[:2000]
        job.status = VectorSyncJob.Status.FAILED
        job.save(update_fields=["attempts", "last_error", "status", "updated_at"])
        return False


def _json_faq_docs(faq) -> list:
    """Build stable-id ETL dicts from a JSONFAQ row (mirrors save contract)."""
    items = faq.data
    if isinstance(items, dict):
        items = items.get("faqs", [])
    items = [o for o in (items or []) if isinstance(o, dict)]
    docs = []
    for idx, obj in enumerate(items):
        docs.append({
            "id": f"json:{faq.pk}:{idx}",
            "question": obj.get("question") or "",
            "answer": obj.get("answer") or "",
            "informal_answer": obj.get("informal_answer", ""),
            "category": obj.get("category", ""),
            "tags": obj.get("tags", ""),
            "example_dialogue": obj.get("example_dialogue", ""),
            "rag_tips": obj.get("rag_tips", ""),
            "json_faq_id": str(faq.pk),
        })
    return docs


def process_pending(limit: int | None = None) -> dict:
    """Claim pending jobs oldest-first and run them. Returns a summary."""
    from apps.core.models import VectorSyncJob

    done = failed = 0
    qs = VectorSyncJob.objects.filter(
        status=VectorSyncJob.Status.PENDING
    ).order_by("created_at", "pk")
    if limit is not None:
        qs = qs[:limit]
    for job in qs:
        # Claim inside its own transaction so overlapping runs rarely collide.
        claimed = VectorSyncJob.objects.filter(
            pk=job.pk, status=VectorSyncJob.Status.PENDING
        ).update(status=VectorSyncJob.Status.PROCESSING)
        if not claimed:
            continue
        job.status = VectorSyncJob.Status.PROCESSING
        if process_one(job):
            VectorSyncJob.objects.filter(pk=job.pk).update(
                status=VectorSyncJob.Status.DONE
            )
            done += 1
        else:
            failed += 1
    return {"done": done, "failed": failed}
