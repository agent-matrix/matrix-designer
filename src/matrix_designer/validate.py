"""Validate a Design Bundle — *AI proposes, Matrix Definitions enforce.*

Two layers:
1. **Schema** — the bundle must satisfy ``schemas/design-bundle.schema.json``.
2. **Design rules** — the design-pack's rule IDs (e.g. GAME-001…010) are checked so the
   brain cannot approve itself. Returns a verdict mirroring Matrix Builder:
   ``approved`` / ``needs-repair`` / ``rejected``.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from ._resources import schema_path

# Kept as a module attribute for backwards compatibility; resolved via the package
# data resolver so a pip-installed wheel and editable checkouts both work.
SCHEMA_PATH = str(schema_path())


def _load_schema() -> Dict[str, Any]:
    with open(schema_path(), "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_schema(bundle: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    try:
        import jsonschema  # type: ignore

        validator = jsonschema.Draft202012Validator(_load_schema())
        for e in sorted(validator.iter_errors(bundle), key=lambda e: e.path):
            loc = "/".join(str(p) for p in e.path) or "<root>"
            errors.append(f"schema: {loc}: {e.message}")
    except ImportError:
        # minimal structural check when jsonschema isn't installed
        for req in ("schema_version", "design_id", "project", "framework_decision", "batch_roadmap", "provenance"):
            if req not in bundle:
                errors.append(f"schema: missing required '{req}'")
        if not bundle.get("batch_roadmap"):
            errors.append("schema: batch_roadmap must have >= 1 batch")
    return errors


def validate_rules(bundle: Dict[str, Any]) -> List[Dict[str, str]]:
    """Generic design-rule checks that apply across packs (a starter set)."""
    violations: List[Dict[str, str]] = []

    def fail(rule_id: str, severity: str, message: str) -> None:
        violations.append({"rule_id": rule_id, "severity": severity, "message": message})

    roadmap = bundle.get("batch_roadmap", [])
    # DESIGN-001 — every batch is scoped (has allowed_files + acceptance)
    for b in roadmap:
        if not b.get("allowed_files"):
            fail("DESIGN-001", "high", f"batch {b.get('id')} has no allowed_files (would improvise)")
        if not b.get("acceptance"):
            fail("DESIGN-002", "high", f"batch {b.get('id')} has no acceptance criteria")
    # DESIGN-003 — dependencies must reference real batches
    ids = {b.get("id") for b in roadmap}
    for b in roadmap:
        for dep in b.get("depends_on", []):
            if dep not in ids:
                fail("DESIGN-003", "medium", f"batch {b.get('id')} depends_on unknown '{dep}'")
    # DESIGN-004 — acceptance must exist at the bundle level
    if not bundle.get("acceptance", {}).get("functional"):
        fail("DESIGN-004", "high", "no functional acceptance criteria for the whole solution")
    # DESIGN-005 — the dependency graph must be acyclic
    cycle = _first_cycle({b.get("id"): list(b.get("depends_on", [])) for b in roadmap})
    if cycle:
        fail("DESIGN-005", "high", f"dependency cycle: {' → '.join(cycle)}")
    # GAME-006 — web-games must declare a visual acceptance target
    if bundle.get("domain") == "web-game":
        if not (bundle.get("visual_target") and bundle.get("acceptance", {}).get("visual")):
            fail("GAME-006", "high", "web-game has no visual target / visual acceptance (the v1 failure mode)")
        # GAME-003 — no single-file game beyond a prototype
        stack = " ".join(bundle.get("framework_decision", {}).get("stack", [])).lower()
        if bundle.get("quality_level") in ("production", "enterprise") and "single" in bundle.get("source", {}).get("idea", "").lower() and "phaser" not in stack:
            fail("GAME-003", "medium", "production game should use an engine, not a single file")
    return violations


def _first_cycle(graph: Dict[Any, List[Any]]) -> List[Any]:
    """Return one cycle path if the dependency graph has one, else []."""
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}
    stack: List[Any] = []

    def visit(n: Any) -> List[Any]:
        color[n] = GREY
        stack.append(n)
        for dep in graph.get(n, []):
            if dep not in color:
                continue
            if color[dep] == GREY:
                return stack[stack.index(dep):] + [dep]
            if color[dep] == WHITE:
                found = visit(dep)
                if found:
                    return found
        color[n] = BLACK
        stack.pop()
        return []

    for node in graph:
        if color[node] == WHITE:
            found = visit(node)
            if found:
                return found
    return []


def verdict(bundle: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    from .rules import load_rules

    schema_errors = validate_schema(bundle)
    rule_violations = validate_rules(bundle)
    critical = [v for v in rule_violations if v["severity"] in ("high", "critical")]
    if schema_errors:
        status = "rejected"
    elif critical:
        status = "needs-repair"
    else:
        status = "approved"
    report = {
        "status": status,
        "schema_errors": schema_errors,
        "violations": rule_violations,
        "rules_catalog": sorted(load_rules().keys()),
        "summary": f"{status}: {len(schema_errors)} schema errors, {len(rule_violations)} rule violations",
    }
    return status, report
