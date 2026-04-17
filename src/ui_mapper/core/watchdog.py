"""Hardware watchdog — protects GPU and aborts stuck sessions.

Runs a background thread that polls GPU temperature, VRAM usage and
mapper progress. Signals to the orchestrator when to pause (soft alarm)
or abort (hard alarm) a long-running mapping session.

See docs/adr/004-hardware-watchdog.md for thresholds and rationale.

Dependencies are *optional*:
- ``pynvml`` for NVIDIA GPU metrics
- ``psutil`` for process / RAM fallback

When neither is installed the watchdog still monitors session duration
and stuck detection — just without GPU visibility. It will log the
limitation so the user knows what's being skipped.
"""

from __future__ import annotations
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from .profile import HardwareThresholds

logger = logging.getLogger(__name__)


# Optional hardware libraries -------------------------------------------------

try:
    import pynvml  # type: ignore
    _HAS_PYNVML = True
except ImportError:
    _HAS_PYNVML = False

try:
    import psutil  # type: ignore
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


# -----------------------------------------------------------------------------
# Types
# -----------------------------------------------------------------------------

class WatchdogStatus(str, Enum):
    """High-level health state the watchdog reports to the orchestrator."""
    OK = "ok"
    SOFT_ALARM = "soft_alarm"       # pause gracefully, wait for clear
    HARD_ALARM = "hard_alarm"       # abort with checkpoint
    STUCK = "stuck"                 # no progress + GPU idle → abort
    SESSION_MAX = "session_max"     # max hours reached → stop cleanly


@dataclass
class WatchdogState:
    status: WatchdogStatus = WatchdogStatus.OK
    gpu_temp_c: float | None = None
    vram_used_percent: float | None = None
    gpu_utilization_percent: float | None = None
    elapsed_hours: float = 0.0
    seconds_since_progress: float = 0.0
    pause_events: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)  # e.g. ["gpu", "ram"]


# -----------------------------------------------------------------------------
# Watchdog
# -----------------------------------------------------------------------------

