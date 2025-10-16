"""Service-matching prompt: map a free-text request to the best catalog service."""

from langchain_core.prompts import ChatPromptTemplate


def build_service_matching_prompt() -> ChatPromptTemplate:
    """Service matcher template (JSON-only output contract)."""
    return ChatPromptTemplate.from_messages(
        [
            (
                "human",
                """
                أنت وكيل مطابقة خدمات دقيق وموضوعي. مهمتك هي قراءة طلب العميل ومطابقته بأفضل خدمة من قائمة الخدمات المقدمة.

                ## Available services (Context):
                {formatted_services}

                ## Question:
                {query}

                ## Output rules:
                1.  يجب أن يكون الإخراج **حصريًا** بصيغة JSON.
                2.  يجب عليك اختيار **خدمة واحدة فقط** هي الأفضل مطابقة.
                3.  إذا كانت المطابقة جيدة، اجعل `confidence_score` (الثقة) رقمًا بين 0.80 و 1.00.
                4.  إذا كانت المطابقة ضعيفة أو غير واضحة، اجعل `confidence_score` بين 0.50 و 0.79.
                5.  إذا لم يكن هناك أي مطابقة معقولة، فاجعل `service_id` القيمة "NONE" و `confidence_score` القيمة 0.00.
                6. اجب بصيغة JSON فقط بهذا الشكل:
                    {{
                        "service_id": "الأفضل مطابقة ID",
                        "confidence_score": 0.00,
                        "matching_reason": "سبب اختيار الخدمة المطابقة"
                    }}
            """,
            )
        ]
    )
