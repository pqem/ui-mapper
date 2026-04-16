"""LLM Knowledge mapper — asks the LLM what it already knows about the app.

This is the fastest and cheapest mapper. It leverages the LLM's training data
to get a rough map of menus, shortcuts, and common operations. Typically gives
60-70% coverage in seconds.
"""

from __future__ import annotations
import json
import logging
from datetime import timedelta

from .base import BaseMapper
from ..core.types import UIMap, Menu, MenuItem, Shortcut, Tool, Dialog
from ..core.config import AppConfig
from ..core.session import SessionState
from ..providers.base import VLMProvider

log = logging.getLogger(__name__)

PROMPT_TEMPLATE = """You are an expert on the desktop application "{app_name}".
List everything you know about its user interface structure in the following JSON format.
Be as complete as possible — include ALL menus, shortcuts, tools, and dialogs you know of.

The application locale/language is: {locale}
The platform is: {platform}

Respond ONLY with valid JSON, no markdown, no explanation:

{{
  "menus": {{
    "File": {{
      "access_key": "Alt+F",
      "items": [
        {{"name": "New", "shortcut": "Ctrl+N", "action": "Create new document"}},
        {{"name": "Open", "shortcut": "Ctrl+O", "action": "Open existing file"}},
        {{"name": "Export", "children": [
          {{"name": "Export...", "shortcut": "Ctrl+Alt+Shift+W", "action": "Export dialog"}}
        ]}}
      ]
    }}
  }},
  "shortcuts": [
    {{"keys": "Ctrl+S", "action": "Save", "category": "File"}},
    {{"keys": "Ctrl+Z", "action": "Undo", "category": "Edit"}}
  ],
  "tools": [
    {{"name": "Move Tool", "shortcut": "V", "category": "Selection"}},
    {{"name": "Pen Tool", "shortcut": "P", "category": "Drawing"}}
  ],
  "dialogs": {{
    "export": {{
      "title": "Export",
      "opened_by": "Ctrl+Alt+Shift+W",
      "elements": ["format selector", "quality slider", "export button"]
    }}
  }}
}}
"""


class LLMKnowledgeMapper(BaseMapper):
    """Extracts UI knowledge from the LLM's training data."""

    def can_map(self, app_config: AppConfig) -> bool:
        return True  # Always available if a VLM provider is configured

    def get_priority(self) -> int:
        return 10  # Runs first (cheapest and fastest)

    def get_name(self) -> str:
        return "llm_knowledge"

    def estimate_duration(self, app_config: AppConfig) -> timedelta:
        return timedelta(seconds=30)

    def map(
        self,
        app_config: AppConfig,
        session: SessionState,
        provider: VLMProvider | None = None,
    ) -> UIMap:
        if provider is None:
            raise RuntimeError("LLM Knowledge mapper requires a VLM provider")

        log.info(f"Querying LLM for knowledge about {app_config.display_name}...")

        prompt = PROMPT_TEMPLATE.format(
            app_name=app_config.display_name,
            locale=app_config.locale,
            platform=app_config.platform,
        )

        response = provider.query_text(prompt)

        # Parse JSON response
        ui_map = UIMap(
            app_name=app_config.name,
            locale=app_config.locale,
            sources=["llm_knowledge"],
        )

        try:
            # Clean response: strip markdown code fences if present
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text.rsplit("```", 1)[0]

            data = json.loads(text)
            ui_map = self._parse_response(data, app_config)
            log.info(
                f"LLM knowledge: {len(ui_map.menus)} menus, "
                f"{len(ui_map.shortcuts)} shortcuts, "
                f"{len(ui_map.tools)} tools"
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            log.warning(f"Failed to parse LLM response: {e}")
            log.debug(f"Raw response: {response[:500]}")

        return ui_map

    def _parse_response(self, data: dict, app_config: AppConfig) -> UIMap:
        """Parse the JSON response into a UIMap."""
        ui_map = UIMap(
            app_name=app_config.name,
            locale=app_config.locale,
            sources=["llm_knowledge"],
        )

        # Parse menus
        for menu_name, menu_data in data.get("menus", {}).items():
            items = []
            for item_data in menu_data.get("items", []):
                children = []
                for child_data in item_data.get("children", []):
                    children.append(MenuItem(
                        name=child_data.get("name", ""),
                        shortcut=child_data.get("shortcut", ""),
                        action=child_data.get("action", ""),
                    ))
                items.append(MenuItem(
                    name=item_data.get("name", ""),
                    shortcut=item_data.get("shortcut", ""),
                    action=item_data.get("action", ""),
                    children=children,
                ))
            ui_map.menus[menu_name] = Menu(
                name=menu_name,
                items=items,
                access_key=menu_data.get("access_key", ""),
            )

        # Parse shortcuts
        for sc_data in data.get("shortcuts", []):
            ui_map.shortcuts.append(Shortcut(
                keys=sc_data.get("keys", ""),
                action=sc_data.get("action", ""),
                category=sc_data.get("category", ""),
            ))

        # Parse tools
        for tool_data in data.get("tools", []):
            ui_map.tools.append(Tool(
                name=tool_data.get("name", ""),
                shortcut=tool_data.get("shortcut", ""),
                category=tool_data.get("category", ""),
                description=tool_data.get("description", ""),
            ))

        # Parse dialogs
        for dialog_id, dialog_data in data.get("dialogs", {}).items():
            ui_map.dialogs[dialog_id] = Dialog(
                id=dialog_id,
                title=dialog_data.get("title", ""),
            )

        return ui_map
