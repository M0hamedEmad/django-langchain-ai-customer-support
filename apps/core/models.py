from __future__ import annotations
import logging
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


logger = logging.getLogger(__name__)

class WebSiteConfig(models.Model):
    LLM_PROVIDERS = [
        ("openai", "openai"),
        ("gemini", "gemini"),
        ("deepseek", "deepseek"),
    ]
    LLM_MODELS = [
        ("gpt-4o-mini", "gpt-4o-mini"),
        ("gemini-2.5-flash", "gemini-2.5-flash"),
        ("gemini-2.5-pro", "gemini-2.5-pro"),
        ("deepseek/deepseek-chat-v3.1:free", "deepseek"),
        ("other", "other")
    ]

    llm_provider = models.CharField(max_length=32, choices=LLM_PROVIDERS, null=True, blank=True)
    llm_model = models.CharField(max_length=128, null=True, blank=True, choices=LLM_MODELS)
    other = models.CharField(max_length=255, null=True, blank=True)

    premium_llm_provider = models.CharField(max_length=32, choices=LLM_PROVIDERS, null=True, blank=True)
    premium_llm_model = models.CharField(max_length=128, null=True, blank=True, choices=LLM_MODELS)
    premium_other = models.CharField(max_length=255, null=True, blank=True)

    hardness_score = models.IntegerField(default=5)

    class Meta:
        verbose_name = "LLM Config"
        verbose_name_plural = "LLM Config"

    def __str__(self):
        return f"LLM Config {self.llm_provider} {self.llm_model}"


    def save(self, *args, **kwargs):

        if not self.pk:
            if WebSiteConfig.objects.all().exists():
                raise ValidationError("Only one site configuration is allowed.")

        self.check_provider(self.llm_provider, self.llm_model)
        self.check_provider(self.premium_llm_provider, self.premium_llm_model)
        
        super().save(*args, **kwargs)

    def get_llm_model(self):
        return self.llm_model if self.llm_model != 'other' else self.other

    def get_pm_llm_model(self):
        return self.premium_llm_model if self.premium_llm_model != 'other' else self.premium_other

    def check_provider(self, provider, llm):
        if not provider or not llm or llm == "other":
            return
        if provider == "gemini" and not llm.startswith("gemini"):
            raise ValueError("google LLM model must start with 'gemini'")
        if provider == "openai" and not llm.startswith("gpt"):
            raise ValueError("openai LLM model must start with 'gpt'")
        if provider == "deepseek" and not llm.startswith("deepseek"):
            raise ValueError("deepseek LLM model must start with 'deepseek'")




class Company(models.Model):
    class BusinessType(models.TextChoices):
        ECOMMERCE = "ecommerce", "ecommerce"
        GYM = "gym", "gym"
        RESTAURANT = "restaurant", "restaurant"
        GENERAL = "general", "general"

    business_type = models.CharField(max_length=32, choices=BusinessType.choices, default=BusinessType.GENERAL)
    business_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    working_hours = models.TextField(null=True, blank=True)
    company_policies = models.TextField(null=True, blank=True)
    company_contact = models.TextField(null=True, blank=True)
    common_questions = models.TextField(null=True, blank=True)
    common_services = models.TextField(null=True, blank=True)

    language = models.CharField(max_length=8, default="ar")
    timezone = models.CharField(max_length=64, default="UTC")

    booking_enabled = models.BooleanField(default=True)

    vector_namespace = models.CharField(max_length=255, blank=True)
    api_key = models.CharField(max_length=128, unique=True, blank=True, null=True)
    settings = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.business_name} ({self.business_type})"

    def get_company_info(self) -> str:
        return f"""
        معلومات الشركة
        --------------------

        - نوع العمل التجاري: {self.business_type}
        - اسم الشركة: {self.business_name}
        - وصف الشركة: {self.description}
        - ساعات العمل: {self.working_hours}
        - سياسات الشركة: {self.company_policies}
        - معلومات التواصل (هاتف، فيسبوك، إلخ): {self.company_contact}
        - الأسئلة الشائعة: {self.common_questions}
        - الخدمات الأساسية: {self.common_services}
        - اللغة: {self.language}
        - المنطقة الزمنية: {self.timezone}
        - نظام الحجز مفعّل: {self.booking_enabled}
        """

    def get_company_general_info(self) -> str:
        return f"""
        Business Type: 
            {self.business_type}
        Business Name: 
            {self.business_name}
        Description:
             {self.description}
        """        


    def save(self, *args, **kwargs):
        from apps.ingestion.outbox import enqueue_vector_sync
        super().save(*args, **kwargs)
        # Vector sync runs in the outbox worker; the DB write never waits.
        enqueue_vector_sync(self, VectorSyncJob.Kind.COMPANY_INFO, self.pk)


class Service(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="services")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    duration_minutes = models.PositiveIntegerField("Duration", null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.company.business_name} - {self.name}"


class FAQ(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="faqs")
    question = models.TextField()
    answer = models.TextField()
    informal_answer = models.TextField(blank=True)
    category = models.CharField(max_length=128, blank=True)
    tags = models.JSONField(default=list, blank=True)
    example_dialogue = models.TextField(blank=True)
    rag_tips = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"FAQ[{self.company.business_name}] {self.category or ''}"


    # def save(self, *args, **kwargs):
    #     from apps.ingestion.etl import upsert_faqs
    #     super().save(*args, **kwargs)
    #     data = [
    #         {
    #             "id": self.id,
    #             "question": self.question,
    #             "answer": self.answer,
    #             "informal_answer": self.informal_answer,
    #             "category": self.category,
    #             "tags": self.tags,
    #             "example_dialogue": self.example_dialogue,
    #             "rag_tips": self.rag_tips
    #         }
    #     ]
    #     upsert_faqs(self.company, data)        


