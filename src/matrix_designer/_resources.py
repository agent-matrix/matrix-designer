"""Locate packaged data (schema + design-packs) robustly.

The schema and design-packs ship **inside the package** (``matrix_designer/_data``) so a
plain ``pip install matrix-designer`` works. For backward compatibility this resolver
also honours explicit env overrides and the historical repo-root layout
(``<repo>/schemas`` and ``<repo>/packs``), so editable checkouts and older deployments
keep working unchanged.

Resolution order:
1. Explicit env override (``MATRIX_DESIGNER_DATA`` for the data root; ``MATRIX_DESIGNER_PACKS``
   for packs specifically — kept for compatibility).
2. The packaged ``matrix_designer/_data`` directory (the normal installed case).
3. The legacy repo-root ``schemas/`` / ``packs/`` (editable / old layout).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:  # py3.9+: importlib.resources.files
    from importlib.resources import files as _ir_files
except Exception:  # pragma: no cover
    _ir_files = None  # type: ignore


def _packaged_data() -> Optional[Path]:
    """The ``_data`` directory shipped inside the installed package, if present."""
    if _ir_files is None:
        return None
    try:
        p = Path(str(_ir_files("matrix_designer"))) / "_data"
        return p if p.exists() else None
    except Exception:
        return None


def _legacy_root() -> Path:
    """Repo root for an editable / source checkout (src/matrix_designer/_resources.py)."""
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """Root that contains ``schemas/`` and ``packs/`` (packaged, or legacy repo-root)."""
    env = os.environ.get("MATRIX_DESIGNER_DATA", "").strip()
    if env:
        return Path(env)
    pkg = _packaged_data()
    if pkg is not None:
        return pkg
    return _legacy_root()


def schema_path() -> Path:
    """Absolute path to ``design-bundle.schema.json`` (packaged first, then legacy)."""
    for base in (data_dir(), _legacy_root()):
        cand = base / "schemas" / "design-bundle.schema.json"
        if cand.exists():
            return cand
    # Return the preferred location even if missing, so callers raise a clear path.
    return data_dir() / "schemas" / "design-bundle.schema.json"


def packs_dir() -> str:
    """Directory that holds the design-packs.

    Honours the historical ``MATRIX_DESIGNER_PACKS`` override first, then the packaged
    location, then the legacy repo-root.
    """
    env = os.environ.get("MATRIX_DESIGNER_PACKS", "").strip()
    if env:
        return env
    for base in (data_dir(), _legacy_root()):
        cand = base / "packs"
        if cand.exists():
            return str(cand)
    return str(data_dir() / "packs")
