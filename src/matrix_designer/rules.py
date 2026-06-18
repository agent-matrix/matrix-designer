"""Design-rule catalog loader.

Aggregates the rule definitions declared in ``packs/*/rules.yaml`` (DESIGN-*, GAME-*,
APP-*) so the governance layer has one source of truth. The *checks* live in
``validate.py``; this module is the *catalog* — used to display which rules govern a
bundle and to assert, in tests, that every enforced rule is declared.
"""
from __future__ import annotations

import glob
import os
from functools import lru_cache
from typing import Any, Dict, List

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

PACKS_DIR = os.environ.get(
    "MATRIX_DESIGNER_PACKS",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "packs"),
)


@lru_cache(maxsize=1)
def load_rules() -> Dict[str, Dict[str, Any]]:
    """Return {rule_id: {title, severity, check, pack}} across all packs."""
    catalog: Dict[str, Dict[str, Any]] = {}
    if yaml is None:
        return catalog
    for path in glob.glob(os.path.join(PACKS_DIR, "*", "rules.yaml")):
        try:
            doc = yaml.safe_load(open(path, encoding="utf-8")) or {}
        except Exception:
            continue
        pack = doc.get("id", os.path.basename(os.path.dirname(path)))
        for rule in doc.get("rules", []):
            rid = rule.get("id")
            if rid:
                catalog[rid] = {"title": rule.get("title", ""), "severity": rule.get("severity", "medium"),
                                "check": rule.get("check", ""), "pack": pack}
    return catalog


def rule_ids() -> List[str]:
    return sorted(load_rules().keys())
