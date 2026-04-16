"""Abstract VLM provider interface."""

from __future__ import annotations
from abc import ABC, abstractmethod


class VLMProvider(ABC):
    """Interface for vision-language model providers.

    Every provider (Gemini, Ollama, OpenRouter) implements this.
    The ProviderManager selects and rotates between them.
    """

    @abstractmethod
    def query_text(self, prompt: str) -> str:
        """Send a text-only query and get a response."""

    @abstractmethod
    def query_vision(self, prompt: str, image: bytes) -> str:
        """Send an image + prompt and get a response."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is currently available."""

    @abstractmethod
    def remaining_quota(self) -> int | None:
        """Estimated remaining requests. None = unlimited (local)."""

    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name."""
