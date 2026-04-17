"""Tool-surface tests — end-to-end behavior against a fake map + dry-run driver."""

from __future__ import annotations
import json
from pathlib import Path

import pytest

from ui_mapper.mcp_server.driver import Driver
from ui_mapper.mcp_server.map_loader import load_map
from ui_mapper.mcp_server.tools import ToolSurface


SAMPLE = {
    "schema_version": "2.0",
    "app_name": "demo",
    "locale": "en",
    "platform": "windows",
    "completion_pct": 50.0,
    "app_metadata": {"name": "demo", "display_name": "Demo", "version": "2.1"},
    "menus": {
        "file": {
            "name": "File",
            "items": [
                {"name": "Save", "shortcut": "Ctrl+S"},
                {"name": "Open", "shortcut": "Ctrl+O"},
            ],
        },
    },
    "shortcuts": [
        {"keys": "Ctrl+Z", "action": "Undo", "category": "edit"},
        {"keys": "Ctrl+Y", "action": "Redo", "category": "edit"},
    ],
    "tools": [
        {"name": "Brush", "shortcut": "B", "category": "paint"},
        {"name": "Eraser", "shortcut": "E", "category": "paint"},
    ],
    "dialogs": {
        "export": {"id": "export", "title": "Export", "elements": []},
    },
}


@pytest.fixture
def surface(tmp_path: Path) -> ToolSurface:
    p = tmp_path / "map.json"
    p.write_text(json.dumps(SAMPLE), encoding="utf-8")
    return ToolSurface(load_map(p), Driver(dry_run=True))


# -- query tools -------------------------------------------------------------

def test_get_app_info(surface: ToolSurface):
    info = surface.get_app_info()
    assert info["app_name"] == "demo"
    assert info["version"] == "2.1"
    assert info["counts"]["shortcuts"] == 2


def test_list_menus_respects_limit(surface: ToolSurface):
    items = surface.list_menus(limit=1)
    assert len(items) == 1


def test_list_menus_contains_filter(surface: ToolSurface):
    items = surface.list_menus(contains="save")
    assert len(items) == 1
    assert items[0]["name"] == "Save"


def test_list_shortcuts_by_category(surface: ToolSurface):
    items = surface.list_shortcuts(category="edit")
    assert len(items) == 2


def test_list_tools_by_contains(surface: ToolSurface):
    items = surface.list_tools(contains="erase")
    assert len(items) == 1
    assert items[0]["name"] == "Eraser"


def test_search_across_types(surface: ToolSurface):
    hits = surface.search_map("ctrl")
    assert any(h["keys"] == "Ctrl+Z" for h in hits["shortcuts"])


# -- action tools ------------------------------------------------------------

def test_execute_shortcut_succeeds_in_dry_run(surface: ToolSurface):
    r = surface.execute_shortcut("Ctrl+S")
    assert r["ok"] is True


def test_execute_shortcut_rejects_empty(surface: ToolSurface):
    r = surface.execute_shortcut("")
    assert r["ok"] is False


def test_execute_menu_action_found(surface: ToolSurface):
    r = surface.execute_menu_action("File > Save")
    assert r["ok"] is True
    assert r["entry"]["shortcut"] == "Ctrl+S"


def test_execute_menu_action_not_found(surface: ToolSurface):
    r = surface.execute_menu_action("Nope > None")
    assert r["ok"] is False
    assert "not found" in r["message"].lower()


def test_execute_action_by_description(surface: ToolSurface):
    r = surface.execute_action_by_description("Undo")
    assert r["ok"] is True
    assert r["entry"]["keys"] == "Ctrl+Z"


def test_type_text_dry_run(surface: ToolSurface):
    r = surface.type_text("hello")
    assert r["ok"] is True


def test_click_at_dry_run(surface: ToolSurface):
    r = surface.click_at(10, 20, "right")
    assert r["ok"] is True
