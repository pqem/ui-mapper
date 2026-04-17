"""SnapshotWriter persistence tests."""

from __future__ import annotations
from pathlib import Path

from ui_mapper.visual.snapshots import SnapshotWriter, snapshot_dir_for


def test_snapshot_dir_layout(tmp_path: Path):
    d = snapshot_dir_for(tmp_path, "my-app", "sess-123")
    assert d == tmp_path / "my-app" / "sess-123"


def test_save_step_writes_png_prompt_response(tmp_path: Path):
    writer = SnapshotWriter(target_dir=tmp_path / "snaps")
    png = writer.save_step(
        "menu_bar",
        image_bytes=b"\x89PNG\r\n\x1a\nFAKE",
        prompt="list menus",
        response="[\"File\"]",
    )
    assert png is not None
    assert png.exists()
    assert png.name == "001_menu_bar.png"
    assert (png.parent / "001_menu_bar.prompt.txt").read_text(encoding="utf-8") == "list menus"
    assert (png.parent / "001_menu_bar.response.txt").read_text(encoding="utf-8") == "[\"File\"]"


def test_save_step_auto_increments_index(tmp_path: Path):
    writer = SnapshotWriter(target_dir=tmp_path / "snaps")
    writer.save_step("a", image_bytes=b"img")
    writer.save_step("b", image_bytes=b"img")
    third = writer.save_step("c", image_bytes=b"img")
    assert third is not None
    assert third.name.startswith("003_")


def test_save_step_slugifies_weird_names(tmp_path: Path):
    writer = SnapshotWriter(target_dir=tmp_path / "snaps")
    png = writer.save_step("File > Export...!", image_bytes=b"img")
    assert png is not None
    # spaces and punctuation collapsed into underscores
    assert "File_Export" in png.name


def test_save_step_skips_empty_components(tmp_path: Path):
    writer = SnapshotWriter(target_dir=tmp_path / "snaps")
    png = writer.save_step("note_only", image_bytes=None, prompt="", response="only response")
    # no PNG because image_bytes was None
    assert png is None
    produced = list((tmp_path / "snaps").glob("001_*"))
    names = [p.name for p in produced]
    assert any(n.endswith(".response.txt") for n in names)
    assert not any(n.endswith(".png") for n in names)


def test_save_note_writes_text(tmp_path: Path):
    writer = SnapshotWriter(target_dir=tmp_path / "snaps")
    path = writer.save_note("err", "boom")
    assert path is not None
    assert path.name.endswith(".note.txt")
    assert path.read_text(encoding="utf-8") == "boom"


def test_disabled_writer_does_nothing(tmp_path: Path):
    writer = SnapshotWriter(target_dir=tmp_path / "snaps", enabled=False)
    assert writer.save_step("x", image_bytes=b"img") is None
    assert writer.save_note("n", "text") is None
    assert not (tmp_path / "snaps").exists()


def test_writer_creates_dir_lazily(tmp_path: Path):
    target = tmp_path / "snaps" / "nested"
    writer = SnapshotWriter(target_dir=target)
    assert not target.exists()
    writer.save_step("first", image_bytes=b"img")
    assert target.exists()
