"""FastMCP server that exposes a UIMap via stdio.

Run as:
    python -m ui_mapper serve <app-name>

The server is constructed eagerly (map is loaded, tools are registered)
and then handed to FastMCP which owns the event loop.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Any

from .driver import Driver
from .map_loader import load_map
from .tools import ToolSurface

log = logging.getLogger(__name__)


def build_server(map_path: Path, dry_run: bool = False):
    """Construct a FastMCP server bound to a single mapped application.

    Returns the ``FastMCP`` instance (which has ``.run()``). The import
    of ``mcp.server.fastmcp`` is lazy so that unit tests can import
    ``build_server`` without forcing the SDK dependency.
    """
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "mcp SDK not installed — run `pip install ui-mapper[mcp]`"
        ) from e

    loaded = load_map(map_path)
    driver = Driver(dry_run=dry_run)
    surface = ToolSurface(loaded, driver)

    server = FastMCP(
        name=f"ui-mapper:{loaded.app_name}",
        instructions=(
            f"Tools to control {loaded.display_name or loaded.app_name} "
            f"(version {loaded.version or 'unknown'}, "
            f"{loaded.completion_pct:.0f}% coverage). "
            "Prefer search_map / list_* to discover what's possible, "
            "then execute_shortcut / execute_menu_action to act. "
            "The target app must be focused on the user's screen for actions to land."
        ),
    )

    # -- Query tools ---------------------------------------------------------

    @server.tool()
    def get_app_info() -> dict[str, Any]:
        """Return metadata about the mapped application (name, version, counts)."""
        return surface.get_app_info()

    @server.tool()
    def list_menus(limit: int = 50, contains: str = "") -> list[dict[str, Any]]:
        """List menu entries. ``contains`` filters by substring (case-insensitive)."""
        return surface.list_menus(limit=limit, contains=contains)

    @server.tool()
    def list_shortcuts(
        limit: int = 50, category: str = "", contains: str = "",
    ) -> list[dict[str, Any]]:
        """List keyboard shortcuts. Filter by category and/or substring."""
        return surface.list_shortcuts(limit=limit, category=category, contains=contains)

    @server.tool()
    def list_tools_registered(
        limit: int = 50, category: str = "", contains: str = "",
    ) -> list[dict[str, Any]]:
        """List tools/brushes exposed by the app (toolbox)."""
        return surface.list_tools(limit=limit, category=category, contains=contains)

    @server.tool()
    def list_dialogs(limit: int = 50, contains: str = "") -> list[dict[str, Any]]:
        """List known dialog windows and their element counts."""
        return surface.list_dialogs(limit=limit, contains=contains)

    @server.tool()
    def search_map(query: str, limit: int = 20) -> dict[str, list[dict[str, Any]]]:
        """Full-text search across menus, shortcuts, tools and dialogs."""
        return surface.search_map(query=query, limit=limit)

    # -- Action tools --------------------------------------------------------

    @server.tool()
    def execute_shortcut(keys: str) -> dict[str, Any]:
        """Press a keyboard shortcut (e.g. ``Ctrl+S``) on the focused application."""
        return surface.execute_shortcut(keys)

    @server.tool()
    def execute_menu_action(path: str) -> dict[str, Any]:
        """Execute a menu entry by its path (e.g. ``File > Export...``)."""
        return surface.execute_menu_action(path)

    @server.tool()
    def execute_action_by_description(action: str) -> dict[str, Any]:
        """Find the best matching entry for a free-text action and execute it."""
        return surface.execute_action_by_description(action)

    @server.tool()
    def type_text(text: str) -> dict[str, Any]:
        """Type text into the focused application (e.g. filling a dialog field)."""
        return surface.type_text(text)

    @server.tool()
    def click_at(x: int, y: int, button: str = "left") -> dict[str, Any]:
        """Click at absolute screen coordinates. Prefer shortcuts when possible."""
        return surface.click_at(x=x, y=y, button=button)

    return server


def run_stdio(map_path: Path, dry_run: bool = False) -> None:
    """Build and run the MCP server over stdio. Blocks until the client disconnects."""
    server = build_server(map_path, dry_run=dry_run)
    log.info("ui-mapper MCP server starting (map=%s, dry_run=%s)", map_path, dry_run)
    server.run()  # FastMCP defaults to stdio transport
