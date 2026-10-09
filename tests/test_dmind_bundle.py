"""The .dmind bundle (B5): shared archive corpus, determinism, tampering, fuzzing and the CLI."""

import hashlib
import json
import random
import zlib
from pathlib import Path

import pytest

from matrix_designer import dmind_bundle as b
from matrix_designer.cli import main
from matrix_designer.dmind import from_outline
from matrix_designer.dmind_file import read_dmind

ROOT = Path(__file__).parents[1]
CASES = ROOT / "examples/dmind/archive-cases.json"
# Canonical-JSON digest of the shared archive corpus. DayPilot pins the same value; regenerate the
# file with tests/ui/gen-archive-corpus.mjs there and update both pins together.
PINNED_CORPUS = "7821afee40c47f81788c3703597c07bea277e2142341c408cbd76ab398e6da5d"

corpus = json.loads(CASES.read_text())
PNG = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 1, 0, 0, 0, 1, 8, 6, 0, 0, 0, 31, 21, 196, 137])
PDF = b"%PDF-1.4\n%fake body\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def limits(case):
    raw = case.get("limits")
    if not raw:
        return b.BUNDLE_LIMITS
    return b.ZipLimits(raw["maxEntries"], raw["maxEntryBytes"], raw["maxTotalBytes"], raw["maxRatio"])


