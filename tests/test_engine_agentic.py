"""The agentic (LLM) output parser must never break the contract.

These exercise the parsing/merge path without needing an LLM: the deterministic backend
is the safety net, but the parser itself must tolerate messy model JSON (extra keys,
string-instead-of-list fields, prose around the JSON, missing ids).
"""
from matrix_designer.engine import DesignEngine, _batch_from_dict


def test_batch_from_dict_tolerates_extra_and_loose_fields():
    b = _batch_from_dict({
        "id": "batch-01",
        "name": "Bootstrap",
        "allowed_files": "src/main.ts",          # string instead of list
        "acceptance": ["builds"],
        "extra_unknown_key": "ignored",           # would have raised on Batch(**b)
    })
    assert b is not None
    assert b.id == "batch-01"
    assert b.allowed_files == ["src/main.ts"]     # coerced to a list
    assert b.depends_on == []                      # safe default


def test_batch_from_dict_rejects_missing_id():
    assert _batch_from_dict({"name": "no id"}) is None


def test_parse_agentic_output_extracts_json_from_prose():
    eng = DesignEngine(backend="off")
    raw = (
        "Sure! Here is the design:\n```json\n"
        '{"batch_roadmap": [{"id": "b1", "name": "Scaffold", '
        '"allowed_files": ["index.html"], "acceptance": ["page renders"], '
        '"weird": 123}], "acceptance": {"functional": ["app runs"]}}\n```\n'
        "Hope that helps."
    )
    bundle = eng._parse_agentic_output(raw, idea="a site", blueprint={"slug": "site", "stack": ["html"]},
                                       quality_level="standard")
    assert bundle is not None
    assert [b.id for b in bundle.batch_roadmap] == ["b1"]
    assert bundle.batch_roadmap[0].allowed_files == ["index.html"]


def test_parse_agentic_output_returns_none_without_json():
    eng = DesignEngine(backend="off")
    assert eng._parse_agentic_output("no json here", "i", {"slug": "x"}, "standard") is None
