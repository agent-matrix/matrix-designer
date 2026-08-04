"""Provider-side contract: what a control plane (DayPilot) needs from this service.

DayPilot drives the whole chain over HTTP — pick a blueprint, design the bundle,
govern it, then hand each batch to GitPilot to build. These tests pin the *shape* of
that chain so a change here that would break the consumer fails here first, rather
than silently 404-ing or dropping a field in production.

The mirrored consumer test lives in DayPilot (`tests/test_matrix_designer.py`); the
golden payloads on both sides describe the same responses.
"""

import pytest

from matrix_designer.service import (
    blueprints_handler,
    bundle_handler,
    refine_handler,
    review_handler,
)

IDEA = "a task manager web app for small teams"


# ── The chain, endpoint by endpoint ─────────────────────────────────────────

def test_blueprints_offer_three_choosable_plans():
    """Step 1: the user picks a plan, so each candidate must be presentable."""
    out = blueprints_handler(IDEA)
    assert [c["id"] for c in out["candidates"]] == ["minimal", "standard", "production"]
    for c in out["candidates"]:
        assert c["title"] and c["summary"] and c["difficulty"] and c["estimate"]
        assert isinstance(c["stack"], list)
    assert sum(1 for c in out["candidates"] if c["recommended"]) == 1


def test_each_candidate_carries_a_dependency_ordered_roadmap():
    """DayPilot schedules one task per batch, so batches need ids and real deps."""
    details = blueprints_handler(IDEA)["details"]
    for candidate_id, det in details.items():
        batches = det["batches"]
        assert batches, f"{candidate_id} has no batches"
        ids = {b["id"] for b in batches}
        for b in batches:
            assert b["id"] and b["name"]
            # A dependency must name a batch in the same roadmap — otherwise the
            # consumer cannot decide what is blocked and what can start now.
            assert set(b.get("depends_on") or []) <= ids
        assert any(not b.get("depends_on") for b in batches), "nothing could start first"


def test_bundle_is_the_full_governed_design_document():
    """Step 2: the chosen plan becomes the artifact the build chain consumes."""
    doc = bundle_handler(IDEA, candidate_id="standard")
    for key in ("schema_version", "design_id", "project", "framework_decision",
                "batch_roadmap", "acceptance", "provenance", "governance"):
        assert key in doc, f"missing {key}"
    # Already governed on the way out: nobody builds from an unvalidated design.
    assert doc["governance"]["validation_status"] in {"approved", "needs-repair", "rejected"}
    assert doc["provenance"]["design_digest"].startswith("sha256:")
    for batch in doc["batch_roadmap"]:
        assert batch["id"] and batch["allowed_files"] and batch["acceptance"]


def test_the_chosen_candidate_decides_the_stack_and_the_depth():
    """Choosing a plan must actually change the design, or the choice is theatre."""
    minimal = bundle_handler(IDEA, candidate_id="minimal")
    production = bundle_handler(IDEA, candidate_id="production")
    assert minimal["quality_level"] != production["quality_level"]
    assert len(minimal["batch_roadmap"]) <= len(production["batch_roadmap"])
    # The candidate's stack reaches the framework decision rather than being re-guessed.
    assert bundle_handler(IDEA, candidate_id="standard")["framework_decision"]["stack"]


def test_an_explicit_blueprint_still_wins():
    """A caller that already knows its stack skips candidate selection entirely."""
    doc = bundle_handler(IDEA, blueprint={"slug": "widget", "stack": ["Go", "HTMX"]})
    assert doc["framework_decision"]["stack"] == ["Go", "HTMX"]
    assert doc["project"] == "widget"


def test_review_returns_actionable_findings_not_just_a_boolean():
    """Step 3: governance the consumer can show a human and block on.

    A roadmap whose batches wait on each other is well-formed but unbuildable —
    exactly the class of defect a human would miss and a reviewer must catch.
    """
    doc = bundle_handler(IDEA, candidate_id="standard")
    first, second = doc["batch_roadmap"][0], doc["batch_roadmap"][1]
    first["depends_on"] = [second["id"]]
    second["depends_on"] = [first["id"]]

    review = review_handler(doc, target="task-manager")
    assert review["status"] == "needs-repair"
    assert 0 <= review["score"] < 100
    assert "DESIGN-005" in {f["rule_id"] for f in review["findings"]}
    assert review["suggestions"], "a finding without a fix is not actionable"
    for finding in review["findings"]:
        assert finding["severity"] and finding["area"] and finding["note"]


def test_a_malformed_bundle_is_rejected_with_the_reason():
    """Nothing downstream should build from a document that isn't a Design Bundle."""
    review = review_handler({"design_id": "dsn-x", "batch_roadmap": []}, target="x")
    assert review["status"] == "rejected"
    assert review["schema_errors"]
    assert any(f["area"] == "schema" for f in review["findings"])


def test_a_clean_bundle_reviews_clean():
    doc = bundle_handler(IDEA, candidate_id="standard")
    review = review_handler(doc)
    assert review["status"] == "approved"
    assert review["score"] == 100 and review["findings"] == []


def test_review_without_a_bundle_is_refused_not_invented():
    review = review_handler({})
    assert review["error"] and review["findings"] == []


def test_empty_idea_is_refused_on_every_entry_point():
    assert bundle_handler("   ")["error"]
    assert blueprints_handler("")["error"]
    assert refine_handler("", "add auth")["error"]


# ── Over HTTP, on the paths the consumer actually calls ─────────────────────

def test_the_four_endpoints_exist_on_the_paths_consumers_use():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from matrix_designer.service import build_app

    client = TestClient(build_app())
    assert client.get("/healthz").status_code == 200
    assert client.post("/design/blueprints", json={"idea": IDEA}).status_code == 200
    assert client.post("/design/refine", json={"idea": IDEA, "message": "add auth"}).status_code == 200

    bundle = client.post("/design/bundle", json={"idea": IDEA, "candidate_id": "standard"})
    assert bundle.status_code == 200
    doc = bundle.json()
    assert doc["batch_roadmap"]

    review = client.post("/design/review", json={"bundle": doc, "target": "task-manager"})
    assert review.status_code == 200
    assert review.json()["status"] == "approved"


def test_the_api_key_guard_covers_the_new_endpoints(monkeypatch):
    """New surface must not be a hole in an existing deployment's auth."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from matrix_designer.service import build_app

    monkeypatch.setenv("MATRIX_DESIGNER_API_KEY", "s3cret")
    client = TestClient(build_app())
    for path, body in (("/design/bundle", {"idea": IDEA}),
                       ("/design/review", {"bundle": {"design_id": "d"}})):
        assert client.post(path, json=body).status_code == 401
        assert client.post(path, json=body, headers={"X-API-Key": "s3cret"}).status_code == 200
    # Health stays open so probes keep working.
    assert client.get("/healthz").status_code == 200
