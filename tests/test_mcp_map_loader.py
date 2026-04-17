"""map_loader tests — parsing v2 UIMap JSON into a searchable view."""

from __future__ import annotations
import json
from pathlib import Path

import pytest

from ui_mapper.mcp_server.map_loader import load_map


SAMPLE_MAP = {
    "schema_version": "2.0",
    "app_name": "demo-app",
    "app_version": "1.0.0",
    "locale": "en",
    "platform": "windows",
    "completion_pct": 72.0,
    "app_metadata": {
        "name": "demo-app",
        "display_name": "Demo App",
        "version": "1.0.0",
    },
    "menus": {
        "file": {
            "name": "File",
            "items": [
                {
                    "name": "Save",
                    "shortcut": "Ctrl+S",
                    "provenance": {"source": "uia", "confidence": 0.95},
                },
                {
                    "name": "Export",
                    "children": [
                        {
                            "name": "PNG",
                            "shortcut": "Ctrl+Alt+P",
                            "provenance": {"source": "llm-knowledge", "confidence": 0.8},
                        },
                    ],
                },
            ],
        },
    },
    "shortcuts": [
        {
            "keys": "Ctrl+Z",
            "action": "Undo",
            "category": "edit",
            "provenance": {"source": "uia", "confidence": 0.99},
        },
    ],
    "tools": [
        {
            "name": "Brush",
            "shortcut": "B",
            "category": "paint",
            "description": "Paint with a brush",
        },
    ],
    "dialogs": {
        "export": {
            "id": "export",
            "title": "Export",
            "elements": [{"name": "format"}, {"name": "quality"}],
            "provenance": {"source": "visual", "confidence": 0.7},
        },
    },
}


@pytest.fixture
def map_path(tmp_path: Path) -> Path:
    p = tmp_path / "map.json"
    p.write_text(json.dumps(SAMPLE_MAP), encoding="utf-8")
    return p


def test_load_populates_metadata(map_path: Path):
    m = load_map(map_path)
    assert m.app_name == "demo-app"
    assert m.display_name == "Demo App"
    assert m.version == "1.0.0"
    assert m.schema_version == "2.0"
    assert m.completion_pct == pytest.approx(72.0)


def test_load_flattens_nested_menus(map_path: Path):
    m = load_map(map_path)
    paths = [entry.path for entry in m.menus]
    assert "File > Save" in paths
    assert "File > Export" in paths
    assert "File > Export > PNG" in paths


def test_load_preserves_provenance(map_path: Path):
    m = load_map(map_path)
    save = next(e for e in m.menus if e.name == "Save")
    assert save.source == "uia"
    assert save.confidence == 0.95


def test_search_is_case_insensitive(map_path: Path):
    m = load_map(map_path)
    hits = m.search("undo")
    assert len(hits["shortcuts"]) == 1
    assert hits["shortcuts"][0].keys == "Ctrl+Z"


def test_search_across_types(map_path: Path):
    m = load_map(map_path)
    hits = m.search("export")
    # menu entries and dialog should match
    assert any("Export" in e.path for e in hits["menus"])
    assert any(d.id == "export" for d in hits["dialogs"])


def test_find_menu_returns_exact_match(map_path: Path):
    m = load_map(map_path)
    entry = m.find_menu("File > Save")
    assert entry is not None
    assert entry.shortcut == "Ctrl+S"


def test_find_menu_none_for_missing(map_path: Path):
    m = load_map(map_path)
    assert m.find_menu("Nonsense > Path") is None


def test_find_shortcut_for_action(map_path: Path):
    m = load_map(map_path)
    sc = m.find_shortcut_for_action("Undo")
    assert sc is not None
    assert sc.keys == "Ctrl+Z"


def test_load_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_map(tmp_path / "nope.json")
