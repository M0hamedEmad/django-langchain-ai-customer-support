from __future__ import annotations
import hashlib
import json
from typing import Any, Dict, Generator, List

from django.http import  HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from apps.core.models import Company, Conversation, Message, Customer, Service, FAQ
from apps.api.serializers import ServiceSerializer, FAQUpsertItemSerializer
# from apps.ingestion.etl import upsert_faqs
from apps.ai.workflow import handle_chat


def _get_company_from_request(request: HttpRequest) -> Company | None:
    key = request.headers.get("X-Company-Key") or request.META.get("HTTP_X_COMPANY_KEY")
    if not key:
        return None
    try:
        return Company.objects.get(api_key=key)
    except Company.DoesNotExist:
        return None



class ChatStreamView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any):

        company = _get_company_from_request(request)
        if not company:
            return Response({"detail": "شركة غير معروفة. تأكد من المفتاح."}, status=status.HTTP_401_UNAUTHORIZED)

        body = request.data if isinstance(request.data, dict) else json.loads(request.body.decode("utf-8"))
        message: str = (body.get("message") or "").strip()
        session_id: str = body.get("session_id") or f"sess-{timezone.now().timestamp()}"
        customer_payload: Dict[str, Any] = body.get("customer") or {}

        if not message:
            return Response({"detail": "من فضلك أرسل رسالة."}, status=status.HTTP_400_BAD_REQUEST)

        # Load or create customer
        customer = None
        if any(customer_payload.get(k) for k in ("phone", "email", "name")):
            customer, _ = Customer.objects.get_or_create(
                company=company,
                phone=customer_payload.get("phone", ""),
                defaults={
                    "name": customer_payload.get("name", ""),
                    "email": customer_payload.get("email", ""),
                },
            )

        # Load or create conversation
        conv, _ = Conversation.objects.get_or_create(
            company=company,
            session_id=session_id,
            customer= customer
        )
        # if customer and not conv.customer:
        #     conv.customer = customer
        #     conv.save(update_fields=["customer"])  # attach customer lazily


        # Execute graph to get response
        # Build short conversation history (last 8 messages)
        recent: List[Message] = list(
            Message.objects.filter(conversation=conv).order_by("-created_at")[:8]
        )
        history = [
            {"role": m.role, "content": m.content}
            for m in reversed(recent)
        ]            

        # Deduplicate incoming user message
        msg = Message.objects.create(
            conversation=conv,
            role=Message.Role.USER,
            content=message,
            meta={"lang": "ar"},
        )


        state = {
            "company_id": str(company.id),
            "session_id": session_id,
            "original_message": message,
            "messages": [{"role": "user", "content": message}],
            "lang": company.language or "ar",

            "customer_id": None if not customer else customer.id,
            "customer_name": None if not customer else customer.name,
            "customer_phone": None if not customer else customer.phone,

            "conversation_history": history,
        }
        result =  handle_chat(message, session_id, 1, company, init_state=state)
        try:
            final_text: str = result["messages"][-1]["content"]

            Message.objects.create(
                conversation=conv,
                role=Message.Role.ASSISTANT,
                content=final_text,
                meta={"lang": "ar"},
            )

        except Exception as e:
            print(e)
            if msg:
                msg.delete()
            final_text = result
      
        return JsonResponse({"message": final_text})

      


class ServicesView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any):
        company = _get_company_from_request(request)
        if not company:
            return Response({"detail": "شركة غير معروفة."}, status=status.HTTP_401_UNAUTHORIZED)
        qs = Service.objects.filter(company=company, is_active=True).order_by("name")
        return Response(ServiceSerializer(qs, many=True).data)


class FAQBulkUpsertView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any):
        from apps.ingestion.etl import upsert_faqs

        company = _get_company_from_request(request)
        if not company:
            return Response({"detail": "شركة غير معروفة."}, status=status.HTTP_401_UNAUTHORIZED)

        data = request.data
        if not isinstance(data, dict) or "faqs" not in data:
            return Response({"detail": "صيغة غير صحيحة. استخدم {faqs: [...]}"}, status=status.HTTP_400_BAD_REQUEST)

        items = data.get("faqs") or []
        if not isinstance(items, list) or not items:
            return Response({"detail": "لا يوجد عناصر لإدراجها."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = FAQUpsertItemSerializer(data=items, many=True)
        serializer.is_valid(raise_exception=True)

        upserted: list[FAQ] = []
        for item in serializer.validated_data:
            faq_id = item.get("id")
            defaults = {
                "question": item["question"],
                "answer": item["answer"],
                "informal_answer": item.get("informal_answer", ""),
                "category": item.get("category", ""),
                "tags": item.get("tags", []),
                "example_dialogue": item.get("example_dialogue", ""),
                "rag_tips": item.get("rag_tips", ""),
            }
            if faq_id:
                faq, _ = FAQ.objects.update_or_create(
                    id=faq_id, company=company, defaults=defaults
                )
            else:
                faq = FAQ.objects.create(company=company, **defaults)
            upserted.append(faq)

        # Update vector store
        stats = upsert_faqs(company, upserted)

        return Response({"ok": True, "count": len(upserted), "vector": stats}, status=status.HTTP_200_OK)


class FAQReindexAllView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any):
        from apps.ingestion.etl import upsert_faqs

        company = _get_company_from_request(request)
        if not company:
            return Response({"detail": "شركة غير معروفة."}, status=status.HTTP_401_UNAUTHORIZED)
        faqs = FAQ.objects.filter(company=company)
        stats = upsert_faqs(company, faqs)
        return Response({"ok": True, "count": faqs.count(), "vector": stats})


class ConversationMessagesView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request: HttpRequest, session_id: str, *args: Any, **kwargs: Any):
        company = _get_company_from_request(request)
        if not company:
            return Response({"detail": "Company not found"}, status=status.HTTP_401_UNAUTHORIZED)

        customer_phone = request.query_params.get("customer_id")

        query = {
            "company": company,
            "session_id": session_id
        }

        if customer_phone:
            customer = Customer.objects.filter(company=company, phone=customer_phone).first()
        if not customer:
            return JsonResponse({"detail": "Customer external id is required", "messages": []})
        
        query["customer"] = customer

        try:
            conversation = Conversation.objects.get(**query)
            messages = conversation.messages.all().values('role', 'content', 'created_at')
            messages_obj = []
            for message in messages:
                messages_obj.append({
                    "role": message["role"],
                    "content": message["content"],
                    "created_at": message["created_at"],
                })
            return JsonResponse({"messages": messages_obj})
        except:
            return JsonResponse({"detail": "Conversation not found", "messages": []})

