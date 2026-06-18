"""Blueprint Details data model — the package the Matrix Builder Details page renders.

These dataclasses mirror the TypeScript interfaces in the Details page
(BlueprintCandidate / BlueprintDetails / ArchitectureNode / FilePlanItem /
BlueprintBatch / ChatMessage), so Matrix Designer's output drops straight into the UI
and into Matrix Builder's contract chain.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class ArchitectureNode:
    name: str
    description: str
    dependencies: List[str] = field(default_factory=list)


@dataclass
class FilePlanItem:
    path: str
    description: str


@dataclass
class BlueprintBatch:
    id: str
    name: str
    purpose: str
    tasks: List[str] = field(default_factory=list)
    allowed_files: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    validation_checks: List[str] = field(default_factory=list)
    must_not_change: List[str] = field(default_factory=list)


@dataclass
class ChatMessage:
    id: str
    role: str  # "user" | "blueprint"
    content: str
    timestamp: str = ""


@dataclass
class BlueprintCandidate:
    id: str           # "minimal" | "standard" | "production"
    tier: str         # "Minimal" | "Standard" | "Production"
    title: str
    summary: str
    file_count: int
    difficulty: str
    estimate: str
    stack: List[str]
    recommended: bool = False


@dataclass
class BlueprintDetails:
    candidate_id: str
    overview: str
    architecture: List[ArchitectureNode]
    batches: List[BlueprintBatch]
    file_plan: List[FilePlanItem]
    matrix_rules: List[str]
    acceptance_criteria: List[str] = field(default_factory=list)
    validation_plan: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    design_brain: Optional[str] = None
    chat_history: List[ChatMessage] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
