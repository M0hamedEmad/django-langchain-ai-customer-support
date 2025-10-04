import os
import json
import logging
from datetime import datetime, timedelta
from typing import TypedDict, List, Optional, Dict, Any
from enum import Enum

# LangChain imports
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema import HumanMessage, AIMessage
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter

# LangGraph imports
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver


import os


from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings





def get_embeddings() -> Any:
    provider = "gemini"

    if provider in ("gemini", "google", "google-genai") and GoogleGenerativeAIEmbeddings is not None:
        # Prefer configurable embeddings model; default to text-embedding-004
        model_name = os.getenv("GOOGLE_EMBEDDINGS_MODEL", "models/gemini-embedding-001")
        if not os.getenv("GOOGLE_API_KEY"):
            raise RuntimeError("GOOGLE_API_KEY not set in environment")
        return GoogleGenerativeAIEmbeddings(model=model_name)

    # default to OpenAI
    return OpenAIEmbeddings(model="text-embedding-3-large")


def collection_name() -> str:
    return f"company_{1}"

def get_vectorstore():
    embeddings = get_embeddings()
    vs = Chroma(
        collection_name=collection_name(),
        embedding_function=embeddings,
        persist_directory="/home/mohamed/Desktop/programming/professional_customer_support/backend/.chroma",
    )
    return vs


def get_retriever(top_k: int = 5):
    vs = get_vectorstore()
    return vs.as_retriever(search_kwargs={"k": top_k})

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IntentType(Enum):
    """تعداد أنواع النوايا المختلفة"""
    GENERAL_INQUIRY = "استفسار_عام"
    SERVICE_BOOKING = "حجز_خدمة"
    BOOKING_MODIFICATION = "تعديل_حجز"
    COMPLAINT = "شكوى"
    MEMBERSHIP_INQUIRY = "استفسار_عضوية"
    UNCLEAR = "غير_واضح"

class ConversationState(TypedDict):
    """حالة المحادثة"""
    messages: List[Dict[str, Any]]
    current_intent: Optional[str]
    customer_id: Optional[str]
    customer_data: Optional[Dict[str, Any]]
    booking_context: Optional[Dict[str, Any]]
    conversation_history: List[Dict[str, Any]]
    rag_context: Optional[str]
    requires_escalation: bool
    satisfaction_score: Optional[int]
    session_id: str
    language: str
    current_step: str

