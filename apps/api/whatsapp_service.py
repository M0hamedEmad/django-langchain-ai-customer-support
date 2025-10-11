import requests
import json

class WhatsAppService:
    def __init__(self):
        self.base_url = "https://almahd.technoplus.tech/"
        self.access_token = "23|Pw3A7VimquYUJEFizpvZxXYyKASodkb3JAdjyPQN45d41034"
        self.session_id = "190d46ce-d1be-4a8a-b2b1-f544b94d808d"
        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json'
        }
    
    
    def check_connection(self):
        """Check if WhatsApp session is connected"""
        url = f"{self.base_url}/whatsapp/api/v1/session/{self.session_id}/check"
        response = requests.get(url, headers=self.headers)
        return response.json()
    


    def get_messages(self, phone_number, limit=10):
        """
        Get messages from specific phone number
        phone_number: WITHOUT + sign (e.g., '201234567890')
        """
        url = f"{self.base_url}/whatsapp/api/v1/chat/{phone_number}/messages"
        params = {
            'session_id': self.session_id,
            'limit': limit,
            'from_me': 0  # Only received messages
        }
        response = requests.get(url, headers=self.headers, params=params)
        return response.json()
    

    def send_message(self, phone_number, text):
        """
        Send message to phone number
        phone_number: WITH + sign (e.g., '+201234567890')
        """
        url = f"{self.base_url}/whatsapp/api/v1/message/text/send"
        data = {
            "session_id": self.session_id,
            "receiver": phone_number,
            "text": text
        }
        response = requests.post(url, headers=self.headers, json=data)
        return response.json()


# api = WhatsAppService()
# # Note: Use phone number WITHOUT the '+' sign
# chat_id = "201099247834"  # NOT +201234567890

# # Get last 10 received messages
# messages = api.get_messages(
#     phone_number=chat_id,
#     limit=10,
# )

# for message in messages['data']:
#     print(f"From: {message.get('key', {}).get('fromMe')}")
#     print(f"Message: {message.get('content', {}).get('conversation')}")
#     print("---")