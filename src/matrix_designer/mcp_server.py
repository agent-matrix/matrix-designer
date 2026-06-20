"""matrix-designer-mcp — the agentic "batches guy" as an MCP server.

Matrix Builder (or any MCP client) invokes these tools *optionally*, after a blueprint
is chosen, to have an LLM crew design the full proposal and decompose it into every
batch with all details. Each tool emits one schema-checked slice of a ``design-bundle``;
``generate_batches`` and ``assemble_design_bundle`` produce the whole thing.

Run::

    pip install "matrix-designer[mcp,agentic]"
    python -m matrix_designer.mcp_server          # stdio MCP server

Tools (1:1 with the design pipeline):
    analyze_idea            idea(+refs)            -> goal_analysis
    decompose_reference     image/pdf/url          -> visual_target + asset hints
    propose_architecture    idea + blueprint       -> architecture + contracts
    generate_batches        idea + blueprint       -> batch_roadmap   (THE batches guy)
    assemble_design_bundle  all of the above       -> design-bundle (validated)
    validate_design         design-bundle          -> approved|needs-repair|rejected
    export_to_builder       design-bundle          -> Matrix Builder inputs (idea/blueprint/mb-next)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .engine import DesignEngine
from .exporter import to_mb_export
from .graph import design_blueprints, refine, run_design
from .validate import verdict

try:
    from mcp.server.fastmcp import FastMCP  # type: ignore
    _HAVE_MCP = True
except Exception:  # pragma: no cover
    _HAVE_MCP = False


# Plain callables so the package is usable/testable without the MCP runtime installed.
def analyze_idea(idea: str, references: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    eng = DesignEngine()
    b = eng.design(idea, blueprint={"slug": "draft", "stack": []}, references=references)
    return b.to_dict()["goal_analysis"]


def decompose_reference(kind: str, ref: str, note: str = "") -> Dict[str, Any]:
    """Stub for visual decomposition; the agentic backend fills this with a vision LLM."""
    return {
        "visual_target": {"style": "(derive from reference)", "must_include": [], "reference_digests": []},
        "asset_hints": [],
        "note": f"decompose {kind}:{ref} {note}".strip(),
    }


def propose_architecture(idea: str, blueprint: Dict[str, Any]) -> Dict[str, Any]:
    b = DesignEngine().design(idea, blueprint)
    d = b.to_dict()
    return {"architecture": d.get("architecture"), "contracts": d.get("contracts")}


def generate_batches(idea: str, blueprint: Dict[str, Any], quality_level: str = "standard",
                     references: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """THE batches guy: full ordered, dependency-aware roadmap for the chosen blueprint."""
    b = DesignEngine().design(idea, blueprint, references=references, quality_level=quality_level)
    return {"batch_roadmap": b.to_dict()["batch_roadmap"], "count": len(b.batch_roadmap)}


def assemble_design_bundle(idea: str, blueprint: Dict[str, Any], quality_level: str = "standard",
                           references: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    b = DesignEngine().design(idea, blueprint, references=references, quality_level=quality_level)
    bundle = b.to_dict()
    status, report = verdict(bundle)
    bundle.setdefault("governance", {})["validation_status"] = status
    return {"design_bundle": bundle, "validation": report}


def validate_design(design_bundle: Dict[str, Any]) -> Dict[str, Any]:
    _, report = verdict(design_bundle)
    return report


def export_to_builder(design_bundle: Dict[str, Any]) -> Dict[str, Any]:
    return to_mb_export(design_bundle)


def generate_blueprints(idea: str, references: Optional[List[Dict[str, str]]] = None,
                        constraints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run the LangGraph multi-agent brain → 3 blueprints (Minimal/Standard/Production)
    with full Blueprint Details (overview, architecture, batches, file plan, Matrix rules)
    that the Matrix Builder Details page renders directly."""
    out = design_blueprints(idea, references, constraints)
    out.pop("_state", None)
    return out


def refine_design(idea: str, message: str, candidate_id: str = "standard",
                  constraints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Orchestrator chat: apply a free-text modification (e.g. 'add a boss level',
    'reduce scope', 'add audit logging') to a blueprint and return the updated details."""
    state = run_design(idea, None, constraints)
    out = refine(state, message, candidate_id)
    out.pop("_state", None)
    return out


def build_server():  # pragma: no cover
    if not _HAVE_MCP:
        raise RuntimeError("Install the MCP extra:  pip install 'matrix-designer[mcp]'")
    mcp = FastMCP("matrix-designer")
    mcp.tool()(analyze_idea)
    mcp.tool()(decompose_reference)
    mcp.tool()(propose_architecture)
    mcp.tool()(generate_batches)
    mcp.tool()(generate_blueprints)
    mcp.tool()(refine_design)
    mcp.tool()(assemble_design_bundle)
    mcp.tool()(validate_design)
    mcp.tool()(export_to_builder)
    return mcp


def main() -> None:  # pragma: no cover
    build_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
