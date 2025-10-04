from __future__ import annotations
import hashlib
import json
from typing import Any, Dict, Generator, List

from django.http import StreamingHttpResponse, HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from apps.core.models import Company, Conversation, Message, Customer, Service, FAQ
from apps.api.serializers import ServiceSerializer, FAQUpsertItemSerializer
from apps.ai.graph import run_chat
from apps.ingestion.etl import upsert_faqs
import asyncio

def _get_company_from_request(request: HttpRequest) -> Company | None:
    key = request.headers.get("X-Company-Key") or request.META.get("HTTP_X_COMPANY_KEY")
    if not key:
        return None
    try:
        return Company.objects.get(api_key=key)
    except Company.DoesNotExist:
        return None


def _hash_message(content: str, role: str) -> str:
    return hashlib.sha256(f"{role}:{content}".encode("utf-8")).hexdigest()


class ChatStreamView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any):
        from apps.ai.workflow import handle_chat

        session_id = "session_001"
        customer_id = "12345"  # اختياري

        messages = [
            # "محمد عماد ورقمي 1010220323 العنوان الفيوم"
            # "حجز شهر واحد"
            "عايز احجز خدمه "
            # "اي الخدمات اللي انتو بتقدموها"
            # "إيه أنواع الاشتراكات المتاحة؟"
            # "عندي مشكلة وعايز اعمل شكوي"
            # "السلام عليكم، أريد معلومات عن خدمات النادي",
            # "أريد حجز جلسة تدريب شخصي",
            # "ما هي حالة عضويتي الحالية؟",
            # "عايز اعرف الخدمات المتاحة",
            # "عايز اعرف اسعار الباقات عندكم؟",
            # "هل يمكنني تجميد العضوية بسبب السفر؟",
            # "عندي ظهر ... اقدر اجي؟",
            # "هل يوجد خصم للشركات لو جبت 7 موظفين؟",
            # "وش يصير لو نسيت أدفع قبل التجديد؟",
            # "هل يمكنني استخدام عضويتي لأخي؟ بدي يتدرب معي.",
            # "عندي سكري .. شنو اسوي قبل ما ابدا التمرين؟",
            # "هل يوجد تطبيق؟ وينزل منين؟",
            # "بدي اعمل بيرثداي لبنتي عندكم، في إمكانية؟",
            # "هل الأجهزة عليها تعقيم؟ قلقان من الكورونا",
            # "ممكن ادفع فودافون كاش؟",
            # "هل يمكنني حجز حصتين في نفس اليوم؟",
            # "عندي اشتراك شهري وعايز احوله لسنوي .. اعمل ايه؟",
            # "هل يمكنني الدخول بدون حذاء رياضي؟",
            # "هل يوجد بار صحي داخل الجيم؟",
        ]

        for message in messages:
            print(f"العميل: {message}")
            response = handle_chat(message, session_id, customer_id, Company.objects.filter().first())
            print(f"المساعد: {response}")
            print("-" * 50)

        return HttpResponse(f"res: {response}", status=status.HTTP_200_OK)


    def post(self, request: HttpRequest, *args: Any, **kwargs: Any):
        from apps.ai.workflow import handle_chat

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
            defaults={"customer": customer},
        )
        if customer and not conv.customer:
            conv.customer = customer
            conv.save(update_fields=["customer"])  # attach customer lazily

        # Execute graph to get response
        # Build short conversation history (last 8 messages)
        recent: List[Message] = list(
            Message.objects.filter(conversation=conv).order_by("-created_at")[:20]
        )
        history = [
            {"role": m.role, "content": m.content}
            for m in reversed(recent)
        ]            

        # Deduplicate incoming user message
        user_hash = _hash_message(message, "user")
        msg = Message.objects.get_or_create(
            conversation=conv,
            role=Message.Role.USER,
            dedup_hash=user_hash,
            defaults={"content": message, "meta": {"lang": "ar"}},
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

            assistant_hash = _hash_message(final_text, "assistant")
            Message.objects.get_or_create(
                conversation=conv,
                role=Message.Role.ASSISTANT,
                dedup_hash=assistant_hash,
                defaults={
                    "content": final_text,
                    # "meta": {
                    #     "node": result.get("debug", {}).get("node"),
                    #     "booking": result.get("booking"),
                    #     "intent": result.get("intent"),
                    # },
                },
            )

        except Exception as e:
            print(e)
            if msg:
                msg[0].delete()
            final_text = final_text
      
        return JsonResponse({"message": final_text})

        # def event_stream() -> Generator[bytes, None, None]:
        #     # naive chunking for SSE demo
        #     chunks = [final_text[i:i+40] for i in range(0, len(final_text), 40)] or [final_text]
        #     for ch in chunks:
        #         yield f"data: {ch}\n\n".encode("utf-8")
        #     yield b"event: done\n" + f"data: {json.dumps({'ok': True})}\n\n".encode("utf-8")

        # return StreamingHttpResponse(event_stream(), content_type="text/event-stream")



    # def post(self, request: HttpRequest, *args: Any, **kwargs: Any):
    #     company = _get_company_from_request(request)
    #     if not company:
    #         return Response({"detail": "شركة غير معروفة. تأكد من المفتاح."}, status=status.HTTP_401_UNAUTHORIZED)

    #     body = request.data if isinstance(request.data, dict) else json.loads(request.body.decode("utf-8"))
    #     message: str = (body.get("message") or "").strip()
    #     session_id: str = body.get("session_id") or f"sess-{timezone.now().timestamp()}"
    #     customer_payload: Dict[str, Any] = body.get("customer") or {}

    #     if not message:
    #         return Response({"detail": "من فضلك أرسل رسالة."}, status=status.HTTP_400_BAD_REQUEST)

    #     # Load or create customer
    #     customer = None
    #     if any(customer_payload.get(k) for k in ("phone", "email", "name")):
    #         customer, _ = Customer.objects.get_or_create(
    #             company=company,
    #             phone=customer_payload.get("phone", ""),
    #             defaults={
    #                 "name": customer_payload.get("name", ""),
    #                 "email": customer_payload.get("email", ""),
    #             },
    #         )

    #     # Load or create conversation
    #     conv, _ = Conversation.objects.get_or_create(
    #         company=company,
    #         session_id=session_id,
    #         defaults={"customer": customer},
    #     )
    #     if customer and not conv.customer:
    #         conv.customer = customer
    #         conv.save(update_fields=["customer"])  # attach customer lazily

    #     # Deduplicate incoming user message
    #     user_hash = _hash_message(message, "user")
    #     Message.objects.get_or_create(
    #         conversation=conv,
    #         role=Message.Role.USER,
    #         dedup_hash=user_hash,
    #         defaults={"content": message, "meta": {"lang": "ar"}},
    #     )

    #     # Execute graph to get response
    #     # Build short conversation history (last 8 messages)
    #     recent: List[Message] = list(
    #         Message.objects.filter(conversation=conv).order_by("-created_at")[:8]
    #     )
    #     history = [
    #         {"role": m.role, "content": m.content}
    #         for m in reversed(recent)
    #     ]

    #     state = {
    #         "company_id": str(company.id),
    #         "session_id": session_id,
    #         "original_message": message,
    #         "message": message,
    #         "lang": company.language or "ar",
    #         "customer": {"id": str(customer.id) if customer else None, "name": customer.name if customer else None, "phone": customer.phone if customer else None},
    #         "history": history,
    #     }
    #     result = run_chat(state=state, company=company, conversation=conv)
    #     final_text: str = (result.get("answer") or {}).get("text") or result.get("answer_text") or "تمام، تحت أمرك!"

    #     # Save assistant message (dedupe)
    #     assistant_hash = _hash_message(final_text, "assistant")
    #     Message.objects.get_or_create(
    #         conversation=conv,
    #         role=Message.Role.ASSISTANT,
    #         dedup_hash=assistant_hash,
    #         defaults={
    #             "content": final_text,
    #             "meta": {
    #                 "node": result.get("debug", {}).get("node"),
    #                 "booking": result.get("booking"),
    #                 "intent": result.get("intent"),
    #             },
    #         },
    #     )

    #     def event_stream() -> Generator[bytes, None, None]:
    #         # naive chunking for SSE demo
    #         chunks = [final_text[i:i+40] for i in range(0, len(final_text), 40)] or [final_text]
    #         for ch in chunks:
    #             yield f"data: {ch}\n\n".encode("utf-8")
    #         yield b"event: done\n" + f"data: {json.dumps({'ok': True})}\n\n".encode("utf-8")

    #     return StreamingHttpResponse(event_stream(), content_type="text/event-stream")


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

