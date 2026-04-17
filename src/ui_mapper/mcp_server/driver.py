"""Drive a live application — keyboard shortcuts + clicks.

The driver is intentionally thin for MVP: the vast majority of useful
actions on a mapped app are already exposed as keyboard shortcuts. Menu
path navigation, drag-drop and deep UIA interactions will come as the
visual mapper and UIA driver mature.

Shortcut parsing is permissive:
- Any case: ``ctrl+s`` = ``Ctrl+S`` = ``CTRL+S``.
- Any separator: ``+`` or whitespace.
- Synonyms: ``cmd`` → ``command``, ``control`` → ``ctrl``.
- Literal ``+`` inside a chord is written as ``plus``.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable


# -----------------------------------------------------------------------------
# Parsing
# -----------------------------------------------------------------------------

_MODIFIER_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl",
    "alt": "alt", "option": "alt", "opt": "alt",
    "shift": "shift",
    "cmd": "command", "command": "command", "super": "win", "meta": "win",
    "win": "win", "windows": "win",
}

_NAMED_KEYS = {
    # Function keys handled separately as F1-F24
    "enter": "enter", "return": "enter",
    "esc": "esc", "escape": "esc",
    "space": "space", "spacebar": "space",
    "tab": "tab",
    "backspace": "backspace", "bksp": "backspace",
    "delete": "delete", "del": "delete",
    "home": "home", "end": "end",
    "pageup": "pageup", "pagedown": "pagedown",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "plus": "+", "minus": "-",
    "insert": "insert", "ins": "insert",
}


def parse_shortcut(spec: str) -> list[str]:
    """Normalize a human shortcut string to a pyautogui key list.

    Returns an empty list on empty input.
    """
    if not spec:
        return []
    # allow spaces as separators, collapse whitespace
    token = spec.replace(" ", "+")
    parts = [p.strip().lower() for p in token.split("+") if p.strip()]
    out: list[str] = []
    for p in parts:
        if p in _MODIFIER_ALIASES:
            out.append(_MODIFIER_ALIASES[p])
        elif p in _NAMED_KEYS:
            out.append(_NAMED_KEYS[p])
        elif len(p) == 1:
            out.append(p)
        elif p.startswith("f") and p[1:].isdigit() and 1 <= int(p[1:]) <= 24:
            out.append(p)
        else:
            # unknown token — pass through lowercase; pyautogui may still map it
            out.append(p)
    return out


# -----------------------------------------------------------------------------
# Driver
# -----------------------------------------------------------------------------

@dataclass
class DriverResult:
    ok: bool
    message: str
    data: dict | None = None


class Driver:
    """Thin wrapper over pyautogui used to execute actions.

    ``pyautogui`` is an optional dependency. If missing, operations
    return a DriverResult(ok=False, ...) rather than crashing — the MCP
    server surfaces that to the LLM as a tool error.

    ``dry_run=True`` makes the driver log intended actions without
    actually touching the keyboard / mouse — used in tests and when
    the user wants to preview behavior without risk.
    """

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._pyautogui = None
        self._import_error: str | None = None
        try:
            import pyautogui  # type: ignore
            pyautogui.FAILSAFE = True  # mouse → screen corner aborts
            self._pyautogui = pyautogui
        except ImportError as e:
            self._import_error = str(e)

    # -- keyboard --------------------------------------------------------

    def press_shortcut(self, spec: str) -> DriverResult:
        keys = parse_shortcut(spec)
        if not keys:
            return DriverResult(ok=False, message="empty shortcut")
        if self.dry_run:
            return DriverResult(ok=True, message=f"dry-run: {'+'.join(keys)}")
        if self._pyautogui is None:
            return DriverResult(
                ok=False,
                message=f"pyautogui not installed: {self._import_error}",
            )
        try:
            if len(keys) == 1:
                self._pyautogui.press(keys[0])
            else:
                self._pyautogui.hotkey(*keys)
            return DriverResult(ok=True, message=f"pressed {'+'.join(keys)}")
        except Exception as e:  # pragma: no cover — hardware-dependent
            return DriverResult(ok=False, message=f"keypress failed: {e}")

    def type_text(self, text: str, interval: float = 0.02) -> DriverResult:
        if self.dry_run:
            return DriverResult(ok=True, message=f"dry-run: type {len(text)} chars")
        if self._pyautogui is None:
            return DriverResult(
                ok=False,
                message=f"pyautogui not installed: {self._import_error}",
            )
        try:
            self._pyautogui.typewrite(text, interval=interval)
            return DriverResult(ok=True, message=f"typed {len(text)} chars")
        except Exception as e:  # pragma: no cover
            return DriverResult(ok=False, message=f"type failed: {e}")

    # -- mouse -----------------------------------------------------------

    def click_at(self, x: int, y: int, button: str = "left") -> DriverResult:
        if self.dry_run:
            return DriverResult(ok=True, message=f"dry-run: click {button} at ({x},{y})")
        if self._pyautogui is None:
            return DriverResult(
                ok=False,
                message=f"pyautogui not installed: {self._import_error}",
            )
        try:
            self._pyautogui.click(x=x, y=y, button=button)
            return DriverResult(ok=True, message=f"clicked {button} at ({x},{y})")
        except Exception as e:  # pragma: no cover
            return DriverResult(ok=False, message=f"click failed: {e}")
