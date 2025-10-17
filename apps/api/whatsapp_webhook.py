"""WhatsApp inbound webhook: validate, store idempotently, reply 200 fast.

AI processing happens asynchronously in the `process_inbox` worker, never in
the webhook request. Retried gateway deliveries are free: `message_id` is
unique, so a redelivery returns ``{"status": "duplicate"}`` without new rows.

Accepted payloads (gateway-agnostic):
  simple: {"message_id": ..., "phone_number": ..., "message_body": ...,
           "sender_name"?: ..., "timestamp"?: ...}
  raw gateway shape: {"key": {"id", "remoteJid", "fromMe"},
                      "content": {"conversation"}, "messageTimestamp"}

Auth: `X-Company-Key` (401 like the rest of the API). If
`WHATSAPP_WEBHOOK_SECRET` is set, the same value must arrive as
`X-Webhook-Secret` (403 otherwise).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Tuple

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.views import _get_company_from_request
from apps.core.models import WhatsAppMessage

logger = logging.getLogger(__name__)


def normalize_payload(data: Dict[str, Any]) -> Tuple[str, str, str, str, int] | None:
    """Return (message_id, phone, body, sender, timestamp) or None if invalid."""
    if not isinstance(data, dict):
        return None
    if "message_id" in data or "message_body" in data:
        message_id = str(data.get("message_id") or "").strip()
        phone = str(data.get("phone_number") or "").strip().lstrip("+")
        body = str(data.get("message_body") or "").strip()
        sender = str(data.get("sender_name") or "").strip()
        timestamp = data.get("timestamp") or 0
    else:
        key = data.get("key") or {}
        content = data.get("content") or {}
        message_id = str(key.get("id") or "").strip()
        sender = str(key.get("remoteJid") or "").strip()
        phone = sender.lstrip("+")
        body = str(content.get("conversation") or "").strip()
        timestamp = data.get("messageTimestamp", 0)
    try:
        timestamp = int(timestamp)
    except (TypeError, ValueError):
        timestamp = 0
    if not message_id or not phone or not body:
        return None
    return message_id, phone, body, sender, timestamp


class WhatsAppWebhookView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args: Any, **kwargs: Any):
        company = _get_company_from_request(request)
        if not company:
            return Response(
                {"detail": "شركة غير معروفة. تأكد من المفتاح."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        expected = os.getenv("WHATSAPP_WEBHOOK_SECRET") or ""
        if expected:
            provided = request.headers.get("X-Webhook-Secret") or request.META.get(
                "HTTP_X_WEBHOOK_SECRET", ""
            )
            if provided != expected:
                return Response(
                    {"detail": "Invalid webhook secret."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        parsed = normalize_payload(request.data)
        if parsed is None:
            return Response(
                {"detail": "صيغة غير صحيحة. message_id و phone_number و message_body مطلوبة."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        message_id, phone, body, sender, timestamp = parsed

        _, created = WhatsAppMessage.objects.get_or_create(
            message_id=message_id,
            defaults={
                "company": company,
                "phone_number": phone,
                "sender_name": sender,
                "message_body": body,
                "timestamp": timestamp,
            },
        )
        if not created:
            return Response({"status": "duplicate"}, status=status.HTTP_200_OK)
        return Response({"status": "queued"}, status=status.HTTP_201_CREATED)
