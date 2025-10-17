"""ETL pure builders + outbox lifecycle (vector backend mocked)."""

from unittest.mock import patch

from apps.core.models import JSONFAQ, VectorSyncJob
from apps.ingestion.etl import handle_faq_questions


def test_faq_ids_stable():
    docs, ids = handle_faq_questions(
        [{"id": 7, "question": "q?", "answer": "a!", "category": "c"}], 1
    )
    assert ids == ["faq:7"]
    assert docs[0].metadata["faq_id"] == "7"
    assert "سؤال: q?" in docs[0].page_content


def test_faq_model_instances_and_list_tags():
    class FakeFAQ:
        id = 9
        question = "q?"
        answer = "a!"
        informal_answer = ""
        category = None
        tags = ["x", "y"]
        example_dialogue = ""
        rag_tips = ""
        json_faq_id = ""

    docs, ids = handle_faq_questions([FakeFAQ()], 1)
    assert ids == ["faq:9"]
    assert docs[0].metadata["tags"] == "x,y"
    assert docs[0].metadata["category"] == ""
    assert all(isinstance(v, (str, int)) for v in docs[0].metadata.values())


def test_outbox_coalesces_and_processes(db, company):
    jf = JSONFAQ.objects.create(
        company=company, name="j", data=[{"question": "q?", "answer": "a!"}]
    )
    jf.save()
    assert VectorSyncJob.objects.filter(kind="json_faq", status="pending").count() == 1

    calls = {}
    with (
        patch(
            "apps.ingestion.etl.delete_json_faq",
            side_effect=lambda c, pk: calls.setdefault("del", pk),
        ),
        patch(
            "apps.ingestion.etl.upsert_faqs",
            side_effect=lambda c, docs: calls.setdefault("docs", docs),
        ),
        patch("apps.ingestion.etl.upsert_company_info"),
    ):
        from apps.ingestion.outbox import process_pending

        assert process_pending() == {"done": 2, "failed": 0}
    assert calls["docs"][0]["id"] == f"json:{jf.pk}:0"
    assert VectorSyncJob.objects.filter(status="done").count() == 2


def test_outbox_failure_keeps_row(db, company):
    with patch(
        "apps.ingestion.etl.upsert_company_info",
        side_effect=RuntimeError("dead backend"),
    ):
        from apps.ingestion.outbox import process_pending

        assert process_pending() == {"done": 0, "failed": 1}
    job = VectorSyncJob.objects.get(kind="company_info")
    assert job.status == "failed" and job.attempts == 1 and job.last_error
    assert company.__class__.objects.filter(pk=company.pk).exists()
