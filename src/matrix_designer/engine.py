"""The design engine — *the batches guy*.

Given the chosen **blueprint** (from Matrix Builder) plus the original idea and any
references, the engine architects the FULL proposal and emits a governed
``design-bundle`` with every batch and all details.

Two execution modes, same output contract:

* **agentic** (default when an LLM is configured) — a small **CrewAI** crew of
  specialised agents (Goal Analyst → Architect → Visual Director → *Batch Planner*)
  collaborates to design the solution and decompose it into dependency-aware batches.
  LangGraph / Langflow back-ends are pluggable behind the same ``DesignEngine`` API.
* **deterministic** (fallback) — heuristic planner that always runs with no LLM, no
  network, so CI and offline use never break. It also seeds/sanity-checks the agentic
  output.

The engine never *approves* its own design — that is the job of
``validate.py`` against Matrix Definitions design-packs (AI proposes, Definitions enforce).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .models import Batch, DesignBundle
from .packs import load_pack

# Which agentic backend to use: "crewai" | "langgraph" | "langflow" | "auto" | "off"
DESIGN_BACKEND = os.environ.get("MATRIX_DESIGNER_BACKEND", "auto")

# Fields the Batch dataclass accepts — used to filter LLM output defensively so an extra
# or missing key from a model never raises (the agentic layer must never break the contract).
_BATCH_FIELDS = {"id", "name", "purpose", "allowed_files", "acceptance",
                 "depends_on", "new_features", "must_not_change"}
_BATCH_LISTS = {"allowed_files", "acceptance", "depends_on", "new_features", "must_not_change"}


def _batch_from_dict(b: Dict[str, Any]) -> Optional[Batch]:
    """Build a Batch from arbitrary LLM JSON: keep only known keys, coerce list fields,
    and supply safe defaults. Returns None if the batch has no usable id."""
    bid = str(b.get("id") or "").strip()
    if not bid:
        return None
    kept = {k: v for k, v in b.items() if k in _BATCH_FIELDS}
    kept["id"] = bid
    kept.setdefault("name", bid)
    kept.setdefault("purpose", "")
    for key in _BATCH_LISTS:
        val = kept.get(key)
        if val is None:
            kept[key] = []
        elif isinstance(val, str):
            kept[key] = [val]
        elif not isinstance(val, list):
            kept[key] = list(val) if isinstance(val, (tuple, set)) else [str(val)]
    try:
        return Batch(**kept)
    except Exception:
        return None


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------
class DesignEngine:
    def __init__(self, backend: str = DESIGN_BACKEND, model: Optional[str] = None):
        self.backend = backend
        self.model = model or os.environ.get("MATRIX_DESIGNER_MODEL", "")

    def design(
        self,
        idea: str,
        blueprint: Dict[str, Any],
        references: Optional[List[Dict[str, str]]] = None,
        quality_level: str = "standard",
    ) -> DesignBundle:
        """Architect the full proposal + batches for the chosen blueprint."""
        references = references or []
        agentic = self._maybe_agentic(idea, blueprint, references, quality_level)
        if agentic is not None:
            return agentic.stamp_digest()
        return self._deterministic(idea, blueprint, references, quality_level).stamp_digest()

    # ---- agentic path (CrewAI / LangGraph / Langflow) --------------------------------
    def _maybe_agentic(self, idea, blueprint, references, quality_level) -> Optional[DesignBundle]:
        if self.backend in ("off",):
            return None
        try:
            if self.backend in ("crewai", "auto"):
                return self._crewai_design(idea, blueprint, references, quality_level)
        except Exception as exc:  # never let the agent layer break the contract
            print(f"[matrix-designer] agentic backend unavailable ({exc}); using deterministic planner")
        return None

    def _crewai_design(self, idea, blueprint, references, quality_level) -> Optional[DesignBundle]:
        """Design via a CrewAI crew. Requires `pip install crewai` + an LLM in env.

        The crew is intentionally small and role-pure so each agent owns one section of
        the Design Bundle; the Batch Planner produces the ordered roadmap.
        """
        try:
            from crewai import Agent, Crew, Process, Task  # noqa: F401
        except Exception:
            return None
        if not (self.model or os.environ.get("OPENAI_API_KEY") or os.environ.get("WATSONX_API_KEY")
                or os.environ.get("ANTHROPIC_API_KEY")):
            return None  # no LLM configured → let the deterministic planner run

        stack = ", ".join(blueprint.get("stack", []))
        analyst = Agent(role="Goal Analyst", goal="Find the real goal, complexity, risks and missing decisions.",
                        backstory="You expose what the user is truly building before anyone writes code.")
        architect = Agent(role="Solution Architect", goal=f"Design scenes/routes, systems, services and entity contracts for a {stack} solution.",
                          backstory="You make the pieces fit so no batch improvises.")
        director = Agent(role="Visual & UX Director", goal="Define the visual/UX target and the asset/UI manifest so 'done' has a LOOK.",
                        backstory="You turn 'make it premium' into a concrete, checkable acceptance target.")
        planner = Agent(role="Batch Planner", goal="Decompose everything into an ordered, dependency-aware batch roadmap with allowed_files, acceptance and must_not_change per batch.",
                       backstory="You are the batches guy: every batch is small, scoped, additive, validated, and fits the whole.")

        ctx = f"IDEA:\n{idea}\n\nCHOSEN BLUEPRINT:\n{blueprint}\n\nREFERENCES:\n{references}\n\nQUALITY: {quality_level}"
        tasks = [
            Task(description=f"{ctx}\n\nProduce goal_analysis JSON.", agent=analyst, expected_output="goal_analysis object"),
            Task(description="Produce architecture + contracts JSON.", agent=architect, expected_output="architecture + contracts objects"),
            Task(description="Produce visual_target + asset_manifest + acceptance.visual JSON.", agent=director, expected_output="visual_target, asset_manifest, visual acceptance"),
            Task(description="Produce the full batch_roadmap (>=1 batches) + functional acceptance, as JSON matching design-bundle.schema.json.", agent=planner, expected_output="batch_roadmap + acceptance"),
        ]
        crew = Crew(agents=[analyst, architect, director, planner], tasks=tasks, process=Process.sequential)
        raw = crew.kickoff()
        bundle = self._parse_agentic_output(str(raw), idea, blueprint, quality_level)
        # always reconcile against the deterministic skeleton so required fields exist
        skeleton = self._deterministic(idea, blueprint, references, quality_level)
        return _merge(skeleton, bundle)

    def _parse_agentic_output(self, raw: str, idea, blueprint, quality_level) -> Optional[DesignBundle]:
        import json
        import re

        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None
        roadmap = [
            _batch_from_dict(b)
            for b in data.get("batch_roadmap", [])
            if isinstance(b, dict) and b.get("id")
        ]
        roadmap = [b for b in roadmap if b is not None]
        if not roadmap:
            return None
        return DesignBundle(
            design_id=f"dsn-{blueprint.get('slug','project')}",
            project=blueprint.get("slug", "project"),
            slug=blueprint.get("slug"),
            quality_level=quality_level,
            source={"idea": idea},
            goal_analysis=data.get("goal_analysis", {"real_goal": idea, "complexity": "medium"}),
            framework_decision={"stack": blueprint.get("stack", []), "rationale": blueprint.get("rationale", "")},
            visual_target=data.get("visual_target"),
            architecture=data.get("architecture", {"systems": ["app"]}),
            contracts=data.get("contracts"),
            asset_manifest=data.get("asset_manifest", []),
            acceptance=data.get("acceptance", {"functional": ["builds and runs"]}),
            batch_roadmap=roadmap,
            provenance={"created_by": "matrix-designer", "ai_assisted": True, "model": self.model or "crewai"},
        )

    # ---- deterministic fallback ------------------------------------------------------
    def _deterministic(self, idea, blueprint, references, quality_level) -> DesignBundle:
        slug = blueprint.get("slug", "project")
        stack = blueprint.get("stack", ["html", "css", "js"])
        domain = _infer_domain(idea, stack)
        pack = load_pack(_pack_for_domain(domain))

        roadmap = _scaffold_roadmap(domain, slug)
        # honour quality: production/enterprise get the polish + release batches
        if quality_level in ("starter",):
            roadmap = roadmap[: max(2, len(roadmap) - 2)]

        return DesignBundle(
            design_id=f"dsn-{slug}",
            project=slug,
            slug=slug,
            domain=domain,
            quality_level=quality_level,
            source={"idea": idea, "references": references},
            goal_analysis={
                "real_goal": idea.strip()[:280],
                "complexity": "large" if len(roadmap) >= 7 else "medium",
                "missing_decisions": pack.get("missing_decisions", []),
                "risks": pack.get("risks", []),
            },
            framework_decision={
                "stack": stack,
                "rationale": blueprint.get("rationale", f"Chosen blueprint stack for a {domain} build."),
                "deployment_target": blueprint.get("deployment_target", "static-pages" if domain in ("web-game", "landing-page") else "docker"),
            },
            visual_target=pack.get("visual_target"),
            architecture=pack.get("architecture", {"systems": ["app"]}),
            contracts=pack.get("contracts"),
            asset_manifest=pack.get("asset_manifest", []),
            acceptance=pack.get("acceptance", {"functional": ["project builds", "app runs with zero errors"]}),
            batch_roadmap=roadmap,
            governance={"design_packs": [pack.get("id", "generic-v1")], "rules_applied": pack.get("rules", []), "validation_status": "not-run"},
            provenance={"created_by": "matrix-designer", "ai_assisted": False, "model": "deterministic"},
        )


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------
def _infer_domain(idea: str, stack: List[str]) -> str:
    s = (idea + " " + " ".join(stack)).lower()
    if any(k in s for k in ("game", "platformer", "phaser", "arcade", "canvas")):
        return "web-game"
    if any(k in s for k in ("api", "fastapi", "endpoint", "rest")):
        return "api"
    if any(k in s for k in ("agent", "crew", "langgraph", "workflow")):
        return "agent"
    if any(k in s for k in ("dashboard", "admin", "analytics")):
        return "dashboard"
    if any(k in s for k in ("landing", "marketing")):
        return "landing-page"
    return "web-app"


def _pack_for_domain(domain: str) -> str:
    return {"web-game": "web-game-platformer-v1"}.get(domain, "web-saas-product-v1")


def _scaffold_roadmap(domain: str, slug: str) -> List[Batch]:
    if domain == "web-game":
        names = [
            ("Framework scaffold", "Engine project builds + empty scene renders."),
            ("Asset pipeline", "Original programmatic asset set + preload."),
            ("Data-driven level engine", "Level config + fixed builder + parallax."),
            ("Player + collectibles", "Movement + correctly-rendered pickups."),
            ("Enemies + power-ups", "Stomp/damage/lives + power-ups."),
            ("HUD + gate", "HUD, panels, level-end gate."),
            ("Campaign + story + boss", "Episodes as data + narrative + boss."),
            ("Meta + polish + release", "Title/victory/credits + CI deploy."),
        ]
    else:
        names = [
            ("Project scaffold", "Builds, lints, empty app boots."),
            ("Data model + migrations", "Schema + migrations apply."),
            ("API / services", "Core endpoints/services with tests."),
            ("UI system + routes", "Design system + key routes."),
            ("Auth + state", "Auth flow + persisted state."),
            ("Polish + release", "Responsive, perf, CI deploy."),
        ]
    out: List[Batch] = []
    for i, (name, purpose) in enumerate(names, 1):
        out.append(Batch(
            id=f"batch-{i:02d}", name=name, purpose=purpose,
            depends_on=[f"batch-{i-1:02d}"] if i > 1 else [],
            allowed_files=[f"src/**  # scoped per '{name}' — refine before build"],
            acceptance=["builds clean", "feature works", "no runtime errors"],
        ))
    return out


def _merge(base: DesignBundle, override: Optional[DesignBundle]) -> DesignBundle:
    if override is None:
        return base
    # agentic roadmap wins if non-empty; everything else fills gaps from the skeleton
    if override.batch_roadmap:
        base.batch_roadmap = override.batch_roadmap
    for fld in ("goal_analysis", "visual_target", "architecture", "contracts", "acceptance"):
        val = getattr(override, fld, None)
        if val:
            setattr(base, fld, val)
    if override.asset_manifest:
        base.asset_manifest = override.asset_manifest
    base.provenance = override.provenance or base.provenance
    return base
