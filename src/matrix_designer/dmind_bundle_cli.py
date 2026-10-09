"""``mdesign dmind-pack`` and ``dmind-unpack``: bundle attachments from the command line."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

from .dmind_bundle import (
    MAX_ASSET_BYTES,
    MAX_ASSETS,
    MAX_ATTACHMENTS_PER_TOPIC,
    Asset,
    BundleError,
    all_attachments,
    asset_path,
    attachments_of,
    clean_file_name,
    pack_bundle,
    sniff_type,
    unpack_bundle,
)
from .dmind_file import detect_form, read_dmind, write_dmind


def _load(path: str) -> tuple[dict[str, Any], dict[str, Asset]]:
    data = Path(path).read_bytes()
    if detect_form(data) == "zip":
        try:
            u = unpack_bundle(data)
        except BundleError as exc:
            raise ValueError(str(exc)) from exc
        return u.document, u.assets
    return read_dmind(data), {}


def pack(args) -> int:
    document, assets = _load(args.diagram)
    for spec in args.attach:
        topic, sep, file = spec.partition("=")
        if not sep or not topic or not file:
            raise ValueError("--attach expects TOPIC_ID=FILE")
        node = next((n for n in document["nodes"] if n["id"] == topic), None)
        if node is None:
            raise ValueError(f"topic {topic!r} does not exist in the diagram")
        path = Path(file)
        if path.stat().st_size > MAX_ASSET_BYTES:
            raise ValueError(f"{path.name} is larger than {MAX_ASSET_BYTES // 1_000_000} MB")
        data = path.read_bytes()
        type_ = sniff_type(data, path.name)
        if type_ is None:
            raise ValueError(
                f"{path.name}: attachments can be PNG, JPEG, GIF or WebP images, PDFs, or txt and md files "
                "(SVG is not allowed)"
            )
        ref = "sha256:" + hashlib.sha256(data).hexdigest()
        have = attachments_of(node)
        if any(a["asset"] == ref for a in have):
            raise ValueError(f"{path.name} is already attached to {topic}")
        if len(have) >= MAX_ATTACHMENTS_PER_TOPIC:
            raise ValueError(f"a topic can hold {MAX_ATTACHMENTS_PER_TOPIC} attachments")
        if ref not in {a["asset"] for a in all_attachments(document)} and len(all_attachments(document)) >= MAX_ASSETS:
            raise ValueError(f"a diagram can hold {MAX_ASSETS} different attachments")
        entry = {"asset": ref, "name": clean_file_name(path.name), "type": type_, "bytes": len(data)}
        node.setdefault("metadata", {})["attachments"] = [*have, entry]
        assets[ref] = Asset(data, entry["name"], type_)
    Path(args.out).write_bytes(pack_bundle(document, assets))
    return 0


def unpack(args) -> int:
    data = Path(args.bundle).read_bytes()
    try:
        u = unpack_bundle(data)
    except BundleError as exc:
        raise ValueError(str(exc)) from exc
    root = Path(args.dir)
    (root / "assets").mkdir(parents=True, exist_ok=True)
    # Names come from validated hashes and types, never from the archive; "xb" never overwrites.
    targets = [(root / "document.json", write_dmind(u.document))]
    for ref, asset in u.assets.items():
        targets.append((root / asset_path(ref[7:], asset.type), asset.data))
    for path, content in targets:
        with path.open("xb") as handle:
            handle.write(content)
    for warning in u.warnings:
        print(warning, file=sys.stderr)
    return 0
