"""Abstract mapper interface."""

from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import timedelta

from ..core.types import UIMap
from ..core.config import AppConfig
from ..core.session import SessionState
from ..providers.base import VLMProvider


class BaseMapper(ABC):
    """Interface for UI mapping strategies.

    Each mapper discovers UI elements using a different method.
    The orchestrator runs them in priority order and merges results.
    """

    @abstractmethod
    def can_map(self, app_config: AppConfig) -> bool:
        """Check if this mapper can work with the given app."""

    @abstractmethod
    def map(
        self,
        app_config: AppConfig,
        session: SessionState,
        provider: VLMProvider | None = None,
    ) -> UIMap:
        """Execute mapping and return discovered UI elements."""

    @abstractmethod
    def get_priority(self) -> int:
        """Lower number = runs first. 10=LLM knowledge, 20=config, 30=UIA, 40=visual."""

    @abstractmethod
    def get_name(self) -> str:
        """Human-readable mapper name."""

    def estimate_duration(self, app_config: AppConfig) -> timedelta:
        """Estimate how long this mapper will take."""
        return timedelta(minutes=5)  # Default estimate
