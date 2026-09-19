"""Telegram bot interface for Matchmaker Agent."""

import logging
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler as TGMessageHandler,
    filters,
)

from matchmaker.config import settings
from matchmaker.interfaces.base import MessageHandler

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot that interfaces with the Matchmaker agent."""

    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.telegram_bot_token
        if not self.token:
            raise ValueError("Telegram bot token not configured")

        self.handler = MessageHandler()
        self.application: Optional[Application] = None

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not update.effective_user or not update.message:
            return

        user_id = str(update.effective_user.id)

        welcome_message = """👋 Welcome to the Matchmaker Agent!

I'm here to help uncover challenges you face in your work and connect you with solutions from the ecosystem.

**How this works:**
1. I'll ask you some questions about your daily work
2. We'll identify pain points together
3. I'll search for existing solutions or propose new ones
4. You'll get a formal document you can share

**Commands:**
/start - Show this message
/restart - Start a new conversation
/status - Check conversation status

Ready? Tell me a bit about yourself and what you do."""

        await update.message.reply_text(welcome_message, parse_mode="Markdown")

        # Initialize conversation
        responses = await self.handler.handle_message(
            platform="telegram",
            user_id=user_id,
            message="[User started conversation]",
        )

        for response in responses:
            await update.message.reply_text(response)

    async def restart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /restart command."""
        if not update.effective_user or not update.message:
            return

        user_id = str(update.effective_user.id)
        response = await self.handler.restart_conversation("telegram", user_id)
        await update.message.reply_text(response)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        if not update.effective_user or not update.message:
            return

        user_id = str(update.effective_user.id)
        status = self.handler.get_conversation_status("telegram", user_id)

        status_text = f"""📊 **Conversation Status**

Active: {"Yes" if status["active"] else "No"}
Stage: {status["status"].replace("_", " ").title()}
Interview turns: {status["turns"]}"""

        await update.message.reply_text(status_text, parse_mode="Markdown")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle regular text messages."""
        if not update.effective_user or not update.message or not update.message.text:
            return

        user_id = str(update.effective_user.id)
        message = update.message.text

        # Show typing indicator
        await update.message.chat.send_action("typing")

        # Process message through agent
        responses = await self.handler.handle_message(
            platform="telegram",
            user_id=user_id,
            message=message,
        )

        # Send responses
        for response in responses:
            # Split long messages (Telegram limit is 4096 chars)
            if len(response) > 4000:
                chunks = [response[i : i + 4000] for i in range(0, len(response), 4000)]
                for chunk in chunks:
                    await update.message.reply_text(chunk)
            else:
                await update.message.reply_text(response)

    def build_application(self) -> Application:
        """Build the Telegram application."""
        self.application = Application.builder().token(self.token).build()

        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("restart", self.restart_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(
            TGMessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )

        return self.application

    def run(self) -> None:
        """Run the bot with polling."""
        app = self.build_application()
        logger.info("Starting Telegram bot...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


def run_telegram_bot():
    """Entry point to run the Telegram bot."""
    bot = TelegramBot()
    bot.run()
