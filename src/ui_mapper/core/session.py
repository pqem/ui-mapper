"""Session management — checkpoints for resumable mapping."""

from __future__ import annotations
import json
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class SessionState:
    """Tracks mapping progress so sessions can be resumed."""
    app_name: str
    started_at: float = 0.0
    last_checkpoint: float = 0.0
    status: str = "idle"  # "idle", "running", "paused", "completed", "error"

    # Progress tracking
    completed_mappers: list[str] = field(default_factory=list)
    current_mapper: str = ""
    mapper_progress: dict[str, Any] = field(default_factory=dict)

    # For visual mapper: track explored UI areas
    explored_menus: list[str] = field(default_factory=list)
    explored_dialogs: list[str] = field(default_factory=list)
    explored_tools: list[str] = field(default_factory=list)

    # Error log
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def is_resumable(self) -> bool:
        return self.status in ("running", "paused")


class SessionManager:
    """Manages mapping sessions with checkpoint save/load."""

    def __init__(self, maps_dir: str | Path):
        self.maps_dir = Path(maps_dir)

    def _meta_path(self, app_name: str) -> Path:
        return self.maps_dir / app_name / "session.json"

    def load(self, app_name: str) -> SessionState:
        """Load existing session or create new one."""
        meta_path = self._meta_path(app_name)
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SessionState(**data)
        return SessionState(app_name=app_name)

    def save(self, state: SessionState) -> None:
        """Save session checkpoint."""
        state.last_checkpoint = time.time()
        meta_path = self._meta_path(state.app_name)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(asdict(state), f, indent=2)

    def start(self, app_name: str) -> SessionState:
        """Start or resume a session."""
        state = self.load(app_name)
        if state.is_resumable:
            state.status = "running"
        else:
            state = SessionState(
                app_name=app_name,
                started_at=time.time(),
                status="running",
            )
        self.save(state)
        return state

    def complete(self, state: SessionState) -> None:
        """Mark session as completed."""
        state.status = "completed"
        self.save(state)

    def mark_error(self, state: SessionState, error: str) -> None:
        """Record an error without stopping the session."""
        state.errors.append({
            "time": str(time.time()),
            "error": error,
        })
        if len(state.errors) > 100:
            state.errors = state.errors[-50:]  # Keep last 50
        self.save(state)

    def list_sessions(self) -> list[SessionState]:
        """List all known sessions."""
        sessions = []
        if not self.maps_dir.exists():
            return sessions
        for app_dir in self.maps_dir.iterdir():
            if app_dir.is_dir():
                meta = app_dir / "session.json"
                if meta.exists():
                    sessions.append(self.load(app_dir.name))
        return sessions
