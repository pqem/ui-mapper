"""Profile save/load + safe-mode graduation tests."""

from __future__ import annotations
import os
from pathlib import Path

import pytest

from ui_mapper.core.profile import (
    HardwareThresholds,
    Profile,
    load_profile,
    save_profile,
)


def test_defaults_are_safe_mode():
    p = Profile()
    assert p.preferences.safe_mode is True
    assert p.preferences.language == "es"
    assert p.hardware_thresholds.gpu_temp_soft == 75
    assert p.hardware_thresholds.gpu_temp_hard == 82
    assert p.hardware_thresholds.session_max_hours == 2.0


def test_graduate_from_safe_mode_loosens_thresholds():
    p = Profile()
    p.graduate_from_safe_mode()

    assert p.preferences.safe_mode is False
    assert p.hardware_thresholds.gpu_temp_soft == 80
    assert p.hardware_thresholds.gpu_temp_hard == 85
    assert p.hardware_thresholds.session_max_hours == 6.0


def test_round_trip_save_and_load(tmp_path: Path):
    target = tmp_path / "profile.yaml"
    original = Profile()
    original.preferences.language = "en"
    original.hardware_thresholds.gpu_temp_soft = 77

    save_profile(original, target)
    assert target.exists()

    loaded = load_profile(target)
    assert loaded.preferences.language == "en"
    assert loaded.hardware_thresholds.gpu_temp_soft == 77


def test_load_missing_file_returns_safe_defaults(tmp_path: Path):
    missing = tmp_path / "nope.yaml"
    loaded = load_profile(missing)
    assert loaded.preferences.safe_mode is True


def test_resolve_env_placeholder(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_KEY", "shh-secret")
    p = Profile()
    assert p.resolve_env("env:FAKE_KEY") == "shh-secret"
    assert p.resolve_env("literal-value") == "literal-value"


def test_resolve_env_missing_returns_empty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DOES_NOT_EXIST", raising=False)
    p = Profile()
    assert p.resolve_env("env:DOES_NOT_EXIST") == ""


def test_from_dict_tolerates_unknown_keys():
    # A future schema may add fields we don't know yet — don't crash on load.
    data = {
        "preferences": {"language": "pt", "future_field": "x"},
        "hardware_thresholds": {"gpu_temp_soft": 70, "another_future": 99},
    }
    p = Profile.from_dict(data)
    assert p.preferences.language == "pt"
    assert p.hardware_thresholds.gpu_temp_soft == 70
