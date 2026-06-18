"""Shared LangGraph state — the single design document every agent reads and writes.

Modelled as a TypedDict so it works as a LangGraph ``StateGraph`` state (with reducers)
and as a plain dict in the deterministic fallback runner. Mirrors the schema in the
design analysis: idea → requirements → architecture → ui → batches → rules → candidates.
"""
from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class Requirements(TypedDict, total=False):
    features: List[str]
    constraints: List[str]
    users: List[str]
    non_functional: List[str]
    domain: str


class DesignState(TypedDict, total=False):
    # inputs
    idea: str
    references: List[Dict[str, str]]
    constraints: Dict[str, Any]
    # working memory, filled by the specialist agents
    requirements: Requirements
    architecture: List[Dict[str, str]]
    ui_layout: Dict[str, Any]
    asset_plan: List[Dict[str, str]]
    matrix_rules: List[str]
    # the deliverable: three blueprints (minimal → standard → production)
    candidates: List[Dict[str, Any]]
    details: Dict[str, Any]  # candidateId -> BlueprintDetails dict
    # orchestrator chat (human-in-the-loop refinement)
    chat_history: List[Dict[str, str]]
    # diagnostics
    violations: List[Dict[str, str]]
    log: List[str]


TIERS: List[Dict[str, Any]] = [
    {"id": "minimal", "tier": "Minimal", "quality": "starter", "difficulty": "Easy", "time": "a weekend", "scale": 0.55},
    {"id": "standard", "tier": "Standard", "quality": "standard", "difficulty": "Medium", "time": "about one week", "scale": 1.0, "recommended": True},
    {"id": "production", "tier": "Production", "quality": "production", "difficulty": "Hard", "time": "about three weeks", "scale": 1.6},
]


def new_state(idea: str, references=None, constraints=None) -> DesignState:
    return DesignState(
        idea=idea,
        references=references or [],
        constraints=constraints or {},
        requirements={},
        architecture=[],
        ui_layout={},
        asset_plan=[],
        matrix_rules=[],
        candidates=[],
        details={},
        chat_history=[],
        violations=[],
        log=[],
    )
