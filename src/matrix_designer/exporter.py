"""Export a Design Bundle into Matrix Builder inputs.

The bundle's ``batch_roadmap`` becomes the ``mb next`` sequence, and each blueprint
candidate is stamped with ``design_bundle_ref`` + ``design_digest`` so it is *provably
derived* from the brain. This is the seam into the existing contract chain:

    idea-request -> [design-bundle] -> blueprint-candidate(x3) -> matrix-bundle -> prompt-pack -> validation
"""
from __future__ import annotations

from typing import Any, Dict, List


def to_idea_request(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """The additive fields Matrix Designer contributes to an idea-request."""
    src = bundle.get("source", {})
    return {
        "schema_version": "matrix.builder.idea/v1",
        "idea": src.get("idea", ""),
        "build_type": bundle.get("build_type", "app"),
        "quality_level": bundle.get("quality_level", "standard"),
        # additive, backward-compatible extensions:
        "design_mode": "design-first",
        "references": src.get("references", []),
    }


def to_blueprint_overlay(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Fields to merge onto each blueprint-candidate so it links to the brain."""
    prov = bundle.get("provenance", {})
    return {
        "design_bundle_ref": f"design-bundle://{bundle.get('design_id')}",
        "design_digest": prov.get("design_digest", ""),
        "generator_actions": [b["id"] for b in bundle.get("batch_roadmap", [])],
        "validation_checks": bundle.get("acceptance", {}).get("functional", []),
    }


def to_mb_next_sequence(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The ordered batches as Matrix Builder `mb next` inputs (allow-list + acceptance)."""
    seq: List[Dict[str, Any]] = []
    for b in bundle.get("batch_roadmap", []):
        seq.append({
            "batch_id": b["id"],
            "goal": f"{b['name']} — {b['purpose']}",
            "allowed_files": b.get("allowed_files", []),
            "must_not_change": b.get("must_not_change", []),
            "acceptance_criteria": b.get("acceptance", []),
            "depends_on": b.get("depends_on", []),
        })
    return seq


def to_mb_export(bundle: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "idea_request": to_idea_request(bundle),
        "blueprint_overlay": to_blueprint_overlay(bundle),
        "mb_next_sequence": to_mb_next_sequence(bundle),
    }
