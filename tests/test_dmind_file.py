"""The .dmind file (B1): round trip, bounds, version messages and CLI use."""

import json
from pathlib import Path

import pytest

from matrix_designer.cli import main
from matrix_designer.dmind_file import MIME, detect_form, read_dmind, write_dmind

FIXTURE = Path(__file__).parents[1] / "examples/dmind/order-system.dmind.json"


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_round_trip_is_lossless_and_readable():
    doc = fixture()
    doc["future"] = {"kept": True}
    doc["nodes"][0]["icon"] = "star"
    data = write_dmind(doc)
    assert data.startswith(b'{\n  "schema_version"') and data.endswith(b"}\n")
    assert read_dmind(data) == doc  # unknown fields survive
    assert read_dmind(write_dmind(read_dmind(data))) == doc
    assert MIME == "application/vnd.dmind+json"


def test_byte_order_mark_and_unicode_are_accepted():
    doc = fixture()
    doc["title"] = "订单 🚀"
    data = b"\xef\xbb\xbf" + json.dumps(doc, ensure_ascii=False).encode("utf-8")
    assert read_dmind(data)["title"] == "订单 🚀"


@pytest.mark.parametrize(
    ("data", "fragment"),
    [
        (b"\xff\xfe{", "not a dmind|UTF-8"),
        (b'{"schema_version": ', "not valid JSON"),
        (b"hello", "should be JSON"),
        (b'{"schema_version":"dmind/v2"}', "dmind/v2"),
        (b"PK\x03\x04", "ZIP"),
        (b"x" * 2_000_001, "2 MB"),
        (b'{"schema_version":"dmind/v1"}', "invalid diagram"),
    ],
)
def test_bad_files_are_refused_with_a_reason(data, fragment):
    with pytest.raises(ValueError, match=fragment):
        read_dmind(data)


def test_detect_form():
    assert detect_form(b'  {"a":1}') == "json"
    assert detect_form(b"\xef\xbb\xbf{") == "json"
    assert detect_form(b"PK\x03\x04") == "zip"
    assert detect_form(b"") == "unknown"


def test_cli_writes_and_reads_dmind_files(tmp_path, capsys):
    path = tmp_path / "inventory.dmind"
    assert main(["diagram", "--topic", "Inventory system", "-o", str(path)]) == 0
    assert path.read_bytes().endswith(b"}\n")
    doc = read_dmind(path.read_bytes())
    assert doc["title"] == "Inventory system"
    out = tmp_path / "proposal.json"
    assert main(["diagram-bundle", str(path), "-o", str(out)]) == 0
    assert json.loads(out.read_text())["source_diagram_id"] == doc["id"]
    bad = tmp_path / "bad.dmind"
    bad.write_text("not json")
    assert main(["diagram-bundle", str(bad)]) == 2
    assert "should be JSON" in capsys.readouterr().err
