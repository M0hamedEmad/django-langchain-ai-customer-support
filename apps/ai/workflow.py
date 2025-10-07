import logging
import re
from typing import Optional

from langgraph.graph import StateGraph, END

import json
from datetime import datetime

# LangChain imports
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import HumanMessage

from langgraph.checkpoint.memory import MemorySaver


from .state import ConversationState, IntentType, IntentSubType

from .llm_providers import get_chat_model

from apps.ai.retrieval.arabic_preprocess import normalize_arabic
from apps.ai.retrieval.chroma_store import get_vectorstore
from apps.core.models import Service, Customer, Booking, WebSiteConfig

from langchain_core.tools import tool


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



class CustomerServiceChatbot:
    """نظام خدمة العملاء المتقدم"""

    def __init__(self, company=None):
        
        self.company = company


        web_config = WebSiteConfig.objects.filter().first()
        llm_provider = None
        llm_model = None
        p_llm_provider = None
        p_llm_model = None
        self.hardness = 5
                
        if web_config:
            llm_provider = web_config.llm_provider
            llm_model = web_config.get_llm_model()
            p_llm_provider = web_config.premium_llm_provider
            p_llm_model = web_config.get_pm_llm_model()
            self.hardness = web_config.hardness_score

        self.llm = get_chat_model(provider=llm_provider, model_name=llm_model)

        self.pm_llm = get_chat_model(provider=p_llm_provider, model_name=p_llm_model)

        self.setup_rag_system()
        
        self.setup_data()

        self.setup_templates()
        
        self.setup_conversation_graph()



    def setup_rag_system(self):
        try:
            self.vectorstore = get_vectorstore(self.company)
            
            
            logger.info("تم إعداد نظام RAG بنجاح")
        except Exception as e:
            logger.error(f"خطأ في إعداد نظام RAG: {e}")
            self.vectorstore = None        


    def setup_data(self):
        self.services_db = Service.objects.filter(company=self.company, is_active=True)

        self.services_info = "\n".join([
                f"id: {s.id}, name:{s.name}, price: {s.price}, description: {s.description}"
                for s in self.services_db
            ])

    
    def setup_templates(self):
        self.intent_classifier_template = ChatPromptTemplate.from_messages([
            ("system", """
            أنت مساعد ذكي لتحليل نوايا العملاء في شركة. حلل الرسالة التالية وحدد النية والنوع الفرعي ودرجة الثقة.
            حدد النوايا بناء على المحادثة الكلية و الرسالة و اختر نوع النية من النوايا المحتملة والأنواع الفرعية

            النوايا المحتملة والأنواع الفرعية:

            تأكد ان انوايا المحتملة  فقط:(استفسار_عام, حجز_خدمة, تعديل_حجز, شكوى, غير_واضح)
            
            1. استفسار_عام:
               - طلب_معلومات_عامة: أسئلة عامة عن الشركة أو ساعات العمل أو الموقع
               - طلب_معلومات_خدمة: أسئلة عن خدمة معينة أو أسعار أو تفاصيل
            
            2. حجز_خدمة:
               - طلب_حجز: العميل يريد حجز خدمة بشكل فعلي
               - تأكيد_طلب_الحجز: العميل يريد تأكيد حجز خدمة تأتي علي شكل رساله تأكيد وقلبها رساله طلب تأكيد 
               - طلب_معلومات_حجز: يسأل عن كيفية الحجز أو الأوقات المتاحة
            
            3. تعديل_حجز:
               - إلغاء_حجز: يريد إلغاء او تعديل حجز موجود او يريد ان يعرف معلومات كل  القديمه 
               - تعديل_معلومات_الحجز: يريد تغيير  معلومات الحجز
            
            4. شكوى:
               - استفسار_شكوى: يسأل عن كيفية تقديم شكوى أو متابعة شكوى
               - تقديم_شكوى: يقدم شكوى فعلية مع تفاصيل المشكلة
            
            5. غير_واضح: النية غير واضحة (استخدم هذا بحذر شديد) اذا كان السؤال غير واضح من المهم ان تراجه كل المخداثه السابقه للتحديد
            

            بعد ذالك استخرج معلومات إضافية اذا كانت متوفرة عن العميل مثل
            - الاسم
            - رقم الهاتف
            - العنوان
            - نوع الخدمة
            - تاريخ الحجز
            - رقم الحجز
            
            بعد ذالك عرف مدي صعوبة السؤال وتعقيده وهل يحتاج تفكير ام لا اذا كان مجرد سؤال بسيط واضح القيمة من 1 ال 10 حيث 10 صعب جدا
            اذا كان السؤال يحتاج اجابة محترفه او السؤال غير واضح معنه ان صعب اجعل القيمه 5 او اكبر

            اجب بصيغة JSON فقط بهذا الشكل:
            {{
                "intent": "النية_الرئيسية",
                "intent_type": "النوع_الفرعي",
                "confidence": 0.95,
                "hardness": 5,
                "customer": {{
                    "name": "اسم العميل",
                    "phone": "رقم الهاتف",
                    "address": "العنوان",
                    "service": "نوع الخدمة",
                    "booking_date": "تاريخ الحجز",
                    "booking_id": "رقم الحجز"
                }}
            }}
            
            درجة الثقة (confidence) يجب أن تكون رقم من 0 إلى 1:
            - 0.9-1.0: واضح جداً
            - 0.7-0.89: واضح
            - 0.5-0.69: متوسط الوضوح
            - أقل من 0.5: غير واضح

            معلومات عن الشركة التي تعمل فيها:
            {company_info}
            """),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "الرسالة: {message}")
        ])

        self.response_generator_template = ChatPromptTemplate.from_messages([
            ("system", """
            أنت موظف خدمة زبائن حبّاب وشاطر كلش بنظام الرد على أسئلة الزبائن.
            تساعد الزبائن بالعربي والإنجليزي، بس الأولوية للعربي للزبائن اللي يحچون عربي.
                        
            صفاتك الشخصية:
            - حبّاب، وصبور، وتفتهم
            - محترف بس بطريقة لطيفة وخليك ردودك رسمية بشكل كبير ولكن لطيفة
            - تستخدم تحيات وعبارات تواصل مناسبة لثقافتنا بدون مبالغه
            - تبيّن تعاطفك واهتمامك الصدوقي  بدون مبالغه
            - تحچي بطريقة طبيعية وسلسة
            - لا يجب ان تكون الاجابة طويلة 

            شغلك الأساسي:
            1. تشرح خدماتنا للزبائن
            2. تجاوب على أسئلتهم بخصوص الأسعار والمدة وإذا متوفرة أو لا
            3. ترشد الزبائن بعملية الحجز
            4. تاخذ المعلومات المطلوبة (الاسم، رقم التلفون، العنوان، نوع الخدمة)
            5. تأكد الحجوزات

          
            معلومات إضافية: {additional_info}


            سياق الحچي الحالي:
            - شنو يريد الزبون: {intent}
            - اللغة اللي يفضلها: {language}
            - وين واصلين بالحچي: {current_step}
            
           تعليمات:
            - إذا الزبون كتب بالعربي، جاوبه بالعربي
            - إذا كتب بالإنجليزي، جاوبه بالإنجليزي
            - كون متعاون ووجّه الزبون بطريقة سهلة وحبّابة
            - ابتعد عن الروتين والجمود، خليك لطيف
            - اتأكد من المعلومات قبل ما تثبّت الحجز
            - خلّي تنسيق الرسالة سهل للقراية ولا تضيّف هواي علامات 
            - بنهاية الرسالة، اسأل الزبون سؤال اختياري إذا أكو شي يأهله ينتقل للمرحلة الجاية بطريقة لطيفة.
            - في حاله العربي دائما تكلم بللهجه العراقي
            - اذا لم تسطيع تحديد نوع العميل كلمه بصيغه المذكر

            معلومات عن الشركة اللي تشتغل بيها:
            {company_info}
            """),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", """
                المعلومات الأساسية المهمة اللي تخص السؤال,   context: 
                   {context}

                السؤال: the question:
                    "{query}"

            """)
        ])
        

        self.matching_prompt = ChatPromptTemplate.from_messages([
            ("human", """
                أنت وكيل مطابقة خدمات دقيق وموضوعي. مهمتك هي قراءة طلب العميل ومطابقته بأفضل خدمة من قائمة الخدمات المقدمة.

                ## قائمة الخدمات المتاحة (Context):
                {formatted_services}

                ## السؤال:
                {query}

                ## قواعد الإخراج:
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
            """)
        ])

        self.booking_confirm_prompt = ChatPromptTemplate.from_messages([
            ("human", """
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
            """),
        ])


    def setup_conversation_graph(self):
        """
        Build a LangGraph StateGraph using the node functions.
        Some nodes require company/conversation context, supplied via closures.
        """
        workflow = StateGraph(ConversationState)

        workflow.add_node("receive_message", self.receive_message)
        workflow.add_node("analyze_intent", self.analyze_intent)

        workflow.add_node("handle_general_inquiry", self.handle_general_inquiry)
        
        workflow.add_node("handle_service_booking", self.handle_service_booking)
        workflow.add_node("confirm_booking", self.confirm_booking)
        workflow.add_node("execute_create_booking", self.execute_create_booking)
        
        
        workflow.add_node("handle_service_information", self.handle_service_information)

        workflow.add_node("handle_booking_modification", self.handle_booking_modification)
        workflow.add_node("handle_complaint", self.handle_complaint)
        workflow.add_node("clarify_intent", self.clarify_intent)        

        workflow.add_node("generate_response", self.generate_response)
        
        workflow.set_entry_point("receive_message")
        workflow.add_edge("receive_message", "analyze_intent")

        workflow.add_conditional_edges(
            "analyze_intent",
            self.route_by_intent,
            {
                "general_inquiry": "handle_general_inquiry",

                "service_booking": "handle_service_booking",
                "service_information": "handle_service_information",
                "booking_modification": "handle_booking_modification",

                "complaint": "handle_complaint",
                "unclear": "clarify_intent"
            }
        )
        workflow.add_conditional_edges(
            "handle_service_booking", 
             self.route_after_collection,
             {
                "confirm_booking": "confirm_booking",
                "generate_response": "generate_response",
                "execute_create_booking": "execute_create_booking",
             }
            )

        workflow.add_edge("handle_general_inquiry", "generate_response")
        workflow.add_edge("handle_service_information", "generate_response")
        workflow.add_edge("confirm_booking", "generate_response")
        workflow.add_edge("execute_create_booking", "generate_response")

        workflow.add_edge("handle_booking_modification", "generate_response")
        workflow.add_edge("handle_complaint", "generate_response")
        workflow.add_edge("clarify_intent", "generate_response")

        workflow.add_edge("generate_response", END)
        
        memory = MemorySaver()
        self.app = workflow.compile(checkpointer=memory)
        
        return self.app


    def generate_response(self, state: ConversationState) -> ConversationState:
        if not state.get("messages"):
            return state
        
        query = state["original_message"]
        context = state.get("rag_context", "")
        additional_info = f"الخطوة الحالية: {state.get('current_step', 'غير محدد')}"
        info = self.company.get_company_general_info()
        
        try:            
            prompt = self.response_generator_template.format_messages(
                chat_history=state["conversation_history"],
                context=context,
                query=query,
                additional_info=additional_info,
                company_info=info,
                intent=state.get("current_intent", "غير محدد"),
                language=state.get("language", "ar"),
                current_step=state.get("current_step", "غير محدد")
            )
            
            if self.hardness > 4 or state["intent_confidence"] < 0.7:
                response = self.pm_llm.invoke(prompt)
            else:
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
    

    def receive_message(self, state: ConversationState) -> ConversationState:   
        messages = state.get('messages', [])[-1] if state.get('messages') else 'لا توجد رسائل'
        
        try:
            messages = normalize_arabic(messages['content'])
        except Exception as e:
            print(e)

        logger.info(f"تم استقبال رسالة جديدة: {messages}")
        state["current_step"] = "receive_message"

        return state
    

    def analyze_intent(self, state: ConversationState) -> ConversationState:
        if not state.get("messages"):
            state["current_intent"] = IntentType.UNCLEAR.value
            state["intent_type"] = IntentSubType.UNCLEAR.value
            state["intent_confidence"] = 0.0
            return state
        
        last_message = state["original_message"]
        info = self.company.get_company_general_info()

        try:
            chat_history = state.get("conversation_history", [])
            prompt = self.intent_classifier_template.format_messages(
                message=last_message, company_info=info, chat_history=chat_history)
            response = self.llm.invoke(prompt)
            response_text = response.content.strip()
            
            try:
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                if json_start != -1 and json_end > json_start:
                    json_text = response_text[json_start:json_end]
                    intent_data = json.loads(json_text)
                    
                    intent = intent_data.get("intent", "")
                    intent_type = intent_data.get("intent_type", "")
                    customer = intent_data.get("customer", {})
                    confidence = float(intent_data.get("confidence", 0.5))
                    self.hardness = float(intent_data.get("hardness", 5))
                    
                    valid_intents = [e.value for e in IntentType]
                    valid_intent_types = [e.value for e in IntentSubType]
                    
                    if intent in valid_intents:
                        state["current_intent"] = intent
                    else:
                        state["current_intent"] = IntentType.UNCLEAR.value
                        
                    if intent_type in valid_intent_types:
                        state["intent_type"] = intent_type
                    else:
                        state["intent_type"] = IntentSubType.UNCLEAR.value
                    
                    state["intent_confidence"] = max(0.0, min(1.0, confidence))

                    if customer:
                        state["customer_name"] = customer.get("name") or state.get("customer_name", None)
                        state["customer_phone"] = customer.get("phone") or state.get("customer_phone", None)
                        # state["customer_address"] = customer.get("address") or state.get("customer_address", None)
                        state["selected_service"] = customer.get("service") or state.get("selected_service", None)
                        state["booking_date"] = customer.get("booking_date") or state.get("booking_date", None)
                        state["booking_id"] = customer.get("booking_id") or state.get("booking_id", None)

                    

                else:
                    raise ValueError("لم يتم العثور على JSON في الاستجابة")
                    
            except (json.JSONDecodeError, ValueError) as json_error:
                logger.warning(f"فشل تحليل JSON، محاولة التحليل القديم: {json_error}")
                # الرجوع للطريقة القديمة
                intent = response_text
                valid_intents = [e.value for e in IntentType]
                if intent in valid_intents:
                    state["current_intent"] = intent
                else:
                    state["current_intent"] = IntentType.UNCLEAR.value
                state["intent_type"] = IntentSubType.UNCLEAR.value
                state["intent_confidence"] = 0.5

        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"خطأ في تحليل النية: {e}")
            state["current_intent"] = IntentType.UNCLEAR.value
            state["intent_type"] = IntentSubType.UNCLEAR.value
            state["intent_confidence"] = 0.0
        
        state["current_step"] = "analyze_intent"
        logger.info(f"تم تحديد النية: {state['current_intent']} | النوع: {state.get('intent_type')} | الثقة: {state.get('intent_confidence', 0):.2f} | الصعوبة: {self.hardness}")
        return state


    def handle_general_inquiry(self, state: ConversationState) -> ConversationState:
        state["current_step"] = "handle_general_inquiry"
        
        if not state.get("messages"):
            return state
        
        query = state["original_message"]
        
        # البحث في قاعدة المعرفة
        if self.vectorstore:
            relevant_docs = self.vectorstore.similarity_search(query)
            context = "\n\n".join([doc.page_content for doc in relevant_docs])
            state["rag_context"] = context
        else:
            state["rag_context"] = "معلومات عامة عن النادي الرياضي"
        
        logger.info("تم التعامل مع الاستفسار العام")
        return state


    def handle_service_information(self, state: ConversationState) -> ConversationState:
        state["current_step"] = "handle_service_information"
        
        if not state.get("messages"):
            return state
        
        query = state["original_message"]
        
        # البحث في قاعدة المعرفة
        if self.vectorstore:
            self.handle_general_inquiry(state)

            services_info = "\n".join([
                f"- {s['name']} : {s['price']} جنيه - {s['description']}"
                for s in self.services_db.values()
            ])

            state["rag_context"] = f"""
                {state["rag_context"]}

                الخدمات المتاحة: {services_info}
            """
        else:
            state["rag_context"] = "معلومات عامة عن النادي الرياضي"
        
        logger.info("تم التعامل مع الاستفسار العام")
        return state
        

    def handle_service_booking(self, state: ConversationState) -> ConversationState:
        state["current_step"] = "handle_service_booking"
        
        # Check what information is missing
        missing = []
        if not state.get("customer_name"):
            missing.append("name")
        if not state.get("customer_phone"):
            missing.append("phone")
        if not state.get("selected_service"):
            missing.append("service")

        state["missing_info"] = missing

        last_message = state["original_message"]
        
        phone_pattern = re.compile(r'\b\d{10,11}\b')
        phone_match = phone_pattern.search(last_message)
        if phone_match and not state.get("customer_phone"):
            state["customer_phone"] = phone_match.group()
            if "phone" in missing:
                missing.remove("phone")

        if not state.get("selected_service") and self.services_db:
            from rapidfuzz import process, fuzz  # type: ignore
            names = list(self.services_db.values_list("name", flat=True))
            if names:
                best = process.extractOne(last_message, names, scorer=fuzz.partial_ratio)
                if best and best[1] >= 70:
                    state["selected_service_id"] = best[0]

        
        if state.get("selected_service") and not state.get("selected_service_id") and self.services_db :
            from rapidfuzz import process, fuzz  # type: ignore
            names = list(self.services_db.values_list("name", flat=True))
            if names:
                best = process.extractOne(last_message, names, scorer=fuzz.partial_ratio)
                if best and best[1] >= 70:
                    state["selected_service_id"] = best[0]

        if missing:
            services_info = "\n".join([
                f"- {s['name']} : {s['price']} جنيه - {s['description']}"
                for s in self.services_db.values()
            ])
            
            state["rag_context"] = f"""            
            Missing information: {', '.join(missing)}
            
            Ask the customer politely for the missing information in a conversational way.
            If service is missing, list the available services with their numbers.

            الخدمات المتاحة: {services_info}
            """

        service_id = state.get("selected_service_id", None)
       
        if not service_id:
            service = self.get_service_object_with_llm(state)            
            
        state["service_object"] = None if not service else service.id
        return state


    def confirm_booking(self, state: ConversationState) -> ConversationState:
        """Ask for booking confirmation"""
        service = state.get("service_object", None)
        
        if service:
            service = Service.objects.filter(id=service).first()

        customer_name = state.get("customer_name", "")
        customer_phone = state.get("customer_phone", "")
        customer_address = state.get("customer_address", "")
        booking_date = state.get("booking_date", "")
        booking_id = state.get("booking_id", "")
        selected_service = state.get("selected_service", "")

        name = ""
        description = ""
        price = ""
        
        if service:
            name = service.name or selected_service
            description = service.description or ""
            price = service.price 

        formatted_context = f"""
            أنت مساعد آلي دقيق ومحترف. مهمتك هي عرض تفاصيل الحجز التالية للحصول على تأكيد نهائي من العميل. يجب عليك إتباع القواعد الشرطية الصارمة: لا تُدرج أي سطر أو جزء معلومات عن متغير فارغ.

            من المهم جدا ان تكون رسالتك بغرض طلب تأكيد الحجز من العميل وتتم بصيغة السؤال دائما

            تأكد من موضوع الاسم والرقم اذا وجدوا في رساله الرد .
            لا تسأل عن اي عنصر عير موجود في رساله الرد
            اجعل رساله الرد قصيرة

            1. رسالة البداية المخصصة:
            اختر رسالة بداية مناسبة

            2. ملخص تفاصيل الحجز والخدمة:
            نحن على وشك تأكيد حجزك رقم . يرجى مراجعة التفاصيل أدناه قبل التأكيد النهائي:

            أ. معلومات العميل والحجز:
            {"- رقم الحجز:" if booking_id else ""} {booking_id}
            {"- العميل:" if customer_name else ""} {customer_name}
            {"- رقم التواصل:" if customer_phone else ""} {customer_phone}
            {"- التاريخ والوقت:" if booking_date else ""} {booking_date}
            {"- موقع الخدمة:" if customer_address else ""} {customer_address}

            ب. تفاصيل الخدمة:
            - الخدمة المحجوزة: {name}
            - [إذا كانت description]: وصف الخدمة: {description}
            - [إذا كانت price]: التكلفة: {price}

            3. السؤال النهائي للتأكيد:
            "هل المعلومات المذكورة أعلاه صحيحة وتؤكد المضي قدماً في الحجز؟ (يرجى الرد بنعم للتأكيد)"

            4. رسالة الختام المخصصة:
            اختر رسالة نهاية مناسبة
        """
        state["rag_context"] = formatted_context

        return state


    def execute_create_booking(self, state: ConversationState) -> ConversationState:
        """Handle booking creation"""
        state["current_step"] = "execute_create_booking"
        service = state.get("service_object", None)
        
        if service:
            service = Service.objects.filter(id=service).first()

        customer = self.get_customer_object_with_llm(state)
        
        customer_name = state.get("customer_name", "")
        customer_phone = state.get("customer_phone", "")
        customer_address = state.get("customer_address", "")
        booking_date = state.get("booking_date", "")
        booking_id = state.get("booking_id", "")
        selected_service = state.get("selected_service", "")

        notes = f"""
            اسم العميل : {customer_name}
            رقم الهاتف : {customer_phone}
            العنوان : {customer_address}
            تاريخ الحجز : {booking_date}
            الخدمة : {selected_service}
        """

        booking = Booking.objects.create(
            company_id=state["company_id"],
            customer=customer,
            service=service,
            service_text=selected_service,
            status=Booking.Status.CONFIRMED,
            notes=notes,
            source=Booking.Source.CHAT,
            date=booking_date,
        )

        state["rag_context"] = f"""
            ارسال رساله لانها تم انشاء حجزك واضف هذه المعلومات.
            اذا كانت هناك معلومات فارغه لا تتضفها
            رقم الحجز : {booking.id}
            الخدمة : {selected_service if not service else service.name}
            تاريخ الحجز : {booking_date}
            العنوان : {customer_address}
            رقم الهاتف : {customer_phone}
            اسم العميل : {customer_name}
            
        """ 

        return state


    def handle_complaint(self, state: ConversationState) -> ConversationState:
        """التعامل مع الشكاوى"""
        state["current_step"] = "handle_complaint"
        
        if not state.get("messages"):
            return state
        
        complaint_text = state["original_message"]
        
        # تقييم خطورة الشكوى
        severity_keywords = {
            "عالية": ["خطر", "إصابة", "طبي", "طوارئ", "تسمم", "حريق"],
            "متوسطة": ["سوء معاملة", "خطأ", "تأخير", "رد أموال", "إلغاء"],
            "منخفضة": ["اقتراح", "تحسين", "ملاحظة", "استفسار"]
        }
        
        severity = "متوسطة"
        for level, keywords in severity_keywords.items():
            if any(keyword in complaint_text for keyword in keywords):
                severity = level
                break
        
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
    

    ## Routing functions
    def route_by_intent(self, state: ConversationState) -> str:
        """توجيه المحادثة حسب النية"""
        intent = state.get("current_intent", "")
        
        if intent == IntentType.GENERAL_INQUIRY.value:
            return self.route_general_inquiry(state)
        elif intent == IntentType.SERVICE_BOOKING.value:
            return self.route_service_booking(state)
        elif intent == IntentType.BOOKING_MODIFICATION.value:
            return "booking_modification"
        elif intent == IntentType.COMPLAINT.value:
            return "complaint"
        elif intent == IntentType.MEMBERSHIP_INQUIRY.value:
            return "membership_inquiry"
        else:
            return "unclear"


    def route_general_inquiry(self, state):
        intent_type = state.get("intent_type", "")
        
        if intent_type == IntentSubType.GENERAL_INFO_REQUEST.value:
            return "general_inquiry"
        elif intent_type == IntentSubType.SERVICE_INFO_REQUEST.value:
            return "service_information"
        
        return "general_inquiry"


    def route_service_booking(self, state):
        intent_type = state.get("intent_type", "")
        
        if intent_type == IntentSubType.BOOKING_REQUEST.value:
            return "service_booking"
        elif intent_type == IntentSubType.BOOKING_INFO_REQUEST.value:
            return "service_information"
        elif intent_type == IntentSubType.BOOKING_CONFIRMATION.value:
            return "service_booking"
        
        return "service_booking"
            

    def route_after_collection(self, state):
        missing = state.get("missing_info", [])

        if missing:
            return "generate_response"
        elif state.get("intent_type", "") == IntentSubType.BOOKING_CONFIRMATION.value:
            return "execute_create_booking"
        
        return "confirm_booking"


    ######## Booking modification ########

    def handle_booking_modification(self, state: ConversationState):
        result = self.analyze_request(state)

        action_type = result.get("action_type")
        booking_id = result.get("booking_id")
        edit_fields = result.get("edit_fields")
        rag_context = ""

        bookings_context = "Current bookings for the user:\n"
        for idx, booking in enumerate(state["user_bookings"], 1):
            bookings_context += f"\n{idx}. Booking #{booking['id']}:"
            bookings_context += f"\n   - Service: {booking['service']}"
            bookings_context += f"\n   - service_text: {booking['service_text']}"
            bookings_context += f"\n   - Date: {booking['date']}"
            bookings_context += f"\n   - Status: {booking['status']}"
            bookings_context += f"\n   - notes: {booking['notes']}"
            bookings_context += f"\n   - Can Cancel: {'Yes' if booking['is_cancellable'] else 'No'}"        

        if not action_type:
            rag_context = """
            مشكلة في تحدد نية العميل:
            لا أفهم الإجراء الذي تريد تنفيذه على حجوزاتك. هل يمكنك توضيحه أكثر واختيار أحد الخيارات التالية: 
                تعديل حجز محدد، أو إلغاء حجز محدد، أو إلغاء حجز الحجوزات، أو المعلومات المتعلقة بحجوزاتك.
                        
            """

        if not booking_id:
            rag_context += f"""
                تحديد الحجز المحدد:
                يمكنك اختيار أي من هذه الحجوزات.

                {bookings_context}

             """

        if not edit_fields and action_type == "edit":
            rag_context += """
                تحديد الحقل المحدد:
               الحقول التي تريد تعديلها

             """

        if rag_context:
            state["rag_context"] = rag_context
            return state

        # if action_type == "edit":
        #     return self.handle_edit_booking(state, booking_id, edit_fields)
        # elif action_type == "cancel":
        #     return self.handle_cancel_booking(state, booking_id)
        # elif action_type == "cancel_all":
        #     return self.handle_cancel_all_bookings(state)
        # elif action_type == "info":
        #     return self.handle_info_booking(state, booking_id)
        # elif action_type == "confirm previous booking":
        #     return self.handle_confirm_previous_booking(state)
        
        return state
        


    def analyze_request(self, state: ConversationState) -> ConversationState:
        """
        Analyze user request and determine action type.
        Provides context of all user bookings to LLM.
        """
        state["current_step"] = "clarify_intent"

        # Fetch user bookings for context
        customer = self.get_customer_object_with_llm(state)
        bookings = self.fetch_user_bookings(customer)

        if not bookings:
            state["rag_context"] = "I see you don't have any bookings yet. Would you like to make a new booking?"
            return state

        state["user_bookings"] = bookings
        
        # Build context message
        bookings_context = "Current bookings for the user:\n"
        for idx, booking in enumerate(state["user_bookings"], 1):
            bookings_context += f"\n{idx}. Booking #{booking['id']}:"
            bookings_context += f"\n   - Service: {booking['service']}"
            bookings_context += f"\n   - service_text: {booking['service_text']}"
            bookings_context += f"\n   - Date: {booking['date']}"
            bookings_context += f"\n   - Status: {booking['status']}"
            bookings_context += f"\n   - notes: {booking['notes']}"
            bookings_context += f"\n   - Can Cancel: {'Yes' if booking['is_cancellable'] else 'No'}"

        user_messete = state["original_message"]

        
        analysis_prompt = f"""
        Analyze the user's request and determine the action needed.
        
        {bookings_context}
        
        User's last message: {user_messete}
        
        Determine:
        1. Action type: 'edit', 'cancel', 'cancel_all', 'info'  or 'confirm previous booking'
        2. Which booking ID if specific booking mentioned user can choose more than booking so make it list [1,2,3] if user choose all make it all id in the ilist
        3. What fields to edit if editing
        
        Respond in JSON format.
        {{
            "action_type": "edit",
            "booking_id": 123,
            "edit_fields": ["date", "time"]
        }}
        """
        
        response = self.llm.invoke([HumanMessage(content=analysis_prompt)])
        
        # Parse LLM response and update state
        try:
            json_start = response.content.find('{')
            json_end = response.content.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_text = response.content[json_start:json_end]
                analysis = json.loads(json_text)

                state["action_type"] = analysis.get("action_type")
                if "booking_id" in analysis:
                    state["selected_booking"] = next(
                        (b for b in state["user_bookings"] if b["id"] == analysis["booking_id"]),
                        None
                    )
                if "edit_fields" in analysis:
                    state["edit_fields"] = analysis["edit_fields"]
            else:
                state["rag_context"] = ""
        except Exception:
            import traceback
            print(traceback.format_exc())
        
        return state    


    def fetch_user_bookings(self, customer):
        """
        Fetch all bookings for a specific user.
        Returns booking details with status information.
        """
        try:
            bookings = Booking.objects.filter(customer=customer, company=self.company).order_by('-created_at')
            
            if not bookings.exists():
                return []

            booking_list = []
            for booking in bookings:
                customer = None if booking.customer is None else booking.customer.id
                service = None if not booking.service else booking.service.id

                booking_list.append({
                    "id": booking.id,
                    "customer": customer,
                    "service": service,
                    "service_text": booking.service_text,
                    "status": booking.status,
                    "date": booking.date,
                    "notes": booking.notes,
                    "source": booking.source,
                    "created_at": booking.created_at,
                    "is_cancellable": booking.status not in ["completed", "cancelled"]
                })

            return booking_list
          
        except Exception as e:
            print(e)
            return []


    @tool
    def get_booking_details(self, state: ConversationState, booking_id: int) -> dict:
        """
        Get detailed information about a specific booking.
        Validates that the booking belongs to the user.
        """
        try:
            customer = self.get_customer_object_with_llm(state)
            booking = Booking.objects.get(id=booking_id, customer=customer, company=self.company)
            
            state["state"]["booking_context"] = {
                "success": True,
                "booking": {
                    "id": booking.id,
                    "customer": booking.customer,
                    "service": booking.service,
                    "service_text": booking.service_text,
                    "status": booking.status,
                    "date": booking.date,
                    "notes": booking.notes,
                    "source": booking.source,
                    "created_at": booking.created_at,
                    "is_editable": booking.status in ["created", "confirmed", "cancelled"],
                    "is_cancellable": booking.status not in ["completed", "cancelled"]
                }
            }
        except ObjectDoesNotExist:
            return {
                "success": False,
                "message": f"Booking #{booking_id} not found or doesn't belong to you.",
                "booking": None
            }
        

    @tool
    def cancel_booking(self, state: ConversationState, booking_id: int, reason: Optional[str] = None) -> dict:
        """
        Cancel a specific booking after validation.
        Only non-completed bookings can be cancelled.
        """
        try:
            with transaction.atomic():
                customer = self.get_customer_object_with_llm(state)
                booking = Booking.objects.select_for_update().get(
                    id=booking_id, 
                    customer=customer
                )
                
                if booking.status in ["completed", "cancelled"]:
                    return {
                        "success": False,
                        "message": f"Cannot cancel booking #{booking_id}. Status: {booking.status}"
                    }
                
                # Store previous status for rollback if needed
                previous_status = booking.status
                
                booking.status = "cancelled"
                booking.save()
                
                return {
                    "success": True,
                    "message": f"Booking #{booking_id} has been successfully cancelled.",
                    "previous_status": previous_status,
                    "booking_id": booking_id
                }
        except ObjectDoesNotExist:
            return {
                "success": False,
                "message": f"Booking #{booking_id} not found or doesn't belong to you."
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error cancelling booking: {str(e)}"
            }


    @tool
    def cancel_all_bookings(self, state: ConversationState) -> dict:
        """
        Cancel all active bookings for a user.
        Only cancels bookings that are not completed or already cancelled.
        """
        try:
            with transaction.atomic():
                customer = self.get_customer_object_with_llm(state)
                active_bookings = Booking.objects.select_for_update().filter(
                    customer=customer, company=self.company,
                ).exclude(status__in=["completed", "cancelled"])
                
                if not active_bookings.exists():
                    return {
                        "success": False,
                        "message": "You don't have any active bookings to cancel.",
                        "cancelled_count": 0
                    }
                
                count = active_bookings.count()
                booking_ids = list(active_bookings.values_list('id', flat=True))
                
                active_bookings.update(
                    status="cancelled",
                )
                
                return {
                    "success": True,
                    "message": f"Successfully cancelled {count} active booking(s).",
                    "cancelled_count": count,
                    "booking_ids": booking_ids
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error cancelling bookings: {str(e)}",
                "cancelled_count": 0
            }



    @tool
    def edit_booking(
        self,
        booking_id: int,
        date: Optional[str] = None,
        notes: Optional[str] = None,
        service: Optional[str] = None,
        state: ConversationState= None) -> dict:
        """
        Edit booking information after confirmation.
        Only editable fields can be modified.
        """
        try:
            with transaction.atomic():
                customer = self.get_customer_object_with_llm(state)

                booking = Booking.objects.select_for_update().get(
                    id=booking_id,
                    customer=customer
                )
                
                if booking.status not in ["pending", "confirmed"]:
                    return {
                        "success": False,
                        "message": f"Cannot edit booking #{booking_id}. Current status: {booking.status}"
                    }
                
                changes = {}

                # Update fields if provided
                if date:
                    try:
                        booking.date = new_date
                        changes["date"] = date
                    except ValueError:
                        return {
                            "success": False,
                            "message": "Invalid date format. Use YYYY-MM-DD."
                        }
                
                
                if notes is not None:
                    booking.notes = notes
                    changes["notes"] = notes
                
                if service is not None:
                    booking.service = service
                    changes["service"] = service
                
                if changes:
                    booking.save()
                    
                    return {
                        "success": True,
                        "message": f"Booking #{booking_id} has been successfully updated.",
                        "changes": changes,
                        "booking_id": booking_id
                    }
                else:
                    return {
                        "success": False,
                        "message": "No changes were provided."
                    }
        
        except ObjectDoesNotExist:
            return {
                "success": False,
                "message": f"Booking #{booking_id} not found or doesn't belong to you."
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error updating booking: {str(e)}"
            }

    ##### utilites

    def get_customer_object_with_llm(self, state: ConversationState):
        """Fetch customer object using LLM"""
        customer_id = state.get("customer_id", None)

        if customer_id:
            try:
                return Customer.objects.get(id=customer_id)
            except Exception as e:
                logger.error(f"Error fetching customer details: {e}")
                return None

        customer_phone = state.get("customer_phone", None)

        if customer_phone:
            try:
                return Customer.objects.get(phone=customer_phone)
            except Exception as e:
                logger.error(f"Error fetching customer details: {e}")
                return None
        
        return None


    def get_service_object_with_llm(self, state: ConversationState):
        """Fetch service object using LLM"""
        selected_service = state.get("selected_service", None)
        
        if not selected_service:
            return None


        prompt = self.matching_prompt.format_messages(
            query= selected_service,
            formatted_services= self.services_info
        )

        response = self.llm.invoke(prompt)
        response_text = response.content.strip()
        
        try:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_text = response_text[json_start:json_end]
                service_data = json.loads(json_text)
                
                service = service_data.get("service_id", "")
                confidence_score = service_data.get("confidence_score", 0)
                
                if service and confidence_score > 0.5:
                    return Service.objects.filter(id=service).first()
                
                return None
        except Exception:
            import traceback

            logger.error(f"Error parsing JSON response in service booking: {traceback.format_exc()}")
            return None


    def handle_message(self, message: str, session_id: str, customer_id: Optional[str] = None, init_state: Optional[ConversationState] = None) -> str:
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
            result = self.app.invoke(init_state or current_state, config)
            return result
            
      
                
        except Exception as e:
            import traceback
            logger.error(f"خطأ في معالجة الرسالة: {e}\n{traceback.format_exc()}")
            return "عذراً، حدث خطأ تقني. يرجى المحاولة مرة أخرى لاحقاً."







# def compile_workflow(*, company, conversation):
#     """
#     Build a LangGraph StateGraph using the node functions.
#     Some nodes require company/conversation context, supplied via closures.
#     """
#     g = StateGraph(GraphState)

#     # Wrappers to inject company/conversation
#     def _retrieve(state: Dict[str, Any]) -> Dict[str, Any]:
#         return nodes.retrieve(state, company=company)

#     def _booking_params(state: Dict[str, Any]) -> Dict[str, Any]:
#         return nodes.booking_params(state, company=company)

#     def _booking_execute(state: Dict[str, Any]) -> Dict[str, Any]:
#         return nodes.booking_execute(state, company=company, conversation=conversation)

#     def _escalate(state: Dict[str, Any]) -> Dict[str, Any]:
#         return nodes.escalate(state, company=company, conversation=conversation)

#     # Add nodes
#     g.add_node("preprocess_ar", nodes.preprocess_ar)
#     g.add_node("customer_identifier", nodes.customer_identifier)
#     g.add_node("classify_intent", nodes.classify_intent)
#     g.add_node("retrieve", _retrieve)
#     g.add_node("generate_answer", nodes.generate_answer)
#     g.add_node("booking", nodes.booking)
#     g.add_node("booking_params", _booking_params)
#     g.add_node("booking_confirmation_handler", nodes.booking_confirmation_handler)
#     g.add_node("booking_execute", _booking_execute)
#     g.add_node("escalate", _escalate)
#     g.add_node("error_handler", nodes.error_handler)

#     # Entry
#     g.set_entry_point("preprocess_ar")

#     # Linear edges
#     g.add_edge("preprocess_ar", "customer_identifier")
#     g.add_edge("customer_identifier", "classify_intent")

#     # Conditional routing from classify_intent
#     def route_intent(state: Dict[str, Any]) -> str:
#         label = (state.get("intent") or {}).get("label")
#         return label or "FAQ"

#     g.add_conditional_edges(
#         "classify_intent",
#         route_intent,
#         {
#             "FAQ": "retrieve",
#             "SMALL_TALK": "generate_answer",
#             "BOOKING": "booking",
#             "ESCALATE": "escalate",
#         },
#     )

#     # Retrieval to answer
#     g.add_edge("retrieve", "generate_answer")

#     # Booking subgraph
#     g.add_edge("booking", "booking_params")

#     def route_params(state: Dict[str, Any]) -> str:
#         status = ((state.get("booking") or {}).get("params_status")) or "incomplete"
#         return status

#     g.add_conditional_edges(
#         "booking_params",
#         route_params,
#         {
#             "complete": "booking_confirmation_handler",
#             "incomplete": "generate_answer",
#         },
#     )

#     def route_confirmation(state: Dict[str, Any]) -> str:
#         confirmed = (((state.get("booking") or {}).get("confirmation") or {}).get("confirmed")) or False
#         return "confirmed" if confirmed else "not_confirmed"

#     g.add_conditional_edges(
#         "booking_confirmation_handler",
#         route_confirmation,
#         {
#             "confirmed": "booking_execute",
#             "not_confirmed": "generate_answer",
#         },
#     )

#     g.add_edge("booking_execute", "generate_answer")

#     # Terminal
#     g.add_edge("generate_answer", END)
#     g.add_edge("escalate", END)

#     return g.compile()









def handle_chat(message, session_id, customer_id, company, init_state=None):
    """
    Minimal orchestrator that mimics the LangGraph flow described in ARCHITECTURE.md.
    It executes nodes in sequence with conditional routing.

    Later this can be replaced with a real LangGraph StateGraph app.
    """
    try:
        chatbot = CustomerServiceChatbot(company=company)

        session_id = "session_001"
        customer_id = "12345"  # اختياري

        final_state = chatbot.handle_message(message, session_id, customer_id, init_state=init_state)
        return final_state  # includes answer/debug/intent/booking
    except Exception as e:  # safety net
        print(e)
        return e








