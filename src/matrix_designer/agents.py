"""The specialist agents — each owns one slice of the design and writes it into the
shared state. These are the LangGraph *nodes*. Implementations are deterministic so the
graph always runs offline; when an LLM is configured, ``llm_assist`` lets a node refine
its draft (the structure/contract stays identical, the contents get richer).

Roles (per the design analysis):
  planner  → requirements → architect → uiux → batch_planner → quality → synthesizer
                                                         ↑__________ refine (chat) __________|
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .blueprint import (
    ArchitectureNode, BlueprintBatch, BlueprintCandidate, BlueprintDetails, FilePlanItem,
)
from .state import DesignState, TIERS

RMD_RULES = [
    "RMD-101: AI coders are workers, not architects.",
    "RMD-103: Control files are protected.",
    "RMD-111: Acceptance criteria are law.",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def llm_assist(role: str, prompt: str) -> Optional[str]:
    """Optional hook: refine a node's draft with the configured LLM (watsonx by default).
    Returns None when no model is available, so the deterministic draft stands."""
    if os.environ.get("MATRIX_DESIGNER_BACKEND", "auto") == "off":
        return None
    if not (os.environ.get("WATSONX_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")):
        return None
    try:  # LangGraph/LangChain chat model, kept optional
        from langchain.chat_models import init_chat_model  # type: ignore
        model = os.environ.get("MATRIX_DESIGNER_MODEL", "")
        if not model:
            return None
        llm = init_chat_model(model)
        return str(llm.invoke(f"[{role}]\n{prompt}").content)
    except Exception:
        return None


# --------------------------------------------------------------------------------------
# node 1 — Planner / orchestrator
# --------------------------------------------------------------------------------------
def planner_node(state: DesignState) -> DesignState:
    idea = state["idea"]
    domain = _infer_domain(idea, state.get("constraints", {}))
    state.setdefault("log", []).append(f"planner: domain={domain}")
    state["requirements"] = {"domain": domain}  # seed; requirements_node fills the rest
    return state


# --------------------------------------------------------------------------------------
# node 2 — Requirements analyst
# --------------------------------------------------------------------------------------
def requirements_node(state: DesignState) -> DesignState:
    idea = state["idea"]
    domain = state["requirements"].get("domain", "web-app")
    constraints = state.get("constraints", {})
    forbidden = constraints.get("forbidden_stack", [])
    features = _features_for(domain, idea)
    state["requirements"] = {
        "domain": domain,
        "features": features,
        "constraints": _constraints_for(domain, constraints),
        "users": ["end user", "operator/admin"],
        "non_functional": ["responsive", "accessible (WCAG AA)", "no runtime errors", "CI build"],
    }
    if forbidden:
        state["requirements"]["constraints"].append(f"forbidden: {', '.join(forbidden)}")
    state.setdefault("log", []).append(f"requirements: {len(features)} features")
    return state


# --------------------------------------------------------------------------------------
# node 3 — Architect
# --------------------------------------------------------------------------------------
def architect_node(state: DesignState) -> DesignState:
    domain = state["requirements"]["domain"]
    stack = _stack_for(domain, state.get("constraints", {}))
    state["constraints"] = {**state.get("constraints", {}), "_stack": stack}
    nodes = _architecture_for(domain, stack)
    state["architecture"] = [n.__dict__ for n in nodes]
    state.setdefault("log", []).append(f"architect: {len(nodes)} components on {', '.join(stack)}")
    return state


# --------------------------------------------------------------------------------------
# node 4 — UI/UX designer
# --------------------------------------------------------------------------------------
def uiux_node(state: DesignState) -> DesignState:
    domain = state["requirements"]["domain"]
    state["ui_layout"] = {
        "style": "premium, dark, Apple-like; green accent; glass cards; generous spacing",
        "primary_flows": _flows_for(domain),
    }
    state["asset_plan"] = _assets_for(domain)
    state.setdefault("log", []).append("uiux: layout + asset plan")
    return state


# --------------------------------------------------------------------------------------
# node 5 — Batch planner  (fan-out: one roadmap per tier, simplest → hardest)
# --------------------------------------------------------------------------------------
def batch_planner_node(state: DesignState) -> DesignState:
    domain = state["requirements"]["domain"]
    full = _full_roadmap(domain)
    details: Dict[str, Any] = {}
    for t in TIERS:
        n = max(3, round(len(full) * t["scale"]))
        batches = full[:n] if n <= len(full) else full + _extra_batches(domain, n - len(full), len(full))
        details[t["id"]] = [b for b in batches]  # store raw batches; synthesizer wraps them
    state["details"] = details  # interim: tier -> [BlueprintBatch]
    state.setdefault("log", []).append(f"batch_planner: {len(full)} base batches, 3 tiers")
    return state


# --------------------------------------------------------------------------------------
# node 6 — Quality checker (governance / Matrix Definitions)
# --------------------------------------------------------------------------------------
def quality_node(state: DesignState) -> DesignState:
    state["matrix_rules"] = list(RMD_RULES)
    violations: List[Dict[str, str]] = []
    for tier_id, batches in state.get("details", {}).items():
        for b in batches:
            if not b.allowed_files:
                violations.append({"rule_id": "DESIGN-001", "severity": "high", "message": f"{tier_id}/{b.id} has no allowed_files"})
            if not b.acceptance_criteria:
                violations.append({"rule_id": "DESIGN-002", "severity": "high", "message": f"{tier_id}/{b.id} has no acceptance"})
    state["violations"] = violations
    state.setdefault("log", []).append(f"quality: {len(violations)} violations")
    return state


# --------------------------------------------------------------------------------------
# node 7 — Blueprint synthesizer (assemble candidates + full BlueprintDetails per tier)
# --------------------------------------------------------------------------------------
def synthesizer_node(state: DesignState) -> DesignState:
    domain = state["requirements"]["domain"]
    stack = state.get("constraints", {}).get("_stack", ["html", "css", "js"])
    arch = [ArchitectureNode(**a) for a in state["architecture"]]
    file_plan = _file_plan_for(domain, stack)
    candidates: List[Dict[str, Any]] = []
    out_details: Dict[str, Any] = {}
    for t in TIERS:
        batches: List[BlueprintBatch] = state["details"][t["id"]]
        files = max(8, round(len(file_plan) * (2 + t["scale"] * 4)))
        cand = BlueprintCandidate(
            id=t["id"], tier=t["tier"],
            title=f"{t['tier']} {'controlled blueprint' if t['id'] != 'standard' else 'Matrix Bundle'}",
            summary=_summary_for(domain, t, state["idea"]),
            file_count=files, difficulty=t["difficulty"], estimate=t["time"], stack=stack,
            recommended=bool(t.get("recommended")),
        )
        candidates.append(cand.__dict__)
        det = BlueprintDetails(
            candidate_id=t["id"],
            overview=_overview_for(domain, t, state["idea"]),
            architecture=arch if t["id"] != "minimal" else arch[: max(2, len(arch) - 2)],
            batches=batches,
            file_plan=file_plan if t["id"] != "minimal" else file_plan[: max(4, len(file_plan) - 2)],
            matrix_rules=state["matrix_rules"],
            acceptance_criteria=_acceptance_for(domain, t),
            validation_plan=["lint", "typecheck", "unit tests", "allowed-file check", "forbidden-file check", "Matrix commit check"],
            risks=_risks_for(domain),
            assumptions=["original assets only" if domain == "web-game" else "auth required if data is sensitive"],
            design_brain=f"Designed by Matrix Designer (LangGraph multi-agent) · {len(batches)} batches · tier {t['tier']}.",
            chat_history=[],
        )
        out_details[t["id"]] = det.to_dict()
    state["candidates"] = candidates
    state["details"] = out_details
    state.setdefault("log", []).append("synthesizer: 3 blueprints assembled")
    return state


# --------------------------------------------------------------------------------------
# orchestrator chat — refine the design from a free-text instruction
# --------------------------------------------------------------------------------------
def refine_node(state: DesignState, message: str, candidate_id: str = "standard") -> DesignState:
    state.setdefault("chat_history", []).append({"role": "user", "content": message, "timestamp": _now()})
    m = message.lower()
    det = state["details"].get(candidate_id)
    action = "Noted."
    if det:
        batches = det["batches"]
        if any(k in m for k in ("boss", "level", "enemy", "feature", "add", "analytic", "audit", "auth", "dashboard")):
            new_id = f"batch-{len(batches) + 1:02d}"
            name = _refine_batch_name(m)
            batches.append(BlueprintBatch(id=new_id, name=name, purpose=f"Added from chat: {message.strip()}",
                                          tasks=[message.strip()], allowed_files=["src/**"],
                                          acceptance_criteria=["feature works", "no runtime errors"],
                                          validation_checks=["unit tests"]).__dict__)
            action = f"Added {new_id} — {name}. Review and Save latest edits."
        elif any(k in m for k in ("reduce", "smaller", "simpler", "remove", "drop")):
            if len(batches) > 3:
                dropped = batches.pop()
                action = f"Reduced scope — removed {dropped['name']}."
        elif "split" in m:
            action = "Split request noted; the batch planner will divide the targeted batch on save."
    state["chat_history"].append({"role": "blueprint", "content": action, "timestamp": _now()})
    state.setdefault("log", []).append(f"refine: {action}")
    return state


# ======================================================================================
# domain knowledge (deterministic brains)
# ======================================================================================
def _infer_domain(idea: str, constraints: Dict[str, Any]) -> str:
    s = (idea + " " + " ".join(str(v) for v in constraints.values())).lower()
    if any(k in s for k in ("game", "platformer", "phaser", "arcade", "canvas")):
        return "web-game"
    if any(k in s for k in ("api", "fastapi", "endpoint", "service", "rest")):
        return "api"
    if any(k in s for k in ("agent", "crew", "langgraph", "workflow", "mcp")):
        return "agent"
    if any(k in s for k in ("dashboard", "admin", "analytics", "triage", "bot")):
        return "saas"
    return "web-app"


def _stack_for(domain: str, constraints: Dict[str, Any]) -> List[str]:
    pref = constraints.get("preferred_stack") or []
    if pref:
        return list(pref)
    return {
        "web-game": ["Phaser 3", "TypeScript", "Vite"],
        "api": ["FastAPI", "PostgreSQL", "Docker"],
        "agent": ["Python", "LangGraph", "FastAPI"],
        "saas": ["Next.js", "FastAPI", "PostgreSQL", "Docker"],
    }.get(domain, ["Next.js", "FastAPI", "PostgreSQL"])


def _features_for(domain: str, idea: str) -> List[str]:
    return {
        "web-game": ["player movement", "collectibles", "enemies", "power-ups", "levels", "boss", "HUD", "audio"],
        "api": ["data model", "CRUD endpoints", "auth", "background jobs", "rate limits"],
        "agent": ["tools", "graph workflow", "state/checkpoints", "human-in-loop", "MCP server"],
        "saas": ["auth", "dashboard", "data model", "integrations", "admin", "metrics", "audit log"],
    }.get(domain, ["core UI", "data model", "auth", "settings"])


def _constraints_for(domain: str, c: Dict[str, Any]) -> List[str]:
    base = [f"deployment: {c.get('deployment_target', 'static-pages' if domain == 'web-game' else 'docker')}"]
    if domain == "web-game":
        base.append("original assets only")
    return base


def _architecture_for(domain: str, stack: List[str]) -> List[ArchitectureNode]:
    if domain == "web-game":
        return [
            ArchitectureNode("Web Client (Phaser)", "Canvas game, scenes, physics, camera"),
            ArchitectureNode("Asset pipeline", "Original sprites/tiles/audio", ["Web Client (Phaser)"]),
            ArchitectureNode("Level engine", "Data-driven levels (config + builder)", ["Web Client (Phaser)"]),
            ArchitectureNode("HUD / UI", "Score, lives, RMD HUD", ["Web Client (Phaser)"]),
            ArchitectureNode("CI / Pages", "Build + deploy to GitHub Pages", ["Web Client (Phaser)"]),
        ]
    if domain == "api":
        return [
            ArchitectureNode("API (FastAPI)", "Endpoints + business logic"),
            ArchitectureNode("Database", "Schema + migrations", ["API (FastAPI)"]),
            ArchitectureNode("Worker", "Background jobs", ["API (FastAPI)"]),
            ArchitectureNode("Deployment", "Docker / cloud", ["API (FastAPI)"]),
        ]
    return [
        ArchitectureNode("Web App", stack[0] if stack else "Frontend"),
        ArchitectureNode("API", "Business logic", ["Web App"]),
        ArchitectureNode("Database", "Persistent storage", ["API"]),
        ArchitectureNode("Worker / Queue", "Background jobs", ["API"]),
        ArchitectureNode("Admin Dashboard", "Ops & analytics", ["Web App", "API"]),
    ]


def _flows_for(domain: str) -> List[str]:
    return {
        "web-game": ["title → story → play → victory → credits"],
        "saas": ["sign in → dashboard → detail → settings"],
    }.get(domain, ["land → core action → result"])


def _assets_for(domain: str) -> List[Dict[str, str]]:
    if domain == "web-game":
        return [{"name": n, "kind": k} for n, k in
                [("hero", "spritesheet"), ("enemies", "sprite"), ("coin", "sprite"), ("tiles", "tile"), ("parallax", "background"), ("sfx", "audio")]]
    return [{"name": "design tokens", "kind": "theme"}, {"name": "component library", "kind": "ui"}]


def _full_roadmap(domain: str) -> List[BlueprintBatch]:
    if domain == "web-game":
        spec = [
            ("Game foundation", "Vite + Phaser scaffold, empty scene, Pages config.", ["vite.config.ts", "src/main.ts", "src/scenes/Boot*.ts"], ["builds", "blank canvas renders"]),
            ("Asset pipeline", "Original pixel-art set + Preload.", ["scripts/gen_assets.py", "public/assets/**", "src/scenes/Preload*.ts"], ["assets load", "anims build"]),
            ("Tilemap world", "Data-driven level + parallax + camera.", ["src/levels/**", "src/scenes/Game*.ts"], ["camera follows", "collisions work"]),
            ("Player & controls", "Hero movement + round collectibles.", ["src/entities/Player.ts", "src/entities/Coin.ts"], ["jump works", "coins are round"]),
            ("Enemies & power-ups", "Patrol AI, stomp, shield, double-jump.", ["src/entities/**"], ["stomp kills", "power-ups apply"]),
            ("HUD & gate", "Metallic HUD + animated Matrix Gate.", ["src/ui/HUD.ts", "src/scenes/Game*.ts"], ["HUD reads", "gate advances level"]),
            ("Campaign & boss", "Episodes as data + story + Rogue Architect.", ["src/levels/episodes.ts", "src/scenes/Story*.ts"], ["8 episodes", "boss opens gate"]),
            ("Polish & release", "Particles, audio, title/victory/credits, CI.", [".github/workflows/deploy.yml", "src/scenes/**"], ["60fps", "CI deploys"]),
        ]
    else:
        spec = [
            ("Foundation", "Scaffold, config, schema, auth, baseline tests.", ["apps/web/**", "services/api/**", "db/**"], ["builds", "app boots"]),
            ("Integrations", "External apps, events, endpoints, jobs.", ["services/api/**", "services/worker/**"], ["events ingest", "endpoints respond"]),
            ("Workflow & logic", "Routing, business rules, notifications.", ["services/api/**", "packages/shared/**"], ["rules apply"]),
            ("Admin & analytics", "Dashboard, users, metrics, audit log.", ["apps/web/**", "services/api/**"], ["dashboard renders", "audit records"]),
            ("Hardening & deploy", "Security, rate limits, Docker, CI/CD.", ["docker-compose.yml", ".github/**"], ["CI green"]),
            ("Validation & release", "Tests, evidence, Matrix validation.", ["tests/**", "docs/**"], ["tests pass", "Matrix approves"]),
        ]
    out: List[BlueprintBatch] = []
    for i, (name, purpose, allowed, accept) in enumerate(spec, 1):
        out.append(BlueprintBatch(id=f"batch-{i:02d}", name=name, purpose=purpose,
                                  tasks=[purpose], allowed_files=allowed,
                                  depends_on=[f"batch-{i-1:02d}"] if i > 1 else [],
                                  acceptance_criteria=accept, validation_checks=["lint", "typecheck", "tests"]))
    return out


def _extra_batches(domain: str, count: int, start: int) -> List[BlueprintBatch]:
    extras = ["Accessibility & i18n", "Observability & metrics", "Performance pass", "Security review", "Docs & onboarding"]
    out: List[BlueprintBatch] = []
    for k in range(count):
        i = start + k + 1
        out.append(BlueprintBatch(id=f"batch-{i:02d}", name=extras[k % len(extras)], purpose="Production hardening.",
                                  tasks=["hardening"], allowed_files=["**"], depends_on=[f"batch-{i-1:02d}"],
                                  acceptance_criteria=["meets the production bar"], validation_checks=["tests"]))
    return out


def _file_plan_for(domain: str, stack: List[str]) -> List[FilePlanItem]:
    if domain == "web-game":
        return [FilePlanItem(p, d) for p, d in [
            ("src/scenes", "Boot/Preload/Title/Game/Victory/Credits"), ("src/levels", "episode data + builder"),
            ("src/entities", "Player, enemies, Coin"), ("public/assets", "original art"),
            ("scripts/gen_assets.py", "asset generator"), (".github/workflows/deploy.yml", "CI → Pages"), ("README.md", "overview")]]
    return [FilePlanItem(p, d) for p, d in [
        ("apps/web", "Web app and dashboard"), ("services/api", "API and business logic"),
        ("services/worker", "Background jobs and queue"), ("packages/shared", "Shared types and utils"),
        ("db", "Migrations and seeds"), ("docker-compose.yml", "Local environment"), ("README.md", "overview")]]


def _summary_for(domain: str, t: Dict[str, Any], idea: str) -> str:
    kind = {"minimal": "Small controlled build package", "standard": "Recommended controlled blueprint", "production": "Hardened Matrix Bundle with release evidence"}[t["id"]]
    return f"{kind} for: {idea.strip()[:90]}"


def _overview_for(domain: str, t: Dict[str, Any], idea: str) -> str:
    return (f"This {t['tier'].lower()} blueprint builds {idea.strip()[:120]}. "
            f"It is delivered in ordered, validated batches; each batch is scoped to an allow-list and "
            f"gated by Matrix validation before it lands.")


def _acceptance_for(domain: str, t: Dict[str, Any]) -> List[str]:
    if domain == "web-game":
        return ["movement, collectibles, enemies work", "typecheck clean; build produces dist/", "zero runtime errors",
                *(["8-episode campaign + boss", "deployed to GitHub Pages"] if t["id"] != "minimal" else [])]
    return ["app builds and boots", "core flow works with tests", "Matrix validation approves the build",
            *(["auth + audit log", "CI/CD deploy"] if t["id"] != "minimal" else [])]


def _risks_for(domain: str) -> List[str]:
    if domain == "web-game":
        return ["level tuning may need iteration", "asset look depends on the art pass"]
    return ["external credentials required", "data sensitivity may require auth hardening"]


def _refine_batch_name(m: str) -> str:
    if "boss" in m: return "Boss encounter"
    if "level" in m: return "Extra level"
    if "analytic" in m or "metric" in m: return "Analytics & metrics"
    if "audit" in m: return "Audit logging"
    if "auth" in m: return "Auth & access"
    if "dashboard" in m: return "Admin dashboard"
    return "Refinement"
