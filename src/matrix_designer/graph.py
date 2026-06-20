"""The Matrix Designer graph — a LangGraph multi-agent workflow (the "design brain").

Topology: **Planner + Subagents** orchestrated as a sequential ``StateGraph`` that
fans out to three blueprints (Minimal → Standard → Production) inside the batch/synth
nodes, then a human-in-the-loop ``refine`` entry point for the orchestrator chat:

    planner → requirements → architect → uiux → batch_planner → quality → synthesizer → END
                                                              ↑___ refine(chat) ___|

LangGraph is used when installed (durable state, checkpointing, parallelism); otherwise
an identical deterministic runner executes the same nodes in order, so the brain always
runs offline and in CI.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from . import agents
from .state import DesignState, new_state

# Ordered pipeline of specialist nodes (name → callable).
PIPELINE = [
    ("planner", agents.planner_node),
    ("requirements", agents.requirements_node),
    ("architect", agents.architect_node),
    ("uiux", agents.uiux_node),
    ("batch_planner", agents.batch_planner_node),
    ("quality", agents.quality_node),
    ("synthesizer", agents.synthesizer_node),
]


def _build_langgraph():
    """Compile the StateGraph if LangGraph is importable; else return None."""
    if os.environ.get("MATRIX_DESIGNER_BACKEND", "auto") not in ("langgraph", "auto"):
        return None
    try:
        from langgraph.graph import StateGraph, END  # type: ignore
    except Exception:
        return None
    g = StateGraph(DesignState)
    for name, fn in PIPELINE:
        g.add_node(name, fn)
    g.set_entry_point(PIPELINE[0][0])
    for (a, _), (b, _) in zip(PIPELINE, PIPELINE[1:]):
        g.add_edge(a, b)
    g.add_edge(PIPELINE[-1][0], END)
    try:
        from langgraph.checkpoint.memory import MemorySaver  # type: ignore
        return g.compile(checkpointer=MemorySaver())
    except Exception:
        return g.compile()


def _run_deterministic(state: DesignState) -> DesignState:
    for _, fn in PIPELINE:
        state = fn(state)
    return state


def run_design(idea: str, references=None, constraints=None) -> DesignState:
    """Run the full multi-agent design and return the final state (3 blueprints + details)."""
    state = new_state(idea, references, constraints)
    app = _build_langgraph()
    if app is not None:
        try:
            cfg = {"configurable": {"thread_id": "design-1"}}
            result = app.invoke(state, cfg)
            # LangGraph returns the merged state dict
            return result  # type: ignore[return-value]
        except Exception as exc:
            state.setdefault("log", []).append(f"langgraph fell back: {exc}")
    return _run_deterministic(state)


def design_blueprints(idea: str, references=None, constraints=None) -> Dict[str, Any]:
    """Public API: the 3 candidate cards + full BlueprintDetails per candidate."""
    state = run_design(idea, references, constraints)
    return {
        "candidates": state["candidates"],
        "details": state["details"],
        "matrix_rules": state["matrix_rules"],
        "violations": state.get("violations", []),
        "trace": state.get("log", []),
        "_state": state,  # kept for chat refinement continuity
    }


def refine(state: DesignState, message: str, candidate_id: str = "standard") -> Dict[str, Any]:
    """Orchestrator chat: apply a free-text modification and return the updated package."""
    state = agents.refine_node(state, message, candidate_id)
    reply = state["chat_history"][-1]["content"] if state.get("chat_history") else ""
    return {
        "reply": reply,
        "details": state["details"],
        "candidates": state["candidates"],
        "chat_history": state["chat_history"],
        "_state": state,
    }
