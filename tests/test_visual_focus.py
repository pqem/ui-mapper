"""focus_window sanity tests — skipped on non-Windows hosts."""

from __future__ import annotations
import platform

import pytest

from ui_mapper.visual.focus import focus_window


def test_focus_non_windows_is_noop():
    if platform.system() == "Windows":
        pytest.skip("test covers non-Windows fallback only")
    assert focus_window("Notepad") is False


def test_focus_empty_name_returns_false():
    assert focus_window("") is False


def test_focus_missing_process_returns_false():
    # A process that almost certainly isn't running
    assert focus_window("definitely-not-a-real-process-xyz-123") is False
