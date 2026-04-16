"""Mapper orchestrator — coordinates all mappers, merges results, checkpoints."""

from __future__ import annotations
import json
import time
import logging
from pathlib import Path
from datetime import datetime

from .base import BaseMapper
from .llm_knowledge import LLMKnowledgeMapper
from .uia import UIAMapper
from ..core.types import UIMap
from ..core.config import AppConfig, Config
from ..core.session import SessionManager, SessionState
from ..providers.manager import ProviderManager

log = logging.getLogger(__name__)


class MapperOrchestrator:
    """Runs all available mappers in priority order and merges results."""

    def __init__(self, config: Config, provider: ProviderManager):
        self.config = config
        self.provider = provider
        self.session_mgr = SessionManager(config.maps_dir)
        self._mappers: list[BaseMapper] = self._build_mapper_chain()

    def _build_mapper_chain(self) -> list[BaseMapper]:
        """Build ordered list of mappers."""
        mappers: list[BaseMapper] = [
            LLMKnowledgeMapper(),
            UIAMapper(),
        ]

        # Try to load optional mappers
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

        # Sort by priority
        mappers.sort(key=lambda m: m.get_priority())
        return mappers

    def map(self, app_name: str, resume: bool = True) -> UIMap:
        """Run full mapping for an application."""
        if app_name not in self.config.apps:
            raise ValueError(
                f"Unknown app: {app_name}. "
                f"Available: {list(self.config.apps.keys())}"
            )

        app_config = self.config.apps[app_name]
        session = self.session_mgr.start(app_name)

        # Check for existing map to merge into
        combined = self._load_existing_map(app_name) or UIMap(
            app_name=app_name,
            locale=app_config.locale,
        )

        log.info(f"Starting mapping for {app_config.display_name}")
        log.info(f"Available mappers: {[m.get_name() for m in self._mappers]}")

        for mapper in self._mappers:
            name = mapper.get_name()

            # Skip already completed mappers (for resume)
            if resume and name in session.completed_mappers:
                log.info(f"Skipping {name} (already completed)")
                continue

            if not mapper.can_map(app_config):
                log.info(f"Skipping {name} (not applicable)")
                continue

            session.current_mapper = name
            self.session_mgr.save(session)

            log.info(f"Running mapper: {name} (priority {mapper.get_priority()})")
            est = mapper.estimate_duration(app_config)
            log.info(f"Estimated duration: {est}")

            try:
                result = mapper.map(
                    app_config=app_config,
                    session=session,
                    provider=self.provider if self.provider.is_available() else None,
                )
                combined.merge(result)
                session.completed_mappers.append(name)
                log.info(f"Mapper {name} completed successfully")
            except Exception as e:
                log.error(f"Mapper {name} failed: {e}")
                self.session_mgr.mark_error(session, f"{name}: {e}")

            # Checkpoint after each mapper
            self._save_map(app_name, combined)
            self.session_mgr.save(session)

        # Finalize
        combined.mapped_at = datetime.now().isoformat()
        combined.app_version = app_config.metadata.get("version", "")
        self._calculate_completion(combined)

        self._save_map(app_name, combined)
        self.session_mgr.complete(session)

        log.info(
            f"Mapping complete: {len(combined.menus)} menus, "
            f"{len(combined.shortcuts)} shortcuts, "
            f"{len(combined.tools)} tools, "
            f"{len(combined.dialogs)} dialogs "
            f"({combined.completion_pct:.0f}% estimated coverage)"
        )

        return combined

    def _load_existing_map(self, app_name: str) -> UIMap | None:
        """Load an existing map if available."""
        map_path = Path(self.config.maps_dir) / app_name / "map.json"
        if not map_path.exists():
            return None
        try:
            with open(map_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Basic reconstruction (simplified)
            return UIMap(
                app_name=data.get("app_name", app_name),
                locale=data.get("locale", ""),
                sources=data.get("sources", []),
            )
        except Exception:
            return None

    def _save_map(self, app_name: str, ui_map: UIMap) -> None:
        """Save map to JSON file."""
        map_dir = Path(self.config.maps_dir) / app_name
        map_dir.mkdir(parents=True, exist_ok=True)
        map_path = map_dir / "map.json"

        with open(map_path, "w", encoding="utf-8") as f:
            json.dump(ui_map.to_dict(), f, indent=2, ensure_ascii=False)

        log.info(f"Map saved to {map_path}")

    def _calculate_completion(self, ui_map: UIMap) -> None:
        """Estimate completion percentage based on what was found."""
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
