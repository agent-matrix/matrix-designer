"""Design-pack loader.

Design-packs are the reusable, governed templates that seed a Design Bundle for a
domain (their rules ultimately live in **Matrix Definitions**; vendored here so the
engine runs offline). A pack supplies the visual target, architecture skeleton, entity
contracts, asset manifest, acceptance defaults, risks and the rule IDs that the
validator will enforce.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict

import json

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

PACKS_DIR = os.environ.get(
    "MATRIX_DESIGNER_PACKS",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "packs"),
)


@lru_cache(maxsize=32)
def load_pack(pack_id: str) -> Dict[str, Any]:
    """Load packs/<pack_id>/pack.yaml (falls back to a minimal generic pack)."""
    path_yaml = os.path.join(PACKS_DIR, pack_id, "pack.yaml")
    path_json = os.path.join(PACKS_DIR, pack_id, "pack.json")
    if yaml is not None and os.path.exists(path_yaml):
        with open(path_yaml, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    if os.path.exists(path_json):
        with open(path_json, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {
        "id": "generic-v1",
        "architecture": {"systems": ["app"]},
        "acceptance": {"functional": ["project builds", "app runs with zero errors"]},
        "rules": [],
        "missing_decisions": [],
        "risks": [],
    }