class HardwareWatchdog:
    """Background watchdog for hardware and session health.

    Usage:
        wd = HardwareWatchdog(profile.hardware_thresholds)
        wd.start()
        try:
            for mapper in mappers:
                while wd.should_pause():
                    time.sleep(5)
                if wd.should_abort():
                    break
                mapper.run()
                wd.report_progress(f"finished {mapper.name}")
        finally:
            wd.stop()
    """

    def __init__(
        self,
        thresholds: HardwareThresholds,
        on_soft_alarm: Callable[[WatchdogState], None] | None = None,
        on_hard_alarm: Callable[[WatchdogState], None] | None = None,
    ) -> None:
        self.thresholds = thresholds
        self.on_soft_alarm = on_soft_alarm
        self.on_hard_alarm = on_hard_alarm

        self._state = WatchdogState()
        self._state.capabilities = self._detect_capabilities()

        self._start_monotonic = 0.0
        self._last_progress_monotonic = 0.0

        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self._thread: threading.Thread | None = None

        self._nvml_handle: object | None = None

    # ----- capability probing -----

    def _detect_capabilities(self) -> list[str]:
        caps: list[str] = []
        if _HAS_PYNVML:
            try:
                pynvml.nvmlInit()
                caps.append("gpu")
            except Exception as e:  # pragma: no cover — hardware-dependent
                logger.info("pynvml init failed: %s — GPU metrics disabled", e)
        if _HAS_PSUTIL:
            caps.append("ram")
        if not caps:
            logger.warning(
                "watchdog: neither pynvml nor psutil available — "
                "monitoring limited to session duration and progress"
            )
        return caps

    def _init_nvml_handle(self) -> None:
        if not _HAS_PYNVML or "gpu" not in self._state.capabilities:
            return
        try:
            self._nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception as e:  # pragma: no cover
            logger.warning("watchdog: failed to get GPU handle: %s", e)
            self._nvml_handle = None

    # ----- lifecycle -----

    def start(self) -> None:
        if self._thread is not None:
            return
        self._start_monotonic = time.monotonic()
        self._last_progress_monotonic = self._start_monotonic
        self._init_nvml_handle()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="ui-mapper-watchdog", daemon=True
        )
        self._thread.start()
        logger.info(
            "watchdog started (capabilities=%s, soft=%s°C, hard=%s°C, session_max=%.1fh)",
            self._state.capabilities,
            self.thresholds.gpu_temp_soft,
            self.thresholds.gpu_temp_hard,
            self.thresholds.session_max_hours,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        if _HAS_PYNVML and "gpu" in self._state.capabilities:
            try:
                pynvml.nvmlShutdown()
            except Exception:  # pragma: no cover
                pass

    # ----- public API for the orchestrator / mappers -----

    def report_progress(self, note: str = "") -> None:
        """Called by the orchestrator/mapper whenever forward progress is made."""
        with self._state_lock:
            self._last_progress_monotonic = time.monotonic()
            if note:
                logger.debug("watchdog: progress reported — %s", note)

    def should_pause(self) -> bool:
        with self._state_lock:
            return self._state.status == WatchdogStatus.SOFT_ALARM

    def should_abort(self) -> bool:
        with self._state_lock:
            return self._state.status in {
                WatchdogStatus.HARD_ALARM,
                WatchdogStatus.STUCK,
                WatchdogStatus.SESSION_MAX,
            }

    def wait_for_clear(self, timeout_seconds: float = 600.0) -> bool:
        """Block until the soft alarm clears or timeout is reached."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if not self.should_pause():
                return True
            if self.should_abort():
                return False
            time.sleep(2.0)
        return False

    def get_state(self) -> WatchdogState:
        with self._state_lock:
            # shallow copy so callers can read without holding the lock
            return WatchdogState(
                status=self._state.status,
                gpu_temp_c=self._state.gpu_temp_c,
                vram_used_percent=self._state.vram_used_percent,
                gpu_utilization_percent=self._state.gpu_utilization_percent,
                elapsed_hours=self._state.elapsed_hours,
                seconds_since_progress=self._state.seconds_since_progress,
                pause_events=list(self._state.pause_events),
                capabilities=list(self._state.capabilities),
            )

    # ----- internal loop -----

    def _run_loop(self) -> None:
        interval = max(5, self.thresholds.poll_interval_seconds)
        while not self._stop_event.is_set():
            self._tick()
            self._stop_event.wait(timeout=interval)

    def _tick(self) -> None:
        now = time.monotonic()
        elapsed_h = (now - self._start_monotonic) / 3600.0
        since_progress_s = now - self._last_progress_monotonic

        gpu_temp, vram_pct, gpu_util = self._read_gpu_metrics()

        new_status = self._classify(elapsed_h, since_progress_s, gpu_temp, vram_pct, gpu_util)

        with self._state_lock:
            prev_status = self._state.status
            self._state.status = new_status
            self._state.gpu_temp_c = gpu_temp
            self._state.vram_used_percent = vram_pct
            self._state.gpu_utilization_percent = gpu_util
            self._state.elapsed_hours = elapsed_h
            self._state.seconds_since_progress = since_progress_s
            if new_status != prev_status and new_status != WatchdogStatus.OK:
                event = f"{new_status.value} at {elapsed_h:.2f}h (temp={gpu_temp}, vram={vram_pct})"
                self._state.pause_events.append(event)
                logger.warning("watchdog: %s", event)

        # Fire callbacks outside the lock
        if new_status != prev_status:
            if new_status == WatchdogStatus.SOFT_ALARM and self.on_soft_alarm:
                self.on_soft_alarm(self.get_state())
            elif new_status in {
                WatchdogStatus.HARD_ALARM,
                WatchdogStatus.STUCK,
                WatchdogStatus.SESSION_MAX,
            } and self.on_hard_alarm:
                self.on_hard_alarm(self.get_state())

    def _read_gpu_metrics(self) -> tuple[float | None, float | None, float | None]:
        """Return (temp_C, vram_used_percent, gpu_util_percent) — any can be None."""
        if self._nvml_handle is None:
            return None, None, None
        try:
            temp = float(pynvml.nvmlDeviceGetTemperature(
                self._nvml_handle, pynvml.NVML_TEMPERATURE_GPU
            ))
            mem = pynvml.nvmlDeviceGetMemoryInfo(self._nvml_handle)
            vram_pct = (mem.used / mem.total) * 100.0 if mem.total else None
            util = pynvml.nvmlDeviceGetUtilizationRates(self._nvml_handle)
            gpu_util = float(util.gpu) if util else None
            return temp, vram_pct, gpu_util
        except Exception as e:  # pragma: no cover — hardware-dependent
            logger.debug("watchdog: GPU read failed: %s", e)
            return None, None, None

    def _classify(
        self,
        elapsed_h: float,
        since_progress_s: float,
        gpu_temp: float | None,
        vram_pct: float | None,
        gpu_util: float | None,
    ) -> WatchdogStatus:
        t = self.thresholds

        # Session duration — stop cleanly, not an error
        if elapsed_h >= t.session_max_hours:
            return WatchdogStatus.SESSION_MAX

        # Stuck detection: no progress + GPU idle (or unknown)
        stuck_limit_s = t.stuck_detection_minutes * 60
        if since_progress_s >= stuck_limit_s:
            gpu_is_idle = gpu_util is None or gpu_util < 5.0
            if gpu_is_idle:
                return WatchdogStatus.STUCK

        # Hard thresholds — abort immediately
        if gpu_temp is not None and gpu_temp >= t.gpu_temp_hard:
            return WatchdogStatus.HARD_ALARM
        if vram_pct is not None and vram_pct >= t.vram_hard_percent:
            return WatchdogStatus.HARD_ALARM

        # Soft thresholds — pause and let things cool off
        if gpu_temp is not None and gpu_temp >= t.gpu_temp_soft:
            return WatchdogStatus.SOFT_ALARM
        if vram_pct is not None and vram_pct >= t.vram_soft_percent:
            return WatchdogStatus.SOFT_ALARM

        return WatchdogStatus.OK
