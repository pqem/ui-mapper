"""Bounding-box parser + scaling tests."""

from __future__ import annotations

from ui_mapper.visual.coordinates import (
    Box,
    BoxesResult,
    parse_menu_boxes,
    scale_box_to_screen,
)


def test_parse_valid_response():
    payload = """{
      "image_width": 1920,
      "image_height": 1080,
      "items": [
        {"name": "File", "x": 10, "y": 5, "width": 35, "height": 24},
        {"name": "Edit", "x": 50, "y": 5, "width": 35, "height": 24}
      ]
    }"""
    r = parse_menu_boxes(payload)
    assert r.image_width == 1920
    assert r.image_height == 1080
    assert len(r.items) == 2
    assert r.items[0].name == "File"
    assert r.items[0].center == (27, 17)


def test_parse_accepts_fenced_response():
    payload = (
        "```json\n"
        '{"image_width": 800, "image_height": 600, "items": ['
        '{"name": "View", "x": 0, "y": 0, "width": 40, "height": 20}'
        ']}\n```'
    )
    r = parse_menu_boxes(payload)
    assert len(r.items) == 1
    assert r.items[0].name == "View"


def test_parse_rejects_zero_size_items():
    payload = """{
      "image_width": 100, "image_height": 100,
      "items": [
        {"name": "File", "x": 0, "y": 0, "width": 0, "height": 20},
        {"name": "Edit", "x": 30, "y": 0, "width": 20, "height": 0}
      ]
    }"""
    r = parse_menu_boxes(payload)
    assert r.items == []


def test_parse_skips_missing_names():
    payload = """{
      "image_width": 100, "image_height": 100,
      "items": [
        {"name": "", "x": 0, "y": 0, "width": 10, "height": 10},
        {"name": "File", "x": 10, "y": 0, "width": 20, "height": 20}
      ]
    }"""
    r = parse_menu_boxes(payload)
    assert [b.name for b in r.items] == ["File"]


def test_parse_invalid_json_returns_empty():
    r = parse_menu_boxes("nope")
    assert r.items == []
    assert r.image_width == 0


def test_find_is_case_insensitive():
    r = BoxesResult(
        image_width=100, image_height=100,
        items=[Box(name="File", x=0, y=0, width=10, height=10)],
    )
    assert r.find("file") is not None
    assert r.find("FILE") is not None
    assert r.find("Missing") is None


def test_scale_box_proportional():
    box = Box(name="x", x=100, y=50, width=40, height=20)
    scaled = scale_box_to_screen(
        box, reported_width=1000, reported_height=500,
        actual_width=2000, actual_height=1000,
    )
    assert (scaled.x, scaled.y, scaled.width, scaled.height) == (200, 100, 80, 40)


def test_scale_box_rejects_implausible_scale():
    box = Box(name="x", x=10, y=10, width=40, height=20)
    # Reported image is tiny relative to actual → 10x scale, implausible
    scaled = scale_box_to_screen(
        box, reported_width=100, reported_height=50,
        actual_width=3000, actual_height=1500,
    )
    # Returns original rather than scaling into garbage
    assert (scaled.x, scaled.width) == (10, 40)


def test_scale_box_missing_dims_returns_original():
    box = Box(name="x", x=10, y=10, width=40, height=20)
    assert scale_box_to_screen(box, 0, 0, 1920, 1080) is box or (
        scale_box_to_screen(box, 0, 0, 1920, 1080).x == 10
    )
