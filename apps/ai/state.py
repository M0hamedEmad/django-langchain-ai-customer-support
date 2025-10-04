from __future__ import annotations
from typing import Any, Dict, TypedDict, List, Optional

from enum import Enum
from apps.core.models import Service

class GraphState(TypedDict, total=False):

    turn: int
    original_message: str
    message: str
    lang: str
    customer: Dict[str, Optional[str]]
    # Last N messages as conversation history to ground responses
    history: List[Dict[str, str]]  # each: {"role": "user|assistant|system", "content": str}
    intent: Dict[str, Any]
    booking: Dict[str, Any]
    retrieval: Dict[str, Any]
    answer: Dict[str, Any]
    escalation: Dict[str, Any]
    errors: List[str]
    debug: Dict[str, Any]



class IntentType(Enum):
    """تعداد أنواع النوايا المختلفة"""
    GENERAL_INQUIRY = "استفسار_عام"
    SERVICE_BOOKING = "حجز_خدمة"
    BOOKING_MODIFICATION = "تعديل_حجز"
    COMPLAINT = "شكوى"
    MEMBERSHIP_INQUIRY = "استفسار_عضوية"
    UNCLEAR = "غير_واضح"


class IntentSubType(Enum):
    """أنواع فرعية للنوايا"""
    # استفسار_عام
    GENERAL_INFO_REQUEST = "طلب_معلومات_عامة"
    SERVICE_INFO_REQUEST = "طلب_معلومات_خدمة"
    
    # حجز_خدمة
    BOOKING_REQUEST = "طلب_حجز"
    BOOKING_INFO_REQUEST = "طلب_معلومات_حجز"
    BOOKING_CONFIRMATION = "تأكيد_طلب_الحجز"
    
    # تعديل_حجز
    BOOKING_CANCEL = "إلغاء_حجز"
    BOOKING_RESCHEDULE = "تعديل_معلومات_الحجز"
    
    # شكوى
    COMPLAINT_INQUIRY = "استفسار_شكوى"
    COMPLAINT_SUBMISSION = "تقديم_شكوى"
    
    # استفسار_عضوية
    MEMBERSHIP_INFO = "معلومات_عضوية"
    MEMBERSHIP_RENEWAL = "تجديد_عضوية"
    
    # غير_واضح
    UNCLEAR = "غير_واضح"

class ConversationState(TypedDict):
    """حالة المحادثة"""
    company_id: str
    session_id: str    
    messages: List[Dict[str, Any]]
    original_message: str
    
    current_intent: Optional[str]
    intent_type: Optional[str]  # النوع الفرعي للنية
    intent_confidence: Optional[float]  # درجة الثقة من 0 إلى 1
    
    customer_id: Optional[str]
    customer_name: Optional[str]
    customer_phone: Optional[str]
    customer_address: Optional[str]
    
    selected_service_id: Optional[str]
    selected_service: Optional[str]
    service_object:Optional[Any]
    booking_date: Optional[str]
    booking_id: Optional[str]
    missing_info: Optional[List[str]]
    
    booking_context: Optional[Dict[str, Any]]
    user_bookings: List[dict]

    conversation_history: List[Dict[str, Any]]
    history: List[Dict[str, Any]]
    rag_context: Optional[str]
    requires_escalation: bool
    satisfaction_score: Optional[int]
    language: str
    current_step: str

    errors: List[str]
    debug: Dict[str, Any]

