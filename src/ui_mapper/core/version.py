"""App version detection.

Resolves the version of a running or installed application so that maps
can be tied to a specific build. When the detected version changes from
the previous map, the orchestrator can offer a diff-update instead of a
full re-map.

Primary strategy on Windows: PowerShell ``Get-Item ... | VersionInfo``.
Fallbacks: WMI on the running process, then executable hash alone.
"""

from __future__ import annotations
import hashlib
import json
import platform
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .types import AppMetadata


# -----------------------------------------------------------------------------
# Low-level helpers
# -----------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_executable(path: Path, chunk_size: int = 1 << 20) -> str:
    """Return the sha256 of a file. Empty string on failure."""
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def _run_powershell(script: str, timeout: float = 10.0) -> str:
    """Execute a PowerShell one-liner and return stdout (stripped).

    Returns empty string on any failure — callers decide what to do.
    """
    if platform.system() != "Windows":
        return ""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


# -----------------------------------------------------------------------------
# Strategies
# -----------------------------------------------------------------------------

def version_from_exe_path(exe_path: Path) -> str:
    """Read FileVersion / ProductVersion from an executable's metadata."""
    if not exe_path.exists():
        return ""
    script = (
        f"(Get-Item '{exe_path}').VersionInfo | "
        "Select-Object ProductVersion, FileVersion | ConvertTo-Json -Compress"
    )
    out = _run_powershell(script)
    if not out:
        return ""
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return ""
    # Prefer ProductVersion; fall back to FileVersion
    return (data.get("ProductVersion") or data.get("FileVersion") or "").strip()


def exe_path_from_process(process_name: str) -> Path | None:
    """Locate the executable of a running process by name.

    ``process_name`` should be what Task Manager shows (e.g. ``Designer.exe``
    or ``Designer``). Returns the first match.
    """
    if not process_name:
        return None
    # normalize — strip .exe if present, PowerShell's Get-Process uses bare name
    bare = process_name[:-4] if process_name.lower().endswith(".exe") else process_name
    script = (
        f"(Get-Process -Name '{bare}' -ErrorAction SilentlyContinue | "
        "Select-Object -First 1).Path"
    )
    out = _run_powershell(script)
    if not out:
        return None
    candidate = Path(out)
    return candidate if candidate.exists() else None


# -----------------------------------------------------------------------------
# High-level entry point
# -----------------------------------------------------------------------------

def detect_app_metadata(
    app_name: str,
    display_name: str = "",
    process_name: str = "",
    exe_path: str | Path | None = None,
    locale: str = "",
) -> AppMetadata:
    """Detect version and build an ``AppMetadata`` block.

    Resolution order:
    1. Explicit ``exe_path`` argument.
    2. Running process (``process_name``) → exe path → version.
    3. Empty metadata (caller decides what to do).

    This function never raises. Missing data comes back as empty strings.
    """
    path: Path | None = None
    if exe_path:
        path = Path(exe_path)
        if not path.exists():
            path = None

    if path is None and process_name:
        path = exe_path_from_process(process_name)

    version = version_from_exe_path(path) if path else ""
    exe_hash = hash_executable(path) if path else ""

    return AppMetadata(
        name=app_name,
        display_name=display_name or app_name,
        version=version,
        version_detected_at=_now_iso() if version else "",
        executable_path=str(path) if path else "",
        executable_hash=exe_hash,
        locale=locale,
        platform=platform.system().lower(),
    )


def version_changed(current: AppMetadata, previous: AppMetadata | None) -> bool:
    """True if the target app changed between runs.

    Prefers version string comparison. Falls back to executable hash when
    version is missing on either side (e.g. unsigned builds).
    """
    if previous is None:
        return False
    if current.version and previous.version:
        return current.version != previous.version
    if current.executable_hash and previous.executable_hash:
        return current.executable_hash != previous.executable_hash
    return False


def load_previous_metadata(map_path: Path) -> AppMetadata | None:
    """Read ``app_metadata`` from an existing map JSON, if present.

    Returns ``None`` if the file doesn't exist or has no v2 metadata.
    """
    if not map_path.exists():
        return None
    try:
        with map_path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    block = data.get("app_metadata")
    if not block:
        return None
    return AppMetadata(
        name=block.get("name", ""),
        display_name=block.get("display_name", ""),
        version=block.get("version", ""),
        version_detected_at=block.get("version_detected_at", ""),
        executable_path=block.get("executable_path", ""),
        executable_hash=block.get("executable_hash", ""),
        locale=block.get("locale", ""),
        platform=block.get("platform", "windows"),
    )
