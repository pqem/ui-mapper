"""Watchdog classification logic tests.

The threaded polling loop is not exercised here — we inject metrics
directly into the private ``_classify`` method to verify decision rules.
"""

from __future__ import annotations

from ui_mapper.core.profile import HardwareThresholds
from ui_mapper.core.watchdog import HardwareWatchdog, WatchdogStatus


def _make(thresholds: HardwareThresholds | None = None) -> HardwareWatchdog:
    return HardwareWatchdog(thresholds or HardwareThresholds())


def test_classify_ok_under_all_limits():
    wd = _make()
    status = wd._classify(
        elapsed_h=0.5,
        since_progress_s=10,
        gpu_temp=60,
        vram_pct=50,
        gpu_util=80,
    )
    assert status == WatchdogStatus.OK


def test_classify_soft_alarm_on_temp():
    wd = _make(HardwareThresholds(gpu_temp_soft=75, gpu_temp_hard=85))
    status = wd._classify(
        elapsed_h=0.5, since_progress_s=10, gpu_temp=77, vram_pct=50, gpu_util=80,
    )
    assert status == WatchdogStatus.SOFT_ALARM


def test_classify_hard_alarm_on_temp():
    wd = _make(HardwareThresholds(gpu_temp_soft=75, gpu_temp_hard=85))
    status = wd._classify(
        elapsed_h=0.5, since_progress_s=10, gpu_temp=90, vram_pct=50, gpu_util=80,
    )
    assert status == WatchdogStatus.HARD_ALARM


def test_classify_hard_alarm_on_vram():
    wd = _make(HardwareThresholds(vram_hard_percent=95))
    status = wd._classify(
        elapsed_h=0.1, since_progress_s=10, gpu_temp=60, vram_pct=97, gpu_util=10,
    )
    assert status == WatchdogStatus.HARD_ALARM


def test_classify_session_max_trumps_everything():
    wd = _make(HardwareThresholds(session_max_hours=2))
    status = wd._classify(
        elapsed_h=2.5, since_progress_s=10, gpu_temp=50, vram_pct=30, gpu_util=50,
    )
    assert status == WatchdogStatus.SESSION_MAX


def test_classify_stuck_when_no_progress_and_gpu_idle():
    wd = _make(HardwareThresholds(stuck_detection_minutes=10))
    status = wd._classify(
        elapsed_h=0.5,
        since_progress_s=11 * 60,   # 11 min without progress
        gpu_temp=40,
        vram_pct=20,
        gpu_util=2,                 # idle
    )
    assert status == WatchdogStatus.STUCK


def test_classify_not_stuck_when_gpu_working():
    wd = _make(HardwareThresholds(stuck_detection_minutes=10))
    status = wd._classify(
        elapsed_h=0.5,
        since_progress_s=11 * 60,
        gpu_temp=70,
        vram_pct=50,
        gpu_util=90,  # busy — probably processing a long prompt
    )
    assert status == WatchdogStatus.OK


def test_classify_gracefully_without_gpu_metrics():
    # When pynvml isn't available, gpu_temp/vram_pct are None
    wd = _make()
    status = wd._classify(
        elapsed_h=0.5, since_progress_s=60, gpu_temp=None, vram_pct=None, gpu_util=None,
    )
    # No GPU data → only time-based checks apply → OK
    assert status == WatchdogStatus.OK
