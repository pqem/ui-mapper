"""Bring a target application window to the foreground (Windows).

Extracted from ``mappers/visual.py`` so both mappers and tests can reuse
the helper without importing the full VisualMapper.
"""

from __future__ import annotations
import logging
import platform
import subprocess

log = logging.getLogger(__name__)


_POWERSHELL_SCRIPT = """
Add-Type -AssemblyName Microsoft.VisualBasic
$proc = Get-Process -Name '{process_name}' -ErrorAction SilentlyContinue |
    Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
if ($proc) {{
    [Microsoft.VisualBasic.Interaction]::AppActivate($proc.Id)
    Write-Output "OK:$($proc.Id)"
}} else {{
    Write-Output "ERROR:Process not found"
}}
""".strip()


def focus_window(process_name: str, timeout: float = 10.0) -> bool:
    """Bring the first top-level window of ``process_name`` to the front.

    ``process_name`` accepts with or without the ``.exe`` suffix.
    Returns ``True`` when the activation call succeeded. Does not raise.
    """
    if platform.system() != "Windows":
        log.debug("focus_window is Windows-only; skipping on %s", platform.system())
        return False
    if not process_name:
        return False

    bare = process_name[:-4] if process_name.lower().endswith(".exe") else process_name
    script = _POWERSHELL_SCRIPT.format(process_name=bare)

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        log.warning("focus_window: subprocess failed: %s", e)
        return False

    output = (result.stdout or "").strip()
    if output.startswith("OK:"):
        log.debug("focused %s (%s)", process_name, output)
        return True
    log.warning("focus_window: could not focus %s — %s", process_name, output or "no output")
    return False
