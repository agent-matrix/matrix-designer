"""Matrix Designer HTTP service — the brain over HTTP, for Matrix Builder's control plane.

Exposes the two tools the Details page needs (`generate_blueprints`, `refine_design`)
as JSON endpoints, alongside the stdio MCP server (`mcp_server.py`). The core handlers
are plain functions (testable without FastAPI); ``build_app()`` wraps them in a FastAPI
app when the extra is installed.

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
except Exception:  # pragma: no cover - core install without the service extra
    BlueprintsIn = None  # type: ignore
    RefineIn = None  # type: ignore


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

    return app


def main() -> None:  # pragma: no cover
    import uvicorn  # type: ignore
    uvicorn.run(build_app(), host=DEFAULT_HOST, port=DEFAULT_PORT)


if __name__ == "__main__":  # pragma: no cover
    main()
