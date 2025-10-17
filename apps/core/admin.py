from django.contrib import admin

from .models import (
    FAQ,
    JSONFAQ,
    AuditLog,
    Booking,
    Company,
    Conversation,
    Customer,
    EscalationTicket,
    Message,
    Service,
    VectorSyncJob,
    WebSiteConfig,
    WhatsAppMessage,
)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("company", "name", "price", "duration_minutes", "is_active")
    list_filter = ("company", "is_active")

    fieldsets = (
        (None, {"fields": ("company", "name", "description", "price", "is_active")}),
    )


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("company", "name", "phone", "email")
    list_filter = ("company",)
    search_fields = ("name", "phone", "email")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("company", "service", "customer", "status", "date")
    list_filter = ("company", "status")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("company", "session_id", "status", "updated_at")
    list_filter = ("company", "status")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "content", "role", "created_at")
    list_filter = ("role",)


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = (
        "message_id",
        "company",
        "phone_number",
        "sender_name",
        "message_body",
        "timestamp",
        "received_at",
        "is_processed",
    )
    list_filter = ("company", "is_processed")


@admin.register(EscalationTicket)
class EscalationTicketAdmin(admin.ModelAdmin):
    list_display = ("company", "conversation", "priority", "status", "created_at")
    list_filter = ("company", "priority", "status")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("company", "actor", "action", "created_at")
    list_filter = ("company", "actor")


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("company", "category", "question")
    list_filter = ("company", "category")
    search_fields = ("question", "answer")


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("business_name", "business_type", "language", "booking_enabled")
    search_fields = ("business_name", "api_key")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "business_type",
                    "business_name",
                    "api_key",
                    "description",
                    "common_questions",
                    "common_services",
                )
            },
        ),
        (
            "Extra",
            {
                "fields": (
                    "company_policies",
                    "company_contact",
                    "language",
                    "booking_enabled",
                )
            },
        ),
    )


@admin.register(WebSiteConfig)
class WebConfigAdmin(admin.ModelAdmin):
    list_display = (
        "llm_provider",
        "llm_model",
        "other",
        "premium_llm_provider",
        "premium_llm_model",
        "premium_other",
    )


@admin.register(JSONFAQ)
class JSONFAQAdmin(admin.ModelAdmin):
    list_display = ("company", "name", "data")


@admin.register(VectorSyncJob)
class VectorSyncJobAdmin(admin.ModelAdmin):
    list_display = (
        "company",
        "kind",
        "op",
        "ref_id",
        "status",
        "attempts",
        "updated_at",
    )
    list_filter = ("status", "kind", "op")
    actions = ("requeue",)

    @admin.action(description="Requeue selected jobs as pending")
    def requeue(self, request, queryset):
        updated = queryset.update(status=VectorSyncJob.Status.PENDING)
        self.message_user(request, f"Requeued {updated} job(s).")
