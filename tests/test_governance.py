"""batch-08 — Matrix Definitions design rules: the validator enforces the catalog."""
import json
import os

from matrix_designer.rules import load_rules, rule_ids
from matrix_designer.validate import verdict

ROOT = os.path.dirname(os.path.dirname(__file__))


def _good_bundle():
    with open(os.path.join(ROOT, "examples", "contract-quest", "design-bundle.json"), encoding="utf-8") as fh:
        return json.load(fh)


def test_rule_catalog_loads_all_families():
    ids = rule_ids()
    assert any(r.startswith("DESIGN-") for r in ids)
    assert any(r.startswith("GAME-") for r in ids)
    assert any(r.startswith("APP-") for r in ids)
    assert load_rules()["DESIGN-001"]["severity"] == "high"


def test_unscoped_batch_is_rejected():
    bundle = _good_bundle()
    bundle["batch_roadmap"][0]["allowed_files"] = []  # unscoped → schema + DESIGN-001
    status, report = verdict(bundle)
    assert status == "rejected", report["summary"]


def test_game_without_visual_acceptance_needs_repair():
    bundle = _good_bundle()
    bundle.pop("visual_target", None)
    bundle["acceptance"]["visual"] = []
    status, report = verdict(bundle)
    assert status == "needs-repair"
    assert any(v["rule_id"] == "GAME-006" for v in report["violations"])


def test_dependency_cycle_is_caught():
    bundle = _good_bundle()
    b = bundle["batch_roadmap"]
    b[0]["depends_on"] = [b[1]["id"]]
    b[1]["depends_on"] = [b[0]["id"]]  # cycle
    status, report = verdict(bundle)
    assert status == "needs-repair"
    assert any(v["rule_id"] == "DESIGN-005" for v in report["violations"])


def test_good_bundle_still_approved():
    status, report = verdict(_good_bundle())
    assert status == "approved", report["summary"]
    assert "DESIGN-001" in report["rules_catalog"]