def test_corpus_is_the_pinned_shared_file():
    canonical = json.dumps(corpus, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert hashlib.sha256(canonical.encode()).hexdigest() == PINNED_CORPUS, (
        "archive-cases.json changed: regenerate it in DayPilot, copy it here, and update both pins"
    )
    assert b.BUNDLE_LIMITS == b.ZipLimits(**{
        "max_entries": corpus["limits"]["maxEntries"], "max_entry_bytes": corpus["limits"]["maxEntryBytes"],
        "max_total_bytes": corpus["limits"]["maxTotalBytes"], "max_ratio": corpus["limits"]["maxRatio"],
    })


@pytest.mark.parametrize("case", corpus["zip"]["valid"], ids=lambda c: c["name"])
def test_valid_archives_open_with_the_same_contents(case):
    out = b.read_zip(bytes.fromhex(case["hex"]))
    assert {name: sha(data) for name, data in out.items()} == case["entries"]


@pytest.mark.parametrize("case", corpus["zip"]["refused"], ids=lambda c: c["name"])
def test_hostile_archives_are_refused(case):
    with pytest.raises(b.BundleError):
        b.read_zip(bytes.fromhex(case["hex"]), limits(case))


@pytest.mark.parametrize("case", corpus["bundle"]["refused"], ids=lambda c: c["name"])
def test_tampered_bundles_are_refused(case):
    with pytest.raises(b.BundleError):
        b.unpack_bundle(bytes.fromhex(case["hex"]))


def test_the_genuine_bundle_opens_with_its_attachments():
    case = corpus["bundle"]["valid"][0]
    unpacked = b.unpack_bundle(bytes.fromhex(case["hex"]))
    assert {ref: a.type for ref, a in unpacked.assets.items()} == case["assets"]
    assert unpacked.warnings == []
    assert unpacked.document["title"] == "Spec"
    expected = (json.dumps(unpacked.document, indent=2, ensure_ascii=False) + "\n").encode()
    assert sha(expected) == case["document_sha256"]


@pytest.mark.parametrize("case", corpus["writer"], ids=lambda c: c["name"])
def test_writer_output_is_byte_identical_to_the_typescript_writer(case):
    out = b.write_zip([(e["name"], e["text"].encode()) for e in case["entries"]])
    assert sha(out) == case["sha256"]


def test_repacking_the_genuine_bundle_reproduces_it_exactly():
    case = corpus["bundle"]["valid"][0]
    original = bytes.fromhex(case["hex"])
    u = b.unpack_bundle(original)
    assert b.pack_bundle(u.document, u.assets) == original  # TS wrote it; Python writes the same bytes


def test_round_trip_with_new_attachments_and_stable_order():
    doc = from_outline("Spec", "Design\nBuild", "mindmap")
    assets = {}
    for node, name, data in (("n1", "sketch.png", PNG), ("n2", "brief.pdf", PDF)):
        ref = "sha256:" + sha(data)
        entry = {"asset": ref, "name": name, "type": b.sniff_type(data, name), "bytes": len(data)}
        next(n for n in doc["nodes"] if n["id"] == node).setdefault("metadata", {})["attachments"] = [entry]
        assets[ref] = b.Asset(data, name, entry["type"])
    packed = b.pack_bundle(doc, assets)
    assert b.pack_bundle(doc, dict(reversed(list(assets.items())))) == packed
    again = b.unpack_bundle(packed)
    assert again.document == doc and set(again.assets) == set(assets)
    files = b.read_zip(packed)
    assert list(files)[:2] == ["manifest.json", "document.json"]
    manifest = json.loads(files["manifest.json"])
    assert list(manifest) == ["assets", "document", "format"]
    # unreferenced files are left out; a missing one is reported, not invented
    extra = {**assets, "sha256:" + "c" * 64: b.Asset(b"x", "x.txt", "text/plain")}
    assert len(b.unpack_bundle(b.pack_bundle(doc, extra)).assets) == 2
    partial = b.unpack_bundle(b.pack_bundle(doc, {k: v for k, v in assets.items() if v.type == "image/png"}))
    assert "1 attachment(s) are referenced but not included" in partial.warnings[0]
    with pytest.raises(b.BundleError, match="recorded hash"):
        b.pack_bundle(doc, {k: b.Asset(b"tampered", v.name, v.type) for k, v in assets.items()})


@pytest.mark.parametrize(
    ("data", "name", "expected"),
    [
        (PNG, "x", "image/png"),
        (bytes([0xFF, 0xD8, 0xFF, 0xE0]), "x", "image/jpeg"),
        (b"GIF89a\x01\x00", "x", "image/gif"),
        (b"GIF87a\x01\x00", "x", "image/gif"),
        (b"RIFF\0\0\0\0WEBPVP8 ", "x", "image/webp"),
        (PDF, "x", "application/pdf"),
        (PNG, "photo.pdf", "image/png"),
        (b"# Notes", "notes.md", "text/markdown"),
        (b"plain", "notes.txt", "text/plain"),
        (b"plain", "notes", None),
        (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "x.txt", None),
        (b"<?xml version='1.0'?><svg/>", "x.md", None),
        (b"a\x00b", "x.txt", None),
        (b"\xff\xfeA", "x.txt", None),
        (b"MZ\x90\x00", "x.bin", None),
        (b"", "x.txt", None),
    ],
)
def test_type_comes_from_the_bytes(data, name, expected):
    assert b.sniff_type(data, name) == expected


def test_file_names_are_cleaned():
    assert b.clean_file_name("../../a/b\\c.png") == "c.png"
    assert b.clean_file_name("a\x01b .txt") == "ab.txt"
    assert b.clean_file_name("  ") == "file" and len(b.clean_file_name("x" * 300)) == 120


def test_attachment_references_ignore_malformed_entries():
    node = {"metadata": {"attachments": [None, 5, {"asset": "bad"}, {"asset": "sha256:" + "b" * 64, "name": "ok.pdf", "type": "application/pdf", "bytes": 3}, {"asset": "sha256:" + "b" * 64, "name": "x", "type": "image/svg+xml", "bytes": 3}, {"asset": "sha256:" + "b" * 64, "name": "x", "type": "application/pdf", "bytes": True}]}}
    assert [a["name"] for a in b.attachments_of(node)] == ["ok.pdf"]
    assert b.attachments_of({"metadata": {"attachments": "nope"}}) == []
    assert b.attachments_of({}) == []


def test_zip_writer_refuses_what_a_bundle_never_contains():
    for bad in ("../x", "/x", "a/../b", "a\\b", "C:x", "", "é.txt", "dir/", "a\x00b", "x" * 201):
        with pytest.raises(b.BundleError):
            b.write_zip([(bad, b"")])
    with pytest.raises(b.BundleError, match="Duplicate"):
        b.write_zip([("A", b""), ("a", b"")])


def test_crc_check_value_and_large_entries():
    assert zlib.crc32(b"123456789") == 0xCBF43926
    big = random.Random(1).randbytes(3_000_000)
    out = b.read_zip(b.write_zip([("manifest.json", b"{}\n"), ("empty", b""), ("assets/big.bin", big)]))
    assert list(out) == ["manifest.json", "empty", "assets/big.bin"] and out["assets/big.bin"] == big


def test_fuzzed_bundles_never_crash_or_hang():
    """Random damage to a real bundle must end in a clean refusal or a valid read, nothing else."""
    original = bytes.fromhex(corpus["bundle"]["valid"][0]["hex"])
    rng = random.Random(20261002)
    refused = accepted = 0
    for _ in range(1500):
        data = bytearray(original)
        for _ in range(rng.choice((1, 1, 2, 3, 8))):
            data[rng.randrange(len(data))] = rng.randrange(256)
        if rng.random() < 0.15:
            data = data[: rng.randrange(len(data))]
        if rng.random() < 0.05:
            data += rng.randbytes(rng.randrange(1, 40))
        try:
            b.unpack_bundle(bytes(data))
            accepted += 1
        except b.BundleError:
            refused += 1
    assert refused > 1000, "most random damage must be noticed"
    assert accepted + refused == 1500


def test_fuzzed_header_fields_stay_inside_bundle_errors():
    original = bytes.fromhex(corpus["zip"]["valid"][0]["hex"])
    rng = random.Random(7)
    for _ in range(2000):
        data = bytearray(original)
        data[rng.randrange(len(data))] ^= 1 << rng.randrange(8)
        try:
            b.read_zip(bytes(data))
        except b.BundleError:
            pass


def test_read_dmind_opens_both_forms_and_cli_pack_unpack(tmp_path, capsys):
    doc = from_outline("Inventory", "API\nDatabase", "system")
    src = tmp_path / "inventory.dmind"
    assert main(["diagram", "--topic", "Inventory", "--kind", "system", "-o", str(src)]) == 0
    sketch, spec = tmp_path / "sketch.png", tmp_path / "spec.md"
    sketch.write_bytes(PNG)
    spec.write_text("# Spec\n")
    out = tmp_path / "packed.dmind"
    assert main(["dmind-pack", str(src), "--attach", f"root={sketch}", "--attach", f"root={spec}", "-o", str(out)]) == 0
    assert out.read_bytes()[:2] == b"PK"
    assert read_dmind(out.read_bytes())["title"] == "Inventory"  # read_dmind opens the bundle form too
    dest = tmp_path / "unpacked"
    assert main(["dmind-unpack", str(out), "-d", str(dest)]) == 0
    assert json.loads((dest / "document.json").read_text())["nodes"][0]["metadata"]["attachments"][0]["name"] == "sketch.png"
    assert sorted(p.suffix for p in (dest / "assets").iterdir()) == [".md", ".png"]
    assert (dest / "assets" / f"{sha(PNG)}.png").read_bytes() == PNG
    # never overwrites, and bundles can be re-packed with more files
    assert main(["dmind-unpack", str(out), "-d", str(dest)]) == 2
    again = tmp_path / "again.dmind"
    assert main(["dmind-pack", str(out), "-o", str(again)]) == 0
    assert again.read_bytes() == out.read_bytes()
    assert main(["diagram-bundle", str(out), "-o", str(tmp_path / "proposal.json")]) == 0
    assert doc["title"] == "Inventory"


@pytest.mark.parametrize(
    "extra",
    [
        ["--attach", "ghost=FILE"],
        ["--attach", "FILE"],
        ["--attach", "root="],
    ],
)
def test_cli_pack_refusals(tmp_path, capsys, extra):
    src = tmp_path / "d.dmind"
    main(["diagram", "--topic", "T", "-o", str(src)])
    f = tmp_path / "FILE"
    f.write_bytes(PNG)
    args = [a.replace("FILE", str(f)) if a != "root=" else a for a in extra]
    assert main(["dmind-pack", str(src), *args, "-o", str(tmp_path / "o.dmind")]) == 2
    assert capsys.readouterr().err


def test_cli_pack_refuses_unsafe_files(tmp_path, capsys):
    src = tmp_path / "d.dmind"
    main(["diagram", "--topic", "T", "-o", str(src)])
    svg = tmp_path / "x.svg"
    svg.write_text("<svg><script>alert(1)</script></svg>")
    assert main(["dmind-pack", str(src), "--attach", f"root={svg}", "-o", str(tmp_path / "o.dmind")]) == 2
    assert "SVG is not allowed" in capsys.readouterr().err
    big = tmp_path / "big.png"
    big.write_bytes(PNG + bytes(b.MAX_ASSET_BYTES))
    assert main(["dmind-pack", str(src), "--attach", f"root={big}", "-o", str(tmp_path / "o.dmind")]) == 2
    assert "larger than 5 MB" in capsys.readouterr().err
    img = tmp_path / "a.png"
    img.write_bytes(PNG)
    assert main(["dmind-pack", str(src), "--attach", f"root={img}", "--attach", f"root={img}", "-o", str(tmp_path / "o.dmind")]) == 2
    assert "already attached" in capsys.readouterr().err
