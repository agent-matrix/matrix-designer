"""Matrix Designer HTTP service — the brain over HTTP, for Matrix Builder's control plane.

Exposes the tools the Details page needs (`generate_blueprints`, `refine_design`) plus
the two the build chain needs (`design_bundle`, `review`) as JSON endpoints, alongside
the stdio MCP server (`mcp_server.py`). The core handlers are plain functions (testable
without FastAPI); ``build_app()`` wraps them in a FastAPI app when the extra is
installed.

The four endpoints are one chain, and a control plane may enter at any point:

    /design/blueprints  idea            → 3 candidate blueprints (pick one)
    /design/refine      + free text     → the same package, adjusted
    /design/bundle      + candidate_id  → the full governed Design Bundle
    /design/review      bundle          → schema + design-rule verdict

``/design/bundle`` and ``/design/review`` are thin wrappers over
:class:`~matrix_designer.engine.DesignEngine` and
:func:`~matrix_designer.validate.verdict` — the same code paths the ``mdesign`` CLI
has always used, now reachable over HTTP.

    pip install "matrix-designer[service]"
    python -m matrix_designer.service           # uvicorn on :8077

Trust boundary
--------------
This service is designed to run **inside** Matrix Builder's control plane (a trusted,
internal hop). It exposes no auth by default so the existing deployment is unchanged.
For an exposed/enterprise deployment, opt into hardening with env vars (all default-off):

* ``MATRIX_DESIGNER_API_KEY``      — when set, ``/design/*`` requires
  ``Authorization: Bearer <key>`` or ``X-API-Key: <key>`` (``/healthz`` stays open).
* ``MATRIX_DESIGNER_CORS_ORIGINS`` — comma-separated allow-list; when set, enables CORS.
* ``MATRIX_DESIGNER_HOST``         — bind host (default ``0.0.0.0``).
* ``MATRIX_DESIGNER_MAX_IDEA``     — max idea length (default 8000 chars; longer is rejected).

Governance: provider-agnostic. With no provider the deterministic runner answers, so the
service never blocks and never calls an unapproved model; an operator MAY restrict
providers via ``MATRIX_DESIGNER_ALLOWED_PROVIDERS``.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from .graph import design_blueprints, refine, run_design

DEFAULT_PORT = int(os.environ.get("MATRIX_DESIGNER_PORT", "8077"))
DEFAULT_HOST = os.environ.get("MATRIX_DESIGNER_HOST", "0.0.0.0")
MAX_IDEA_CHARS = int(os.environ.get("MATRIX_DESIGNER_MAX_IDEA", "8000"))
MAX_MESSAGE_CHARS = int(os.environ.get("MATRIX_DESIGNER_MAX_MESSAGE", "4000"))


def provider_guard() -> Optional[str]:
    """Provider-agnostic: Matrix Designer works with OllaBridge or any LLM provider, so no
    provider is restricted. Kept as a hook for an operator-defined allow-list via
    MATRIX_DESIGNER_ALLOWED_PROVIDERS (comma-separated); unset = allow all."""
    allow = os.environ.get("MATRIX_DESIGNER_ALLOWED_PROVIDERS", "").strip()
    if not allow:
        return None  # allow any provider (default)
    provider = os.environ.get("MATRIX_DESIGNER_PROVIDER", os.environ.get("GITPILOT_PROVIDER", "")).lower()
    allowed = {p.strip().lower() for p in allow.split(",")} | {"", "none"}
    if provider not in allowed:
        return f"provider '{provider}' is not in MATRIX_DESIGNER_ALLOWED_PROVIDERS ({allow})."
    return None


def _clean_idea(idea: str) -> str:
    """Trim and length-cap the idea defensively (never crash on huge/empty input)."""
    return (idea or "").strip()[:MAX_IDEA_CHARS]


# ---- core handlers (no web framework required) ---------------------------------------
def blueprints_handler(idea: str, references: Optional[List[Dict[str, str]]] = None,
                       constraints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    err = provider_guard()
    if err:
        return {"error": err, "candidates": [], "details": {}}
    idea = _clean_idea(idea)
    if not idea:
        return {"error": "idea is required (non-empty).", "candidates": [], "details": {}}
    out = design_blueprints(idea, references, constraints)
    out.pop("_state", None)
    return out


def refine_handler(idea: str, message: str, candidate_id: str = "standard",
                   constraints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    err = provider_guard()
    if err:
        return {"error": err, "reply": err, "details": {}, "candidates": []}
    idea = _clean_idea(idea)
    if not idea:
        msg = "idea is required (non-empty)."
        return {"error": msg, "reply": msg, "details": {}, "candidates": []}
    message = (message or "").strip()[:MAX_MESSAGE_CHARS]
    state = run_design(idea, None, constraints)
    out = refine(state, message, candidate_id)
    out.pop("_state", None)
    return out


def _slug(text: str) -> str:
    """A filesystem/repo-safe project slug derived from the idea."""
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return "-".join(slug.split("-")[:5])[:48] or "project"


def _blueprint_for(idea: str, candidate_id: str, references=None,
                   constraints=None) -> tuple[Dict[str, Any], str]:
    """Resolve a candidate id ('minimal'|'standard'|'production') to the blueprint dict
    the engine designs against, plus that tier's quality level.

    This is the 'pick a plan, then design it' step: the caller chose one of the three
    candidates from /design/blueprints, and we hand the engine that candidate's stack
    and rationale rather than making it guess again.
    """
    from .state import TIERS

    package = design_blueprints(idea, references, constraints)
    package.pop("_state", None)
    candidates = package.get("candidates") or []
    chosen = next((c for c in candidates if c.get("id") == candidate_id), None)
    if chosen is None:
        chosen = next((c for c in candidates if c.get("recommended")), None)
    if chosen is None and candidates:
        chosen = candidates[0]
    if chosen is None:
        return {"slug": _slug(idea), "stack": []}, "standard"
    tier = next((t for t in TIERS if t["id"] == chosen.get("id")), None)
    blueprint = {
        "slug": _slug(idea),
        "stack": list(chosen.get("stack") or []),
        "rationale": chosen.get("summary", ""),
    }
    return blueprint, str((tier or {}).get("quality") or "standard")


def bundle_handler(idea: str, blueprint: Optional[Dict[str, Any]] = None, candidate_id: str = "",
                   references: Optional[List[Dict[str, str]]] = None,
                   constraints: Optional[Dict[str, Any]] = None,
                   quality_level: str = "") -> Dict[str, Any]:
    """The full governed Design Bundle for a chosen blueprint — the build chain's input.

    Returns the Design Bundle document itself (the artifact Matrix Builder, GitPilot and
    DayPilot all consume), with ``governance.validation_status`` already stamped by the
    same verdict the CLI applies, so no consumer builds from an unvalidated design.
    """
    err = provider_guard()
    if err:
        return {"error": err}
    idea = _clean_idea(idea)
    if not idea:
        return {"error": "idea is required (non-empty)."}

    from .engine import DesignEngine
    from .validate import verdict

    bp = dict(blueprint or {})
    if not bp:
        bp, tier_quality = _blueprint_for(idea, candidate_id, references, constraints)
        quality_level = quality_level or tier_quality
    bp.setdefault("slug", _slug(idea))

    bundle = DesignEngine().design(idea, bp, references, quality_level or "standard")
    doc = bundle.to_dict()
    status, _report = verdict(doc)
    # Only the status is stamped: the document must stay valid against
    # design-bundle.schema.json, and the findings belong to /design/review.
    doc.setdefault("governance", {})["validation_status"] = status
    return doc


def review_handler(bundle: Optional[Dict[str, Any]] = None, target: str = "",
                   kind: str = "design-bundle") -> Dict[str, Any]:
    """Govern a Design Bundle: schema + design-rule verdict, as reviewable findings.

    The brain cannot approve itself — this runs the same checks Matrix Definitions
    enforce, so a consumer can block on a design before any code is written.
    """
    from .validate import verdict

    if not isinstance(bundle, dict) or not bundle:
        return {"error": "bundle is required (the Design Bundle document to review).",
                "findings": [], "suggestions": [], "score": 0, "status": "rejected"}

    status, report = verdict(bundle)
    findings = [
        {"severity": v.get("severity", "medium"), "area": v.get("rule_id", "design"),
         "note": v.get("message", ""), "rule_id": v.get("rule_id", "")}
        for v in report["violations"]
    ]
    findings += [
        {"severity": "critical", "area": "schema", "note": err, "rule_id": "SCHEMA"}
        for err in report["schema_errors"]
    ]
    return {
        "review_id": f"rev-{bundle.get('design_id') or _slug(target or 'bundle')}",
        "target": target or str(bundle.get("design_id") or bundle.get("project") or ""),
        "kind": kind,
        "status": status,
        "score": _score(report),
        "findings": findings,
        "suggestions": _suggestions(report),
        "schema_errors": report["schema_errors"],
        "rules_catalog": report["rules_catalog"],
        "summary": report["summary"],
    }


_SEVERITY_PENALTY = {"critical": 25, "high": 15, "medium": 7, "low": 3}


def _score(report: Dict[str, Any]) -> int:
    """A 0–100 design score derived from the violations — deterministic, not a guess."""
    penalty = 20 * len(report["schema_errors"])
    penalty += sum(_SEVERITY_PENALTY.get(v.get("severity", "medium"), 7) for v in report["violations"])
    return max(0, min(100, 100 - penalty))


def _suggestions(report: Dict[str, Any]) -> List[str]:
    """One actionable line per distinct rule that fired (the fix, not the complaint)."""
    from .rules import load_rules

    catalog = load_rules()
    seen, out = set(), []
    for v in report["violations"]:
        rid = v.get("rule_id", "")
        if rid in seen:
            continue
        seen.add(rid)
        title = (catalog.get(rid) or {}).get("title", "")
        out.append(f"{rid}: {title}" if title else v.get("message", ""))
    return out


def health() -> Dict[str, Any]:
    from . import __version__
    return {"status": "ok", "service": "matrix-designer", "version": __version__,
            "provider_ok": provider_guard() is None}


# ---- request models (module-level so FastAPI can resolve them under
#      `from __future__ import annotations`; only defined when pydantic is installed) ---
try:  # pragma: no cover - pydantic ships with the [service] extra
    from pydantic import BaseModel, Field

    class BlueprintsIn(BaseModel):
        idea: str = Field(..., min_length=1, max_length=MAX_IDEA_CHARS)
        references: Optional[List[Dict[str, str]]] = None
        constraints: Optional[Dict[str, Any]] = None

    class RefineIn(BaseModel):
        idea: str = Field(..., min_length=1, max_length=MAX_IDEA_CHARS)
        message: str = Field("", max_length=MAX_MESSAGE_CHARS)
        candidate_id: str = Field("standard", max_length=64)
        constraints: Optional[Dict[str, Any]] = None

    class BundleIn(BaseModel):
        idea: str = Field(..., min_length=1, max_length=MAX_IDEA_CHARS)
        candidate_id: str = Field("", max_length=64)
        blueprint: Optional[Dict[str, Any]] = None
        references: Optional[List[Dict[str, str]]] = None
        constraints: Optional[Dict[str, Any]] = None
        quality_level: str = Field("", max_length=32)

    class ReviewIn(BaseModel):
        bundle: Dict[str, Any]
        target: str = Field("", max_length=512)
        kind: str = Field("design-bundle", max_length=64)
except Exception:  # pragma: no cover - core install without the service extra
    BlueprintsIn = None  # type: ignore
    RefineIn = None  # type: ignore
    BundleIn = None  # type: ignore
    ReviewIn = None  # type: ignore


# ---- FastAPI wrapper (optional) ------------------------------------------------------
def build_app():  # pragma: no cover - exercised when fastapi is installed
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException
    except Exception as exc:
        raise RuntimeError("Install the service extra:  pip install 'matrix-designer[service]'") from exc

    app = FastAPI(title="Matrix Designer", version=health()["version"])

    # Optional CORS — only when an allow-list is configured (default: no CORS).
    cors = os.environ.get("MATRIX_DESIGNER_CORS_ORIGINS", "").strip()
    if cors:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=[o.strip() for o in cors.split(",") if o.strip()],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )

    # Optional API key — only enforced when MATRIX_DESIGNER_API_KEY is set (default: open).
    def require_key(
        authorization: Optional[str] = Header(default=None),
        x_api_key: Optional[str] = Header(default=None),
    ) -> None:
        expected = os.environ.get("MATRIX_DESIGNER_API_KEY", "").strip()
        if not expected:
            return  # auth disabled (internal deployment) — unchanged behaviour
        token = x_api_key or ""
        if not token and authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if token != expected:
            raise HTTPException(status_code=401, detail="invalid or missing API key")

    @app.get("/healthz")
    def _health() -> Dict[str, Any]:
        return health()

    @app.post("/design/blueprints")
    def _blueprints(body: BlueprintsIn, _: None = Depends(require_key)) -> Dict[str, Any]:
        return blueprints_handler(body.idea, body.references, body.constraints)

    @app.post("/design/refine")
    def _refine(body: RefineIn, _: None = Depends(require_key)) -> Dict[str, Any]:
        return refine_handler(body.idea, body.message, body.candidate_id, body.constraints)

    @app.post("/design/bundle")
    def _bundle(body: BundleIn, _: None = Depends(require_key)) -> Dict[str, Any]:
        return bundle_handler(body.idea, body.blueprint, body.candidate_id,
                              body.references, body.constraints, body.quality_level)

    @app.post("/design/review")
    def _review(body: ReviewIn, _: None = Depends(require_key)) -> Dict[str, Any]:
        return review_handler(body.bundle, body.target, body.kind)

    return app


def main() -> None:  # pragma: no cover
    import uvicorn  # type: ignore
    uvicorn.run(build_app(), host=DEFAULT_HOST, port=DEFAULT_PORT)


if __name__ == "__main__":  # pragma: no cover
    main()