class Customer(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="customers")
    external_id = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=64, blank=True)
    email = models.EmailField(blank=True)
    locale = models.CharField(max_length=8, default="ar")
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Blank legacy phones ("") stay legal; real phones are unique per company.
            models.UniqueConstraint(
                fields=["company", "phone"],
                condition=~models.Q(phone=""),
                name="uniq_customer_company_phone",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name or self.phone or 'Customer'} @{self.company.business_name}"


class Booking(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "created"
        CONFIRMED = "confirmed", "confirmed"
        CANCELLED = "cancelled", "cancelled"
        COMPLETED = "completed", "completed"

    class Source(models.TextChoices):
        CHAT = "chat", "chat"
        PANEL = "panel", "panel"
        API = "api", "api"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="bookings")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="bookings")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="bookings", null=True, blank=True)
    service_text = models.CharField(max_length=555, blank=True, null=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATED)

    date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.CHAT)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["company", "status", "date"],
                name="booking_company_status_date",
            ),
        ]

    def __str__(self) -> str:
        return f"Booking #{self.pk} - {self.service} ({self.status})"


class Conversation(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "open"
        ESCALATED = "escalated", "escalated"
        CLOSED = "closed", "closed"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="conversations")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="conversations")
    session_id = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    summary = models.TextField(blank=True)
    last_intent = models.CharField(max_length=32, blank=True)

    important_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "session_id"],
                name="uniq_conversation_company_session",
            ),
        ]

    def __str__(self) -> str:
        return f"Conv {self.pk} ({self.company.business_name})"


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", "user"
        ASSISTANT = "assistant", "assistant"
        SYSTEM = "system", "system"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages", db_index=True)
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField()
    meta = models.JSONField(default=dict, blank=True)
    dedup_hash = models.CharField(max_length=64, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")
        constraints = [
            # Legacy rows predate dedup (NULL) and stay legal.
            models.UniqueConstraint(
                fields=["conversation", "dedup_hash"],
                condition=models.Q(dedup_hash__isnull=False),
                name="uniq_message_conversation_dedup",
            ),
        ]

    def __str__(self) -> str:
        return f"Msg {self.role} in Conv {self.conversation_id}"


class WhatsAppMessage(models.Model):
    message_id = models.CharField(max_length=255, unique=True, db_index=True)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="whatsapp_messages",
        null=True, blank=True,
        help_text="Set by the webhook; legacy polled rows predate it.",
    )
    phone_number = models.CharField(max_length=20)
    sender_name = models.CharField(max_length=255, blank=True, null=True)
    message_body = models.TextField()
    timestamp = models.BigIntegerField()
    received_at = models.DateTimeField(auto_now_add=True)
    is_processed = models.BooleanField(default=False)
    reply_text = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=["is_processed", "received_at"]),
        ]
    
    def __str__(self):
        return f"{self.phone_number}: {self.message_body[:50]}"



class EscalationTicket(models.Model):
    class Priority(models.TextChoices):
        LOW = "low", "low"
        MEDIUM = "medium", "medium"
        HIGH = "high", "high"

    class Status(models.TextChoices):
        NEW = "new", "new"
        ASSIGNED = "assigned", "assigned"
        RESOLVED = "resolved", "resolved"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="escalations")
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="escalations")
    reason = models.TextField()
    priority = models.CharField(max_length=16, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    transcript_snapshot = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Escalation {self.pk} ({self.status})"


class AuditLog(models.Model):
    class Actor(models.TextChoices):
        SYSTEM = "system", "system"
        USER = "user", "user"
        ADMIN = "admin", "admin"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="audit_logs")
    actor = models.CharField(max_length=16, choices=Actor.choices, default=Actor.SYSTEM)
    action = models.CharField(max_length=255)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    diff = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Audit {self.actor} {self.action}"



class VectorSyncJob(models.Model):
    """Outbox row for vector-store sync (processed by `process_outbox`).

    Model saves enqueue instead of calling Chroma inline, so embedding or
    vector-DB outages never block DB writes and never slow down requests.
    Repeated saves coalesce into one pending row per (company, kind, ref).
    """

    class Kind(models.TextChoices):
        COMPANY_INFO = "company_info", "company_info"
        JSON_FAQ = "json_faq", "json_faq"

    class Op(models.TextChoices):
        UPSERT = "upsert", "upsert"
        DELETE = "delete", "delete"

    class Status(models.TextChoices):
        PENDING = "pending", "pending"
        PROCESSING = "processing", "processing"
        DONE = "done", "done"
        FAILED = "failed", "failed"

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="vector_jobs"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    op = models.CharField(max_length=8, choices=Op.choices, default=Op.UPSERT)
    ref_id = models.BigIntegerField(
        help_text="Company pk for company_info, JSONFAQ pk for json_faq."
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"VectorJob {self.kind}/{self.op} ref={self.ref_id} ({self.status})"



class JSONFAQ(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="json_fq")
    name = models.CharField(max_length=100, blank=True, null=True)  # optional label
    data = models.JSONField()

    def __str__(self):
        return self.name or f"JSON #{self.pk}"



    def save(self, *args, **kwargs):
        from apps.ingestion.outbox import enqueue_vector_sync

        super().save(*args, **kwargs)
        enqueue_vector_sync(self.company, VectorSyncJob.Kind.JSON_FAQ, self.pk)

    def delete(self, *args, **kwargs):
        from apps.ingestion.outbox import enqueue_vector_sync

        company, pk = self.company, self.pk
        super().delete(*args, **kwargs)
        enqueue_vector_sync(
            company, VectorSyncJob.Kind.JSON_FAQ, pk, op=VectorSyncJob.Op.DELETE
        )
        