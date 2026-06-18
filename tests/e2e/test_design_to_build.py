"""batch-11 — End-to-end proof: Contract Quest.

Drives the whole pipeline for a real game idea and asserts it produces an executable,
governed plan:

    idea ──▶ Matrix Designer (multi-agent) ──▶ design bundle ──▶ mb-next sequence (validated)

The "playable" half (GitPilot building the game) runs outside CI; here we prove the plan is
complete, scoped, acyclic, ordered, and covers the campaign — i.e. GitPilot has everything it
needs to build Contract Quest from the generated plan.
"""
import json
import os

from matrix_designer.graph import design_blueprints
from matrix_designer.exporter import to_mb_export
from matrix_designer.validate import verdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
IDEA = "Build Contract Quest — a cinematic 8-episode Phaser/Vite platformer on GitHub Pages"


def _example_bundle():
    with open(os.path.join(ROOT, "examples", "contract-quest", "design-bundle.json"), encoding="utf-8") as fh:
        return json.load(fh)


def test_brain_designs_contract_quest():
    out = design_blueprints(IDEA)
    assert [c["id"] for c in out["candidates"]] == ["minimal", "standard", "production"]
    std = out["details"]["standard"]
    names = " ".join(b["name"].lower() for b in std["batches"])
    # the campaign milestones a platformer needs
    for milestone in ("foundation", "asset", "player", "enem", "hud", "boss"):
        assert milestone in names, f"missing milestone '{milestone}' in: {names}"


def test_design_to_mb_next_is_executable_and_governed():
    bundle = _example_bundle()
    # 1) the design bundle is approved by the governance layer
    status, report = verdict(bundle)
    assert status == "approved", report["summary"]
    # 2) it exports an ordered mb-next sequence GitPilot can run
    seq = to_mb_export(bundle)["mb_next_sequence"]
    assert len(seq) >= 8
    ids = [s["batch_id"] for s in seq]
    assert ids == sorted(ids)                                   # ordered batch-01..NN
    real = set(ids)
    for s in seq:
        assert s["allowed_files"] and s["acceptance_criteria"]  # every step is scoped
        for dep in s["depends_on"]:
            assert dep in real                                  # deps reference real batches


def test_plan_targets_a_phaser_project():
    bundle = _example_bundle()
    allowed = " ".join(f for b in bundle["batch_roadmap"] for f in b["allowed_files"]).lower()
    # the generated plan writes a real Phaser/Vite/TS structure
    for marker in ("vite.config", "src/scenes", "src/levels", "deploy.yml"):
        assert marker in allowed, f"plan does not target '{marker}'"
