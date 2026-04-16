"""Gemini API provider with multi-key rotation."""

from __future__ import annotations
import io
import time
import logging
from typing import Any

from .base import VLMProvider

log = logging.getLogger(__name__)


class GeminiProvider(VLMProvider):
    """Google Gemini API with automatic key rotation.

    Supports up to N API keys. When one hits a 429 (rate limit),
    it's marked with a cooldown and the next key is tried.
    """

    COOLDOWN_SECONDS = 65  # Wait slightly over 1 minute for RPM reset
    MODEL = "gemini-2.5-flash-lite-preview-06-17"

    def __init__(self, api_keys: list[str], model: str | None = None):
        self._keys = [k for k in api_keys if k]
        self._key_cooldowns: dict[int, float] = {}
        self._current_idx = 0
        self._model_name = model or self.MODEL
        self._clients: dict[int, Any] = {}
        self._genai = None

        if self._keys:
            try:
                import google.generativeai as genai
                self._genai = genai
            except ImportError:
                log.warning("google-generativeai not installed. Run: pip install ui-mapper[gemini]")

    def _get_client(self, key_idx: int) -> Any:
        """Get or create a Gemini client for the given key index."""
        if key_idx not in self._clients:
            self._genai.configure(api_key=self._keys[key_idx])
            self._clients[key_idx] = self._genai.GenerativeModel(self._model_name)
        return self._clients[key_idx]

    def _pick_key(self) -> int | None:
        """Find an available key (not in cooldown)."""
        now = time.time()
        for _ in range(len(self._keys)):
            idx = self._current_idx % len(self._keys)
            cooldown_until = self._key_cooldowns.get(idx, 0)
            if now >= cooldown_until:
                return idx
            self._current_idx += 1
        return None

    def _call(self, content: list[Any]) -> str:
        """Execute a Gemini API call with key rotation."""
        last_error = None
        for _attempt in range(len(self._keys)):
            idx = self._pick_key()
            if idx is None:
                break

            try:
                # Re-configure for this key
                self._genai.configure(api_key=self._keys[idx])
                model = self._genai.GenerativeModel(self._model_name)
                response = model.generate_content(content)
                return response.text
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "quota" in err_str or "rate" in err_str:
                    log.info(f"Gemini key {idx+1}/{len(self._keys)} rate-limited, rotating")
                    self._key_cooldowns[idx] = time.time() + self.COOLDOWN_SECONDS
                    self._current_idx = idx + 1
                    last_error = e
                else:
                    raise

        raise RuntimeError(
            f"All {len(self._keys)} Gemini keys exhausted. "
            f"Last error: {last_error}"
        )

    def query_text(self, prompt: str) -> str:
        return self._call([prompt])

    def query_vision(self, prompt: str, image: bytes) -> str:
        img_part = {"mime_type": "image/png", "data": image}
        return self._call([prompt, img_part])

    def is_available(self) -> bool:
        if not self._keys or not self._genai:
            return False
        return self._pick_key() is not None

    def remaining_quota(self) -> int | None:
        now = time.time()
        available = sum(1 for i in range(len(self._keys))
                       if now >= self._key_cooldowns.get(i, 0))
        if available == 0:
            return 0
        return available * 50  # Rough estimate per key

    def provider_name(self) -> str:
        return f"Gemini ({len(self._keys)} keys)"
