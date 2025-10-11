from django.core.management.base import BaseCommand
from apps.core.models import WhatsAppMessage, Company, Conversation, Message, Customer
from apps.api.whatsapp_service import WhatsAppService
from apps.ai.workflow import handle_chat
import time
import threading

class Command(BaseCommand):
    help = 'Check for new WhatsApp messages from specific number'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--phone',
            type=str,
            help='Phone number to monitor (without +)',
            required=True
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=10,
            help='Check interval in seconds (default: 10)'
        )

        parser.add_argument(
            '--company',
            type=str,
            help='Company API key to use for AI context',
            required=False
        )

        self.interval = None
        self.conv_open = False
    
    def _get_company(self) -> Company | None:
        """Pick a company context. Adjust if you need specific selection later."""
        if self.company:
            return Company.objects.get(api_key=self.company)
        return Company.objects.first()

    def _get_or_create_customer_and_conversation(self, company: Company, phone_number: str):
        """Ensure a Customer and a Conversation exist for this phone number."""
        customer, _ = Customer.objects.get_or_create(
            company=company,
            phone=phone_number,
            defaults={"name": "", "email": ""},
        )
        conv, _ = Conversation.objects.get_or_create(
            company=company,
            session_id=phone_number,
            defaults={"customer": customer},
        )
        if not conv.customer and customer:
            conv.customer = customer
            conv.save(update_fields=["customer"])
        return customer, conv

    def _build_init_state(self, company: Company, conv: Conversation, customer: Customer | None, message: str) -> dict:
        """Mirror ChatStreamView.post() state building."""
        recent = list(
            Message.objects.filter(conversation=conv).order_by("-created_at")[:8]
        )
        history = [
            {"role": m.role, "content": m.content}
            for m in reversed(recent)
        ]

        state = {
            "company_id": str(company.id),
            "session_id": conv.session_id,
            "original_message": message,
            "messages": [{"role": "user", "content": message}],
            "lang": company.language or "ar",
            "customer_id": None if not customer else customer.id,
            "customer_name": None if not customer else customer.name,
            "customer_phone": None if not customer else customer.phone,
            "conversation_history": history,
        }
        return state

    def _call_ai(self, company: Company, conv: Conversation, customer: Customer | None, message: str) -> str:
        """Create a user message, call the AI workflow, save assistant reply, and return text."""
        msg = Message.objects.create(
            conversation=conv,
            role=Message.Role.USER,
            content=message,
            meta={"lang": company.language or "ar"},
        )

        state = self._build_init_state(company, conv, customer, message)
        result = handle_chat(message, conv.session_id, 1, company, init_state=state)

        try:
            final_text: str = result["messages"][-1]["content"]  # type: ignore[index]

            Message.objects.create(
                conversation=conv,
                role=Message.Role.ASSISTANT,
                content=final_text,
                meta={"lang": company.language or "ar"},
            )
        except Exception:
            # rollback user message on failure to keep transcript clean
            if msg:
                msg.delete()
            final_text = str(result)

        return final_text

    def _process_new_messages(self, phone_number: str, created_batch: list[WhatsAppMessage], whatsapp: WhatsAppService):
        """Aggregate newly saved WhatsApp messages, get AI response, reply, and mark processed."""
        # Combine only non-empty texts
        combined_texts = [m.message_body.strip() for m in created_batch if (m.message_body or "").strip()]
        if not combined_texts:
            return

        combined_message = "\n".join(combined_texts)

        company = self._get_company()
        if not company:
            self.stdout.write(self.style.WARNING("No company found. Skipping AI response."))
            return

        customer, conv = self._get_or_create_customer_and_conversation(company, phone_number)

        # Get AI reply and send back on WhatsApp
        reply_text = self._call_ai(company, conv, customer, combined_message)
        try:
            # print(f"+{phone_number}", reply_text)
            whatsapp.send_message(f"+{phone_number}", reply_text)
            self.stdout.write(self.style.SUCCESS("Sent AI reply via WhatsApp."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to send WhatsApp message: {e}"))

        # Mark batch as processed
        WhatsAppMessage.objects.filter(pk__in=[m.pk for m in created_batch]).update(is_processed=True)

    def fire_and_forget(self, phone_number: str, created_batch: list[WhatsAppMessage], whatsapp: WhatsAppService):
        def send():
            try:
                self._process_new_messages(phone_number, created_batch, whatsapp)
            except Exception:
                pass  # ignore errors
        threading.Thread(target=send, daemon=True).start()


    def handle(self, *args, **options):
        phone_number = options['phone']
        interval = self.interval or options['interval']
        self.company = options['company']
        
        self.stdout.write(
            self.style.SUCCESS(f'Monitoring messages from: {phone_number}')
        )
        self.stdout.write(f'Checking every {interval} seconds...')
        self.stdout.write('Press Ctrl+C to stop\n')
        
        whatsapp = WhatsAppService()
        
        try:
            while True:
                # Get latest messages
                response = whatsapp.get_messages(phone_number, limit=4)
                
                if 'data' in response:
                    created_batch: list[WhatsAppMessage] = []
                    for index, msg in enumerate(response['data']):
                        
                        msg_id = msg.get('key', {}).get('id', '')
                        sender_name=msg.get('key', {}).get('remoteJid', '')
                        message_body=msg.get('content', {}).get('conversation', '')
                        timestamp=msg.get('messageTimestamp', 0)
                        for_me = msg.get('key', {}).get('fromMe')

                        if index==0 and for_me:
                            break
                        
                        if not message_body or not sender_name:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"Invalid message: {msg_id}"
                                )
                            )
                            continue

                        if for_me:
                            continue


                        # Check if message already exists
                        if not WhatsAppMessage.objects.filter(message_id=msg_id).exists():
                            # Save new message
                            wm = WhatsAppMessage.objects.create(
                                message_id=msg_id,
                                phone_number=phone_number,
                                sender_name=sender_name,
                                message_body=message_body,
                                timestamp=timestamp
                            )
                            created_batch.append(wm)
                            
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"New message: {msg.get('content', {}).get('conversation', '')[:50]}"
                                )
                            )
                            
                            self.interval = 5
                        else:
                            self.interval = None
                            
                            # Optional: Auto-reply
                            # whatsapp.send_message(f"+{phone_number}", "Thanks!")

                    # After saving new messages in this cycle, process them together
                    if created_batch:
                        self.fire_and_forget(phone_number, created_batch, whatsapp)
                        time.sleep(1)
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nStopped monitoring'))
