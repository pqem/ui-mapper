"""MCP tool surface — what the LLM can call against a mapped app.

Tools are defined as plain Python methods on ``ToolSurface`` so they can
be unit-tested without the MCP runtime. ``server.py`` wraps each one
with ``@mcp.tool()`` for the stdio protocol.

Design note — two layers of tools:

1. **Query tools** (list_menus, list_shortcuts, search_map, ...) — let
   the LLM discover what's possible in the app without us pre-generating
   a tool per entry (which would explode at hundreds of tools per app).
2. **Action tools** (execute_shortcut, execute_menu_action, type_text,
   click_at) — actually drive the app.

The LLM's normal flow is: search / list → pick → execute.
"""

from __future__ import annotations
from dataclasses import asdict
from typing import Any

from .driver import Driver, DriverResult
from .map_loader import LoadedMap


def _entry_to_dict(entry: Any) -> dict[str, Any]:
    """Serialize a dataclass entry to a clean dict for MCP output."""
    d = asdict(entry)
    # Drop None values to keep payloads slim
    return {k: v for k, v in d.items() if v not in (None, "")}


class ToolSurface:
    """Tool implementations bound to a LoadedMap + Driver."""

    def __init__(self, loaded: LoadedMap, driver: Driver) -> None:
        self.map = loaded
        self.driver = driver

    # ---------------------------------------------------------- Queries --

    def get_app_info(self) -> dict[str, Any]:
        """Return metadata about the mapped application."""
        return {
            "app_name": self.map.app_name,
            "display_name": self.map.display_name,
            "version": self.map.version,
            "platform": self.map.platform,
            "locale": self.map.locale,
            "schema_version": self.map.schema_version,
            "completion_pct": self.map.completion_pct,
            "counts": {
                "menus": len(self.map.menus),
                "shortcuts": len(self.map.shortcuts),
                "tools": len(self.map.tools),
                "dialogs": len(self.map.dialogs),
            },
        }

    def list_menus(self, limit: int = 50, contains: str = "") -> list[dict[str, Any]]:
        """Return menu entries. ``contains`` filters by substring (case-insensitive)."""
        needle = contains.lower().strip()
        items = [
            m for m in self.map.menus
            if not needle or needle in m.path.lower()
        ]
        return [_entry_to_dict(m) for m in items[:limit]]

    def list_shortcuts(
        self, limit: int = 50, category: str = "", contains: str = "",
    ) -> list[dict[str, Any]]:
        cat = category.lower().strip()
        needle = contains.lower().strip()
        items = [
            s for s in self.map.shortcuts
            if (not cat or cat in s.category.lower())
            and (not needle or needle in s.action.lower() or needle in s.keys.lower())
        ]
        return [_entry_to_dict(s) for s in items[:limit]]

    def list_tools(
        self, limit: int = 50, category: str = "", contains: str = "",
    ) -> list[dict[str, Any]]:
        cat = category.lower().strip()
        needle = contains.lower().strip()
        items = [
            t for t in self.map.tools
            if (not cat or cat in t.category.lower())
            and (not needle or needle in t.name.lower() or needle in t.description.lower())
        ]
        return [_entry_to_dict(t) for t in items[:limit]]

    def list_dialogs(self, limit: int = 50, contains: str = "") -> list[dict[str, Any]]:
        needle = contains.lower().strip()
        items = [
            d for d in self.map.dialogs
            if not needle or needle in d.title.lower() or needle in d.id.lower()
        ]
        return [_entry_to_dict(d) for d in items[:limit]]

    def search_map(self, query: str, limit: int = 20) -> dict[str, list[dict[str, Any]]]:
        """Full-text search across menus / shortcuts / tools / dialogs."""
        hits = self.map.search(query, limit=limit)
        return {
            key: [_entry_to_dict(e) for e in entries]
            for key, entries in hits.items()
        }

    # ----------------------------------------------------------- Actions --

    def execute_shortcut(self, keys: str) -> dict[str, Any]:
        """Press a keyboard shortcut (e.g. ``Ctrl+S``) on the foreground app."""
        return _result(self.driver.press_shortcut(keys))

    def execute_menu_action(self, path: str) -> dict[str, Any]:
        """Find a menu entry by path and execute it.

        MVP: resolves the menu entry and presses its shortcut. If the
        entry has no shortcut, returns an error describing what was
        found so the LLM can choose another action.
        """
        entry = self.map.find_menu(path)
        if entry is None:
            return {"ok": False, "message": f"menu path not found: {path}"}
        if not entry.shortcut:
            return {
                "ok": False,
                "message": (
                    f"menu entry found but no shortcut recorded — "
                    f"menu-path navigation via UI will land in a later phase"
                ),
                "entry": _entry_to_dict(entry),
            }
        result = self.driver.press_shortcut(entry.shortcut)
        payload = _result(result)
        payload["entry"] = _entry_to_dict(entry)
        return payload

    def execute_action_by_description(self, action: str) -> dict[str, Any]:
        """Find any entry matching an action description and execute it.

        Prioritizes explicit shortcut entries over menu entries. Useful
        when the LLM knows what it wants (``save document``) but doesn't
        know the exact menu path.
        """
        sc = self.map.find_shortcut_for_action(action)
        if sc and sc.keys:
            result = self.driver.press_shortcut(sc.keys)
            payload = _result(result)
            payload["entry"] = _entry_to_dict(sc)
            return payload

        hits = self.map.search(action, limit=1)
        if hits["menus"]:
            menu = hits["menus"][0]
            if menu.shortcut:
                result = self.driver.press_shortcut(menu.shortcut)
                payload = _result(result)
                payload["entry"] = _entry_to_dict(menu)
                return payload
            return {
                "ok": False,
                "message": "menu match found but no shortcut recorded",
                "entry": _entry_to_dict(menu),
            }
        return {"ok": False, "message": f"no entry matches action: {action}"}

    def type_text(self, text: str) -> dict[str, Any]:
        """Type text into the foreground app (useful inside dialogs)."""
        return _result(self.driver.type_text(text))

    def click_at(self, x: int, y: int, button: str = "left") -> dict[str, Any]:
        """Click at absolute screen coordinates. Prefer shortcuts when possible."""
        return _result(self.driver.click_at(x=x, y=y, button=button))


# -----------------------------------------------------------------------------

def _result(r: DriverResult) -> dict[str, Any]:
    payload = {"ok": r.ok, "message": r.message}
    if r.data:
        payload["data"] = r.data
    return payload
