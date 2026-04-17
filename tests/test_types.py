"""Schema v2 basic tests."""

from __future__ import annotations
import dataclasses

from ui_mapper.core.types import (
    SCHEMA_VERSION,
    Menu,
    MenuItem,
    Provenance,
    ProvenanceSource,
    Shortcut,
    UIMap,
)


def test_schema_version_is_v2():
    assert SCHEMA_VERSION.startswith("2.")
    assert UIMap(app_name="x").schema_version == SCHEMA_VERSION


def test_provenance_defaults():
    p = Provenance()
    assert p.source == ProvenanceSource.UNKNOWN
    assert p.confidence == 0.5


def test_menu_item_accepts_provenance():
    item = MenuItem(
        name="Save",
        provenance=Provenance(source=ProvenanceSource.UIA, confidence=0.9),
    )
    assert item.provenance.source == ProvenanceSource.UIA
    assert item.provenance.confidence == 0.9


def test_uimap_serialization_roundtrip():
    m = UIMap(
        app_name="demo",
        menus={"file": Menu(name="File", items=[
            MenuItem(name="Save", provenance=Provenance(confidence=0.8)),
        ])},
        shortcuts=[Shortcut(keys="Ctrl+S", action="save")],
    )
    data = m.to_dict()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["menus"]["file"]["items"][0]["provenance"]["confidence"] == 0.8


def test_entries_by_confidence_counts_below_threshold():
    m = UIMap(app_name="demo")
    m.menus["f"] = Menu(name="File", items=[
        MenuItem(name="a", provenance=Provenance(confidence=0.2)),
        MenuItem(name="b", provenance=Provenance(confidence=0.9)),
    ])
    m.shortcuts = [
        Shortcut(keys="Ctrl+A", action="all", provenance=Provenance(confidence=0.1)),
    ]
    below = m.entries_by_confidence(threshold=0.5)
    assert below["menus"] == 1
    assert below["shortcuts"] == 1
    assert below["dialogs"] == 0
    assert below["tools"] == 0


def test_merge_preserves_distinct_entries():
    base = UIMap(app_name="x")
    base.menus["f"] = Menu(name="File", items=[MenuItem(name="Save")])
    other = UIMap(app_name="x")
    other.menus["f"] = Menu(name="File", items=[MenuItem(name="Save"), MenuItem(name="Close")])
    base.merge(other)
    names = [i.name for i in base.menus["f"].items]
    assert names == ["Save", "Close"]
