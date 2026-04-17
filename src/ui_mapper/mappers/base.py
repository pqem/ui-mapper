"""Abstract mapper interface."""

from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.types import UIMap
from ..core.config import AppConfig
from ..core.session import SessionState
from ..providers.base import VLMProvider

if TYPE_CHECKING:
    from ..core.watchdog import HardwareWatchdog


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
        watchdog: "HardwareWatchdog | None" = None,
        sessions_root: Path | None = None,
    ) -> UIMap:
        """Execute mapping and return discovered UI elements.

        Optional parameters (added in Phase 3a):
        - ``watchdog``: when provided, long-running mappers should call
          ``watchdog.report_progress()`` on each completed unit of work
          and honor ``should_pause`` / ``should_abort`` between units.
        - ``sessions_root``: directory where mappers may persist debug
          artifacts (screenshots, VLM exchanges). When ``None``, no
          artifacts are written.
        """

    @abstractmethod
    def get_priority(self) -> int:
        """Lower number = runs first. 10=LLM knowledge, 20=config, 30=UIA, 40=visual."""

    @abstractmethod
    def get_name(self) -> str:
        """Human-readable mapper name."""

    def estimate_duration(self, app_config: AppConfig) -> timedelta:
        """Estimate how long this mapper will take."""
        return timedelta(minutes=5)  # Default estimate
