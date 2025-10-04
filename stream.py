import streamlit as st
import requests
import json
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="محادثة ذكية | فيتنس إكستريم العراق",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for RTL support and styling
st.markdown("""
<style>
    .stChatMessage {
        direction: rtl;
        text-align: right;
    }
    div[data-testid="stChatInput"] {
        direction: rtl;
    }
    .session-info {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 10px;
        margin: 10px 0;
        direction: rtl;
        text-align: right;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'phone_number' not in st.session_state:
    st.session_state.phone_number = ""
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'session_number' not in st.session_state:
    st.session_state.session_number = 1
if 'session_id' not in st.session_state:
    # Generate unique session ID based on timestamp
    st.session_state.session_id = f"sess-1"

# Function to save data to browser storage simulation
def save_to_storage():
    """Save phone and messages to session state (simulating browser storage)"""
    st.query_params.update({"user": st.session_state.phone_number})

# Function to load data from storage
def load_from_storage():
    """Load saved phone number from query params"""
    user_phone = st.query_params.get("user", "")
    if user_phone and not st.session_state.logged_in:
        st.session_state.phone_number = user_phone
        return True
    return False

# Function to send chat message to API
def send_chat_message(message, phone_number):
    """Send message to the API and get response"""
    url = "http://localhost:8000/api/v1/chat/stream"
    headers = {
        "X-Company-Key": "gym_2",
        "Content-Type": "application/json"
    }
    data = {
        "session_id": st.session_state.session_id,
        "message": message,
        "customer": {
            "phone": phone_number
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, stream=True)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        st.error(f"خطأ في الاتصال بالخادم: {str(e)}")
        return None

# Function to load old messages
def load_conversation_messages(session_id, phone_number):
    """Load previous conversation messages from API"""
    url = f"http://localhost:8000/api/v1/conversations/{session_id}/messages"
    headers = {
        "X-Company-Key": "gym_2",
        "Content-Type": "application/json"
    }
    params = {
        "customer_id": phone_number
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        messages = data.get('messages', [])
        
        # Convert to Streamlit message format
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        return formatted_messages
    except requests.exceptions.RequestException as e:
        print(f"Error loading messages: {str(e)}")
        return []

# Check for stored phone number on page load
if load_from_storage() and st.session_state.phone_number:
    st.session_state.logged_in = True
    # Load old messages when auto-login
    if not st.session_state.messages:
        old_messages = load_conversation_messages(
            st.session_state.session_id, 
            st.session_state.phone_number
        )
        if old_messages:
            st.session_state.messages = old_messages

# Sidebar
with st.sidebar:
    st.title("🔐 تسجيل الدخول")
    
    # Phone number input
    phone = st.text_input(
        "رقم الهاتف *",
        value=st.session_state.phone_number,
        placeholder="05xxxxxxxx أو +20xxxxxxxxxx",
        max_chars=20,
        key="phone_input"
    )
    
    # Login button
    if st.button("تسجيل الدخول", use_container_width=True):
        if phone and len(phone) >= 10:
            st.session_state.logged_in = True
            st.session_state.phone_number = phone
            
            # Load old messages after login
            old_messages = load_conversation_messages(
                st.session_state.session_id, 
                phone
            )
            if old_messages:
                st.session_state.messages = old_messages
            
            save_to_storage()
            st.success("تم تسجيل الدخول بنجاح!")
            st.rerun()
        else:
            st.error("الرجاء إدخال رقم هاتف صحيح")
    
    # Logout button and session info
    if st.session_state.logged_in:
        st.divider()
        st.success(f"مسجل الدخول: {st.session_state.phone_number}")
        
        # Session number display
        st.markdown(f"""
        <div class="session-info">
            <strong>رقم الجلسة:</strong> {st.session_state.session_number}<br>
            <strong>معرف الجلسة:</strong> {st.session_state.session_id}
        </div>
        """, unsafe_allow_html=True)
        
        
        if st.button("تسجيل الخروج", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.messages = []
            st.session_state.session_number = 1
            st.session_state.session_id = f"sess-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            st.query_params.clear()
            st.rerun()
    
    # Info section
    st.divider()
    st.markdown("### 📱 معلومات")
    st.info("مرحباً بك في خدمة المحادثة الذكية. الرجاء تسجيل الدخول للبدء.")

# Main chat interface
st.title("💬 محادثة ذكية")

if not st.session_state.logged_in:
    st.warning("⚠️ الرجاء تسجيل الدخول من القائمة الجانبية للبدء في المحادثة")
    st.stop()

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(f'<div style="direction: rtl; text-align: right;">{message["content"]}</div>', 
                   unsafe_allow_html=True)

# Chat input
if prompt := st.chat_input("اكتب رسالتك هنا..."):
    # Increment session number
    st.session_state.session_number += 1
    
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message
    with st.chat_message("user"):
        st.markdown(f'<div style="direction: rtl; text-align: right;">{prompt}</div>', 
                   unsafe_allow_html=True)
    
    # Get and display AI response
    with st.chat_message("assistant"):
        with st.spinner("جاري التفكير..."):
            response = send_chat_message(message=prompt, phone_number=st.session_state.phone_number)
            
            if response:
                try:
                    # Parse the response
                    response_data = response.json()
                    ai_message = response_data.get('message', 'عذراً، لم أستطع فهم الرد')
                    
                    # Display the message
                    st.markdown(f'<div style="direction: rtl; text-align: right;">{ai_message}</div>', 
                               unsafe_allow_html=True)
                    
                    # Add AI response to messages
                    st.session_state.messages.append({"role": "assistant", "content": ai_message})
                    
                except json.JSONDecodeError:
                    error_msg = "عذراً، حدث خطأ في معالجة الرد"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
                except Exception as e:
                    error_msg = f"حدث خطأ: {str(e)}"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
            else:
                error_msg = "عذراً، لم أتمكن من الاتصال بالخادم"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
    
    # Save to storage
    save_to_storage()
    
    st.rerun()

# Footer
st.markdown("---")
st.markdown(
    '<div style="text-align: center; color: #666; font-size: 0.85em;">تم تطوير هذا النظام بواسطة نظام المحادثة الذكية</div>', 
    unsafe_allow_html=True
)