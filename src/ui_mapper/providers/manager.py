"""Provider manager — rotation and fallback between VLM providers."""

from __future__ import annotations
import logging
from typing import Any

from .base import VLMProvider
from .gemini import GeminiProvider
from .ollama import OllamaProvider
from ..core.config import ProviderConfig

log = logging.getLogger(__name__)


class ProviderManager(VLMProvider):
    """Manages multiple VLM providers with automatic fallback.

    Order: Gemini (key1 → key2 → key3) → Ollama local.
    If all Gemini keys are exhausted, falls back to Ollama.
    If Ollama is unavailable, raises an error.
    """

    def __init__(self, config: ProviderConfig):
        self._providers: list[VLMProvider] = []
        self._active: VLMProvider | None = None

        # Build provider chain based on config
        for provider_name in config.preferred_order:
            if provider_name == "gemini" and config.gemini_keys:
                self._providers.append(GeminiProvider(config.gemini_keys))
            elif provider_name == "ollama":
                self._providers.append(
                    OllamaProvider(host=config.ollama_host, model=config.ollama_model)
                )

        # If nothing configured, try ollama as last resort
        if not self._providers:
            self._providers.append(OllamaProvider())

    def _get_provider(self) -> VLMProvider:
        """Get the first available provider."""
        for provider in self._providers:
            if provider.is_available():
                if self._active is not provider:
                    log.info(f"Using provider: {provider.provider_name()}")
                    self._active = provider
                return provider
        raise RuntimeError(
            "No VLM provider available. Configure Gemini API keys or install Ollama. "
            "See .env.example for configuration."
        )

    def query_text(self, prompt: str) -> str:
        """Query with automatic fallback between providers."""
        errors = []
        for provider in self._providers:
            if not provider.is_available():
                continue
            try:
                return provider.query_text(prompt)
            except Exception as e:
                log.warning(f"{provider.provider_name()} failed: {e}")
                errors.append(f"{provider.provider_name()}: {e}")
        raise RuntimeError(f"All providers failed: {'; '.join(errors)}")

    def query_vision(self, prompt: str, image: bytes) -> str:
        """Query with image, automatic fallback between providers."""
        errors = []
        for provider in self._providers:
            if not provider.is_available():
                continue
            try:
                return provider.query_vision(prompt, image)
            except Exception as e:
                log.warning(f"{provider.provider_name()} failed: {e}")
                errors.append(f"{provider.provider_name()}: {e}")
        raise RuntimeError(f"All providers failed: {'; '.join(errors)}")

    def is_available(self) -> bool:
        return any(p.is_available() for p in self._providers)

    def remaining_quota(self) -> int | None:
        for p in self._providers:
            if p.is_available():
                q = p.remaining_quota()
                if q is None:
                    return None  # Unlimited (local)
                return q
        return 0

    def provider_name(self) -> str:
        if self._active:
            return self._active.provider_name()
        return "ProviderManager (no active provider)"

    def status_summary(self) -> dict[str, Any]:
        """Get status of all providers for display."""
        summary = {}
        for p in self._providers:
            summary[p.provider_name()] = {
                "available": p.is_available(),
                "quota": p.remaining_quota(),
            }
        return summary
