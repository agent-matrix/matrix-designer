"""End-to-end: engine designs a bundle, it validates, and exports to Matrix Builder."""
import json
import os

from matrix_designer.engine import DesignEngine
from matrix_designer.exporter import to_mb_export
from matrix_designer.validate import verdict

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)


def test_game_design_is_approved_and_has_batches():
    eng = DesignEngine(backend="off")  # deterministic, no network
    bundle = eng.design(
        idea="A cinematic 8-episode side-scrolling arcade platformer for the web.",
        blueprint={"slug": "contract-quest", "stack": ["Phaser 3", "TypeScript", "Vite"], "rationale": "2D arcade"},
        quality_level="production",
    ).to_dict()
    assert bundle["domain"] == "web-game"
    assert len(bundle["batch_roadmap"]) >= 7
    status, report = verdict(bundle)
    # deterministic game pack must supply a visual target → not blocked by GAME-006
    assert status in ("approved", "needs-repair"), report
    assert all(b["allowed_files"] for b in bundle["batch_roadmap"])


def test_export_produces_mb_next_sequence():
    eng = DesignEngine(backend="off")
    bundle = eng.design("A FastAPI service with auth.", {"slug": "svc", "stack": ["FastAPI"]}).to_dict()
    exp = to_mb_export(bundle)
    assert exp["idea_request"]["design_mode"] == "design-first"
    assert len(exp["mb_next_sequence"]) == len(bundle["batch_roadmap"])
    assert exp["blueprint_overlay"]["generator_actions"][0].startswith("batch-")


def test_reference_example_bundle_validates():
    path = os.path.join(ROOT, "examples", "contract-quest", "design-bundle.json")
    with open(path, encoding="utf-8") as fh:
        bundle = json.load(fh)
    status, report = verdict(bundle)
    assert status == "approved", report
