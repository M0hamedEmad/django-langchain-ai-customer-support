import os

import requests


class WhatsAppService:
    def __init__(
        self,
        base_url: str | None = None,
        access_token: str | None = None,
        session_id: str | None = None,
    ):
        self.base_url = (base_url or os.getenv("WHATSAPP_BASE_URL") or "").rstrip("/")
        self.access_token = access_token or os.getenv("WHATSAPP_TOKEN")
        self.session_id = session_id or os.getenv("WHATSAPP_SESSION_ID")
        if not self.base_url or not self.access_token or not self.session_id:
            raise RuntimeError(
                "WhatsApp gateway not configured: set "
                "WHATSAPP_BASE_URL, WHATSAPP_TOKEN and WHATSAPP_SESSION_ID"
            )
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    def check_connection(self, timeout: int = 10):
        """Check if WhatsApp session is connected"""
        url = f"{self.base_url}/whatsapp/api/v1/session/{self.session_id}/check"
        response = requests.get(url, headers=self.headers, timeout=timeout)
        response.raise_for_status()
        return response.json()

    def get_messages(self, phone_number, limit=10, timeout: int = 10):
        """
        Get messages from specific phone number
        phone_number: WITHOUT + sign (e.g., '201234567890')
        """
        url = f"{self.base_url}/whatsapp/api/v1/chat/{phone_number}/messages"
        params = {
            "session_id": self.session_id,
            "limit": limit,
            "from_me": 0,  # Only received messages
        }
        response = requests.get(
            url, headers=self.headers, params=params, timeout=timeout
        )
        response.raise_for_status()
        return response.json()

    def send_message(self, phone_number, text, timeout: int = 10):
        """
        Send message to phone number
        phone_number: WITH + sign (e.g., '+201234567890')
        """
        url = f"{self.base_url}/whatsapp/api/v1/message/text/send"
        data = {"session_id": self.session_id, "receiver": phone_number, "text": text}
        response = requests.post(url, headers=self.headers, json=data, timeout=timeout)
        response.raise_for_status()
        return response.json()
