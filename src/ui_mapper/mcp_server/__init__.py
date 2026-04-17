"""MCP server that exposes a UIMap to LLM clients.

Closes the loop of the project: without a consumer, a map is a dead
document. This module turns a map.json into dynamic tools that an
external LLM (Claude Code, Cursor, ...) can call to control the
application.

See docs/MCP_INTEGRATION.md for setup in specific clients.
"""

from .map_loader import LoadedMap, load_map  # noqa: F401
