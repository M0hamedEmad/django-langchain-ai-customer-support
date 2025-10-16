"""Booking-confirmation prompt: summarize details and ask for confirmation.

NOTE: currently assigned but not invoked by any node (same as before the
Phase 3 split). Kept for the upcoming booking-gate wiring; delete if still
unwired after the nodes/ extraction.
"""

from langchain_core.prompts import ChatPromptTemplate


def build_booking_confirm_prompt() -> ChatPromptTemplate:
    """Booking confirmation template (conditional summary, always ends in a question)."""
    return ChatPromptTemplate.from_messages(
        [
            (
                "human",
                """
                أنت مساعد آلي دقيق ومحترف. مهمتك هي عرض تفاصيل الحجز التالية للحصول على تأكيد نهائي من العميل. يجب عليك إتباع القواعد الشرطية الصارمة: **لا تُدرج أي سطر أو جزء معلومات عن متغير فارغ.**

                من المهم جدا ان تكون رسالتك بغرض طلب تأكيد الحجز من العميل وتتم بصيغة السؤال دائما

                تأكد من موضوع الاسم والرقم اذا وجدوا في رساله الرد .
                لا تسأل عن اي عنصر عير موجود في رساله الرد

                **1. رسالة البداية المخصصة:**
                اختر رسالة بداية مناسبة

                **2. ملخص تفاصيل الحجز والخدمة:**
                نحن على وشك تأكيد حجزك رقم **[booking_id]**. يرجى مراجعة التفاصيل أدناه قبل التأكيد النهائي:

                **أ. معلومات العميل والحجز:**
                - **رقم الحجز:** [booking_id]
                - [إذا كانت customer_name]: **العميل:** {customer_name}
                - [إذا كانت customer_phone]: **رقم التواصل:** {customer_phone}
                - [إذا كانت booking_date]: **التاريخ والوقت:** {booking_date}
                - [إذا كانت customer_address]: **موقع الخدمة:** {customer_address}

                **ب. تفاصيل الخدمة:**
                - **الخدمة المحجوزة:** {name}
                - [إذا كانت description]: **وصف الخدمة:** {description}
                - [إذا كانت price]: **التكلفة:** {price}

                **3. السؤال النهائي للتأكيد:**
                "هل المعلومات المذكورة أعلاه صحيحة وتؤكد **المضي قدماً في الحجز**؟ (يرجى الرد بنعم للتأكيد)"

                **4. رسالة الختام المخصصة:**
                اختر رسالة نهاية مناسبة
            """,
            ),
        ]
    )
