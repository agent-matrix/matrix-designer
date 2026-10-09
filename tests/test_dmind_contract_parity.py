"""dmind/v1 contract parity: validator, outline parser and JSON Schema share one corpus.

The same ``contract-cases.json`` runs in DayPilot (Python validator and TypeScript editor)
and here. A rule the JSON Schema can express must be rejected by the schema too; rules it
cannot express (references, uniqueness, forest shape, byte size) are flagged in the corpus.
"""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from matrix_designer.dmind import from_outline
from matrix_designer.dmind_contract import validate_diagram

ROOT = Path(__file__).parents[1]
SCHEMA = ROOT / "src/matrix_designer/_data/schemas/dmind.schema.json"
FIXTURE = ROOT / "examples/dmind/order-system.dmind.json"
CASES = ROOT / "examples/dmind/contract-cases.json"

# Canonical-JSON digests of the shared contract. DayPilot pins the same values; change the
# schema, fixture or corpus in BOTH repositories together and update both pins.
PINNED = {
    "schema": "a72d842dec9d606474f11acaeb2afcaecb252d88e68ceb1700a8dca3d0778f98",
    "fixture": "be2c8afa7978a29c32693fb7252666563a77d6edd8d2b81934fd45d9b120e095",
    "cases": "bbba4b6458a90b0053a61e8743a37a4a320496d3ec73cfc09e8b4cc2a2d46b50",
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    canonical = json.dumps(load(path), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve(value):
    if isinstance(value, dict) and "$repeat" in value:
        text, times = value["$repeat"]
        return text * times
    return value


def holder(doc, path):
    *keys, last = path.split(".")
    cur = doc
    for key in keys:
        cur = cur[int(key)] if isinstance(cur, list) else cur[key]
    return cur, (int(last) if isinstance(cur, list) else last)


def apply_ops(doc, ops):
    for op in ops:
        if "set" in op:
            cur, key = holder(doc, op["set"])
            cur[key] = deepcopy(resolve(op["value"]))
        elif "delete" in op:
            cur, key = holder(doc, op["delete"])
            del cur[key]  # list index or dict key
        elif "append" in op:
            cur, key = holder(doc, op["append"])
            cur[key].append(deepcopy(resolve(op["value"])))
        elif "grow" in op:
            items, i = doc[op["grow"]], 0
            while len(items) < op["to"]:
                items.append(
                    {"id": f"g{i}", "label": f"g{i}"}
                    if op["grow"] == "nodes"
                    else {"id": f"g{i}", "source": "root", "target": "root", "kind": "relationship"}
                )
                i += 1
        else:  # pragma: no cover - guards corpus typos
            raise AssertionError(f"unknown op {op}")
    return doc


corpus = load(CASES)
schema = Draft202012Validator(load(SCHEMA))


def case_id(case):
    return case["name"]


def test_contract_files_match_the_pinned_digests():
    actual = {"schema": digest(SCHEMA), "fixture": digest(FIXTURE), "cases": digest(CASES)}
    assert actual == PINNED, (
        "dmind/v1 contract changed. Update schema, fixture and corpus in DayPilot AND "
        "Matrix Designer together, then update the pinned digests in both test suites."
    )


def test_schema_itself_is_valid_and_accepts_the_golden_fixture():
    Draft202012Validator.check_schema(load(SCHEMA))
    fixture = load(FIXTURE)
    assert schema.is_valid(fixture)
    assert validate_diagram(fixture) == fixture


@pytest.mark.parametrize("case", corpus["valid"], ids=case_id)
def test_valid_cases_pass_validator_and_schema(case):
    doc = apply_ops(load(FIXTURE), case["ops"])
    assert validate_diagram(doc) == doc  # accepted, unknown fields retained
    assert schema.is_valid(doc), [e.message for e in schema.iter_errors(doc)][:3]


@pytest.mark.parametrize("case", corpus["invalid"], ids=case_id)
def test_invalid_cases_fail_validator_and_where_expressible_schema(case):
    doc = apply_ops(load(FIXTURE), case["ops"])
    with pytest.raises(ValueError):
        validate_diagram(doc)
    if case["schema_rejects"]:
        assert not schema.is_valid(doc), "the JSON Schema should reject: " + case["name"]


@pytest.mark.parametrize("case", corpus["outlines"], ids=case_id)
def test_outline_parser_matches_the_shared_expectations(case):
    doc = from_outline(case["topic"], case["content"], case["kind"])
    index = {n["id"]: i for i, n in enumerate(doc["nodes"])}
    assert [n["label"] for n in doc["nodes"]] == case["nodes"]
    assert [[index[e["source"]], index[e["target"]], e["kind"]] for e in doc["edges"]] == case["edges"]
    assert schema.is_valid(doc)


@pytest.mark.parametrize("case", corpus["invalid_outlines"], ids=case_id)
def test_outline_parser_rejects_instead_of_truncating(case):
    with pytest.raises(ValueError):
        from_outline(resolve(case["topic"]), resolve(case["content"]), case["kind"])
