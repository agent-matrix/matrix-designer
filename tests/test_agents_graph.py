"""The LangGraph multi-agent brain: 3 tiered blueprints + orchestrator chat refinement."""
from matrix_designer.graph import design_blueprints, run_design, refine


def test_three_blueprints_simplest_to_hardest():
    out = design_blueprints("Build a Phaser/Vite platformer game on GitHub Pages")
    ids = [c["id"] for c in out["candidates"]]
    assert ids == ["minimal", "standard", "production"]
    n = {cid: len(out["details"][cid]["batches"]) for cid in ids}
    assert n["minimal"] < n["standard"] < n["production"]   # ramps up
    assert any(c["recommended"] for c in out["candidates"])  # standard is recommended
    assert not out["violations"]                              # governance passes
    std = out["details"]["standard"]
    for key in ("overview", "architecture", "batches", "file_plan", "matrix_rules"):
        assert std[key]                                       # dashboard sections populated


def test_every_batch_is_scoped():
    out = design_blueprints("A FastAPI service with a dashboard and audit log")
    for det in out["details"].values():
        for b in det["batches"]:
            assert b["allowed_files"] and b["acceptance_criteria"]


def test_orchestrator_chat_adds_a_batch():
    state = run_design("Phaser platformer game")
    before = len(state["details"]["standard"]["batches"])
    out = refine(state, "Please add a boss level", "standard")
    after = len(out["details"]["standard"]["batches"])
    assert after == before + 1
    assert "Boss" in out["details"]["standard"]["batches"][-1]["name"]
    assert out["reply"]
    assert out["chat_history"][-1]["role"] == "blueprint"