class CustomerServiceChatbot:
    """نظام خدمة العملاء المتقدم"""
    
    def __init__(self, gemini_api_key: str, knowledge_base_path: str):
        """تهيئة نظام خدمة العملاء"""
        # إعداد النموذج اللغوي
        os.environ["GOOGLE_API_KEY"] = gemini_api_key
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.3,
            convert_system_message_to_human=True
        )
        
        self.memory = SqliteSaver.from_conn_string(":memory:")


        # إعداد نظام RAG
        self.setup_rag_system(knowledge_base_path)
        
        # إعداد قواعد البيانات الوهمية
        self.setup_mock_databases()
        
        # إعداد الرسائل النموذجية
        self.setup_templates()
        
        # إعداد الرسم البياني للمحادثة
        self.setup_conversation_graph()
        
        # إعداد حفظ نقاط التحقق
    
    def setup_rag_system(self, knowledge_base_path: str):
        """إعداد نظام استرجاع المعلومات المعزز"""
        try:
            # إعداد نموذج التضمين
            self.embeddings = get_embeddings()
            
            # إنشاء مخزن المتجهات
            self.vectorstore = get_vectorstore()
            
            
            logger.info("تم إعداد نظام RAG بنجاح")
        except Exception as e:
            logger.error(f"خطأ في إعداد نظام RAG: {e}")
            self.vectorstore = None
    
    def setup_mock_databases(self):
        """إعداد قواعد البيانات الوهمية للعملاء والحجوزات"""
        self.customers_db = {
            "12345": {
                "name": "أحمد محمد",
                "phone": "01234567890",
                "email": "ahmed@example.com",
                "membership_type": "ذهبية",
                "membership_end": "2024-12-31",
                "active_bookings": ["BK001", "BK002"]
            },
            "67890": {
                "name": "فاطمة علي",
                "phone": "09876543210",
                "email": "fatma@example.com",
                "membership_type": "فضية",
                "membership_end": "2024-10-15",
                "active_bookings": ["BK003"]
            }
        }
        
        self.bookings_db = {
            "BK001": {
                "customer_id": "12345",
                "service": "تدريب شخصي",
                "date": "2024-09-30",
                "time": "18:00",
                "trainer": "مدرب أحمد",
                "status": "مؤكد"
            },
            "BK002": {
                "customer_id": "12345",
                "service": "جلسة تدليك",
                "date": "2024-10-02",
                "time": "16:00",
                "therapist": "أخصائي سارة",
                "status": "مؤكد"
            }
        }
        
        self.services_db = {
            "تدريب_شخصي": {
                "name": "تدريب شخصي",
                "duration": 60,
                "price": 200,
                "available_times": ["09:00", "10:00", "11:00", "16:00", "17:00", "18:00"]
            },
            "تدريب_جماعي": {
                "name": "تدريب جماعي",
                "duration": 45,
                "price": 50,
                "available_times": ["08:00", "18:00", "19:00", "20:00"]
            },
            "تدليك_علاجي": {
                "name": "تدليك علاجي",
                "duration": 90,
                "price": 300,
                "available_times": ["10:00", "12:00", "14:00", "16:00"]
            }
        }
    
    def setup_templates(self):
        """إعداد القوالب للرسائل المختلفة"""
        self.intent_classifier_template = ChatPromptTemplate.from_messages([
            ("human", """
            أنت مساعد ذكي لتحليل نوايا العملاء في صالة رياضية. حلل الرسالة التالية وحدد النية:
            
            الرسالة: {message}
            
            النوايا المحتملة:
            1. استفسار_عام - أسئلة عامة عن النادي أو الخدمات
            2. حجز_خدمة - طلب حجز خدمة جديدة
            3. تعديل_حجز - تعديل أو إلغاء حجز موجود
            4. شكوى - شكوى أو مشكلة
            5. استفسار_عضوية - أسئلة عن العضوية
            6. غير_واضح - النية غير واضحة
            
            اجب بالنية فقط دون تفسير:
            """)
        ])
        
        self.response_generator_template = ChatPromptTemplate.from_messages([
            ("human", """
            أنت مساعد خدمة عملاء محترف في صالة رياضية. اجب على استفسار العميل باللغة العربية بطريقة مهذبة ومفيدة.
            
            سياق المحادثة: {context}
            استفسار العميل: {query}
            معلومات إضافية: {additional_info}
            
            تأكد من:
            1. الرد باللغة العربية
            2. استخدام لهجة مهذبة ومهنية
            3. تقديم معلومات دقيقة ومفيدة
            4. اقتراح خطوات عملية عند الحاجة
            
            الرد:
            """)
        ])
    
    def setup_conversation_graph(self):
        """إعداد الرسم البياني للمحادثة"""
        workflow = StateGraph(ConversationState)
        
        # إضافة العقد
        workflow.add_node("receive_message", self.receive_message)
        workflow.add_node("analyze_intent", self.analyze_intent)
        workflow.add_node("handle_general_inquiry", self.handle_general_inquiry)
        workflow.add_node("handle_service_booking", self.handle_service_booking)
        workflow.add_node("handle_booking_modification", self.handle_booking_modification)
        workflow.add_node("handle_complaint", self.handle_complaint)
        workflow.add_node("handle_membership_inquiry", self.handle_membership_inquiry)
        workflow.add_node("clarify_intent", self.clarify_intent)
        workflow.add_node("escalate_to_human", self.escalate_to_human)
        workflow.add_node("generate_response", self.generate_response)
        workflow.add_node("evaluate_satisfaction", self.evaluate_satisfaction)
        
        # إعداد نقطة البداية
        workflow.set_entry_point("receive_message")
        
        # إضافة الحواف الشرطية
        workflow.add_conditional_edges(
            "analyze_intent",
            self.route_by_intent,
            {
                "general_inquiry": "handle_general_inquiry",
                "service_booking": "handle_service_booking",
                "booking_modification": "handle_booking_modification",
                "complaint": "handle_complaint",
                "membership_inquiry": "handle_membership_inquiry",
                "unclear": "clarify_intent"
            }
        )
        
        # إضافة الحواف للاستجابة
        workflow.add_edge("handle_general_inquiry", "generate_response")
        workflow.add_edge("handle_service_booking", "generate_response")
        workflow.add_edge("handle_booking_modification", "generate_response")
        workflow.add_edge("handle_complaint", "generate_response")
        workflow.add_edge("handle_membership_inquiry", "generate_response")
        workflow.add_edge("clarify_intent", "generate_response")
        
        # إضافة حواف التقييم
        workflow.add_edge("generate_response", "evaluate_satisfaction")
        workflow.add_conditional_edges(
            "evaluate_satisfaction",
            self.check_escalation,
            {
                "continue": END,
                "escalate": "escalate_to_human"
            }
        )
        workflow.add_edge("escalate_to_human", END)
        
        self.app = workflow.compile(checkpointer=self.memory)
    
    # عقد الرسم البياني
    def receive_message(self, state: ConversationState) -> ConversationState:
        """استقبال الرسالة الجديدة"""
        print('*********')
        print(state)
        logger.info(f"تم استقبال رسالة جديدة: {state.get('messages', [])[-1] if state.get('messages') else 'لا توجد رسائل'}")
        state["current_step"] = "receive_message"
        return state
    
    def analyze_intent(self, state: ConversationState) -> ConversationState:
        """تحليل نية العميل"""
        if not state.get("messages"):
            state["current_intent"] = IntentType.UNCLEAR.value
            return state
        
        last_message = state["messages"][-1]["content"]
        
        try:
            prompt = self.intent_classifier_template.format_messages(message=last_message)
            response = self.llm.invoke(prompt)
            intent = response.content.strip()
            
            # التحقق من صحة النية
            valid_intents = [e.value for e in IntentType]
            if intent in valid_intents:
                state["current_intent"] = intent
            else:
                state["current_intent"] = IntentType.UNCLEAR.value
                
        except Exception as e:
            logger.error(f"خطأ في تحليل النية: {e}")
            state["current_intent"] = IntentType.UNCLEAR.value
        
        state["current_step"] = "analyze_intent"
        logger.info(f"تم تحديد النية: {state['current_intent']}")
        return state
    
    def handle_general_inquiry(self, state: ConversationState) -> ConversationState:
        """التعامل مع الاستفسارات العامة"""
        state["current_step"] = "handle_general_inquiry"
        
        if not state.get("messages"):
            return state
        
        query = state["messages"][-1]["content"]
        
        # البحث في قاعدة المعرفة
        if self.vectorstore:
            relevant_docs = self.vectorstore.similarity_search(query, k=3)
            context = "\n".join([doc.page_content for doc in relevant_docs])
            state["rag_context"] = context
        else:
            state["rag_context"] = "معلومات عامة عن النادي الرياضي"
        
        logger.info("تم التعامل مع الاستفسار العام")
        return state
    
    def handle_service_booking(self, state: ConversationState) -> ConversationState:
        """التعامل مع حجز الخدمات"""
        state["current_step"] = "handle_service_booking"
        
        if not state.get("booking_context"):
            state["booking_context"] = {
                "step": "service_selection",
                "available_services": list(self.services_db.keys()),
                "selected_service": None,
                "selected_date": None,
                "selected_time": None
            }
        
        booking_step = state["booking_context"]["step"]
        
        if booking_step == "service_selection":
            services_list = "\n".join([f"- {service['name']}: {service['price']} جنيه ({service['duration']} دقيقة)" 
                                     for service in self.services_db.values()])
            state["rag_context"] = f"الخدمات المتاحة:\n{services_list}"
            
        elif booking_step == "confirmation":
            booking_id = f"BK{len(self.bookings_db) + 1:03d}"
            state["booking_context"]["booking_id"] = booking_id
            
        logger.info(f"معالجة حجز الخدمة - الخطوة: {booking_step}")
        return state
    
    def handle_booking_modification(self, state: ConversationState) -> ConversationState:
        """التعامل مع تعديل الحجوزات"""
        state["current_step"] = "handle_booking_modification"
        
        customer_id = state.get("customer_id")
        if customer_id and customer_id in self.customers_db:
            active_bookings = self.customers_db[customer_id]["active_bookings"]
            booking_details = []
            
            for booking_id in active_bookings:
                if booking_id in self.bookings_db:
                    booking = self.bookings_db[booking_id]
                    booking_details.append(
                        f"رقم الحجز: {booking_id}\n"
                        f"الخدمة: {booking['service']}\n"
                        f"التاريخ: {booking['date']}\n"
                        f"الوقت: {booking['time']}\n"
                        f"الحالة: {booking['status']}\n"
                    )
            
            if booking_details:
                state["rag_context"] = "حجوزاتك الحالية:\n\n" + "\n---\n".join(booking_details)
            else:
                state["rag_context"] = "لا توجد لديك حجوزات نشطة حالياً."
        else:
            state["rag_context"] = "يرجى تسجيل الدخول أولاً لعرض حجوزاتك."
        
        logger.info("تم التعامل مع طلب تعديل الحجز")
        return state
    
    def handle_complaint(self, state: ConversationState) -> ConversationState:
        """التعامل مع الشكاوى"""
        state["current_step"] = "handle_complaint"
        
        if not state.get("messages"):
            return state
        
        complaint_text = state["messages"][-1]["content"]
        
        # تقييم خطورة الشكوى
        severity_keywords = {
            "عالية": ["خطر", "إصابة", "طبي", "طوارئ", "تسمم", "حريق"],
            "متوسطة": ["سوء معاملة", "خطأ", "تأخير", "رد أموال", "إلغاء"],
            "منخفضة": ["اقتراح", "تحسين", "ملاحظة", "استفسار"]
        }
        
        severity = "منخفضة"
        for level, keywords in severity_keywords.items():
            if any(keyword in complaint_text for keyword in keywords):
                severity = level
                break
        
        # تسجيل الشكوى
        complaint_id = f"COM{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        if severity == "عالية":
            state["requires_escalation"] = True
            state["rag_context"] = f"تم تسجيل شكواك برقم {complaint_id} وسيتم التواصل معك خلال ساعة واحدة من قبل الإدارة."
        elif severity == "متوسطة":
            state["rag_context"] = f"تم تسجيل شكواك برقم {complaint_id} وسيتم الرد عليك خلال 24 ساعة."
        else:
            state["rag_context"] = f"شكراً لك على ملاحظتك. تم تسجيلها برقم {complaint_id} وسنعمل على تحسين خدماتنا."
        
        logger.info(f"تم تسجيل شكوى بدرجة {severity} - رقم {complaint_id}")
        return state
    
    def handle_membership_inquiry(self, state: ConversationState) -> ConversationState:
        """التعامل مع استفسارات العضوية"""
        state["current_step"] = "handle_membership_inquiry"
        
        customer_id = state.get("customer_id")
        if customer_id and customer_id in self.customers_db:
            customer = self.customers_db[customer_id]
            membership_info = (
                f"معلومات عضويتك:\n\n"
                f"الاسم: {customer['name']}\n"
                f"نوع العضوية: {customer['membership_type']}\n"
                f"تاريخ انتهاء العضوية: {customer['membership_end']}\n"
                f"الهاتف: {customer['phone']}\n"
                f"البريد الإلكتروني: {customer['email']}\n"
            )
            
            # حساب الأيام المتبقية
            try:
                end_date = datetime.strptime(customer['membership_end'], '%Y-%m-%d')
                days_remaining = (end_date - datetime.now()).days
                
                if days_remaining > 0:
                    membership_info += f"\nمتبقي على انتهاء العضوية: {days_remaining} يوم"
                else:
                    membership_info += f"\nعضويتك منتهية منذ {abs(days_remaining)} يوم - يرجى التجديد"
                    
            except ValueError:
                membership_info += "\nيرجى مراجعة تاريخ انتهاء العضوية"
            
            state["rag_context"] = membership_info
        else:
            state["rag_context"] = "يرجى تسجيل الدخول أولاً لعرض معلومات عضويتك."
        
        logger.info("تم التعامل مع استفسار العضوية")
        return state
    
    def clarify_intent(self, state: ConversationState) -> ConversationState:
        """طلب توضيح النية"""
        state["current_step"] = "clarify_intent"
        
        state["rag_context"] = (
            "عذراً، لم أتمكن من فهم طلبك بوضوح. يمكنني مساعدتك في:\n\n"
            "1️⃣ الإجابة على الاستفسارات العامة عن النادي\n"
            "2️⃣ حجز الخدمات المختلفة\n"
            "3️⃣ تعديل أو إلغاء الحجوزات الموجودة\n"
            "4️⃣ تسجيل الشكاوى والملاحظات\n"
            "5️⃣ الاستفسار عن معلومات العضوية\n\n"
            "يرجى إخباري كيف يمكنني مساعدتك اليوم؟"
        )
        
        logger.info("طلب توضيح من العميل")
        return state
    
    def escalate_to_human(self, state: ConversationState) -> ConversationState:
        """تصعيد للعنصر البشري"""
        state["current_step"] = "escalate_to_human"
        
        escalation_id = f"ESC{datetime.now().strftime('%Y%m%d%H%M%S')}"
        state["rag_context"] = (
            f"تم تصعيد استفسارك للفريق المختص برقم {escalation_id}. "
            "سيتواصل معك أحد أعضاء فريق خدمة العملاء قريباً. شكراً لصبرك."
        )
        
        logger.info(f"تم تصعيد المحادثة - رقم {escalation_id}")
        return state
    
    def generate_response(self, state: ConversationState) -> ConversationState:
        """توليد الاستجابة"""
        if not state.get("messages"):
            return state
        
        query = state["messages"][-1]["content"]
        context = state.get("rag_context", "")
        additional_info = f"الخطوة الحالية: {state.get('current_step', 'غير محدد')}"
        
        try:
            prompt = self.response_generator_template.format_messages(
                context=context,
                query=query,
                additional_info=additional_info
            )
            
            response = self.llm.invoke(prompt)
            
            # إضافة الرد إلى المحادثة
            if "messages" not in state:
                state["messages"] = []
            
            state["messages"].append({
                "role": "assistant",
                "content": response.content,
                "timestamp": datetime.now().isoformat()
            })
            
            logger.info("تم توليد الاستجابة بنجاح")
            
        except Exception as e:
            logger.error(f"خطأ في توليد الاستجابة: {e}")
            error_response = "عذراً، حدث خطأ تقني. يرجى المحاولة مرة أخرى أو التواصل مع فريق الدعم."
            
            state["messages"].append({
                "role": "assistant",
                "content": error_response,
                "timestamp": datetime.now().isoformat()
            })
        
        return state
    
    def evaluate_satisfaction(self, state: ConversationState) -> ConversationState:
        """تقييم رضا العميل"""
        state["current_step"] = "evaluate_satisfaction"
        
        # منطق بسيط لتقييم الرضا (يمكن تطويره أكثر)
        if state.get("requires_escalation", False):
            state["satisfaction_score"] = 2  # منخفض
        elif state.get("current_intent") == IntentType.COMPLAINT.value:
            state["satisfaction_score"] = 3  # متوسط
        else:
            state["satisfaction_score"] = 4  # عالي
        
        logger.info(f"تقييم الرضا: {state.get('satisfaction_score', 0)}")
        return state
    
    # دوال التوجيه
    def route_by_intent(self, state: ConversationState) -> str:
        """توجيه المحادثة حسب النية"""
        intent = state.get("current_intent", "")
        
        if intent == IntentType.GENERAL_INQUIRY.value:
            return "general_inquiry"
        elif intent == IntentType.SERVICE_BOOKING.value:
            return "service_booking"
        elif intent == IntentType.BOOKING_MODIFICATION.value:
            return "booking_modification"
        elif intent == IntentType.COMPLAINT.value:
            return "complaint"
        elif intent == IntentType.MEMBERSHIP_INQUIRY.value:
            return "membership_inquiry"
        else:
            return "unclear"
    
    def check_escalation(self, state: ConversationState) -> str:
        """فحص الحاجة للتصعيد"""
        if state.get("requires_escalation", False):
            return "escalate"
        return "continue"
    
    # دوال المساعدة
    def authenticate_customer(self, phone_or_email: str) -> Optional[str]:
        """التحقق من هوية العميل"""
        for customer_id, customer in self.customers_db.items():
            if customer["phone"] == phone_or_email or customer["email"] == phone_or_email:
                return customer_id
        return None
    
    def log_conversation(self, state: ConversationState):
        """تسجيل المحادثة"""
        log_data = {
            "session_id": state.get("session_id", ""),
            "customer_id": state.get("customer_id"),
            "intent": state.get("current_intent"),
            "satisfaction_score": state.get("satisfaction_score"),
            "escalated": state.get("requires_escalation", False),
            "timestamp": datetime.now().isoformat(),
            "message_count": len(state.get("messages", []))
        }
        
        # في البيئة الحقيقية، سيتم حفظ هذا في قاعدة البيانات
        logger.info(f"تم تسجيل المحادثة: {json.dumps(log_data, ensure_ascii=False)}")
    
    # الدالة الرئيسية للتعامل مع الرسائل
    async def handle_message(self, message: str, session_id: str, customer_id: Optional[str] = None) -> str:
        """التعامل مع رسالة جديدة"""
        try:
            # إعداد الحالة الأولية
            config = {"configurable": {"thread_id": session_id}}
            
            # الحصول على الحالة الحالية أو إنشاء حالة جديدة
            current_state = {
                "messages": [{"role": "user", "content": message, "timestamp": datetime.now().isoformat()}],
                "session_id": session_id,
                "customer_id": customer_id,
                "language": "ar",
                "current_step": "start",
                "requires_escalation": False
            }
            
            # تشغيل الرسم البياني
            result = await self.app.ainvoke(current_state, config)
            
            # تسجيل المحادثة
            self.log_conversation(result)
            
            # إرجاع آخر رد من المساعد
            assistant_messages = [msg for msg in result.get("messages", []) if msg["role"] == "assistant"]
            
            if assistant_messages:
                return assistant_messages[-1]["content"]
            else:
                return "عذراً، حدث خطأ في معالجة طلبك. يرجى المحاولة مرة أخرى."
                
        except Exception as e:
            logger.error(f"خطأ في معالجة الرسالة: {e}")
            return "عذراً، حدث خطأ تقني. يرجى المحاولة مرة أخرى لاحقاً."

# مثال على الاستخدام
async def main():
    """مثال على استخدام نظام خدمة العملاء"""
    # إعداد النظام
    chatbot = CustomerServiceChatbot(
        gemini_api_key="AIzaSyCTHPLed8JBzi1vhgKnWF44lYA1lbhLhUQ",
        knowledge_base_path="knowledge_base.txt"
    )
    
    # محاكاة محادثة
    session_id = "session_001"
    customer_id = "12345"  # اختياري
    
    messages = [
        "السلام عليكم، أريد معلومات عن خدمات النادي",
        "أريد حجز جلسة تدريب شخصي",
        "ما هي حالة عضويتي الحالية؟",
    ]
    
    for message in messages:
        print(f"العميل: {message}")
        response = await chatbot.handle_message(message, session_id, customer_id)
        print(f"المساعد: {response}")
        print("-" * 50)

if __name__ == "__main__":
    import asyncio
    print('Start')
    asyncio.run(main())
