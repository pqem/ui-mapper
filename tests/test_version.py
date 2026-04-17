"""Version detection + change detection tests.

Windows-specific paths (PowerShell calls) are not exercised here — those
need an integration harness. We focus on the pure logic: change detection,
hashing, and v2 metadata round-trip.
"""

from __future__ import annotations
import json
from pathlib import Path

from ui_mapper.core.types import AppMetadata
from ui_mapper.core.version import (
    hash_executable,
    load_previous_metadata,
    version_changed,
)


def test_version_changed_on_version_string():
    prev = AppMetadata(name="x", version="3.2.0")
    curr = AppMetadata(name="x", version="3.2.1")
    assert version_changed(curr, prev) is True


def test_version_unchanged_when_equal():
    prev = AppMetadata(name="x", version="3.2.0")
    curr = AppMetadata(name="x", version="3.2.0")
    assert version_changed(curr, prev) is False


def test_version_changed_falls_back_to_hash():
    prev = AppMetadata(name="x", version="", executable_hash="aaaa")
    curr = AppMetadata(name="x", version="", executable_hash="bbbb")
    assert version_changed(curr, prev) is True


def test_version_changed_none_previous_is_false():
    curr = AppMetadata(name="x", version="3.2.0")
    assert version_changed(curr, None) is False


def test_hash_executable_known_content(tmp_path: Path):
    target = tmp_path / "fake.exe"
    target.write_bytes(b"hello")
    # sha256("hello") is well known
    expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert hash_executable(target) == expected


def test_hash_executable_missing_returns_empty(tmp_path: Path):
    assert hash_executable(tmp_path / "nope") == ""


def test_load_previous_metadata_reads_v2_map(tmp_path: Path):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({
        "schema_version": "2.0",
        "app_name": "x",
        "app_metadata": {
            "name": "x",
            "display_name": "X",
            "version": "1.2.3",
            "version_detected_at": "2026-04-17T09:00:00+00:00",
            "executable_path": "C:/x.exe",
            "executable_hash": "deadbeef",
            "locale": "en",
            "platform": "windows",
        },
    }), encoding="utf-8")

    meta = load_previous_metadata(map_path)
    assert meta is not None
    assert meta.version == "1.2.3"
    assert meta.executable_hash == "deadbeef"


def test_load_previous_metadata_v1_returns_none(tmp_path: Path):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"app_name": "x", "app_version": "1.0"}), encoding="utf-8")
    assert load_previous_metadata(map_path) is None


def test_load_previous_metadata_missing_file(tmp_path: Path):
    assert load_previous_metadata(tmp_path / "nope.json") is None
