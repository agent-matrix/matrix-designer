"""Typed in-memory model of a Design Bundle.

A thin mirror of ``schemas/design-bundle.schema.json``. The schema is the source of
truth (it is what Matrix Builder + Matrix Definitions validate against); these
dataclasses make the engine ergonomic to write and test in Python.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "matrix.designer.bundle/v1"


def sha256_digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Batch:
    id: str
    name: str
    purpose: str
    allowed_files: List[str]
    acceptance: List[str]
    depends_on: List[str] = field(default_factory=list)
    new_features: List[str] = field(default_factory=list)
    must_not_change: List[str] = field(default_factory=list)


@dataclass
class DesignBundle:
    design_id: str
    project: str
    source: Dict[str, Any]
    goal_analysis: Dict[str, Any]
    framework_decision: Dict[str, Any]
    architecture: Dict[str, Any]
    acceptance: Dict[str, Any]
    batch_roadmap: List[Batch]
    provenance: Dict[str, Any]
    schema_version: str = SCHEMA_VERSION
    slug: Optional[str] = None
    domain: Optional[str] = None
    build_type: str = "app"
    quality_level: str = "standard"
    visual_target: Optional[Dict[str, Any]] = None
    contracts: Optional[Dict[str, Any]] = None
    asset_manifest: List[Dict[str, Any]] = field(default_factory=list)
    governance: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["batch_roadmap"] = [asdict(b) for b in self.batch_roadmap]
        # drop None optionals so the JSON stays clean / schema-friendly
        return {k: v for k, v in d.items() if v is not None}

    def stamp_digest(self) -> "DesignBundle":
        """Content-address the bundle (everything except the digest itself)."""
        body = self.to_dict()
        body.get("provenance", {}).pop("design_digest", None)
        import json

        digest = sha256_digest(json.dumps(body, sort_keys=True, ensure_ascii=False))
        self.provenance["design_digest"] = digest
        return self
