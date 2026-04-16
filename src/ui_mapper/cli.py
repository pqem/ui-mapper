"""CLI interface for ui-mapper."""

from __future__ import annotations
import sys
import logging
from pathlib import Path

import click

from .core.config import load_config, MAPS_DIR
from .core.session import SessionManager


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def main(verbose: bool) -> None:
    """ui-mapper: Automatic UI mapper for desktop applications."""
    _setup_logging("DEBUG" if verbose else "INFO")


@main.command()
def setup() -> None:
    """Detect hardware, check providers, and configure ui-mapper."""
    from .providers.hardware import detect_system

    click.echo("=== ui-mapper setup ===\n")

    # Detect hardware
    click.echo("Detecting hardware...")
    sys_info = detect_system()
    click.echo(f"  OS: {sys_info.os}")
    click.echo(f"  RAM: {sys_info.ram_gb} GB")

    if sys_info.gpu:
        click.echo(f"  GPU: {sys_info.gpu.name}")
        click.echo(f"  VRAM: {sys_info.gpu.vram_gb:.1f} GB")
        click.echo(f"  Driver: {sys_info.gpu.driver_version}")
    else:
        click.echo("  GPU: Not detected (CPU-only mode)")

    click.echo(f"\n  Recommended Ollama model: {sys_info.recommended_model}")

    # Check providers
    click.echo("\nChecking providers...")
    config = load_config()

    from .providers.manager import ProviderManager
    mgr = ProviderManager(config.providers)
    status = mgr.status_summary()

    for name, info in status.items():
        icon = "OK" if info["available"] else "UNAVAILABLE"
        quota = info["quota"]
        quota_str = f"quota={quota}" if quota is not None else "unlimited"
        click.echo(f"  [{icon}] {name} ({quota_str})")

    if not mgr.is_available():
        click.echo("\nNo providers available! Configure at least one:")
        click.echo("  1. Set GEMINI_API_KEY or GOOGLE_API_KEY env var")
        click.echo("  2. Install and start Ollama: ollama serve")
        click.echo("  See .env.example for details")

    # Check configured apps
    click.echo(f"\nConfigured apps: {len(config.apps)}")
    for name, app in config.apps.items():
        click.echo(f"  - {app.display_name} ({name})")

    click.echo("\nSetup complete!")


@main.command()
@click.argument("app_name")
@click.option("--no-resume", is_flag=True, help="Start fresh (don't resume)")
def map(app_name: str, no_resume: bool) -> None:
    """Map an application's UI. Example: ui-mapper map affinity-designer"""
    _setup_logging("INFO")

    config = load_config()

    if app_name not in config.apps:
        click.echo(f"Unknown app: {app_name}")
        click.echo(f"Available apps: {list(config.apps.keys())}")
        click.echo(f"\nAdd a config file at config/apps/{app_name}.yaml")
        sys.exit(1)

    from .providers.manager import ProviderManager
    from .mappers.orchestrator import MapperOrchestrator

    provider = ProviderManager(config.providers)
    orchestrator = MapperOrchestrator(config, provider)

    try:
        result = orchestrator.map(app_name, resume=not no_resume)
        click.echo(f"\nMapping complete!")
        click.echo(f"  Menus: {len(result.menus)}")
        click.echo(f"  Shortcuts: {len(result.shortcuts)}")
        click.echo(f"  Tools: {len(result.tools)}")
        click.echo(f"  Dialogs: {len(result.dialogs)}")
        click.echo(f"  Sources: {', '.join(result.sources)}")
        click.echo(f"  Coverage: ~{result.completion_pct:.0f}%")
        click.echo(f"\nMap saved to: maps/{app_name}/map.json")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
def status() -> None:
    """Show status of all mapping sessions."""
    config = load_config()
    session_mgr = SessionManager(config.maps_dir)
    sessions = session_mgr.list_sessions()

    if not sessions:
        click.echo("No mapping sessions found.")
        click.echo(f"Start one with: ui-mapper map <app-name>")
        return

    for s in sessions:
        from datetime import datetime
        started = datetime.fromtimestamp(s.started_at).strftime("%Y-%m-%d %H:%M") if s.started_at else "never"
        click.echo(f"\n  {s.app_name}")
        click.echo(f"    Status: {s.status}")
        click.echo(f"    Started: {started}")
        click.echo(f"    Completed mappers: {', '.join(s.completed_mappers) or 'none'}")
        click.echo(f"    Errors: {len(s.errors)}")


@main.command()
@click.argument("app_name")
def export(app_name: str) -> None:
    """Export a map to stdout (for piping to other tools)."""
    import json
    map_path = Path(MAPS_DIR) / app_name / "map.json"
    if not map_path.exists():
        click.echo(f"No map found for {app_name}. Run: ui-mapper map {app_name}", err=True)
        sys.exit(1)

    with open(map_path, "r", encoding="utf-8") as f:
        click.echo(f.read())


if __name__ == "__main__":
    main()
