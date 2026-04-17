"""Driver & shortcut-parser tests (no pyautogui required in dry-run)."""

from __future__ import annotations

from ui_mapper.mcp_server.driver import Driver, parse_shortcut


# -- parser ------------------------------------------------------------------

def test_parse_simple_combo():
    assert parse_shortcut("Ctrl+S") == ["ctrl", "s"]


def test_parse_case_insensitive():
    assert parse_shortcut("CTRL+S") == ["ctrl", "s"]
    assert parse_shortcut("ctrl+s") == ["ctrl", "s"]


def test_parse_multi_modifier():
    assert parse_shortcut("Ctrl+Alt+Shift+W") == ["ctrl", "alt", "shift", "w"]


def test_parse_function_key():
    assert parse_shortcut("F5") == ["f5"]
    assert parse_shortcut("F12") == ["f12"]


def test_parse_named_key():
    assert parse_shortcut("Enter") == ["enter"]
    assert parse_shortcut("Escape") == ["esc"]
    assert parse_shortcut("PageDown") == ["pagedown"]


def test_parse_whitespace_as_separator():
    assert parse_shortcut("Ctrl Alt S") == ["ctrl", "alt", "s"]


def test_parse_empty_returns_empty():
    assert parse_shortcut("") == []
    assert parse_shortcut("   ") == []


def test_parse_alias_cmd_to_command():
    assert parse_shortcut("Cmd+S") == ["command", "s"]


def test_parse_plus_literal():
    # Users should write "plus" for the plus key
    assert parse_shortcut("Ctrl+plus") == ["ctrl", "+"]


# -- driver dry-run ----------------------------------------------------------

def test_driver_dry_run_keypress():
    d = Driver(dry_run=True)
    result = d.press_shortcut("Ctrl+S")
    assert result.ok
    assert "ctrl+s" in result.message.lower()


def test_driver_empty_shortcut_fails():
    d = Driver(dry_run=True)
    result = d.press_shortcut("")
    assert not result.ok


def test_driver_dry_run_type():
    d = Driver(dry_run=True)
    result = d.type_text("hello")
    assert result.ok
    assert "5" in result.message  # "dry-run: type 5 chars"


def test_driver_dry_run_click():
    d = Driver(dry_run=True)
    result = d.click_at(100, 200, "right")
    assert result.ok
    assert "(100,200)" in result.message
    assert "right" in result.message
