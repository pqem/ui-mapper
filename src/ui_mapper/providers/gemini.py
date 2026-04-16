"""Gemini API provider with multi-key rotation."""

from __future__ import annotations
import time
import logging

from .base import VLMProvider

log = logging.getLogger(__name__)


class GeminiProvider(VLMProvider):
    """Google Gemini API with automatic key rotation.

    Supports up to N API keys. When one hits a 429 (rate limit),
    it's marked with a cooldown and the next key is tried.
    Supports both google-genai (new) and google-generativeai (legacy).
    """

    COOLDOWN_SECONDS = 65
    MODEL = "gemini-2.0-flash"

    def __init__(self, api_keys: list[str], model: str | None = None):
        self._keys = [k for k in api_keys if k]
        self._key_cooldowns: dict[int, float] = {}
        self._current_idx = 0
        self._model_name = model or self.MODEL
        self._api_module = None
        self._api_type = ""  # "new" or "legacy"

        if self._keys:
            self._load_api_module()

    def _load_api_module(self) -> None:
        """Try new google-genai first, fall back to legacy google-generativeai."""
        try:
            from google import genai
            self._api_module = genai
            self._api_type = "new"
            log.debug("Using google-genai (new API)")
            return
        except ImportError:
            pass

        try:
            import google.generativeai as genai
            self._api_module = genai
            self._api_type = "legacy"
            log.debug("Using google-generativeai (legacy API)")
            return
        except ImportError:
            pass

        log.warning(
            "No Gemini package found. Install one:\n"
            "  pip install google-genai          (recommended)\n"
            "  pip install google-generativeai    (legacy)"
        )

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

    def _call(self, prompt: str, image_bytes: bytes | None = None) -> str:
        """Execute a Gemini API call with key rotation."""
        last_error = None
        for _attempt in range(len(self._keys)):
            idx = self._pick_key()
            if idx is None:
                break

            try:
                if self._api_type == "new":
                    return self._call_new_api(idx, prompt, image_bytes)
                else:
                    return self._call_legacy_api(idx, prompt, image_bytes)
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
            f"All {len(self._keys)} Gemini keys exhausted. Last error: {last_error}"
        )

    def _call_new_api(self, key_idx: int, prompt: str, image_bytes: bytes | None) -> str:
        """Call using google-genai (new package)."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self._keys[key_idx])

        contents = []
        if image_bytes:
            contents.append(types.Part.from_bytes(data=image_bytes, mime_type="image/png"))
        contents.append(prompt)

        response = client.models.generate_content(
            model=self._model_name,
            contents=contents,
        )
        return response.text

    def _call_legacy_api(self, key_idx: int, prompt: str, image_bytes: bytes | None) -> str:
        """Call using google-generativeai (legacy package)."""
        import google.generativeai as genai

        genai.configure(api_key=self._keys[key_idx])
        model = genai.GenerativeModel(self._model_name)

        content = []
        if image_bytes:
            content.append({"mime_type": "image/png", "data": image_bytes})
        content.append(prompt)

        response = model.generate_content(content)
        return response.text

    def query_text(self, prompt: str) -> str:
        return self._call(prompt)

    def query_vision(self, prompt: str, image: bytes) -> str:
        return self._call(prompt, image)

    def is_available(self) -> bool:
        if not self._keys or not self._api_module:
            return False
        return self._pick_key() is not None

    def remaining_quota(self) -> int | None:
        now = time.time()
        available = sum(1 for i in range(len(self._keys))
                       if now >= self._key_cooldowns.get(i, 0))
        if available == 0:
            return 0
        return available * 50

    def provider_name(self) -> str:
        return f"Gemini ({len(self._keys)} keys, {self._api_type or 'not loaded'})"
