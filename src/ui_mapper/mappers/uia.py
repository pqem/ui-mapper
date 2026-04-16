"""Windows UI Automation mapper — walks the UIA tree to discover UI elements.

Uses PowerShell and the .NET UIAutomation API to enumerate menus, buttons,
dialogs, and their properties. This gives high-confidence data for standard
Windows controls, but misses custom-rendered elements (common in Affinity, etc.).
"""

from __future__ import annotations
import subprocess
import json
import logging
from datetime import timedelta

from .base import BaseMapper
from ..core.types import UIMap, Menu, MenuItem, Shortcut, AccessMethod, AccessMethodType
from ..core.config import AppConfig
from ..core.session import SessionState
from ..providers.base import VLMProvider

log = logging.getLogger(__name__)

MENU_WALK_PS = r'''
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$processName = '{process_name}'
$proc = Get-Process -Name $processName -ErrorAction SilentlyContinue |
    Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1

if (-not $proc) {{
    Write-Output '{{"error": "Process not found: {process_name}"}}'
    exit
}}

$root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)

# Find the menu bar
$menuCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Menu
)
$menuBar = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $menuCond)

$result = @{{ "menus" = @{{}}; "window_title" = $proc.MainWindowTitle }}

if ($menuBar) {{
    $menuItems = $menuBar.FindAll(
        [System.Windows.Automation.TreeScope]::Children,
        [System.Windows.Automation.Condition]::TrueCondition
    )

    foreach ($menuItem in $menuItems) {{
        $menuName = $menuItem.Current.Name
        if (-not $menuName) {{ continue }}

        $items = @()

        # Try to expand the menu
        try {{
            $expandPattern = $menuItem.GetCurrentPattern(
                [System.Windows.Automation.ExpandCollapsePattern]::Pattern
            )
            $expandPattern.Expand()
            Start-Sleep -Milliseconds 400

            # Get child items
            $childCond = New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                [System.Windows.Automation.ControlType]::MenuItem
            )
            $children = $menuItem.FindAll(
                [System.Windows.Automation.TreeScope]::Descendants, $childCond
            )

            foreach ($child in $children) {{
                $childName = $child.Current.Name
                if (-not $childName) {{ continue }}

                # Check for keyboard shortcut in AccessKey or AcceleratorKey
                $shortcut = $child.Current.AcceleratorKey
                if (-not $shortcut) {{ $shortcut = "" }}

                # Check if it has children (submenu)
                $hasChildren = $false
                $patterns = $child.GetSupportedPatterns()
                foreach ($p in $patterns) {{
                    if ($p.ProgrammaticName -eq 'ExpandCollapsePatternIdentifiers.Pattern') {{
                        $hasChildren = $true
                        break
                    }}
                }}

                $items += @{{
                    "name" = $childName
                    "shortcut" = $shortcut
                    "has_submenu" = $hasChildren
                    "automation_id" = $child.Current.AutomationId
                }}
            }}

            # Collapse the menu
            $expandPattern.Collapse()
            Start-Sleep -Milliseconds 200
        }} catch {{
            # Menu might not support ExpandCollapse
        }}

        $result["menus"][$menuName] = @{{
            "items" = $items
            "access_key" = $menuItem.Current.AccessKey
        }}
    }}
}}

# Output as JSON
$result | ConvertTo-Json -Depth 5 -Compress
'''


class UIAMapper(BaseMapper):
    """Maps UI elements using Windows UI Automation tree."""

    def can_map(self, app_config: AppConfig) -> bool:
        return app_config.platform == "windows" and bool(app_config.process_name)

    def get_priority(self) -> int:
        return 30  # After LLM knowledge and config parsing

    def get_name(self) -> str:
        return "uia"

    def estimate_duration(self, app_config: AppConfig) -> timedelta:
        return timedelta(minutes=5)

    def map(
        self,
        app_config: AppConfig,
        session: SessionState,
        provider: VLMProvider | None = None,
    ) -> UIMap:
        log.info(f"Walking UIA tree for {app_config.process_name}...")

        ui_map = UIMap(
            app_name=app_config.name,
            locale=app_config.locale,
            sources=["uia"],
        )

        # Walk menu bar
        menu_data = self._walk_menus(app_config.process_name)
        if menu_data:
            for menu_name, menu_info in menu_data.get("menus", {}).items():
                items = []
                for item_info in menu_info.get("items", []):
                    access = []
                    if item_info.get("shortcut"):
                        access.append(AccessMethod(
                            type=AccessMethodType.KEYBOARD_SHORTCUT,
                            value=item_info["shortcut"],
                        ))
                    if item_info.get("automation_id"):
                        access.append(AccessMethod(
                            type=AccessMethodType.UIA_ELEMENT,
                            value=item_info["automation_id"],
                        ))
                    items.append(MenuItem(
                        name=item_info.get("name", ""),
                        shortcut=item_info.get("shortcut", ""),
                        access_methods=access,
                    ))
                    # Extract shortcuts for the shortcuts list
                    if item_info.get("shortcut"):
                        ui_map.shortcuts.append(Shortcut(
                            keys=item_info["shortcut"],
                            action=item_info.get("name", ""),
                            category=menu_name,
                        ))

                ui_map.menus[menu_name] = Menu(
                    name=menu_name,
                    items=items,
                    access_key=menu_info.get("access_key", ""),
                )

            if menu_data.get("window_title"):
                ui_map.raw_data["window_title"] = menu_data["window_title"]

        log.info(
            f"UIA found: {len(ui_map.menus)} menus, "
            f"{sum(len(m.items) for m in ui_map.menus.values())} items, "
            f"{len(ui_map.shortcuts)} shortcuts"
        )

        session.explored_menus = list(ui_map.menus.keys())
        return ui_map

    def _walk_menus(self, process_name: str) -> dict | None:
        """Execute PowerShell to walk the UIA menu tree."""
        script = MENU_WALK_PS.format(process_name=process_name)
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "-"],
                input=script, capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                log.warning(f"UIA menu walk failed: {result.stderr[:200]}")
                return None

            return json.loads(result.stdout.strip())
        except json.JSONDecodeError as e:
            log.warning(f"Failed to parse UIA output: {e}")
            return None
        except subprocess.TimeoutExpired:
            log.warning("UIA menu walk timed out")
            return None
        except Exception as e:
            log.warning(f"UIA menu walk error: {e}")
            return None
