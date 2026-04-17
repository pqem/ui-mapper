"""Visual mapper — explores UI by taking screenshots and asking a VLM.

v2 upgrades (Phase 3a):
- Every produced entry carries ``Provenance`` (source=VISUAL, method,
  confidence). Parse failures downgrade confidence but still record the
  attempt for later diagnosis.
- Each VLM exchange (screenshot + prompt + response) is persisted under
  ``sessions/<app>/<session_id>/`` so failed runs can be reviewed.
- The mapper reports progress to the watchdog after every menu / dialog
  and honors ``should_abort()`` / ``should_pause()`` between units.

Requires: pyautogui, Pillow (pip install ui-mapper[visual])
"""

from __future__ import annotations
import io
import json
import time
import logging
import platform
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .base import BaseMapper
from ..core.types import (
    UIMap, Menu, MenuItem, Shortcut, Tool, Dialog, DialogElement,
    AccessMethod, AccessMethodType, Provenance, ProvenanceSource,
)
from ..core.config import AppConfig
from ..core.session import SessionState
from ..providers.base import VLMProvider
from ..visual.focus import focus_window
from ..visual.snapshots import SnapshotWriter, snapshot_dir_for

if TYPE_CHECKING:
    from ..core.watchdog import HardwareWatchdog

log = logging.getLogger(__name__)


# ---------------------------------------------------------------- prompts --

MENU_BAR_PROMPT = """Look at this screenshot of the application "{app_name}".
List ALL items visible in the top menu bar (File, Edit, View, etc.).
Respond ONLY with a JSON array of menu names, in order from left to right.
Example: ["File", "Edit", "View", "Help"]
If the app is in Spanish, use the Spanish names: ["Archivo", "Editar", "Vista", "Ayuda"]
JSON only, no explanation:"""

MENU_ITEMS_PROMPT = """Look at this screenshot. A dropdown menu is open.
List ALL visible menu items with their keyboard shortcuts (if shown).
Respond with a JSON array. For each item include name, shortcut (or empty string),
and whether it has a submenu arrow (has_submenu: true/false).
Also note if an item is grayed out/disabled (enabled: false).

Example:
[
  {{"name": "New", "shortcut": "Ctrl+N", "has_submenu": false, "enabled": true}},
  {{"name": "Open", "shortcut": "Ctrl+O", "has_submenu": false, "enabled": true}},
  {{"name": "Export", "shortcut": "", "has_submenu": true, "enabled": true}}
]
JSON only, no explanation:"""

SUBMENU_ITEMS_PROMPT = """Look at this screenshot. A submenu is open (a secondary menu).
List ALL visible submenu items with their keyboard shortcuts.
Respond with a JSON array, same format as before:
[{{"name": "item name", "shortcut": "Ctrl+X", "has_submenu": false, "enabled": true}}]
JSON only:"""

DIALOG_PROMPT = """Look at this screenshot. A dialog window is open in the application.
Describe the dialog:
1. What is the dialog title?
2. List ALL visible elements: buttons, text fields, checkboxes, dropdowns, sliders, tabs.

Respond with JSON:
{{
  "title": "Dialog Title",
  "elements": [
    {{"name": "OK", "type": "button"}},
    {{"name": "Filename", "type": "text_field", "value": "example.txt"}},
    {{"name": "Quality", "type": "slider", "value": "100"}},
    {{"name": "Format", "type": "dropdown", "options": ["PNG", "JPEG", "PDF"]}}
  ]
}}
JSON only:"""

TOOLBAR_PROMPT = """Look at this screenshot of the application "{app_name}".
List ALL visible toolbar buttons and tools on the left sidebar and top toolbar.
For each tool, describe what it appears to be (move tool, pen tool, etc.).

Respond with JSON array:
[
  {{"name": "Move Tool", "position": "left_sidebar", "description": "Arrow cursor for selecting and moving"}},
  {{"name": "Pen Tool", "position": "left_sidebar", "description": "Pen nib for drawing paths"}}
]
JSON only:"""


# ------------------------------------------------------------ primitives --

