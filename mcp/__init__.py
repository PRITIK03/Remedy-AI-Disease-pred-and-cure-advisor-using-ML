"""Remedy-AI MCP server package (Phase 8).

This local package is named `mcp` (as the phase spec requires) while the
official SDK is also importable as `mcp`. To let both coexist:

* the SDK directory is placed FIRST on ``__path__``, so SDK subpackages
  (``mcp.server``, ``mcp.types``, ...) resolve to the official package;
* our own top-level modules (``tools``, ``schemas``) resolve from this
  directory — the SDK ships no modules with those names;
* this package's ``server.py`` is additionally exposed as
  ``mcp.remedy_server`` (the ``mcp.server`` name belongs to the SDK), so it
  stays exactly where the spec requires it on disk.

No SDK symbol is re-implemented, vendored, or modified here.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _sdk_directory() -> Path | None:
    """Locate the installed `mcp` SDK directory (never our own)."""
    candidates: list[Path] = []
    override = os.environ.get("MCP_SDK_PATH")
    if override:
        candidates.append(Path(override))
    for entry in sys.path:
        if not entry:
            continue
        base = Path(entry).resolve()
        if base in (_HERE.parent, _HERE):
            continue
        candidates.append(base / "mcp")
    for candidate in candidates:
        if candidate.is_dir() and candidate != _HERE:
            return candidate
    return None


_SDK = _sdk_directory()
if _SDK is not None:
    # SDK first: `mcp.server` must resolve to the official subpackage.
    __path__ = [str(_SDK), *[p for p in __path__ if p != str(_SDK)]]


def _load_remedy_server():
    """Expose this package's `server.py` as the `mcp.remedy_server` module."""
    module_name = "mcp.remedy_server"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(
        module_name, _HERE / "server.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError("Could not load the Remedy-AI MCP server module.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


__all__ = ["remedy_server"]

# Eagerly register so `import mcp.remedy_server` works normally. `mcp.server`
# is owned by the SDK, so this local module is published under an explicit,
# non-conflicting name while remaining on disk at mcp/server.py.
try:  # pragma: no cover - import guard
    _load_remedy_server()
except Exception:  # noqa: BLE001 - never break `import mcp.tools` for SDK users
    pass

