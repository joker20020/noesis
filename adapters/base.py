"""Base chat adapter — shared by all platform adapters. Inspired by GA's AgentChatMixin."""
import asyncio
from abc import ABC, abstractmethod


class ChatAdapter(ABC):
    """Base class for platform adapters. Subclass must implement start/stop/send."""

    def __init__(self, engine, name: str = "adapter"):
        self._engine = engine
        self.name = name

    @abstractmethod
    async def start(self):
        """Start listening for messages."""

    @abstractmethod
    async def stop(self):
        """Stop the adapter."""

    async def handle_message(self, text: str, chat_id: str, prefix: str = "") -> str:
        """Process a user message through the agent engine. Returns agent response."""
        if not text or not text.strip():
            return ""
        session_id = f"{self.name}_{chat_id}"
        if prefix and text.startswith(prefix):
            text = text[len(prefix):].strip()
        if not text:
            return ""
        try:
            return await self._engine.run(text, session_id=session_id)
        except Exception as e:
            return f"Error: {e}"

    def abort(self):
        """Abort current agent task."""
        self._engine.abort()
