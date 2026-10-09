"""The ``.dmind`` file: UTF-8 JSON in the dmind/v1 schema, or the ZIP bundle form with attachments.

Opening a file never trusts it: size is bounded before parsing, the version is checked with an
actionable message and the full graph contract runs. Unknown fields are kept, not dropped.
"""

from __future__ import annotations

import json
from typing import Any

from .dmind_contract import MAX_BYTES, validate_diagram

EXTENSION = ".dmind"
MAX_BUNDLE_FILE_BYTES = 62_000_000
MIME = "application/vnd.dmind+json"


def detect_form(data: bytes) -> str:
    """``json``, ``zip`` or ``unknown``, from the first bytes (a UTF-8 byte order mark is ignored)."""
    head = data[3:] if data[:3] == b"\xef\xbb\xbf" else data
    stripped = head.lstrip(b" \t\r\n")
    if stripped[:1] == b"{":
        return "json"
    if data[:2] == b"PK":
        return "zip"
    return "unknown"


def read_dmind(data: bytes) -> dict[str, Any]:
    """Parse and validate a ``.dmind`` file's bytes; always returns a detached document."""
    form = detect_form(data)
    if form == "zip":
        # The bundle form carries attachments, so it may be larger than a plain document.
        from .dmind_bundle import BundleError, unpack_bundle

        if len(data) > MAX_BUNDLE_FILE_BYTES:
            raise ValueError("file exceeds 62 MB")
        try:
            return unpack_bundle(data).document
        except BundleError as exc:
            raise ValueError(str(exc)) from exc
    if len(data) > MAX_BYTES:
        raise ValueError("file exceeds 2 MB")
    if form != "json":
        raise ValueError('not a dmind document: it should be JSON starting with "{"')
    try:
        value = json.loads(data.decode("utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise ValueError("file is not valid UTF-8 text") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"file is not valid JSON: {exc.msg}") from exc
    schema = value.get("schema_version") if isinstance(value, dict) else None
    if isinstance(schema, str) and schema.startswith("dmind/") and schema != "dmind/v1":
        raise ValueError(f"file uses {schema}; this version reads dmind/v1")
    return validate_diagram(value)


def write_dmind(document: dict[str, Any]) -> bytes:
    """Readable, diff-friendly bytes: two-space JSON, UTF-8, trailing newline."""
    valid = validate_diagram(document)
    return (json.dumps(valid, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
