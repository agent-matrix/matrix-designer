"""Producer contract and diagram-to-design governance regression coverage."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from matrix_designer.cli import main
from matrix_designer.dmind import diagram_bundle_handler, diagram_handler, from_bundle, from_outline
from matrix_designer.dmind_contract import validate_diagram
from matrix_designer.models import sha256_digest
from matrix_designer.service import build_app, bundle_handler
from matrix_designer.validate import verdict


def test_nested_outline_and_flow_loops_are_distinct():
    graph = from_outline("Order processing", "Receive\n  Validate\n  Reserve\nCharge")
    assert graph["edges"][1]["source"] == "n1"
    graph["edges"].append({"id": "feedback", "source": "n2", "target": "n1", "kind": "flow"})
    assert validate_diagram(graph) == graph
    graph["edges"][-1]["kind"] = "branch"
    with pytest.raises(ValueError):
        validate_diagram(graph)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda g: g["nodes"].append(deepcopy(g["nodes"][0])),
        lambda g: g["edges"][0].update(target="missing"),
        lambda g: g.update(schema_version="dmind/v2"),
        lambda g: g["nodes"][0].update(position={"x": float("nan"), "y": 0}),
        lambda g: g["nodes"][0].update(position={"x": True, "y": 0}),
        lambda g: g["edges"].append(deepcopy(g["edges"][0])),
        lambda g: g["nodes"][0].update(label=""),
        lambda g: g.update(kind=[]),
        lambda g: g["edges"][0].update(source=[]),
        lambda g: g["edges"][0].update(kind={}),
    ],
)
def test_malformed_inputs_refused(mutate):
    graph = from_outline("Topic", "Child")
    mutate(graph)
    with pytest.raises(ValueError):
        validate_diagram(graph)


def test_bounded_sources_are_rejected_without_truncation():
    with pytest.raises(ValueError):
        from_outline("Topic", "x\n" * 1000)
    with pytest.raises(ValueError):
        from_outline("Topic", "x" * 501)
    with pytest.raises(ValueError):
        diagram_handler("Topic", "x\n" * 2500, use_designer=True)


def test_bundle_visualization_preserves_original():
    bundle = bundle_handler("A FastAPI web application for managing inventory", candidate_id="standard")
    before = deepcopy(bundle)
    graph = from_bundle(bundle)
    assert graph["metadata"]["design_bundle"] == before == bundle
    assert len(graph["nodes"]) == len(bundle["batch_roadmap"]) + 1
    assert any(e["kind"] == "dependency" for e in graph["edges"])


def test_handoff_retains_edited_graph_and_recomputes_verdict_and_digest():
    graph = from_outline("Inventory system", "API\n  Validation\nDatabase", "system")
    graph["nodes"][1]["notes"] = "retry at most 3 times; </script><script>alert(1)</script>"
    graph["metadata"] = {"design_bundle": {"governance": {"validation_status": "approved"}}}
    out = diagram_bundle_handler(graph)
    bundle = out["bundle"]
    assert bundle["governance"]["validation_status"] == verdict(bundle)[0]
    reference = bundle["source"]["references"][0]
    assert "UNTRUSTED" in reference["note"] and "retry at most 3" in reference["note"]
    body = deepcopy(bundle)
    digest = body["provenance"].pop("design_digest")
    assert digest == sha256_digest(json.dumps(body, sort_keys=True, ensure_ascii=False))
    assert out["source_diagram_id"] == graph["id"]
    assert out["source_digest"].startswith("sha256:")


def test_http_api_key_errors_and_provider_guard(monkeypatch):
    monkeypatch.setenv("MATRIX_DESIGNER_API_KEY", "test-key")
    c = TestClient(build_app())
    assert c.post("/design/diagrams", json={"topic": "Topic"}).status_code == 401
    headers = {"X-API-Key": "test-key"}
    assert c.post("/design/diagrams", json={"topic": "Topic", "kind": "bad"}, headers=headers).status_code == 422
    graph = c.post("/design/diagrams", json={"topic": "Topic", "content": "Child"}, headers=headers).json()["diagram"]
    graph["nodes"][0]["label"] = ""
    assert c.post("/design/diagrams/bundle", json={"diagram": graph}, headers=headers).status_code == 422
    monkeypatch.setenv("MATRIX_DESIGNER_ALLOWED_PROVIDERS", "ollabridge")
    monkeypatch.setenv("MATRIX_DESIGNER_PROVIDER", "blocked")
    assert c.post("/design/diagrams", json={"topic": "Topic", "use_designer": True}, headers=headers).status_code == 400
    assert c.post("/design/diagrams", json={"topic": "Topic"}, headers=headers).status_code == 200


def test_cli_and_packaged_fixture(tmp_path):
    path = tmp_path / "diagram.json"
    assert main(["diagram", "--topic", "Inventory system", "-o", str(path)]) == 0
    assert validate_diagram(json.loads(path.read_text()))["title"] == "Inventory system"
    fixture = json.loads((Path(__file__).parents[1] / "examples/dmind/order-system.dmind.json").read_text())
    assert validate_diagram(fixture) == fixture
