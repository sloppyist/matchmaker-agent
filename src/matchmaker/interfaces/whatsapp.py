"""WhatsApp interface using Twilio for Matchmaker Agent."""

import logging
from typing import Optional

from fastapi import APIRouter, Form, Request, Response
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

from matchmaker.config import settings
from matchmaker.interfaces.base import MessageHandler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

# Global handler instance (initialized on first request)
_handler: Optional[MessageHandler] = None
_twilio_client: Optional[Client] = None


def get_handler() -> MessageHandler:
    """Get or create the message handler."""
    global _handler
    if _handler is None:
        _handler = MessageHandler()
    return _handler


def get_twilio_client() -> Optional[Client]:
    """Get or create the Twilio client."""
    global _twilio_client
    if _twilio_client is None:
        if settings.twilio_account_sid and settings.twilio_auth_token:
            _twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    return _twilio_client


class WhatsAppHandler:
    """WhatsApp handler using Twilio API."""

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
    ):
        self.account_sid = account_sid or settings.twilio_account_sid
        self.auth_token = auth_token or settings.twilio_auth_token
        self.from_number = from_number or settings.twilio_whatsapp_from

        if self.account_sid and self.auth_token:
            self.client = Client(self.account_sid, self.auth_token)
        else:
            self.client = None
            logger.warning("Twilio credentials not configured")

        self.message_handler = MessageHandler()

    async def send_message(self, to: str, body: str) -> bool:
        """Send a WhatsApp message via Twilio."""
        if not self.client:
            logger.error("Twilio client not configured")
            return False

        try:
            # Ensure WhatsApp format
            if not to.startswith("whatsapp:"):
                to = f"whatsapp:{to}"

            message = self.client.messages.create(
                body=body,
                from_=self.from_number,
                to=to,
            )
            logger.info(f"Sent WhatsApp message: {message.sid}")
            return True
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message: {e}")
            return False

    async def handle_incoming(self, from_number: str, body: str) -> list[str]:
        """Handle an incoming WhatsApp message."""
        # Extract phone number (remove whatsapp: prefix if present)
        user_id = from_number.replace("whatsapp:", "")

        # Check for commands
        if body.strip().lower() == "/restart":
            response = await self.message_handler.restart_conversation("whatsapp", user_id)
            return [response]

        if body.strip().lower() == "/status":
            status = self.message_handler.get_conversation_status("whatsapp", user_id)
            return [
                f"Status: {status['status'].replace('_', ' ').title()}\nInterview turns: {status['turns']}"
            ]

        # Process regular message
        responses = await self.message_handler.handle_message(
            platform="whatsapp",
            user_id=user_id,
            message=body,
        )

        return responses


@router.post("/webhook")
async def whatsapp_webhook(
    request: Request,
    From: str = Form(...),
    Body: str = Form(...),
) -> Response:
    """
    Webhook endpoint for incoming WhatsApp messages via Twilio.
    
    Configure this URL in your Twilio WhatsApp sandbox or production settings.
    """
    handler = get_handler()

    # Extract user ID from WhatsApp number
    user_id = From.replace("whatsapp:", "")

    # Check for commands
    body_lower = Body.strip().lower()

    if body_lower == "/restart":
        response_text = await handler.restart_conversation("whatsapp", user_id)
        responses = [response_text]
    elif body_lower == "/status":
        status = handler.get_conversation_status("whatsapp", user_id)
        responses = [
            f"Status: {status['status'].replace('_', ' ').title()}\nInterview turns: {status['turns']}"
        ]
    elif body_lower in ["/start", "hi", "hello", "hola"]:
        # Welcome message for new users
        welcome = """👋 Welcome to the Matchmaker Agent!

I help uncover challenges in your work and connect you with solutions.

Commands:
/restart - Start over
/status - Check progress

Tell me about yourself and your work!"""
        responses = [welcome]

        # Also initialize conversation
        init_responses = await handler.handle_message(
            platform="whatsapp",
            user_id=user_id,
            message="[User started conversation]",
        )
        responses.extend(init_responses)
    else:
        # Regular message processing
        responses = await handler.handle_message(
            platform="whatsapp",
            user_id=user_id,
            message=Body,
        )

    # Build TwiML response
    twiml = MessagingResponse()
    for response in responses:
        # WhatsApp has a 1600 char limit per message
        if len(response) > 1500:
            chunks = [response[i : i + 1500] for i in range(0, len(response), 1500)]
            for chunk in chunks:
                twiml.message(chunk)
        else:
            twiml.message(response)

    return Response(content=str(twiml), media_type="application/xml")


@router.get("/health")
async def health_check():
    """Health check endpoint for WhatsApp webhook."""
    return {"status": "ok", "service": "whatsapp"}
