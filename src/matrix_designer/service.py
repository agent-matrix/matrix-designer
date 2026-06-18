"""Matrix Designer HTTP service — the brain over HTTP, for Matrix Builder's control plane.

Exposes the two tools the Details page needs (`generate_blueprints`, `refine_design`)
as JSON endpoints, alongside the stdio MCP server (`mcp_server.py`). The core handlers
are plain functions (testable without FastAPI); ``build_app()`` wraps them in a FastAPI
app when the extra is installed.

    pip install "matrix-designer[service]"
    python -m matrix_designer.service           # uvicorn on :8077

Governance: watsonx-only. If a provider is explicitly configured it must be watsonx; with
no provider the deterministic runner answers, so the service never blocks and never calls
an unapproved model.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .graph import design_blueprints, refine, run_design

DEFAULT_PORT = int(os.environ.get("MATRIX_DESIGNER_PORT", "8077"))
APPROVED_PROVIDERS = {"watsonx", "", "none"}


def provider_guard() -> Optional[str]:
    """Return an error string if a non-approved LLM provider is configured, else None."""
    provider = os.environ.get("MATRIX_DESIGNER_PROVIDER", os.environ.get("GITPILOT_PROVIDER", "")).lower()
    if provider not in APPROVED_PROVIDERS:
        return f"provider '{provider}' is not approved (watsonx-only). Set MATRIX_DESIGNER_PROVIDER=watsonx."
    return None


# ---- core handlers (no web framework required) ---------------------------------------
def blueprints_handler(idea: str, references: Optional[List[Dict[str, str]]] = None,
                       constraints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    err = provider_guard()
    if err:
        return {"error": err, "candidates": [], "details": {}}
    out = design_blueprints(idea, references, constraints)
    out.pop("_state", None)
    return out


def refine_handler(idea: str, message: str, candidate_id: str = "standard",
                   constraints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    err = provider_guard()
    if err:
        return {"error": err, "reply": err, "details": {}, "candidates": []}
    state = run_design(idea, None, constraints)
    out = refine(state, message, candidate_id)
    out.pop("_state", None)
    return out


def health() -> Dict[str, Any]:
    from . import __version__
    return {"status": "ok", "service": "matrix-designer", "version": __version__,
            "provider_ok": provider_guard() is None}


# ---- FastAPI wrapper (optional) ------------------------------------------------------
def build_app():  # pragma: no cover - exercised when fastapi is installed
    try:
        from fastapi import Body, FastAPI
    except Exception as exc:
        raise RuntimeError("Install the service extra:  pip install 'matrix-designer[service]'") from exc

    app = FastAPI(title="Matrix Designer", version=health()["version"])

    @app.get("/healthz")
    def _health() -> Dict[str, Any]:
        return health()

    @app.post("/design/blueprints")
    def _blueprints(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        return blueprints_handler(payload.get("idea", ""), payload.get("references"), payload.get("constraints"))

    @app.post("/design/refine")
    def _refine(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        return refine_handler(
            payload.get("idea", ""), payload.get("message", ""),
            payload.get("candidate_id", "standard"), payload.get("constraints"),
        )

    return app


def main() -> None:  # pragma: no cover
    import uvicorn  # type: ignore
    uvicorn.run(build_app(), host="0.0.0.0", port=DEFAULT_PORT)


if __name__ == "__main__":  # pragma: no cover
    main()
