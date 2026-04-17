"""Extract bounding boxes from the VLM and click them.

Keyboard-based menu navigation (Alt, arrows, Enter) fails on apps that
don't implement standard Windows menu accelerators — Affinity Designer,
Blender, many Electron apps. For those we fall back to locating menu
bar items visually and clicking their center.

Coordinate reasoning is delegated entirely to the VLM: we don't try to
detect edges or run classic CV, we just ask for pixel coordinates and
validate the shape of the response.
"""

from __future__ import annotations
import json
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


# --------------------------------------------------------- prompts --

MENU_BAR_BOXES_PROMPT = """Look at this screenshot of a desktop application.

Task: locate every item in the top menu bar (File, Edit, View, Help, etc.)
and return its bounding box in pixel coordinates.

- Origin is the top-left corner of the screenshot.
- Coordinates are integers.
- Include only real menu bar items (not toolbar buttons).

Respond with JSON ONLY:
{{
  "image_width": <int>,
  "image_height": <int>,
  "items": [
    {{"name": "File",  "x": 10, "y": 5, "width": 35, "height": 24}},
    {{"name": "Edit",  "x": 50, "y": 5, "width": 35, "height": 24}}
  ]
}}

JSON only, no explanation:"""


# --------------------------------------------------------- types --

@dataclass
class Box:
    name: str
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


@dataclass
class BoxesResult:
    image_width: int
    image_height: int
    items: list[Box]

    def find(self, name: str) -> Box | None:
        needle = name.strip().lower()
        for b in self.items:
            if b.name.strip().lower() == needle:
                return b
        return None


# --------------------------------------------------------- parsing --

def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        elif "```" in text:
            text = text.rsplit("```", 1)[0]
    return text.strip()


def _coerce_int(raw: Any, default: int = 0) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def parse_menu_boxes(text: str) -> BoxesResult:
    """Tolerant parser for ``MENU_BAR_BOXES_PROMPT`` responses.

    On any malformed payload returns an empty BoxesResult rather than
    raising — callers decide whether to retry or degrade gracefully.
    """
    try:
        data = json.loads(_strip_fences(text))
    except (json.JSONDecodeError, ValueError):
        log.warning("parse_menu_boxes: invalid JSON")
        return BoxesResult(image_width=0, image_height=0, items=[])
    if not isinstance(data, dict):
        return BoxesResult(image_width=0, image_height=0, items=[])

    items: list[Box] = []
    for raw in data.get("items") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "") or "").strip()
        if not name:
            continue
        w = _coerce_int(raw.get("width"), 0)
        h = _coerce_int(raw.get("height"), 0)
        if w <= 0 or h <= 0:
            continue
        items.append(Box(
            name=name,
            x=_coerce_int(raw.get("x"), 0),
            y=_coerce_int(raw.get("y"), 0),
            width=w,
            height=h,
        ))
    return BoxesResult(
        image_width=_coerce_int(data.get("image_width"), 0),
        image_height=_coerce_int(data.get("image_height"), 0),
        items=items,
    )


# --------------------------------------------------------- runtime helpers --

def query_menu_bar_boxes(provider, image: bytes) -> BoxesResult:
    """Ask the VLM to locate menu bar items and return their boxes."""
    try:
        response = provider.query_vision(MENU_BAR_BOXES_PROMPT, image)
    except Exception as e:
        log.warning("query_menu_bar_boxes: provider error %s", e)
        return BoxesResult(image_width=0, image_height=0, items=[])
    return parse_menu_boxes(response)


def scale_box_to_screen(
    box: Box, reported_width: int, reported_height: int,
    actual_width: int, actual_height: int,
) -> Box:
    """Rescale a box when the VLM's reported image size differs from the actual.

    Some models "guess" the image size rather than read it accurately.
    When the reported dimensions are implausible (zero or >2x off) we
    assume the box is already in screen coordinates.
    """
    if reported_width <= 0 or reported_height <= 0:
        return box
    if not actual_width or not actual_height:
        return box
    # Guard against implausible scales — return original
    x_scale = actual_width / reported_width
    y_scale = actual_height / reported_height
    if not (0.5 <= x_scale <= 2.0) or not (0.5 <= y_scale <= 2.0):
        return box
    return Box(
        name=box.name,
        x=int(box.x * x_scale),
        y=int(box.y * y_scale),
        width=int(box.width * x_scale),
        height=int(box.height * y_scale),
    )
