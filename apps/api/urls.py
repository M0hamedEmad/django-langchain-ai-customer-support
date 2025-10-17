from django.urls import path

from . import health, views, whatsapp_webhook

urlpatterns = [
    path("healthz", health.HealthCheckView.as_view(), name="healthz"),
    path("readyz", health.ReadinessCheckView.as_view(), name="readyz"),
    path("chat/stream", views.ChatStreamView.as_view(), name="chat-stream"),
    path("services", views.ServicesView.as_view(), name="services"),
    path(
        "knowledge/faq/bulk_upsert",
        views.FAQBulkUpsertView.as_view(),
        name="faq-bulk-upsert",
    ),
    path(
        "knowledge/faq/reindex", views.FAQReindexAllView.as_view(), name="faq-reindex"
    ),
    path(
        "conversations/<str:session_id>/messages/",
        views.ConversationMessagesView.as_view(),
        name="conversation-messages",
    ),
    path(
        "integrations/whatsapp/webhook",
        whatsapp_webhook.WhatsAppWebhookView.as_view(),
        name="whatsapp-webhook",
    ),
]
