"""Configuration management — loads YAML config and env vars."""

from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
MAPS_DIR = PROJECT_ROOT / "maps"
PROFILES_DIR = PROJECT_ROOT / "profiles"


@dataclass
class AppConfig:
    """Configuration for a specific application to map."""
    name: str
    display_name: str = ""
    process_name: str = ""          # Windows process name
    locale: str = "auto"            # "es", "en", "auto"
    platform: str = "windows"

    # Source hints
    config_files: list[str] = field(default_factory=list)   # Paths to parse
    source_repo: str = ""           # Git repo URL for open source apps
    docs_url: str = ""              # Official documentation URL

    # Visual mapper settings
    visual_enabled: bool = True
    screenshot_delay_ms: int = 500
    exploration_depth: str = "full"  # "quick", "standard", "full"

    # Extra metadata
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderConfig:
    """Configuration for VLM providers."""
    gemini_keys: list[str] = field(default_factory=list)
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "auto"      # "auto" = detect best by VRAM
    openrouter_key: str = ""
    preferred_order: list[str] = field(default_factory=lambda: ["gemini", "ollama"])


@dataclass
class Config:
    """Global ui-mapper configuration."""
    providers: ProviderConfig = field(default_factory=ProviderConfig)
    apps: dict[str, AppConfig] = field(default_factory=dict)
    maps_dir: str = str(MAPS_DIR)
    profiles_dir: str = str(PROFILES_DIR)
    log_level: str = "INFO"
    checkpoint_interval_sec: int = 300  # Save checkpoint every 5 min


def load_config() -> Config:
    """Load config from YAML files + environment variables."""
    config = Config()

    # Load default config
    default_path = CONFIG_DIR / "default.yaml"
    if default_path.exists():
        with open(default_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        _apply_raw_config(config, raw)

    # Load env vars (override YAML)
    _apply_env_vars(config)

    # Load app configs from config/apps/
    apps_dir = CONFIG_DIR / "apps"
    if apps_dir.exists():
        for app_file in apps_dir.glob("*.yaml"):
            app_name = app_file.stem
            with open(app_file, "r", encoding="utf-8") as f:
                app_raw = yaml.safe_load(f) or {}
            app_config = _build_app_config(app_name, app_raw)
            config.apps[app_name] = app_config

    return config


def _apply_raw_config(config: Config, raw: dict[str, Any]) -> None:
    """Apply raw YAML dict to config."""
    if "log_level" in raw:
        config.log_level = raw["log_level"]
    if "checkpoint_interval_sec" in raw:
        config.checkpoint_interval_sec = raw["checkpoint_interval_sec"]
    if "maps_dir" in raw:
        config.maps_dir = raw["maps_dir"]

    providers = raw.get("providers", {})
    if "preferred_order" in providers:
        config.providers.preferred_order = providers["preferred_order"]
    if "ollama_host" in providers:
        config.providers.ollama_host = providers["ollama_host"]
    if "ollama_model" in providers:
        config.providers.ollama_model = providers["ollama_model"]


def _apply_env_vars(config: Config) -> None:
    """Read API keys and settings from environment variables."""
    keys = []
    for i in range(1, 4):
        key = os.environ.get(f"GEMINI_API_KEY_{i}", "")
        if key:
            keys.append(key)
    # Also check the single-key env var
    single = os.environ.get("GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
    if single and single not in keys:
        keys.insert(0, single)
    config.providers.gemini_keys = keys

    ollama_host = os.environ.get("OLLAMA_HOST", "")
    if ollama_host:
        config.providers.ollama_host = ollama_host

    openrouter = os.environ.get("OPENROUTER_API_KEY", "")
    if openrouter:
        config.providers.openrouter_key = openrouter


def _build_app_config(name: str, raw: dict[str, Any]) -> AppConfig:
    """Build AppConfig from raw YAML dict."""
    return AppConfig(
        name=name,
        display_name=raw.get("display_name", name),
        process_name=raw.get("process_name", ""),
        locale=raw.get("locale", "auto"),
        platform=raw.get("platform", "windows"),
        config_files=raw.get("config_files", []),
        source_repo=raw.get("source_repo", ""),
        docs_url=raw.get("docs_url", ""),
        visual_enabled=raw.get("visual_enabled", True),
        screenshot_delay_ms=raw.get("screenshot_delay_ms", 500),
        exploration_depth=raw.get("exploration_depth", "full"),
        metadata=raw.get("metadata", {}),
    )
