import os
import logging
import asyncio
from typing import Dict, List, Optional, Tuple
from collections import deque
from datetime import datetime

import requests
from dotenv import load_dotenv
from telegram import Update, Message
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
AGENT_ACCESS_ID = os.getenv('AGENT_ACCESS_ID')
BOT_TOKEN = os.getenv('BOT_TOKEN')
API_BASE_URL = 'https://agent.timeweb.cloud/api/v1/cloud-ai'
MAX_CONTEXT_SIZE = 10
REQUEST_TIMEOUT = 30


class ConversationManager:
    """Manages conversation context for each chat."""
    
    def __init__(self, max_size: int = MAX_CONTEXT_SIZE):
        self.max_size = max_size
        self.contexts: Dict[int, deque] = {}
        self.parent_ids: Dict[int, Optional[str]] = {}
    
    def add_message(self, chat_id: int, role: str, content: str, message_id: Optional[str] = None) -> None:
        """Add a message to the conversation context."""
        if chat_id not in self.contexts:
            self.contexts[chat_id] = deque(maxlen=self.max_size)
        
        self.contexts[chat_id].append({
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        })
        
        # Update parent message ID if this is an assistant response
        if role == 'assistant' and message_id:
            self.parent_ids[chat_id] = message_id
    
    def get_context(self, chat_id: int) -> List[Dict]:
        """Get conversation context for a chat."""
        if chat_id not in self.contexts:
            return []
        return list(self.contexts[chat_id])
    
    def get_parent_id(self, chat_id: int) -> Optional[str]:
        """Get the last assistant message ID for maintaining conversation flow."""
        return self.parent_ids.get(chat_id)
    
    def clear_context(self, chat_id: int) -> None:
        """Clear conversation context for a chat."""
        if chat_id in self.contexts:
            del self.contexts[chat_id]
        if chat_id in self.parent_ids:
            del self.parent_ids[chat_id]
        logger.info(f"Context cleared for chat {chat_id}")
    
    def format_context_for_prompt(self, chat_id: int) -> str:
        """Format conversation context as a string for the AI prompt."""
        context = self.get_context(chat_id)
        if not context:
            return ""
        
        formatted = "Previous conversation:\n"
        for msg in context:
            formatted += f"{msg['role'].capitalize()}: {msg['content']}\n"
        return formatted


class GPT5Client:
    """Client for interacting with the GPT-5 API."""
    
    def __init__(self, access_id: str, base_url: str):
        self.access_id = access_id
        self.base_url = base_url
        self.session = requests.Session()
    
    def call_agent(self, message: str, parent_message_id: Optional[str] = None) -> Tuple[str, str]:
        """
        Call the GPT-5 agent API.
        
        Returns:
            Tuple of (response_message, message_id)
        """
        url = f"{self.base_url}/agents/{self.access_id}/call"
        
        payload = {
            "message": message
        }
        
        if parent_message_id:
            payload["parent_message_id"] = parent_message_id
        
        try:
            response = self.session.post(
                url,
                json=payload,
                timeout=REQUEST_TIMEOUT,
                headers={
                    "Content-Type": "application/json"
                }
            )
            response.raise_for_status()
            
            data = response.json()
            return data.get("message", "No response"), data.get("id", "")
            
        except requests.exceptions.Timeout:
            logger.error("Request timeout")
            raise Exception("Request timed out. Please try again.")
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise Exception(f"Failed to get response from AI: {str(e)}")


class TelegramBot:
    """Main Telegram bot handler."""
    
    def __init__(self, token: str, gpt_client: GPT5Client):
        self.token = token
        self.gpt_client = gpt_client
        self.conversation_manager = ConversationManager()
        self.application = None
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        await update.message.reply_text(
            "Hello! I'm GPT-5 assistant bot. You can:\n"
            "• Send me a direct message\n"
            "• Use /ask <question> in groups\n"
            "• Mention me with @ in groups\n"
            "• Use /resetc to clear conversation context\n"
            "• Use /help for more information"
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        await update.message.reply_text(
            "Available commands:\n"
            "• /start - Initialize the bot\n"
            "• /ask <question> - Ask a question\n"
            "• /resetc - Clear conversation context\n"
            "• /help - Show this help message\n\n"
            "In groups, you can also mention me with @ to ask questions.\n"
            "I maintain context of the last 10 messages in each chat."
        )
    
    async def reset_context_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /resetc command to clear conversation context."""
        chat_id = update.effective_chat.id
        self.conversation_manager.clear_context(chat_id)
        await update.message.reply_text("Conversation context has been cleared.")
    
    async def ask_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /ask command."""
        if not context.args:
            await update.message.reply_text("Please provide a question after /ask command.")
            return
        
        question = ' '.join(context.args)
        await self.process_message(update, question)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle regular text messages and edited messages."""
        message = update.message or update.edited_message
        
        if message is None or not message.text:
            return
        
        # In private chat, respond to all messages
        if message.chat.type == 'private':
            await self.process_message(update, message.text)
        
        # In groups, only respond when mentioned
        elif message.chat.type in ['group', 'supergroup']:
            bot_username = context.bot.username
            if bot_username and f'@{bot_username}' in message.text:
                # Remove the mention from the text
                text = message.text.replace(f'@{bot_username}', '').strip()
                if text:
                    await self.process_message(update, text)
    
    async def process_message(self, update: Update, user_message: str) -> None:
        """Process user message and get AI response."""
        message = update.message or update.edited_message
        if message is None:
            logger.error("No message found in update")
            return
            
        chat_id = message.chat.id
        
        # Show typing indicator
        await message.chat.send_action(action="typing")
        
        try:
            # Add user message to context
            self.conversation_manager.add_message(chat_id, 'user', user_message)
            
            # Prepare the full prompt with context
            context_str = self.conversation_manager.format_context_for_prompt(chat_id)
            full_prompt = f"{context_str}\nCurrent message: {user_message}" if context_str else user_message
            
            # Get parent message ID for conversation continuity
            parent_id = self.conversation_manager.get_parent_id(chat_id)
            
            # Call GPT-5 API
            response_text, message_id = await asyncio.to_thread(
                self.gpt_client.call_agent,
                full_prompt,
                parent_id
            )
            
            # Add assistant response to context
            self.conversation_manager.add_message(chat_id, 'assistant', response_text, message_id)
            
            # Send response
            await message.reply_text(response_text)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await message.reply_text(
                f"Sorry, an error occurred: {str(e)}"
            )
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log errors and notify user."""
        logger.error(f"Update {update} caused error {context.error}")
        
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "An error occurred while processing your request. Please try again."
            )
    
    def run(self) -> None:
        """Start the bot."""
        # Create application
        self.application = Application.builder().token(self.token).build()
        
        # Register handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("resetc", self.reset_context_command))
        self.application.add_handler(CommandHandler("ask", self.ask_command))
        
        # Handle text messages
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        
        # Register error handler
        self.application.add_error_handler(self.error_handler)
        
        # Start the bot
        logger.info("Starting bot...")
        self.application.run_polling()


def main():
    """Main entry point."""
    # Validate environment variables
    if not AGENT_ACCESS_ID:
        logger.error("AGENT_ACCESS_ID not found in environment variables")
        exit(1)
    
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment variables")
        exit(1)
    
    # Initialize GPT-5 client
    gpt_client = GPT5Client(AGENT_ACCESS_ID, API_BASE_URL)
    
    # Initialize and run bot
    bot = TelegramBot(BOT_TOKEN, gpt_client)
    bot.run()


if __name__ == "__main__":
    main()