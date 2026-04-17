"""User profile — preferences, hardware thresholds, provider config.

Loaded from ``~/.ui-mapper/profile.yaml`` (default) or overridden by
environment variable ``UI_MAPPER_PROFILE``. If the file is missing a
safe-mode profile is returned with conservative thresholds.

See docs/adr/004-hardware-watchdog.md for the rationale behind defaults.
"""

from __future__ import annotations
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Literal

import yaml


Budget = Literal["time", "cost", "quality", "balanced"]


# -----------------------------------------------------------------------------
# Thresholds and nested sections
# -----------------------------------------------------------------------------

@dataclass
class HardwareThresholds:
    """Watchdog limits. See ADR-004."""
    gpu_temp_soft: int = 75          # °C → pause
    gpu_temp_hard: int = 82          # °C → stop
    vram_soft_percent: int = 85      # % → pause
    vram_hard_percent: int = 95      # % → stop
    session_max_hours: float = 2.0   # safe-mode default
    stuck_detection_minutes: int = 15  # no progress + GPU idle → abort
    poll_interval_seconds: int = 30


@dataclass
class Preferences:
    budget: Budget = "balanced"
    language: str = "es"
    preferred_provider: str = "auto"
    safe_mode: bool = True           # first-run default


@dataclass
class GeminiConfig:
    api_keys: list[str] = field(default_factory=lambda: ["env:GOOGLE_API_KEY"])


@dataclass
class OllamaConfig:
    host: str = "localhost:11434"
    preferred_model: str = "auto"


@dataclass
class OpenRouterConfig:
    api_key: str = "env:OPENROUTER_API_KEY"
    preferred_model: str = "auto"


@dataclass
class Providers:
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    openrouter: OpenRouterConfig = field(default_factory=OpenRouterConfig)


# -----------------------------------------------------------------------------
# Profile
# -----------------------------------------------------------------------------

@dataclass
class Profile:
    preferences: Preferences = field(default_factory=Preferences)
    hardware_thresholds: HardwareThresholds = field(default_factory=HardwareThresholds)
    providers: Providers = field(default_factory=Providers)

    # ----- Serialization helpers -----

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Profile:
        prefs_data = data.get("preferences") or {}
        hw_data = data.get("hardware_thresholds") or {}
        prov_data = data.get("providers") or {}

        preferences = Preferences(
            budget=prefs_data.get("budget", "balanced"),
            language=prefs_data.get("language", "es"),
            preferred_provider=prefs_data.get("preferred_provider", "auto"),
            safe_mode=prefs_data.get("safe_mode", True),
        )
        hardware = HardwareThresholds(**{
            k: v for k, v in hw_data.items()
            if k in HardwareThresholds.__dataclass_fields__
        })
        providers = Providers(
            gemini=GeminiConfig(**(prov_data.get("gemini") or {})),
            ollama=OllamaConfig(**(prov_data.get("ollama") or {})),
            openrouter=OpenRouterConfig(**(prov_data.get("openrouter") or {})),
        )
        return cls(
            preferences=preferences,
            hardware_thresholds=hardware,
            providers=providers,
        )

    def resolve_env(self, value: str) -> str:
        """Resolve ``env:VAR_NAME`` placeholders."""
        if value.startswith("env:"):
            return os.environ.get(value[4:], "") or ""
        return value

    def graduate_from_safe_mode(self) -> None:
        """Loosen thresholds after a successful first sessions.

        Called by the CLI when the user explicitly confirms the tool
        behaves as expected. Raises limits to production values.
        """
        self.preferences.safe_mode = False
        self.hardware_thresholds.gpu_temp_soft = 80
        self.hardware_thresholds.gpu_temp_hard = 85
        self.hardware_thresholds.vram_soft_percent = 90
        self.hardware_thresholds.session_max_hours = 6.0


# -----------------------------------------------------------------------------
# Storage
# -----------------------------------------------------------------------------

def default_profile_path() -> Path:
    """Resolve the profile location. Honors ``UI_MAPPER_PROFILE`` env var."""
    override = os.environ.get("UI_MAPPER_PROFILE")
    if override:
        return Path(override)
    return Path.home() / ".ui-mapper" / "profile.yaml"


def load_profile(path: Path | None = None) -> Profile:
    """Load a profile from disk, or return a safe-mode default if missing."""
    target = path or default_profile_path()
    if not target.exists():
        return Profile()
    with target.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Profile.from_dict(data)


def save_profile(profile: Profile, path: Path | None = None) -> Path:
    """Persist a profile to disk. Creates parent directories if needed."""
    target = path or default_profile_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            profile.to_dict(),
            f,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
    return target
