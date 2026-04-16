"""Canonical data model for UI maps.

All modules speak in terms of these types. The UIMap is the final output
that an LLM consumes to control a program.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AccessMethodType(str, Enum):
    """How to trigger an action — ordered by reliability."""
    COMMAND = "command"           # CLI / command line (e.g. AutoCAD)
    API = "api"                  # Scripting API (e.g. SketchUp Ruby)
    KEYBOARD_SHORTCUT = "shortcut"  # Ctrl+S, etc.
    MENU_PATH = "menu_path"      # File > Export > Export...
    UIA_ELEMENT = "uia"          # Windows UI Automation element
    MOUSE_RELATIVE = "mouse_rel" # Click at relative position in dialog


@dataclass
class AccessMethod:
    """One way to perform an action."""
    type: AccessMethodType
    value: str  # The shortcut keys, menu path, command name, etc.
    reliability: float = 1.0  # 0.0-1.0, higher = more reliable
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UIElement:
    """A single UI element (button, field, checkbox, etc.)."""
    name: str
    element_type: str  # "button", "edit", "checkbox", "dropdown", etc.
    automation_id: str = ""
    access_methods: list[AccessMethod] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MenuItem:
    """A single menu item."""
    name: str
    shortcut: str = ""
    action: str = ""  # What it does
    opens: str = ""   # Dialog/submenu it opens (reference by id)
    access_methods: list[AccessMethod] = field(default_factory=list)
    children: list[MenuItem] = field(default_factory=list)


@dataclass
class Menu:
    """A top-level menu (File, Edit, View, etc.)."""
    name: str
    items: list[MenuItem] = field(default_factory=list)
    access_key: str = ""  # Alt+F, etc.


@dataclass
class DialogElement:
    """An element inside a dialog."""
    name: str
    element_type: str  # "button", "edit", "dropdown", "checkbox", etc.
    automation_id: str = ""
    default_value: str = ""
    options: list[str] = field(default_factory=list)  # For dropdowns
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Dialog:
    """A dialog window with its elements."""
    id: str
    title: str
    title_pattern: str = ""  # Regex/glob for matching
    window_class: str = ""   # e.g. "#32770" for standard Windows dialogs
    elements: list[DialogElement] = field(default_factory=list)
    access_methods: list[AccessMethod] = field(default_factory=list)
    opens_next: str = ""  # If this dialog leads to another


@dataclass
class Shortcut:
    """A keyboard shortcut."""
    keys: str        # e.g. "Ctrl+Alt+Shift+W"
    action: str      # What it does
    context: str = ""  # When it's available (e.g. "with selection")
    category: str = ""


@dataclass
class Tool:
    """A tool in the toolbox/toolbar."""
    name: str
    shortcut: str = ""
    category: str = ""
    description: str = ""
    access_methods: list[AccessMethod] = field(default_factory=list)


@dataclass
class UIMap:
    """Complete map of an application's UI. This is the final output."""
    app_name: str
    app_version: str = ""
    locale: str = ""
    platform: str = "windows"

    menus: dict[str, Menu] = field(default_factory=dict)
    shortcuts: list[Shortcut] = field(default_factory=list)
    dialogs: dict[str, Dialog] = field(default_factory=dict)
    tools: list[Tool] = field(default_factory=list)

    # Metadata
    mapped_at: str = ""
    sources: list[str] = field(default_factory=list)
    completion_pct: float = 0.0
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON export."""
        import dataclasses
        return dataclasses.asdict(self)

    def merge(self, other: UIMap) -> None:
        """Merge another UIMap into this one (for combining mapper results)."""
        for key, menu in other.menus.items():
            if key not in self.menus:
                self.menus[key] = menu
            else:
                existing_names = {i.name for i in self.menus[key].items}
                for item in menu.items:
                    if item.name not in existing_names:
                        self.menus[key].items.append(item)

        existing_shortcuts = {s.keys for s in self.shortcuts}
        for shortcut in other.shortcuts:
            if shortcut.keys not in existing_shortcuts:
                self.shortcuts.append(shortcut)

        for key, dialog in other.dialogs.items():
            if key not in self.dialogs:
                self.dialogs[key] = dialog

        existing_tools = {t.name for t in self.tools}
        for tool in other.tools:
            if tool.name not in existing_tools:
                self.tools.append(tool)

        for source in other.sources:
            if source not in self.sources:
                self.sources.append(source)
