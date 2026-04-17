"""Persist screenshots + VLM exchanges for post-mortem debugging.

Every VLM call made by the visual mapper can write three artifacts:

- ``<step>.png`` — the screenshot sent to the model
- ``<step>.prompt.txt`` — the prompt text
- ``<step>.response.txt`` — the raw model response

The directory layout is::

    sessions/<app>/<session_id>/<NNN>_<step_name>.png

Consumers can reconstruct a failed exploration by walking the session
folder after the fact.
"""

from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


_SLUG_RX = re.compile(r"[^a-zA-Z0-9_-]+")


def _slug(name: str, maxlen: int = 48) -> str:
    s = _SLUG_RX.sub("_", name.strip()).strip("_")
    return (s or "step")[:maxlen]


def snapshot_dir_for(
    sessions_root: Path,
    app_name: str,
    session_id: str | None = None,
) -> Path:
    """Build the directory path where snapshots for a session go."""
    sid = session_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(sessions_root) / app_name / sid


@dataclass
class SnapshotWriter:
    """Counter-backed writer that persists screenshots + VLM exchanges.

    The writer creates its directory lazily on the first ``save_step()``
    call so sessions that never reach the visual phase don't leave empty
    folders around.
    """
    target_dir: Path
    enabled: bool = True
    _step_counter: int = 0
    _ensured: bool = field(default=False, init=False)

    # ---- lifecycle -----------------------------------------------------

    def _ensure_dir(self) -> None:
        if self._ensured or not self.enabled:
            return
        self.target_dir.mkdir(parents=True, exist_ok=True)
        self._ensured = True

    def next_index(self) -> int:
        self._step_counter += 1
        return self._step_counter

    # ---- writes --------------------------------------------------------

    def save_step(
        self,
        step_name: str,
        image_bytes: bytes | None = None,
        prompt: str = "",
        response: str = "",
    ) -> Path | None:
        """Persist a single step. Returns the PNG path (or None if disabled).

        Any component can be empty; only non-empty parts are written.
        """
        if not self.enabled:
            return None
        self._ensure_dir()
        idx = self.next_index()
        slug = _slug(step_name)
        base = self.target_dir / f"{idx:03d}_{slug}"

        png_path: Path | None = None
        try:
            if image_bytes:
                png_path = base.with_suffix(".png")
                png_path.write_bytes(image_bytes)
            if prompt:
                base.with_suffix(".prompt.txt").write_text(prompt, encoding="utf-8")
            if response:
                base.with_suffix(".response.txt").write_text(response, encoding="utf-8")
        except OSError as e:  # pragma: no cover — disk-dependent
            log.warning("snapshot write failed (%s): %s", base, e)
            return None
        return png_path

    def save_note(self, step_name: str, text: str) -> Path | None:
        """Persist a plain-text note (e.g. an error trace)."""
        if not self.enabled:
            return None
        self._ensure_dir()
        idx = self.next_index()
        path = self.target_dir / f"{idx:03d}_{_slug(step_name)}.note.txt"
        try:
            path.write_text(text, encoding="utf-8")
            return path
        except OSError as e:  # pragma: no cover
            log.warning("snapshot note failed (%s): %s", path, e)
            return None
