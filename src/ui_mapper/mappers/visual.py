"""Visual mapper — explores UI by taking screenshots and asking a VLM.

This is the most comprehensive but slowest mapper. It:
1. Focuses the target application window
2. Systematically clicks through every menu
3. Takes screenshots and asks the VLM what it sees
4. Records menus, shortcuts, dialogs, tools
5. Supports overnight unattended operation with error recovery

Requires: pyautogui, Pillow (pip install ui-mapper[visual])
"""

from __future__ import annotations
import io
import json
import time
import logging
import subprocess
import platform
from datetime import timedelta
from typing import Any

from .base import BaseMapper
from ..core.types import (
    UIMap, Menu, MenuItem, Shortcut, Tool, Dialog, DialogElement,
    AccessMethod, AccessMethodType,
)
from ..core.config import AppConfig
from ..core.session import SessionState
from ..providers.base import VLMProvider

log = logging.getLogger(__name__)

# Prompt templates for the VLM
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


def _take_screenshot() -> bytes:
    """Capture the entire screen as PNG bytes."""
    import pyautogui
    screenshot = pyautogui.screenshot()
    buf = io.BytesIO()
    screenshot.save(buf, format="PNG")
    return buf.getvalue()


def _take_region_screenshot(x: int, y: int, w: int, h: int) -> bytes:
    """Capture a region of the screen as PNG bytes."""
    import pyautogui
    screenshot = pyautogui.screenshot(region=(x, y, w, h))
    buf = io.BytesIO()
    screenshot.save(buf, format="PNG")
    return buf.getvalue()


def _focus_app(process_name: str) -> bool:
    """Focus the application window (Windows)."""
    if platform.system() != "Windows":
        log.warning("Visual mapper focus only supported on Windows")
        return False

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"""
                Add-Type -AssemblyName Microsoft.VisualBasic
                $proc = Get-Process -Name '{process_name}' -ErrorAction SilentlyContinue |
                    Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
                if ($proc) {{
                    [Microsoft.VisualBasic.Interaction]::AppActivate($proc.Id)
                    Write-Output "OK:$($proc.Id)"
                }} else {{
                    Write-Output "ERROR:Process not found"
                }}
            """],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout.strip()
        if output.startswith("OK:"):
            log.debug(f"Focused {process_name} (PID {output.split(':')[1]})")
            return True
        log.warning(f"Could not focus {process_name}: {output}")
        return False
    except Exception as e:
        log.warning(f"Focus failed: {e}")
        return False


def _click(x: int, y: int) -> None:
    """Click at screen coordinates."""
    import pyautogui
    pyautogui.click(x, y)


def _press_key(key: str) -> None:
    """Press a keyboard key."""
    import pyautogui
    pyautogui.press(key)


def _hotkey(*keys: str) -> None:
    """Press a hotkey combination."""
    import pyautogui
    pyautogui.hotkey(*keys)


