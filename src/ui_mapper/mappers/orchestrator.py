"""Mapper orchestrator — coordinates mappers, merges results, checkpoints.

v2 additions:
- Detects the target app's version before mapping and compares against
  the last known map (warn on version change).
- Runs a hardware watchdog in the background; respects pause/abort
  signals between mappers.
- Populates ``UIMap.app_metadata`` and ``UIMap.map_metadata`` with full
  provenance of the mapping session.
"""

from __future__ import annotations
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from .base import BaseMapper
from .llm_knowledge import LLMKnowledgeMapper
from .uia import UIAMapper
from ..core.config import Config
from ..core.profile import Profile, load_profile
from ..core.session import SessionManager
from ..core.types import MapMetadata, UIMap
from ..core.version import (
    detect_app_metadata,
    load_previous_metadata,
    version_changed,
)
from ..core.watchdog import HardwareWatchdog, WatchdogStatus
from ..providers.manager import ProviderManager

log = logging.getLogger(__name__)


class MapperOrchestrator:
    """Runs all available mappers in priority order and merges results."""

    def __init__(
        self,
        config: Config,
        provider: ProviderManager,
        profile: Profile | None = None,
    ) -> None:
        self.config = config
        self.provider = provider
        self.profile = profile or load_profile()
        self.session_mgr = SessionManager(config.maps_dir)
        self._mappers: list[BaseMapper] = self._build_mapper_chain()

    # -- mapper chain -------------------------------------------------------

    def _build_mapper_chain(self) -> list[BaseMapper]:
        mappers: list[BaseMapper] = [
            LLMKnowledgeMapper(),
            UIAMapper(),
        ]
        try:
            from .source_config import SourceConfigMapper
            mappers.append(SourceConfigMapper())
        except ImportError:
            pass
        try:
            from .visual import VisualMapper
            mappers.append(VisualMapper())
        except ImportError:
            pass
        mappers.sort(key=lambda m: m.get_priority())
        return mappers

    # -- main entry ---------------------------------------------------------

    def map(self, app_name: str, resume: bool = True) -> UIMap:
        if app_name not in self.config.apps:
            raise ValueError(
                f"Unknown app: {app_name}. "
                f"Available: {list(self.config.apps.keys())}"
            )

        app_config = self.config.apps[app_name]
        session = self.session_mgr.start(app_name)
        session_started_monotonic = time.monotonic()
        session_id = hashlib.sha1(
            f"{app_name}-{session.started_at}".encode()
        ).hexdigest()[:12]

        # --- Detect version and compare against previous map -----
        exe_hint = app_config.metadata.get("exe_path", "")
        current_meta = detect_app_metadata(
            app_name=app_name,
            display_name=app_config.display_name,
            process_name=app_config.process_name,
            exe_path=exe_hint or None,
            locale=app_config.locale,
        )
        map_path = Path(self.config.maps_dir) / app_name / "map.json"
        previous_meta = load_previous_metadata(map_path)
        if version_changed(current_meta, previous_meta):
            log.warning(
                "app version changed: previous=%s, current=%s — "
                "the old map may be stale; consider --no-resume or a diff-update",
                previous_meta.version if previous_meta else "unknown",
                current_meta.version or "unknown",
            )

        # --- Load existing map (if resumable) or start fresh -----
        combined = self._load_existing_map(app_name) if resume else None
        if combined is None:
            combined = UIMap(
                app_name=app_name,
                locale=app_config.locale,
                platform=app_config.platform,
            )
        combined.app_metadata = current_meta

        log.info("Starting mapping for %s", app_config.display_name)
        log.info("Available mappers: %s", [m.get_name() for m in self._mappers])
        log.info(
            "App version: %s (detected via %s)",
            current_meta.version or "unknown",
            current_meta.executable_path or "no exe path",
        )

        # --- Start watchdog ----
        watchdog = HardwareWatchdog(self.profile.hardware_thresholds)
        watchdog.start()

        mappers_used: list[str] = []
        try:
            for mapper in self._mappers:
                name = mapper.get_name()

                if watchdog.should_abort():
                    state = watchdog.get_state()
                    log.error("watchdog abort (%s) — stopping mapping loop", state.status.value)
                    self.session_mgr.mark_error(session, f"watchdog: {state.status.value}")
                    break

                if watchdog.should_pause():
                    log.info("watchdog pause — waiting for conditions to clear")
                    cleared = watchdog.wait_for_clear()
                    if not cleared:
                        log.error("watchdog did not clear — aborting")
                        break

                if resume and name in session.completed_mappers:
                    log.info("Skipping %s (already completed)", name)
                    continue

                if not mapper.can_map(app_config):
                    log.info("Skipping %s (not applicable)", name)
                    continue

                session.current_mapper = name
                self.session_mgr.save(session)

                log.info("Running mapper: %s (priority %d)", name, mapper.get_priority())
                log.info("Estimated duration: %s", mapper.estimate_duration(app_config))

                try:
                    result = mapper.map(
                        app_config=app_config,
                        session=session,
                        provider=self.provider if self.provider.is_available() else None,
                        watchdog=watchdog,
                        sessions_root=Path(self.config.maps_dir).parent / "sessions",
                    )
                    combined.merge(result)
                    session.completed_mappers.append(name)
                    mappers_used.append(name)
                    watchdog.report_progress(f"mapper {name} finished")
                    log.info("Mapper %s completed successfully", name)
                except Exception as e:
                    log.exception("Mapper %s failed: %s", name, e)
                    self.session_mgr.mark_error(session, f"{name}: {e}")

                self._save_map(app_name, combined)
                self.session_mgr.save(session)
        finally:
            watchdog.stop()

        # --- Finalize metadata ----
        duration = time.monotonic() - session_started_monotonic
        combined.mapped_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        combined.app_version = current_meta.version or app_config.metadata.get("version", "")
        self._calculate_completion(combined)

        if hasattr(self.provider, "list_active_providers"):
            providers_used = self.provider.list_active_providers()
        elif hasattr(self.provider, "provider_name"):
            name = self.provider.provider_name()
            providers_used = [name] if name else []
        else:
            providers_used = []

        combined.map_metadata = MapMetadata(
            generated_by=f"ui-mapper {self._package_version()}",
            generated_at=combined.mapped_at,
            session_id=session_id,
            duration_seconds=duration,
            providers_used=providers_used,
            mappers_used=mappers_used,
            completion_pct=combined.completion_pct,
        )

        self._save_map(app_name, combined)
        self.session_mgr.complete(session)

        watchdog_state = watchdog.get_state()
        if watchdog_state.pause_events:
            log.info("watchdog events during session: %s", watchdog_state.pause_events)

        log.info(
            "Mapping complete: %d menus, %d shortcuts, %d tools, %d dialogs "
            "(%.0f%% estimated coverage)",
            len(combined.menus),
            len(combined.shortcuts),
            len(combined.tools),
            len(combined.dialogs),
            combined.completion_pct,
        )
        return combined

    # -- helpers ------------------------------------------------------------

    def _load_existing_map(self, app_name: str) -> UIMap | None:
        map_path = Path(self.config.maps_dir) / app_name / "map.json"
        if not map_path.exists():
            return None
        try:
            with map_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return UIMap(
                app_name=data.get("app_name", app_name),
                locale=data.get("locale", ""),
                platform=data.get("platform", "windows"),
                sources=data.get("sources", []),
            )
        except Exception:
            return None

    def _save_map(self, app_name: str, ui_map: UIMap) -> None:
        map_dir = Path(self.config.maps_dir) / app_name
        map_dir.mkdir(parents=True, exist_ok=True)
        map_path = map_dir / "map.json"
        with map_path.open("w", encoding="utf-8") as f:
            json.dump(ui_map.to_dict(), f, indent=2, ensure_ascii=False)
        log.info("Map saved to %s", map_path)

    def _calculate_completion(self, ui_map: UIMap) -> None:
        score = 0
        if ui_map.menus:
            score += 30
        if ui_map.shortcuts:
            score += 25
        if ui_map.tools:
            score += 20
        if ui_map.dialogs:
            score += 15
        if len(ui_map.sources) > 1:
            score += 10
        ui_map.completion_pct = min(score, 100)

    @staticmethod
    def _package_version() -> str:
        try:
            from importlib.metadata import version
            return version("ui-mapper")
        except Exception:
            return "0.1.0"
