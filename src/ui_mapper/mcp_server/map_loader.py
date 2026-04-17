"""Load a UIMap JSON file into a structured, query-friendly form.

Stays agnostic of the MCP SDK — this module can be used from tests and
the TUI alike. The MCP server layers on top.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MenuEntry:
    path: str                   # "File > Export..."
    name: str
    shortcut: str = ""
    confidence: float | None = None
    source: str | None = None
    opens: str = ""


@dataclass
class ShortcutEntry:
    keys: str                   # "Ctrl+Alt+S"
    action: str = ""
    category: str = ""
    context: str = ""
    confidence: float | None = None
    source: str | None = None


@dataclass
class ToolEntry:
    name: str
    shortcut: str = ""
    category: str = ""
    description: str = ""
    confidence: float | None = None
    source: str | None = None


@dataclass
class DialogEntry:
    id: str
    title: str
    element_count: int = 0
    confidence: float | None = None
    source: str | None = None


@dataclass
class LoadedMap:
    """Flat, searchable view of a UIMap for MCP consumers."""
    app_name: str
    display_name: str
    version: str
    platform: str
    locale: str
    schema_version: str
    completion_pct: float

    menus: list[MenuEntry] = field(default_factory=list)
    shortcuts: list[ShortcutEntry] = field(default_factory=list)
    tools: list[ToolEntry] = field(default_factory=list)
    dialogs: list[DialogEntry] = field(default_factory=list)

    raw: dict[str, Any] = field(default_factory=dict)

    # -- search helpers ----------------------------------------------------

    def search(self, query: str, limit: int = 20) -> dict[str, list[Any]]:
        """Case-insensitive substring search across all entry types."""
        q = query.lower().strip()
        if not q:
            return {"menus": [], "shortcuts": [], "tools": [], "dialogs": []}

        def keep(text: str) -> bool:
            return q in text.lower()

        return {
            "menus": [m for m in self.menus if keep(m.path) or keep(m.name)][:limit],
            "shortcuts": [s for s in self.shortcuts if keep(s.action) or keep(s.keys)][:limit],
            "tools": [t for t in self.tools if keep(t.name) or keep(t.description)][:limit],
            "dialogs": [d for d in self.dialogs if keep(d.title) or keep(d.id)][:limit],
        }

    def find_menu(self, path: str) -> MenuEntry | None:
        """Case-insensitive menu lookup by full path ('File > Export...')."""
        target = path.strip().lower()
        for m in self.menus:
            if m.path.lower() == target:
                return m
        return None

    def find_shortcut_for_action(self, action: str) -> ShortcutEntry | None:
        target = action.strip().lower()
        for s in self.shortcuts:
            if target in s.action.lower():
                return s
        return None


# -----------------------------------------------------------------------------
# Parsing
# -----------------------------------------------------------------------------

def _prov_fields(entry: dict[str, Any]) -> tuple[float | None, str | None]:
    prov = entry.get("provenance") or {}
    conf = prov.get("confidence")
    src = prov.get("source")
    return (float(conf) if conf is not None else None, src or None)


def _flatten_menu_items(
    menu_label: str,
    items: list[dict[str, Any]],
    accumulator: list[MenuEntry],
    parent_path: str = "",
) -> None:
    """Walk a menu tree in preorder and emit ``MenuEntry`` rows."""
    for item in items:
        name = item.get("name", "")
        if not name:
            continue
        path = f"{parent_path} > {name}" if parent_path else f"{menu_label} > {name}"
        conf, src = _prov_fields(item)
        accumulator.append(MenuEntry(
            path=path,
            name=name,
            shortcut=item.get("shortcut", "") or "",
            opens=item.get("opens", "") or "",
            confidence=conf,
            source=src,
        ))
        children = item.get("children") or []
        if children:
            _flatten_menu_items(menu_label, children, accumulator, parent_path=path)


def load_map(map_path: Path) -> LoadedMap:
    """Read a v2 UIMap JSON and return a ``LoadedMap``.

    Raises:
        FileNotFoundError: if the file doesn't exist.
        ValueError: if the JSON is not a valid map document.
    """
    path = Path(map_path)
    if not path.exists():
        raise FileNotFoundError(f"map not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"map is not a JSON object: {path}")

    app_meta = data.get("app_metadata") or {}
    schema = data.get("schema_version", "1.x")

    loaded = LoadedMap(
        app_name=data.get("app_name", "") or app_meta.get("name", ""),
        display_name=app_meta.get("display_name") or data.get("app_name", ""),
        version=app_meta.get("version") or data.get("app_version", ""),
        platform=data.get("platform", "windows"),
        locale=data.get("locale", ""),
        schema_version=schema,
        completion_pct=float(data.get("completion_pct", 0.0)),
        raw=data,
    )

    # menus (dict of label → {name, items, access_key, ...})
    for label, menu in (data.get("menus") or {}).items():
        if not isinstance(menu, dict):
            continue
        display_label = menu.get("name") or label
        _flatten_menu_items(display_label, menu.get("items") or [], loaded.menus)

    # shortcuts
    for sc in data.get("shortcuts") or []:
        conf, src = _prov_fields(sc)
        loaded.shortcuts.append(ShortcutEntry(
            keys=sc.get("keys", ""),
            action=sc.get("action", ""),
            category=sc.get("category", ""),
            context=sc.get("context", ""),
            confidence=conf,
            source=src,
        ))

    # tools
    for tool in data.get("tools") or []:
        conf, src = _prov_fields(tool)
        loaded.tools.append(ToolEntry(
            name=tool.get("name", ""),
            shortcut=tool.get("shortcut", ""),
            category=tool.get("category", ""),
            description=tool.get("description", ""),
            confidence=conf,
            source=src,
        ))

    # dialogs
    for dlg_id, dlg in (data.get("dialogs") or {}).items():
        if not isinstance(dlg, dict):
            continue
        conf, src = _prov_fields(dlg)
        elements = dlg.get("elements") or []
        loaded.dialogs.append(DialogEntry(
            id=dlg_id,
            title=dlg.get("title", dlg_id),
            element_count=len(elements),
            confidence=conf,
            source=src,
        ))

    return loaded
