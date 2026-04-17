"""Migrate UIMap JSON files from v1 to v2 schema.

Usage:
    python scripts/migrate_v1_to_v2.py                    # all maps in ./maps
    python scripts/migrate_v1_to_v2.py path/to/map.json   # single file
    python scripts/migrate_v1_to_v2.py --dry-run          # preview only

What it does:
- Adds ``schema_version: "2.0"`` at the top of the document.
- Derives an ``app_metadata`` block from the flat v1 fields
  (``app_name``, ``app_version``, ``locale``, ``platform``).
- Derives a ``map_metadata`` block from the flat v1 timestamps.
- Leaves entries (menus, shortcuts, dialogs, tools) untouched — they keep
  ``provenance: None`` which is a valid v2 state (will be filled in by
  future mapping sessions or verify runs).
- Saves a backup of the original next to it as ``map.v1.json`` before
  overwriting.

This script is idempotent: running it twice is safe (it detects v2 maps
and skips them).
"""

from __future__ import annotations
import argparse
import json
import shutil
import sys
from pathlib import Path


DEFAULT_MAPS_DIR = Path(__file__).resolve().parent.parent / "maps"


def is_already_v2(data: dict) -> bool:
    return data.get("schema_version", "").startswith("2.")


def migrate_document(data: dict) -> dict:
    """Return a new dict upgraded to v2 schema."""
    upgraded = dict(data)  # shallow copy
    upgraded["schema_version"] = "2.0"

    if "app_metadata" not in upgraded or upgraded["app_metadata"] is None:
        upgraded["app_metadata"] = {
            "name": data.get("app_name", ""),
            "display_name": data.get("app_name", ""),
            "version": data.get("app_version", ""),
            "version_detected_at": "",
            "executable_path": "",
            "executable_hash": "",
            "locale": data.get("locale", ""),
            "platform": data.get("platform", "windows"),
        }

    if "map_metadata" not in upgraded or upgraded["map_metadata"] is None:
        upgraded["map_metadata"] = {
            "generated_by": "ui-mapper (migrated from v1)",
            "generated_at": data.get("mapped_at", ""),
            "session_id": "",
            "duration_seconds": 0.0,
            "providers_used": [],
            "mappers_used": list(data.get("sources", [])),
            "completion_pct": float(data.get("completion_pct", 0.0)),
        }

    return upgraded


def migrate_file(path: Path, dry_run: bool = False) -> str:
    """Migrate a single file in place. Returns a status string."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return f"SKIP {path} ({e})"

    if not isinstance(data, dict):
        return f"SKIP {path} (not a JSON object)"

    if is_already_v2(data):
        return f"SKIP {path} (already v2)"

    upgraded = migrate_document(data)

    if dry_run:
        return f"WOULD MIGRATE {path}"

    backup = path.with_suffix(".v1.json")
    shutil.copy2(path, backup)
    with path.open("w", encoding="utf-8") as f:
        json.dump(upgraded, f, indent=2, ensure_ascii=False)
    return f"MIGRATED {path} (backup: {backup.name})"


def discover_maps(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.glob("*/map.json"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate UIMap files from v1 to v2")
    parser.add_argument(
        "target", nargs="?", default=str(DEFAULT_MAPS_DIR),
        help="Map file or maps directory (default: ./maps)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would change without writing",
    )
    args = parser.parse_args()

    root = Path(args.target)
    if not root.exists():
        print(f"target does not exist: {root}", file=sys.stderr)
        return 1

    files = discover_maps(root)
    if not files:
        print(f"no map.json files found under {root}")
        return 0

    for path in files:
        print(migrate_file(path, dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
