"""The HTTP service handlers: 3 blueprints, refinement, and the watsonx-only guard."""
import os

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


def test_watsonx_only_guard(monkeypatch):
    assert provider_guard() is None                      # default: deterministic, allowed
    monkeypatch.setenv("MATRIX_DESIGNER_PROVIDER", "openai")
    assert provider_guard() is not None                  # non-watsonx refused
    out = blueprints_handler("anything")
    assert out["error"] and not out["candidates"]
    monkeypatch.setenv("MATRIX_DESIGNER_PROVIDER", "watsonx")
    assert provider_guard() is None                      # watsonx approved


def test_health():
    h = health()
    assert h["status"] == "ok" and h["service"] == "matrix-designer"


def test_fastapi_app_if_available():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from matrix_designer.service import build_app
    client = TestClient(build_app())
    assert client.get("/healthz").json()["status"] == "ok"
    r = client.post("/design/blueprints", json={"idea": "A FastAPI dashboard"})
    assert len(r.json()["candidates"]) == 3
