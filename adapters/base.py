"""Base class for chat platform adapters."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlatformMessage:
    session_id: str
    user_id: str
    content: str
    platform: str
    metadata: dict[str, Any] = field(default_factory=dict)


class PlatformAdapter(ABC):

    @abstractmethod
    async def start(self):
        """Start listening for messages."""

    @abstractmethod
    async def stop(self):
        """Stop the adapter."""

    @abstractmethod
    async def send(self, session_id: str, content: str):
        """Send a reply back to the platform."""