def _parse_json_response(text: str) -> Any:
    """Parse JSON from VLM response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        elif "```" in text:
            text = text.rsplit("```", 1)[0]
    text = text.strip()
    return json.loads(text)


class VisualMapper(BaseMapper):
    """Explores application UI visually using screenshots + VLM."""

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
        return 40  # Last resort — slowest but most comprehensive

    def get_name(self) -> str:
        return "visual"

    def estimate_duration(self, app_config: AppConfig) -> timedelta:
        depth = app_config.exploration_depth
        if depth == "quick":
            return timedelta(minutes=30)
        elif depth == "standard":
            return timedelta(hours=2)
        return timedelta(hours=6)

    def map(
        self,
        app_config: AppConfig,
        session: SessionState,
        provider: VLMProvider | None = None,
    ) -> UIMap:
        if provider is None:
            raise RuntimeError("Visual mapper requires a VLM provider")

        import pyautogui
        pyautogui.FAILSAFE = True  # Move mouse to corner to abort
        pyautogui.PAUSE = 0.3

        delay = app_config.screenshot_delay_ms / 1000.0

        ui_map = UIMap(
            app_name=app_config.name,
            locale=app_config.locale,
            sources=["visual"],
        )

        log.info(f"Starting visual exploration of {app_config.display_name}")
        log.info(f"Depth: {app_config.exploration_depth}, delay: {delay}s")

        # Step 1: Focus the app
        if not _focus_app(app_config.process_name):
            log.error(f"Cannot focus {app_config.process_name}. Is it running?")
            return ui_map
        time.sleep(1)

        # Step 2: Screenshot the main window to identify menu bar
        log.info("Step 1/4: Identifying menu bar...")
        menu_names = self._identify_menu_bar(app_config, provider, delay)
        log.info(f"Found menu bar items: {menu_names}")

        # Step 3: Explore each menu
        log.info("Step 2/4: Exploring menus...")
        for menu_name in menu_names:
            if menu_name in session.explored_menus:
                log.info(f"  Skipping {menu_name} (already explored)")
                continue

            try:
                menu = self._explore_menu(
                    app_config, provider, menu_name, menu_names, delay
                )
                if menu:
                    ui_map.menus[menu_name] = menu
                    # Extract shortcuts
                    for item in menu.items:
                        if item.shortcut:
                            ui_map.shortcuts.append(Shortcut(
                                keys=item.shortcut,
                                action=item.name,
                                category=menu_name,
                            ))
                session.explored_menus.append(menu_name)
            except Exception as e:
                log.error(f"  Error exploring menu {menu_name}: {e}")
                # Press Escape to close any open menus
                _press_key("escape")
                time.sleep(delay)

        # Step 4: Identify toolbar/tools
        if app_config.exploration_depth in ("standard", "full"):
            log.info("Step 3/4: Identifying tools...")
            try:
                tools = self._identify_tools(app_config, provider, delay)
                ui_map.tools = tools
            except Exception as e:
                log.error(f"Error identifying tools: {e}")

        # Step 5: Explore key dialogs (if full depth)
        if app_config.exploration_depth == "full":
            log.info("Step 4/4: Exploring key dialogs...")
            self._explore_known_dialogs(app_config, provider, ui_map, session, delay)

        log.info(
            f"Visual exploration complete: {len(ui_map.menus)} menus, "
            f"{len(ui_map.shortcuts)} shortcuts, {len(ui_map.tools)} tools"
        )
        return ui_map

    def _identify_menu_bar(
        self, app_config: AppConfig, provider: VLMProvider, delay: float
    ) -> list[str]:
        """Take screenshot and ask VLM to identify menu bar items."""
        _focus_app(app_config.process_name)
        time.sleep(delay)

        image = _take_screenshot()
        prompt = MENU_BAR_PROMPT.format(app_name=app_config.display_name)

        try:
            response = provider.query_vision(prompt, image)
            menu_names = _parse_json_response(response)
            if isinstance(menu_names, list):
                return [str(n) for n in menu_names]
        except Exception as e:
            log.warning(f"Failed to parse menu bar: {e}")

        return []

    def _explore_menu(
        self,
        app_config: AppConfig,
        provider: VLMProvider,
        menu_name: str,
        all_menus: list[str],
        delay: float,
    ) -> Menu | None:
        """Click a menu, screenshot, ask VLM to list items."""
        log.info(f"  Exploring menu: {menu_name}")

        # Click the menu name in the menu bar
        # First, get menu position by index
        menu_idx = all_menus.index(menu_name) if menu_name in all_menus else 0

        _focus_app(app_config.process_name)
        time.sleep(delay)

        # Use Alt key to activate menu bar, then arrow keys to navigate
        _press_key("alt")
        time.sleep(delay)
        # Press Right arrow to get to the correct menu
        for _ in range(menu_idx):
            _press_key("right")
            time.sleep(0.2)
        _press_key("enter")
        time.sleep(delay * 2)

        # Screenshot the opened menu
        image = _take_screenshot()

        # Close the menu
        _press_key("escape")
        _press_key("escape")
        time.sleep(delay)

        # Ask VLM to identify items
        try:
            response = provider.query_vision(MENU_ITEMS_PROMPT, image)
            items_data = _parse_json_response(response)

            if not isinstance(items_data, list):
                return None

            items = []
            for item_data in items_data:
                name = item_data.get("name", "")
                if not name:
                    continue

                shortcut = item_data.get("shortcut", "")
                has_submenu = item_data.get("has_submenu", False)

                menu_item = MenuItem(
                    name=name,
                    shortcut=shortcut,
                    access_methods=[AccessMethod(
                        type=AccessMethodType.MENU_PATH,
                        value=f"{menu_name} > {name}",
                    )],
                )

                # Explore submenu if present and depth allows
                if has_submenu and app_config.exploration_depth in ("standard", "full"):
                    try:
                        children = self._explore_submenu(
                            app_config, provider, menu_name, name,
                            menu_idx, items_data.index(item_data), delay,
                        )
                        menu_item.children = children
                    except Exception as e:
                        log.warning(f"    Submenu error for {name}: {e}")

                items.append(menu_item)

            log.info(f"  {menu_name}: {len(items)} items found")
            return Menu(name=menu_name, items=items)

        except Exception as e:
            log.warning(f"  Failed to parse menu {menu_name}: {e}")
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
    ) -> list[MenuItem]:
        """Open a submenu and read its items."""
        log.info(f"    Exploring submenu: {submenu_name}")

        _focus_app(app_config.process_name)
        time.sleep(delay)

        # Navigate: Alt → Right arrows to menu → Down arrows to item → Right to open submenu
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

        # Close everything
        _press_key("escape")
        _press_key("escape")
        _press_key("escape")
        time.sleep(delay)

        try:
            response = provider.query_vision(SUBMENU_ITEMS_PROMPT, image)
            items_data = _parse_json_response(response)

            children = []
            for item_data in items_data:
                name = item_data.get("name", "")
                if not name:
                    continue
                children.append(MenuItem(
                    name=name,
                    shortcut=item_data.get("shortcut", ""),
                    access_methods=[AccessMethod(
                        type=AccessMethodType.MENU_PATH,
                        value=f"{parent_menu} > {submenu_name} > {name}",
                    )],
                ))
            log.info(f"    {submenu_name}: {len(children)} submenu items")
            return children
        except Exception as e:
            log.warning(f"    Submenu parse error: {e}")
            return []

    def _identify_tools(
        self, app_config: AppConfig, provider: VLMProvider, delay: float
    ) -> list[Tool]:
        """Screenshot and identify toolbar/tool buttons."""
        _focus_app(app_config.process_name)
        time.sleep(delay)

        image = _take_screenshot()
        prompt = TOOLBAR_PROMPT.format(app_name=app_config.display_name)

        try:
            response = provider.query_vision(prompt, image)
            tools_data = _parse_json_response(response)

            tools = []
            for tool_data in tools_data:
                tools.append(Tool(
                    name=tool_data.get("name", ""),
                    category=tool_data.get("position", ""),
                    description=tool_data.get("description", ""),
                ))
            log.info(f"  Found {len(tools)} tools")
            return tools
        except Exception as e:
            log.warning(f"  Tool identification failed: {e}")
            return []

    def _explore_known_dialogs(
        self,
        app_config: AppConfig,
        provider: VLMProvider,
        ui_map: UIMap,
        session: SessionState,
        delay: float,
    ) -> None:
        """Open and explore common dialogs using discovered shortcuts."""
        # Find shortcuts that likely open dialogs (containing "..." or common dialog triggers)
        dialog_shortcuts = []
        for sc in ui_map.shortcuts:
            if any(kw in sc.action.lower() for kw in [
                "export", "nuevo", "new", "guardar como", "save as",
                "preferenc", "config", "ajuste", "setting",
            ]):
                dialog_shortcuts.append(sc)

        for sc in dialog_shortcuts[:10]:  # Limit to 10 dialogs
            dialog_id = sc.action.lower().replace(" ", "_").replace(".", "")
            if dialog_id in session.explored_dialogs:
                continue

            log.info(f"  Exploring dialog: {sc.action} ({sc.keys})")
            try:
                dialog = self._open_and_analyze_dialog(
                    app_config, provider, sc.keys, delay
                )
                if dialog:
                    dialog.id = dialog_id
                    ui_map.dialogs[dialog_id] = dialog
                    session.explored_dialogs.append(dialog_id)
            except Exception as e:
                log.warning(f"  Dialog exploration error for {sc.action}: {e}")
                _press_key("escape")
                time.sleep(delay)

    def _open_and_analyze_dialog(
        self,
        app_config: AppConfig,
        provider: VLMProvider,
        shortcut_keys: str,
        delay: float,
    ) -> Dialog | None:
        """Open a dialog via shortcut, screenshot, analyze, then close."""
        _focus_app(app_config.process_name)
        time.sleep(delay)

        # Parse and send shortcut (e.g., "Ctrl+Alt+Shift+W")
        import pyautogui
        keys = shortcut_keys.lower().replace("mayús", "shift").replace("ctrl", "ctrl")
        parts = [k.strip() for k in keys.split("+")]
        try:
            pyautogui.hotkey(*parts)
        except Exception:
            log.warning(f"  Could not send shortcut: {shortcut_keys}")
            return None

        time.sleep(delay * 4)  # Dialogs may take time to open

        image = _take_screenshot()

        # Close dialog
        _press_key("escape")
        time.sleep(delay * 2)
        # Double escape in case of nested dialogs
        _press_key("escape")
        time.sleep(delay)

        try:
            response = provider.query_vision(DIALOG_PROMPT, image)
            data = _parse_json_response(response)

            elements = []
            for el_data in data.get("elements", []):
                elements.append(DialogElement(
                    name=el_data.get("name", ""),
                    element_type=el_data.get("type", "unknown"),
                    default_value=el_data.get("value", ""),
                    options=el_data.get("options", []),
                ))

            return Dialog(
                id="",
                title=data.get("title", "Unknown"),
                elements=elements,
                access_methods=[AccessMethod(
                    type=AccessMethodType.KEYBOARD_SHORTCUT,
                    value=shortcut_keys,
                )],
            )
        except Exception as e:
            log.warning(f"  Dialog parse error: {e}")
            return None
