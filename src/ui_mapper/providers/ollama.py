"""Ollama local VLM provider."""

from __future__ import annotations
import logging
from typing import Any

from .base import VLMProvider

log = logging.getLogger(__name__)

# Vision models ordered by quality (best first)
VISION_MODELS_BY_VRAM = [
    # (model_name, min_vram_gb, quality_description)
    ("qwen3-vl:8b", 8, "Best quality, newest"),
    ("qwen2.5-vl:7b", 8, "Excellent OCR and UI understanding"),
    ("gemma3:4b", 6, "Good balance, Google's efficient model"),
    ("qwen2.5-vl:3b", 4, "Good quality, fast"),
    ("qwen3-vl:2b", 4, "Decent quality, very fast"),
    ("moondream:1.8b", 2, "Basic, runs on anything"),
]


class OllamaProvider(VLMProvider):
    """Local Ollama VLM provider.

    Auto-detects installed models and picks the best available.
    Falls back gracefully if Ollama isn't running.
    """

    def __init__(self, host: str = "http://localhost:11434", model: str = "auto"):
        self._host = host
        self._requested_model = model
        self._active_model: str | None = None
        self._client: Any = None
        self._available: bool | None = None

    def _ensure_client(self) -> bool:
        """Lazy init: try to connect to Ollama."""
        if self._client is not None:
            return True
        try:
            import ollama
            self._client = ollama.Client(host=self._host)
            # Test connection
            self._client.list()
            return True
        except ImportError:
            log.warning("ollama package not installed. Run: pip install ui-mapper[ollama]")
            return False
        except Exception as e:
            log.warning(f"Cannot connect to Ollama at {self._host}: {e}")
            return False

    def _resolve_model(self) -> str | None:
        """Find the best available vision model."""
        if self._active_model:
            return self._active_model

        if not self._ensure_client():
            return None

        if self._requested_model != "auto":
            self._active_model = self._requested_model
            return self._active_model

        # List installed models
        try:
            response = self._client.list()
            installed = {m.model for m in response.models} if hasattr(response, 'models') else set()
            # Also try older API format
            if not installed and isinstance(response, dict):
                installed = {m.get("name", "") for m in response.get("models", [])}
        except Exception:
            installed = set()

        # Pick best installed vision model
        for model_name, _min_vram, desc in VISION_MODELS_BY_VRAM:
            # Check both exact and prefix match (ollama uses name:tag format)
            base_name = model_name.split(":")[0]
            for inst in installed:
                if inst == model_name or inst.startswith(base_name + ":"):
                    self._active_model = inst
                    log.info(f"Selected Ollama model: {inst} ({desc})")
                    return self._active_model

        log.warning(f"No vision models found in Ollama. Installed: {installed}")
        return None

    def query_text(self, prompt: str) -> str:
        model = self._resolve_model()
        if not model:
            raise RuntimeError("No Ollama vision model available")
        response = self._client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.message.content

    def query_vision(self, prompt: str, image: bytes) -> str:
        model = self._resolve_model()
        if not model:
            raise RuntimeError("No Ollama vision model available")

        import base64
        img_b64 = base64.b64encode(image).decode("utf-8")

        response = self._client.chat(
            model=model,
            messages=[{
                "role": "user",
                "content": prompt,
                "images": [img_b64],
            }],
        )
        return response.message.content

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        self._available = self._resolve_model() is not None
        return self._available

    def remaining_quota(self) -> int | None:
        return None  # Unlimited (local)

    def provider_name(self) -> str:
        model = self._active_model or self._requested_model
        return f"Ollama ({model})"

    @staticmethod
    def recommend_model(vram_gb: float) -> str:
        """Recommend best vision model for given VRAM."""
        for model_name, min_vram, desc in VISION_MODELS_BY_VRAM:
            if vram_gb >= min_vram:
                return model_name
        return "moondream:1.8b"  # Always works