def _take_screenshot() -> bytes:
    import pyautogui
    img = pyautogui.screenshot()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _press_key(key: str) -> None:
    import pyautogui
    pyautogui.press(key)


def _parse_json_response(text: str) -> Any:
    """Parse JSON from a VLM response, stripping markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        elif "```" in text:
            text = text.rsplit("```", 1)[0]
    text = text.strip()
    return json.loads(text)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _visual_provenance(method: str, confidence: float) -> Provenance:
    return Provenance(
        source=ProvenanceSource.VISUAL,
        method=method,
        confidence=confidence,
        verified_at=_now_iso(),
    )


# ------------------------------------------------------------ mapper -----

class VisualMapper(BaseMapper):
    """Explores an application's UI visually using screenshots + VLM."""

    def can_map(self, app_config: AppConfig) -> bool:
        if not app_config.visual_enabled:
            return False
        try:
            import pyautogui  # noqa: F401
            return True
        except ImportError:
            log.warning("pyautogui not installed. Run: pip install ui-mapper[visual]")
            return False

    def get_priority(self) -> int:
        return 40  # runs last — slowest but most comprehensive

    def get_name(self) -> str:
        return "visual"

    def estimate_duration(self, app_config: AppConfig) -> timedelta:
        depth = app_config.exploration_depth
        if depth == "quick":
            return timedelta(minutes=30)
        if depth == "standard":
            return timedelta(hours=2)
        return timedelta(hours=6)

    # -- main -----------------------------------------------------------

    def map(
        self,
        app_config: AppConfig,
        session: SessionState,
        provider: VLMProvider | None = None,
        watchdog: "HardwareWatchdog | None" = None,
        sessions_root: Path | None = None,
    ) -> UIMap:
        if provider is None:
            raise RuntimeError("Visual mapper requires a VLM provider")

        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.3

        delay = app_config.screenshot_delay_ms / 1000.0
        sid = _session_id(session)
        snap = _build_snapshot_writer(sessions_root, app_config.name, sid)

        ui_map = UIMap(
            app_name=app_config.name,
            locale=app_config.locale,
            sources=["visual"],
        )

        log.info("Starting visual exploration of %s", app_config.display_name)
        log.info(
            "depth=%s delay=%.2fs snapshot_dir=%s",
            app_config.exploration_depth, delay, snap.target_dir,
        )

        if not focus_window(app_config.process_name):
            log.error("cannot focus %s — is it running and visible?", app_config.process_name)
            return ui_map
        time.sleep(1)

        # Step 1 — menu bar
        log.info("Step 1/4: Identifying menu bar...")
        menu_names = self._identify_menu_bar(app_config, provider, delay, snap)
        log.info("menu bar: %s", menu_names)
        if watchdog is not None:
            watchdog.report_progress("visual: menu bar identified")

        # Step 2 — each top-level menu
        log.info("Step 2/4: Exploring menus...")
        for menu_name in menu_names:
            if watchdog is not None and watchdog.should_abort():
                log.warning("visual: watchdog abort during menu exploration")
                break
            if watchdog is not None and watchdog.should_pause():
                watchdog.wait_for_clear()

            if menu_name in session.explored_menus:
                log.info("  skipping %s (already explored)", menu_name)
                continue
            try:
                menu = self._explore_menu(
                    app_config, provider, menu_name, menu_names, delay, snap,
                )
                if menu is not None:
                    ui_map.menus[menu_name] = menu
                    for item in menu.items:
                        if item.shortcut:
                            ui_map.shortcuts.append(Shortcut(
                                keys=item.shortcut,
                                action=item.name,
                                category=menu_name,
                                provenance=_visual_provenance(
                                    method="menu-item-extracted",
                                    confidence=0.7,
                                ),
                            ))
                session.explored_menus.append(menu_name)
                if watchdog is not None:
                    watchdog.report_progress(f"visual: menu {menu_name} done")
            except Exception as e:
                log.exception("error exploring menu %s: %s", menu_name, e)
                snap.save_note(f"menu_{menu_name}_error", repr(e))
                _press_key("escape")
                time.sleep(delay)

        # Step 3 — toolbox
        if app_config.exploration_depth in ("standard", "full"):
            log.info("Step 3/4: Identifying tools...")
            try:
                tools = self._identify_tools(app_config, provider, delay, snap)
                ui_map.tools = tools
                if watchdog is not None:
                    watchdog.report_progress("visual: tools identified")
            except Exception as e:
                log.exception("tools identification failed: %s", e)
                snap.save_note("tools_error", repr(e))

        # Step 4 — dialogs (only in full)
        if app_config.exploration_depth == "full":
            log.info("Step 4/4: Exploring key dialogs...")
            self._explore_known_dialogs(
                app_config, provider, ui_map, session, delay, snap, watchdog,
            )

        log.info(
            "visual exploration complete: %d menus, %d shortcuts, %d tools, %d dialogs",
            len(ui_map.menus),
            len(ui_map.shortcuts),
            len(ui_map.tools),
            len(ui_map.dialogs),
        )
        return ui_map

    # -- steps ----------------------------------------------------------

    def _identify_menu_bar(
        self,
        app_config: AppConfig,
        provider: VLMProvider,
        delay: float,
        snap: SnapshotWriter,
    ) -> list[str]:
        focus_window(app_config.process_name)
        time.sleep(delay)
        image = _take_screenshot()
        prompt = MENU_BAR_PROMPT.format(app_name=app_config.display_name)

        response = ""
        try:
            response = provider.query_vision(prompt, image)
            snap.save_step("menu_bar", image_bytes=image, prompt=prompt, response=response)
            menu_names = _parse_json_response(response)
            if isinstance(menu_names, list):
                return [str(n) for n in menu_names]
        except Exception as e:
            log.warning("menu bar parse failed: %s", e)
            snap.save_step(
                "menu_bar_failed",
                image_bytes=image,
                prompt=prompt,
                response=response or f"ERROR: {e}",
            )
        return []

    def _explore_menu(
        self,
        app_config: AppConfig,
        provider: VLMProvider,
        menu_name: str,
        all_menus: list[str],
        delay: float,
        snap: SnapshotWriter,
    ) -> Menu | None:
        log.info("  exploring menu: %s", menu_name)
        menu_idx = all_menus.index(menu_name) if menu_name in all_menus else 0

        focus_window(app_config.process_name)
        time.sleep(delay)
        _press_key("alt")
        time.sleep(delay)
        for _ in range(menu_idx):
            _press_key("right")
            time.sleep(0.2)
        _press_key("enter")
        time.sleep(delay * 2)

        image = _take_screenshot()
        _press_key("escape")
        _press_key("escape")
        time.sleep(delay)

        response = ""
        try:
            response = provider.query_vision(MENU_ITEMS_PROMPT, image)
            snap.save_step(
                f"menu_{menu_name}",
                image_bytes=image,
                prompt=MENU_ITEMS_PROMPT,
                response=response,
            )
            items_data = _parse_json_response(response)
            if not isinstance(items_data, list):
                return None

            items: list[MenuItem] = []
            for item_data in items_data:
                name = item_data.get("name", "")
                if not name:
                    continue
                shortcut = item_data.get("shortcut", "") or ""
                has_submenu = bool(item_data.get("has_submenu", False))

                menu_item = MenuItem(
                    name=name,
                    shortcut=shortcut,
                    access_methods=[AccessMethod(
                        type=AccessMethodType.MENU_PATH,
                        value=f"{menu_name} > {name}",
                    )],
                    provenance=_visual_provenance(
                        method="vlm-menu-items",
                        confidence=0.75 if shortcut else 0.6,
                    ),
                )

                if has_submenu and app_config.exploration_depth in ("standard", "full"):
                    try:
                        children = self._explore_submenu(
                            app_config, provider, menu_name, name,
                            menu_idx, items_data.index(item_data), delay, snap,
                        )
                        menu_item.children = children
                    except Exception as e:
                        log.warning("    submenu error for %s: %s", name, e)
                        snap.save_note(f"submenu_{name}_error", repr(e))

                items.append(menu_item)

            log.info("  %s: %d items", menu_name, len(items))
            return Menu(
                name=menu_name,
                items=items,
                provenance=_visual_provenance(method="vlm-menu", confidence=0.75),
            )
        except Exception as e:
            log.warning("  failed to parse menu %s: %s", menu_name, e)
            snap.save_step(
                f"menu_{menu_name}_failed",
                image_bytes=image,
                prompt=MENU_ITEMS_PROMPT,
                response=response or f"ERROR: {e}",
            )
            return None

    def _explore_submenu(
        self,
        app_config: AppConfig,
        provider: VLMProvider,
        parent_menu: str,
        submenu_name: str,
        menu_idx: int,
        item_idx: int,
        delay: float,
        snap: SnapshotWriter,
    ) -> list[MenuItem]:
        log.info("    exploring submenu: %s", submenu_name)
        focus_window(app_config.process_name)
        time.sleep(delay)

        _press_key("alt")
        time.sleep(delay)
        for _ in range(menu_idx):
            _press_key("right")
            time.sleep(0.15)
        _press_key("enter")
        time.sleep(delay)
        for _ in range(item_idx + 1):
            _press_key("down")
            time.sleep(0.15)
        _press_key("right")
        time.sleep(delay * 2)

        image = _take_screenshot()
        _press_key("escape")
        _press_key("escape")
        _press_key("escape")
        time.sleep(delay)

        response = ""
        try:
            response = provider.query_vision(SUBMENU_ITEMS_PROMPT, image)
            snap.save_step(
                f"submenu_{parent_menu}_{submenu_name}",
                image_bytes=image,
                prompt=SUBMENU_ITEMS_PROMPT,
                response=response,
            )
            items_data = _parse_json_response(response)
            children: list[MenuItem] = []
            for item_data in items_data:
                name = item_data.get("name", "")
                if not name:
                    continue
                shortcut = item_data.get("shortcut", "") or ""
                children.append(MenuItem(
                    name=name,
                    shortcut=shortcut,
                    access_methods=[AccessMethod(
                        type=AccessMethodType.MENU_PATH,
                        value=f"{parent_menu} > {submenu_name} > {name}",
                    )],
                    provenance=_visual_provenance(
                        method="vlm-submenu-items",
                        confidence=0.7 if shortcut else 0.55,
                    ),
                ))
            log.info("    %s: %d submenu items", submenu_name, len(children))
            return children
        except Exception as e:
            log.warning("    submenu parse error: %s", e)
            snap.save_step(
                f"submenu_{parent_menu}_{submenu_name}_failed",
                image_bytes=image,
                prompt=SUBMENU_ITEMS_PROMPT,
                response=response or f"ERROR: {e}",
            )
            return []

    def _identify_tools(
        self,
        app_config: AppConfig,
        provider: VLMProvider,
        delay: float,
        snap: SnapshotWriter,
    ) -> list[Tool]:
        focus_window(app_config.process_name)
        time.sleep(delay)
        image = _take_screenshot()
        prompt = TOOLBAR_PROMPT.format(app_name=app_config.display_name)

        response = ""
        try:
            response = provider.query_vision(prompt, image)
            snap.save_step("tools", image_bytes=image, prompt=prompt, response=response)
            tools_data = _parse_json_response(response)
            tools: list[Tool] = []
            for tool_data in tools_data:
                tools.append(Tool(
                    name=tool_data.get("name", ""),
                    category=tool_data.get("position", ""),
                    description=tool_data.get("description", ""),
                    provenance=_visual_provenance(
                        method="vlm-toolbar", confidence=0.6,
                    ),
                ))
            log.info("  found %d tools", len(tools))
            return tools
        except Exception as e:
            log.warning("  tool identification failed: %s", e)
            snap.save_step(
                "tools_failed",
                image_bytes=image, prompt=prompt, response=response or f"ERROR: {e}",
            )
            return []

    def _explore_known_dialogs(
        self,
        app_config: AppConfig,
        provider: VLMProvider,
        ui_map: UIMap,
        session: SessionState,
        delay: float,
        snap: SnapshotWriter,
        watchdog: "HardwareWatchdog | None",
    ) -> None:
        dialog_shortcuts: list[Shortcut] = []
        for sc in ui_map.shortcuts:
            if any(kw in sc.action.lower() for kw in [
                "export", "nuevo", "new", "guardar como", "save as",
                "preferenc", "config", "ajuste", "setting",
            ]):
                dialog_shortcuts.append(sc)

        for sc in dialog_shortcuts[:10]:
            if watchdog is not None and watchdog.should_abort():
                break
            if watchdog is not None and watchdog.should_pause():
                watchdog.wait_for_clear()

            dialog_id = sc.action.lower().replace(" ", "_").replace(".", "")
            if dialog_id in session.explored_dialogs:
                continue
            log.info("  exploring dialog: %s (%s)", sc.action, sc.keys)
            try:
                dialog = self._open_and_analyze_dialog(
                    app_config, provider, sc.keys, delay, snap,
                )
                if dialog is not None:
                    dialog.id = dialog_id
                    ui_map.dialogs[dialog_id] = dialog
                    session.explored_dialogs.append(dialog_id)
                    if watchdog is not None:
                        watchdog.report_progress(f"visual: dialog {dialog_id}")
            except Exception as e:
                log.warning("  dialog error for %s: %s", sc.action, e)
                snap.save_note(f"dialog_{dialog_id}_error", repr(e))
                _press_key("escape")
                time.sleep(delay)

    def _open_and_analyze_dialog(
        self,
        app_config: AppConfig,
        provider: VLMProvider,
        shortcut_keys: str,
        delay: float,
        snap: SnapshotWriter,
    ) -> Dialog | None:
        focus_window(app_config.process_name)
        time.sleep(delay)

        import pyautogui
        # permissive shortcut parser (lower + "mayús" → shift)
        normalized = shortcut_keys.lower().replace("mayús", "shift")
        parts = [p.strip() for p in normalized.split("+") if p.strip()]
        try:
            pyautogui.hotkey(*parts)
        except Exception as e:
            log.warning("  could not send shortcut %s: %s", shortcut_keys, e)
            return None

        time.sleep(delay * 4)
        image = _take_screenshot()
        _press_key("escape")
        time.sleep(delay * 2)
        _press_key("escape")
        time.sleep(delay)

        response = ""
        try:
            response = provider.query_vision(DIALOG_PROMPT, image)
            snap.save_step(
                f"dialog_{shortcut_keys}",
                image_bytes=image, prompt=DIALOG_PROMPT, response=response,
            )
            data = _parse_json_response(response)
            elements: list[DialogElement] = []
            for el in data.get("elements", []):
                elements.append(DialogElement(
                    name=el.get("name", ""),
                    element_type=el.get("type", "unknown"),
                    default_value=el.get("value", ""),
                    options=el.get("options", []),
                    provenance=_visual_provenance(
                        method="vlm-dialog-element", confidence=0.6,
                    ),
                ))
            return Dialog(
                id="",
                title=data.get("title", "Unknown"),
                elements=elements,
                access_methods=[AccessMethod(
                    type=AccessMethodType.KEYBOARD_SHORTCUT,
                    value=shortcut_keys,
                )],
                provenance=_visual_provenance(method="vlm-dialog", confidence=0.65),
            )
        except Exception as e:
            log.warning("  dialog parse error: %s", e)
            snap.save_step(
                f"dialog_{shortcut_keys}_failed",
                image_bytes=image, prompt=DIALOG_PROMPT,
                response=response or f"ERROR: {e}",
            )
            return None


# ------------------------------------------------------------ helpers ----

def _session_id(session: SessionState) -> str:
    if session.started_at:
        return datetime.fromtimestamp(
            session.started_at, tz=timezone.utc
        ).strftime("%Y%m%dT%H%M%SZ")
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _build_snapshot_writer(
    sessions_root: Path | None, app_name: str, session_id: str,
) -> SnapshotWriter:
    if sessions_root is None:
        # Default: sibling of maps/ in the project root
        sessions_root = Path("sessions")
    target = snapshot_dir_for(sessions_root, app_name, session_id)
    return SnapshotWriter(target_dir=target, enabled=True)
