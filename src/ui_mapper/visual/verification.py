"""Verify UI state between actions using the VLM.

Without verification the visual mapper is flying blind: it presses
keys, trusts that the menu opened, and stores whatever the VLM reports.
When the app doesn't respond to standard keyboard navigation (Affinity
Designer, some CAD suites), the mapper walks into an invisible hole
and the map ends up empty.

This module adds a cheap "did that work?" check between critical
actions so the mapper can decide to retry or fall back to a different
strategy.
"""

from __future__ import annotations
import json
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


# --------------------------------------------------------- prompts --

VERIFY_MENU_OPEN_PROMPT = """Look at this screenshot.

Task: determine if a dropdown menu is currently open in the foreground.

A dropdown menu looks like a vertical list of items that appeared after
clicking a top menu bar entry. It usually has keyboard shortcuts on the
right side of each item.

Respond with JSON ONLY:
{{
  "menu_open": true or false,
  "menu_name": "File" (the top-level menu label if identifiable, else empty string),
  "confidence": 0.0 to 1.0
}}

JSON only, no explanation:"""

VERIFY_DIALOG_OPEN_PROMPT = """Look at this screenshot.

Task: determine if a dialog window is currently visible in the foreground.

A dialog is a separate window (often modal) with a title bar, buttons,
text fields, and a close/cancel button. Distinct from dropdown menus.

Respond with JSON ONLY:
{{
  "dialog_open": true or false,
  "title": "dialog title or empty string",
  "confidence": 0.0 to 1.0
}}

JSON only:"""


# --------------------------------------------------------- types --

@dataclass
class MenuOpenCheck:
    is_open: bool
    menu_name: str
    confidence: float


@dataclass
class DialogOpenCheck:
    is_open: bool
    title: str
    confidence: float


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


def _safe_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(_strip_fences(text))
    except (json.JSONDecodeError, ValueError):
        return None


def parse_menu_open_response(text: str) -> MenuOpenCheck:
    """Parse a ``VERIFY_MENU_OPEN_PROMPT`` reply.

    A permissive reader: on any parse failure we treat the result as
    "not open, low confidence" — better than raising and crashing the
    mapping loop.
    """
    data = _safe_json(text)
    if not isinstance(data, dict):
        return MenuOpenCheck(is_open=False, menu_name="", confidence=0.0)
    return MenuOpenCheck(
        is_open=bool(data.get("menu_open", False)),
        menu_name=str(data.get("menu_name", "") or ""),
        confidence=_coerce_confidence(data.get("confidence")),
    )


def parse_dialog_open_response(text: str) -> DialogOpenCheck:
    data = _safe_json(text)
    if not isinstance(data, dict):
        return DialogOpenCheck(is_open=False, title="", confidence=0.0)
    return DialogOpenCheck(
        is_open=bool(data.get("dialog_open", False)),
        title=str(data.get("title", "") or ""),
        confidence=_coerce_confidence(data.get("confidence")),
    )


def _coerce_confidence(raw: Any) -> float:
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, val))


# --------------------------------------------------------- runtime helpers --

def verify_menu_open(provider, image: bytes, expected_name: str = "") -> MenuOpenCheck:
    """Ask the VLM whether a dropdown menu is open.

    ``expected_name`` is only used to downgrade confidence when the VLM
    reports a different menu than what the mapper expected — a soft
    mismatch signal, not a hard rejection.
    """
    try:
        response = provider.query_vision(VERIFY_MENU_OPEN_PROMPT, image)
    except Exception as e:
        log.warning("verify_menu_open: provider error %s", e)
        return MenuOpenCheck(is_open=False, menu_name="", confidence=0.0)

    check = parse_menu_open_response(response)
    if check.is_open and expected_name and check.menu_name:
        if check.menu_name.strip().lower() != expected_name.strip().lower():
            # Menu is open but it's not the one we wanted — downgrade
            check = MenuOpenCheck(
                is_open=check.is_open,
                menu_name=check.menu_name,
                confidence=check.confidence * 0.5,
            )
    return check


def verify_dialog_open(provider, image: bytes) -> DialogOpenCheck:
    """Ask the VLM whether a modal dialog is open in the foreground."""
    try:
        response = provider.query_vision(VERIFY_DIALOG_OPEN_PROMPT, image)
    except Exception as e:
        log.warning("verify_dialog_open: provider error %s", e)
        return DialogOpenCheck(is_open=False, title="", confidence=0.0)
    return parse_dialog_open_response(response)
