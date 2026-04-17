"""Canonical data model for UI maps.

All modules speak in terms of these types. The UIMap is the final output
that an LLM consumes to control a program.

Schema version: 2.0
- Adds Provenance (source, method, confidence, verified_at) to every entry
- Adds AppMetadata (version detection, exe hash) and MapMetadata blocks
- Keeps flat fields for backwards compatibility with v1 consumers

See docs/ARCHITECTURE.md section 5.1 for the canonical schema.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


SCHEMA_VERSION = "2.0"


# -----------------------------------------------------------------------------
# Provenance — every entry in a v2 map carries this
# -----------------------------------------------------------------------------

class ProvenanceSource(str, Enum):
    """Which subsystem generated an entry."""
    LLM_KNOWLEDGE = "llm-knowledge"
    UIA = "uia"
    SOURCE_CONFIG = "source-config"
    VISUAL = "visual"
    MANUAL = "manual"              # user-edited
    COMMUNITY = "community"        # imported from shared map
    UNKNOWN = "unknown"


@dataclass
class Provenance:
    """Traceability metadata for a single entry.

    Every menu item, dialog, shortcut, and tool in a v2 map carries one.
    Without this we cannot improve the map over time (no feedback loop,
    no confidence-based re-mapping, no differential verification).
    """
    source: ProvenanceSource = ProvenanceSource.UNKNOWN
    method: str = ""               # free text: "uia-tree-walk", "vlm-screenshot", etc.
    confidence: float = 0.5        # 0.0 - 1.0
    verified_at: str = ""          # ISO timestamp of last successful verification
    notes: str = ""                # optional human-readable context

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


# -----------------------------------------------------------------------------
# App and map metadata blocks
# -----------------------------------------------------------------------------

@dataclass
class AppMetadata:
    """Metadata about the target application.

    Populated at mapping time. Drives version-sensitive behavior
    (diff-update vs re-map, community map lookup, etc.).
    """
    name: str = ""
    display_name: str = ""
    version: str = ""
    version_detected_at: str = ""
    executable_path: str = ""
    executable_hash: str = ""      # sha256 of the main executable
    locale: str = ""
    platform: str = "windows"


@dataclass
class MapMetadata:
    """Metadata about the mapping session itself."""
    generated_by: str = ""                 # e.g. "ui-mapper 0.2.0"
    generated_at: str = ""
    session_id: str = ""
    duration_seconds: float = 0.0
    providers_used: list[str] = field(default_factory=list)
    mappers_used: list[str] = field(default_factory=list)
    completion_pct: float = 0.0


# -----------------------------------------------------------------------------
# Access methods — how to trigger an action
# -----------------------------------------------------------------------------

class AccessMethodType(str, Enum):
    """How to trigger an action — ordered by reliability."""
    COMMAND = "command"              # CLI / command line (e.g. AutoCAD)
    API = "api"                      # Scripting API (e.g. SketchUp Ruby)
    KEYBOARD_SHORTCUT = "shortcut"   # Ctrl+S, etc.
    MENU_PATH = "menu_path"          # File > Export > Export...
    UIA_ELEMENT = "uia"              # Windows UI Automation element
    MOUSE_RELATIVE = "mouse_rel"     # Click at relative position in dialog


@dataclass
class AccessMethod:
    """One way to perform an action."""
    type: AccessMethodType
    value: str                       # shortcut keys, menu path, command name, etc.
    reliability: float = 1.0         # 0.0-1.0, higher = more reliable
    metadata: dict[str, Any] = field(default_factory=dict)


# -----------------------------------------------------------------------------
# UI elements
# -----------------------------------------------------------------------------

@dataclass
class UIElement:
    """A single UI element (button, field, checkbox, etc.)."""
    name: str
    element_type: str                # "button", "edit", "checkbox", "dropdown", etc.
    automation_id: str = ""
    access_methods: list[AccessMethod] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: Provenance | None = None


@dataclass
class MenuItem:
    """A single menu item."""
    name: str
    shortcut: str = ""
    action: str = ""                 # what it does
    opens: str = ""                  # dialog/submenu reference by id
    access_methods: list[AccessMethod] = field(default_factory=list)
    children: list[MenuItem] = field(default_factory=list)
    provenance: Provenance | None = None


@dataclass
class Menu:
    """A top-level menu (File, Edit, View, etc.)."""
    name: str
    items: list[MenuItem] = field(default_factory=list)
    access_key: str = ""             # Alt+F, etc.
    provenance: Provenance | None = None


@dataclass
class DialogElement:
    """An element inside a dialog."""
    name: str
    element_type: str                # "button", "edit", "dropdown", "checkbox", etc.
    automation_id: str = ""
    default_value: str = ""
    options: list[str] = field(default_factory=list)  # for dropdowns
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: Provenance | None = None


@dataclass
class Dialog:
    """A dialog window with its elements."""
    id: str
    title: str
    title_pattern: str = ""          # regex/glob for matching
    window_class: str = ""           # e.g. "#32770" for standard Windows dialogs
    elements: list[DialogElement] = field(default_factory=list)
    access_methods: list[AccessMethod] = field(default_factory=list)
    opens_next: str = ""             # if this dialog leads to another
    provenance: Provenance | None = None


@dataclass
class Shortcut:
    """A keyboard shortcut."""
    keys: str                        # e.g. "Ctrl+Alt+Shift+W"
    action: str                      # what it does
    context: str = ""                # when available (e.g. "with selection")
    category: str = ""
    provenance: Provenance | None = None


@dataclass
class Tool:
    """A tool in the toolbox/toolbar."""
    name: str
    shortcut: str = ""
    category: str = ""
    description: str = ""
    access_methods: list[AccessMethod] = field(default_factory=list)
    provenance: Provenance | None = None


# -----------------------------------------------------------------------------
# UIMap — the complete output
# -----------------------------------------------------------------------------

@dataclass
class UIMap:
    """Complete map of an application's UI — the final output.

    v2 structure keeps flat convenience fields (app_name, locale, ...) for
    consumers that already read v1, while adding structured blocks
    (app_metadata, map_metadata) with richer context.
    """
    app_name: str = ""
    app_version: str = ""            # kept for v1 compat; prefer app_metadata.version
    locale: str = ""
    platform: str = "windows"

    menus: dict[str, Menu] = field(default_factory=dict)
    shortcuts: list[Shortcut] = field(default_factory=list)
    dialogs: dict[str, Dialog] = field(default_factory=dict)
    tools: list[Tool] = field(default_factory=list)

    # v1 compat
    mapped_at: str = ""
    sources: list[str] = field(default_factory=list)
    completion_pct: float = 0.0
    raw_data: dict[str, Any] = field(default_factory=dict)

    # v2 additions
    schema_version: str = SCHEMA_VERSION
    app_metadata: AppMetadata | None = None
    map_metadata: MapMetadata | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON export."""
        import dataclasses
        return dataclasses.asdict(self)

    def merge(self, other: UIMap) -> None:
        """Merge another UIMap into this one (for combining mapper results).

        Entries are deduplicated by name/keys. Provenance is preserved from
        whichever mapper produced the entry first — subsequent mappers can
        enrich but don't overwrite.
        """
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

    def entries_by_confidence(self, threshold: float = 0.5) -> dict[str, int]:
        """Count entries whose provenance confidence is below a threshold.

        Useful for reporting (``85% verified, 15% needs re-mapping``) and
        for the verify command.
        """
        below = {"menus": 0, "shortcuts": 0, "dialogs": 0, "tools": 0}
        for menu in self.menus.values():
            for item in menu.items:
                if item.provenance and item.provenance.confidence < threshold:
                    below["menus"] += 1
        for sc in self.shortcuts:
            if sc.provenance and sc.provenance.confidence < threshold:
                below["shortcuts"] += 1
        for dlg in self.dialogs.values():
            if dlg.provenance and dlg.provenance.confidence < threshold:
                below["dialogs"] += 1
        for tool in self.tools:
            if tool.provenance and tool.provenance.confidence < threshold:
                below["tools"] += 1
        return below
