"""The HTTP service handlers: 3 blueprints, refinement, and the watsonx-only guard."""

import pytest

from matrix_designer.service import blueprints_handler, refine_handler, health, provider_guard


def test_blueprints_handler_returns_three():
    out = blueprints_handler("Build a Phaser/Vite platformer on GitHub Pages")
    assert [c["id"] for c in out["candidates"]] == ["minimal", "standard", "production"]
    assert set(out["details"]) == {"minimal", "standard", "production"}


def test_refine_handler_adds_a_batch():
    out = refine_handler("Phaser platformer game", "add a boss level", "standard")
    assert "Boss" in out["details"]["standard"]["batches"][-1]["name"]
    assert out["reply"]


def test_provider_agnostic_by_default(monkeypatch):
    # Default: ANY provider is allowed (OllaBridge or otherwise) — no restriction.
    monkeypatch.setenv("MATRIX_DESIGNER_PROVIDER", "openai")
    assert provider_guard() is None
    assert len(blueprints_handler("anything")["candidates"]) == 3
    # An operator MAY opt into an allow-list.
    monkeypatch.setenv("MATRIX_DESIGNER_ALLOWED_PROVIDERS", "ollabridge,watsonx")
    assert provider_guard() is not None                  # openai not in the list
    monkeypatch.setenv("MATRIX_DESIGNER_PROVIDER", "ollabridge")
    assert provider_guard() is None                      # now allowed


def test_health():
    h = health()
    assert h["status"] == "ok" and h["service"] == "matrix-designer"


def test_fastapi_app_if_available():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from matrix_designer.service import build_app
    client = TestClient(build_app())
    assert client.get("/healthz").json()["status"] == "ok"
    r = client.post("/design/blueprints", json={"idea": "A FastAPI dashboard"})
    assert len(r.json()["candidates"]) == 3
