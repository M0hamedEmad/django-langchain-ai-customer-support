"""API contracts: auth, validation, idempotency, webhook shapes."""

from unittest.mock import patch

from django.test import Client

from apps.core.models import Conversation, Customer, Message

client = Client()


def test_services_requires_key():
    assert client.get("/api/v1/services").status_code == 401


def test_chat_requires_message(api_key):
    response = client.post(
        "/api/v1/chat/stream",
        data={"session_id": "s"},
        content_type="application/json",
        **api_key,
    )
    assert response.status_code == 400


def test_chat_requires_phone(api_key):
    response = client.post(
        "/api/v1/chat/stream",
        data={"session_id": "s", "message": "hi"},
        content_type="application/json",
        **api_key,
    )
    assert response.status_code == 400
    assert "الهاتف" in response.json()["detail"]


def test_chat_success_and_retry_idempotent(api_key, company):
    payload = {"session_id": "s1", "message": "hello", "customer": {"phone": "7000"}}
    fake = {"messages": [{"role": "assistant", "content": "reply"}]}
    with patch("apps.api.views.handle_chat", return_value=fake):
        first = client.post(
            "/api/v1/chat/stream",
            data=payload,
            content_type="application/json",
            **api_key,
        )
        second = client.post(
            "/api/v1/chat/stream",
            data=payload,
            content_type="application/json",
            **api_key,
        )
    assert first.json() == {"message": "reply"}
    assert second.json() == {"message": "reply"}
    conv = Conversation.objects.get(company=company, session_id="s1")
    assert Message.objects.filter(conversation=conv, role="user").count() == 1
    assert Message.objects.filter(conversation=conv, role="assistant").count() == 1


def test_chat_pipeline_failure_is_502(api_key):
    payload = {"session_id": "s2", "message": "hi", "customer": {"phone": "7001"}}
    with patch("apps.api.views.handle_chat", return_value=Exception("down")):
        response = client.post(
            "/api/v1/chat/stream",
            data=payload,
            content_type="application/json",
            **api_key,
        )
    assert response.status_code == 502


def test_conversation_messages_scoping(api_key, company):
    customer = Customer.objects.create(company=company, phone="7002")
    conv = Conversation.objects.create(
        company=company, session_id="s3", customer=customer
    )
    Message.objects.create(conversation=conv, role="user", content="hi")

    response = client.get("/api/v1/conversations/s3/messages/", **api_key)
    assert [m["content"] for m in response.json()["messages"]] == ["hi"]

    unknown = client.get(
        "/api/v1/conversations/s3/messages/?customer_id=000", **api_key
    )
    assert unknown.json()["messages"] == []

    missing = client.get("/api/v1/conversations/nope/messages/", **api_key)
    assert missing.json()["detail"] == "Conversation not found"


def test_webhook_cycle(api_key):
    payload = {"message_id": "w1", "phone_number": "20100", "message_body": "hello"}
    first = client.post(
        "/api/v1/integrations/whatsapp/webhook",
        data=payload,
        content_type="application/json",
        **api_key,
    )
    assert first.status_code == 201
    duplicate = client.post(
        "/api/v1/integrations/whatsapp/webhook",
        data=payload,
        content_type="application/json",
        **api_key,
    )
    assert duplicate.json() == {"status": "duplicate"}
    bad = client.post(
        "/api/v1/integrations/whatsapp/webhook",
        data={"message_id": "w2"},
        content_type="application/json",
        **api_key,
    )
    assert bad.status_code == 400


def test_health_endpoints(db):
    assert client.get("/api/v1/healthz").json() == {"status": "ok"}
    ready = client.get("/api/v1/readyz")
    assert ready.status_code == 200 and ready.json()["status"] == "ready"
    assert "X-Request-ID" in ready


def test_readyz_db_down(db):
    from unittest.mock import patch as _patch

    from django.db.utils import OperationalError

    with _patch(
        "django.db.backends.sqlite3.base.DatabaseWrapper.cursor",
        side_effect=OperationalError("down"),
    ):
        response = client.get("/api/v1/readyz")
    assert response.status_code == 503
    assert response.json()["status"] == "not-ready"


def test_anonymous_throttle(db, monkeypatch):
    from django.core.cache import cache
    from rest_framework.throttling import AnonRateThrottle

    # NOTE: DRF binds THROTTLE_RATES as a class attribute at import, so
    # override_settings(REST_FRAMEWORK=...) cannot change the rate in-process.
    # Patch the mapping itself (auto-reverted) to prove the 429 plumbing.
    cache.clear()  # throttle history is process-global in tests
    monkeypatch.setitem(AnonRateThrottle.THROTTLE_RATES, "anon", "3/min")
    codes = [client.get("/api/v1/healthz").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429
