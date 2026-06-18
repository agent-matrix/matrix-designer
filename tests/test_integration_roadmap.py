"""The integration roadmap is itself a governed, approved Design Bundle."""
import json
import os

from matrix_designer.exporter import to_mb_export
from matrix_designer.validate import verdict

ROOT = os.path.dirname(os.path.dirname(__file__))
BUNDLE = os.path.join(ROOT, "examples", "matrix-builder-integration", "design-bundle.json")


def _load():
    with open(BUNDLE, encoding="utf-8") as fh:
        return json.load(fh)


def test_integration_bundle_is_approved():
    status, report = verdict(_load())
    assert status == "approved", report


def test_roadmap_exports_an_mb_next_sequence():
    bundle = _load()
    exp = to_mb_export(bundle)
    seq = exp["mb_next_sequence"]
    assert len(seq) == len(bundle["batch_roadmap"]) >= 12
    # every step is scoped and dependency-ordered
    ids = {b["id"] for b in bundle["batch_roadmap"]}
    for b in bundle["batch_roadmap"]:
        assert b["allowed_files"] and b["acceptance"]
        for dep in b.get("depends_on", []):
            assert dep in ids


def test_client_first_plan_is_approved():
    """The API-optional re-plan is itself a governed, approved bundle."""
    path = os.path.join(ROOT, "examples", "client-first-workspace", "design-bundle.json")
    with open(path, encoding="utf-8") as fh:
        bundle = json.load(fh)
    status, report = verdict(bundle)
    assert status == "approved", report["summary"]
    # the client engine (batch-01) is the primary path; the server bridge (batch-05) is optional
    names = " ".join(b["name"].lower() for b in bundle["batch_roadmap"])
    assert "browser blueprint-engine" in names
    assert "optional server bridge" in names
