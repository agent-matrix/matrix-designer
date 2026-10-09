"""The ``.dmind`` bundle form (batch B5): a strict ZIP with ``manifest.json``, ``document.json`` and
attachments under ``assets/``. Mirrors the TypeScript reader in DayPilot rule for rule; both are held
to the same corpus (``examples/dmind/archive-cases.json``).

The reader treats every archive as hostile: bounded entries and sizes, no ZIP64, encryption,
symlinks or special files, no unsafe, duplicate or non-ASCII names, no overlapping or out-of-range
entries, local headers must agree with the central directory, inflated data is counted as it is
produced, and CRC-32 is verified. The writer stores entries uncompressed with fixed metadata, so a
given input always produces the same bytes as the TypeScript writer.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any

from .dmind_contract import validate_diagram

BUNDLE_FORMAT = "dmind-bundle/v1"
ASSET_TYPES = (
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/plain",
    "text/markdown",
)
_EXTENSION = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/markdown": "md",
}
MAX_ASSET_BYTES = 5_000_000
MAX_ASSETS = 50
MAX_ATTACHMENTS_PER_TOPIC = 10
MAX_DOCUMENT_BYTES = 2_000_000


class BundleError(ValueError):
    """The archive or bundle was refused; the message says why."""


@dataclass(frozen=True)
class ZipLimits:
    max_entries: int = 200
    max_entry_bytes: int = 10_000_000
    max_total_bytes: int = 60_000_000
    max_ratio: int = 200


BUNDLE_LIMITS = ZipLimits()


def _u16(b: bytes, o: int) -> int:
    return struct.unpack_from("<H", b, o)[0]


def _u32(b: bytes, o: int) -> int:
    return struct.unpack_from("<I", b, o)[0]


_UNSAFE = re.compile(r"[\x00-\x1f\x7f\\]")


def check_entry_name(name: str) -> None:
    if not name or len(name) > 200:
        raise BundleError("The archive contains an entry with an invalid name.")
    if (
        not re.fullmatch(r"[\x20-\x7e]+", name)
        or _UNSAFE.search(name)
        or name.startswith("/")
        or re.match(r"[A-Za-z]:", name)
    ):
        raise BundleError("The archive contains an unsafe entry name and was refused.")
    if any(part in ("", ".", "..") for part in name.removesuffix("/").split("/")):
        raise BundleError("The archive contains an unsafe entry name and was refused.")


def _inflate(raw: bytes, expected: int) -> bytes:
    d = zlib.decompressobj(-15)
    try:
        out = d.decompress(raw, expected + 1)
    except zlib.error as exc:
        raise BundleError("An archive entry could not be decompressed.") from exc
    if len(out) > expected:
        raise BundleError("An archive entry is larger than it declares and was refused.")
    if len(out) != expected:
        raise BundleError("An archive entry is smaller than it declares and was refused.")
    return out


@dataclass
class _Entry:
    name: str
    method: int
    crc: int
    csize: int
    usize: int
    offset: int
    is_dir: bool
    name_bytes: bytes


def read_zip(data: bytes, limits: ZipLimits = BUNDLE_LIMITS) -> dict[str, bytes]:
    """Read an archive into ``{name: bytes}`` (central-directory order) or raise BundleError."""
    n = len(data)
    if n < 22 or _u32(data, 0) != 0x04034B50:
        if n >= 22 and _u32(data, 0) == 0x06054B50:
            raise BundleError("The archive is empty.")
        raise BundleError("This is not a valid ZIP archive.")
    eocd = -1
    for i in range(n - 22, max(0, n - 22 - 65535) - 1, -1):
        if _u32(data, i) == 0x06054B50 and i + 22 + _u16(data, i + 20) == n:
            eocd = i
            break
    if eocd < 0:
        raise BundleError("This is not a valid ZIP archive.")
    disk, cd_disk, here, total = (_u16(data, eocd + o) for o in (4, 6, 8, 10))
    cd_size, cd_offset = _u32(data, eocd + 12), _u32(data, eocd + 16)
    if total == 0xFFFF or cd_size == 0xFFFFFFFF or cd_offset == 0xFFFFFFFF:
        raise BundleError("ZIP64 archives are not supported.")
    if disk != 0 or cd_disk != 0 or here != total:
        raise BundleError("Multi-part archives are not supported.")
    if total > limits.max_entries:
        raise BundleError(f"The archive has more than {limits.max_entries} entries.")
    if cd_offset + cd_size != eocd:
        raise BundleError("The archive directory is damaged.")

    entries: list[_Entry] = []
    seen: set[str] = set()
    p, declared = cd_offset, 0
    for _ in range(total):
        if p + 46 > eocd or _u32(data, p) != 0x02014B50:
            raise BundleError("The archive directory is damaged.")
        made_by, flags, method = _u16(data, p + 4), _u16(data, p + 8), _u16(data, p + 10)
        crc, csize, usize = _u32(data, p + 16), _u32(data, p + 20), _u32(data, p + 24)
        name_len, extra_len, comment_len = _u16(data, p + 28), _u16(data, p + 30), _u16(data, p + 32)
        disk_start, external, offset = _u16(data, p + 34), _u32(data, p + 38), _u32(data, p + 42)
        end = p + 46 + name_len + extra_len + comment_len
        if end > eocd:
            raise BundleError("The archive directory is damaged.")
        if 0xFFFFFFFF in (csize, usize, offset):
            raise BundleError("ZIP64 archives are not supported.")
        if disk_start != 0:
            raise BundleError("Multi-part archives are not supported.")
        if flags & 0x1 or flags & 0x40:
            raise BundleError("Encrypted archives are not supported.")
        name_bytes = data[p + 46 : p + 46 + name_len]
        try:
            name = name_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BundleError("The archive contains an entry name that is not valid text.") from exc
        check_entry_name(name)
        key = name.lower()
        if key in seen:
            raise BundleError("The archive contains duplicate entry names.")
        seen.add(key)
        if made_by >> 8 == 3:
            kind = (external >> 16) & 0o170000
            if kind and kind not in (0o100000, 0o040000):
                raise BundleError("The archive contains a link or special file and was refused.")
        is_dir = name.endswith("/")
        if is_dir and (usize or csize):
            raise BundleError("The archive directory is damaged.")
        if not is_dir:
            if method not in (0, 8):
                raise BundleError("The archive uses an unsupported compression method.")
            if usize > limits.max_entry_bytes:
                raise BundleError("An archive entry is too large.")
            if usize > 1_000_000 and usize > limits.max_ratio * max(csize, 1):
                raise BundleError("The archive looks like a compression bomb and was refused.")
            if method == 0 and csize != usize:
                raise BundleError("The archive directory is damaged.")
            declared += usize
            if declared > limits.max_total_bytes:
                raise BundleError("The archive expands to more than the allowed size.")
        entries.append(_Entry(name, method, crc, csize, usize, offset, is_dir, name_bytes))
        p = end
    if p != eocd:
        raise BundleError("The archive directory is damaged.")

    spans: list[tuple[int, int]] = []
    start_of: dict[str, int] = {}
    for e in entries:
        if e.is_dir:
            continue
        if e.offset + 30 > cd_offset or _u32(data, e.offset) != 0x04034B50:
            raise BundleError("The archive is damaged or out of range.")
        name_len, extra_len = _u16(data, e.offset + 26), _u16(data, e.offset + 28)
        start = e.offset + 30 + name_len + extra_len
        if data[e.offset + 30 : e.offset + 30 + name_len] != e.name_bytes:
            raise BundleError("The archive entry names are inconsistent and it was refused.")
        if start + e.csize > cd_offset:
            raise BundleError("The archive is damaged or out of range.")
        spans.append((e.offset, start + e.csize))
        start_of[e.name] = start
    spans.sort()
    for a, b in zip(spans, spans[1:]):
        if b[0] < a[1]:
            raise BundleError("The archive entries overlap and it was refused.")

    out: dict[str, bytes] = {}
    for e in entries:
        if e.is_dir:
            continue
        start = start_of[e.name]
        raw = data[start : start + e.csize]
        body = bytes(raw) if e.method == 0 else _inflate(raw, e.usize)
        if len(body) != e.usize:
            raise BundleError("An archive entry does not match its declared size.")
        if zlib.crc32(body) & 0xFFFFFFFF != e.crc:
            raise BundleError("An archive entry is damaged (checksum mismatch).")
        out[e.name] = body
    return out


def write_zip(entries: list[tuple[str, bytes]]) -> bytes:
    """Deterministic archive: stored, 1980-01-01, mode 0644, ASCII names. Same bytes as the TS writer."""
    parts: list[bytes] = []
    central: list[bytes] = []
    offset = 0
    names: set[str] = set()
    for name, data in entries:
        check_entry_name(name)
        if name.endswith("/"):
            raise BundleError("Bundle entry names must be plain ASCII file names.")
        if name.lower() in names:
            raise BundleError("Duplicate entry name.")
        names.add(name.lower())
        if len(data) > 0xFFFFFFFE:
            raise BundleError("An entry is too large for this format.")
        nb = name.encode("ascii")
        crc = zlib.crc32(data) & 0xFFFFFFFF
        local = struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0, 0, 0, 0x21, crc, len(data), len(data), len(nb), 0) + nb
        head = (
            struct.pack(
                "<IHHHHHHIIIHHHHHII",
                0x02014B50, 0x0314, 20, 0, 0, 0, 0x21, crc, len(data), len(data), len(nb), 0, 0, 0, 0,
                (0o100644 << 16) & 0xFFFFFFFF, offset,
            )
            + nb
        )
        parts += [local, data]
        central.append(head)
        offset += len(local) + len(data)
    cd = b"".join(central)
    end = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(entries), len(entries), len(cd), offset, 0)
    return b"".join(parts) + cd + end


# --------------------------------------------------------------------------- assets


def sniff_type(data: bytes, name_hint: str = "") -> str | None:
    """The type of a file from its bytes, or None when it is not an allowed type."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"GIF8" and data[4:5] in (b"7", b"9") and data[5:6] == b"a":
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data and re.search(r"\.(txt|md|markdown)$", name_hint, re.I) and b"\x00" not in data:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return None
        if re.match(r"\s*<(svg|\?xml|!doctype\s+svg)", text, re.I):
            return None
        return "text/markdown" if re.search(r"\.(md|markdown)$", name_hint, re.I) else "text/plain"
    return None


def clean_file_name(name: str) -> str:
    base = re.split(r"[\\/]", name)[-1] or "file"
    clean = re.sub(r"[\x00-\x1f\x7f\u2028\u2029]", "", base).strip()[:120]
    return clean or "file"


def asset_path(sha_hex: str, type_: str) -> str:
    return f"assets/{sha_hex}.{_EXTENSION[type_]}"


@dataclass
class Asset:
    data: bytes
    name: str
    type: str


def attachments_of(node: dict[str, Any]) -> list[dict[str, Any]]:
    raw = (node.get("metadata") or {}).get("attachments")
    if not isinstance(raw, list):
        return []
    out = []
    for a in raw:
        if not isinstance(a, dict):
            continue
        ref, name, type_, size = a.get("asset"), a.get("name"), a.get("type"), a.get("bytes")
        if (
            isinstance(ref, str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", ref)
            and isinstance(name, str)
            and type_ in ASSET_TYPES
            and isinstance(size, int)
            and not isinstance(size, bool)
            and size >= 0
        ):
            out.append({"asset": ref, "name": clean_file_name(name), "type": type_, "bytes": size})
    return out[:MAX_ATTACHMENTS_PER_TOPIC]


def all_attachments(doc: dict[str, Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out = []
    for node in doc["nodes"]:
        for a in attachments_of(node):
            if a["asset"] not in seen:
                seen.add(a["asset"])
                out.append(a)
    return out


# --------------------------------------------------------------------------- bundle


@dataclass
class Unpacked:
    document: dict[str, Any]
    assets: dict[str, Asset]
    warnings: list[str] = field(default_factory=list)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def pack_bundle(document: dict[str, Any], assets: dict[str, Asset]) -> bytes:
    valid = validate_diagram(document)
    doc_bytes = (json.dumps(valid, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if len(doc_bytes) > MAX_DOCUMENT_BYTES:
        raise BundleError("The document is too large to bundle.")
    used = [a for a in all_attachments(valid) if a["asset"] in assets]
    if len(used) > MAX_ASSETS:
        raise BundleError(f"A bundle can hold {MAX_ASSETS} attachments.")
    files: list[tuple[str, bytes]] = []
    listed = []
    for a in sorted(used, key=lambda x: x["asset"]):
        asset = assets[a["asset"]]
        digest = hashlib.sha256(asset.data).hexdigest()
        if digest != a["asset"][7:]:
            raise BundleError("An attachment does not match its recorded hash.")
        path = asset_path(digest, asset.type)
        listed.append(
            {"bytes": len(asset.data), "name": clean_file_name(asset.name), "path": path, "sha256": digest, "type": asset.type}
        )
        files.append((path, asset.data))
    manifest = {
        "assets": listed,
        "document": {"bytes": len(doc_bytes), "path": "document.json", "sha256": hashlib.sha256(doc_bytes).hexdigest()},
        "format": BUNDLE_FORMAT,
    }
    return write_zip([("manifest.json", _json_bytes(manifest)), ("document.json", doc_bytes), *files])


def unpack_bundle(data: bytes) -> Unpacked:
    files = read_zip(data, BUNDLE_LIMITS)
    manifest_bytes, doc_bytes = files.get("manifest.json"), files.get("document.json")
    if manifest_bytes is None or doc_bytes is None:
        raise BundleError("This archive is not a dmind bundle (manifest.json or document.json is missing).")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError("The bundle manifest is not valid.") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("format") != BUNDLE_FORMAT
        or not isinstance(manifest.get("document"), dict)
        or not isinstance(manifest.get("assets"), list)
    ):
        raise BundleError(f"This bundle uses an unsupported format (expected {BUNDLE_FORMAT}).")
    if len(doc_bytes) > MAX_DOCUMENT_BYTES:
        raise BundleError("The bundle document is too large.")
    meta = manifest["document"]
    if (
        meta.get("path") != "document.json"
        or meta.get("sha256") != hashlib.sha256(doc_bytes).hexdigest()
        or meta.get("bytes") != len(doc_bytes)
    ):
        raise BundleError("The bundle document does not match its manifest.")
    try:
        doc = json.loads(doc_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError("The bundle document is not valid JSON.") from exc
    try:
        document = validate_diagram(doc)
    except ValueError as exc:
        raise BundleError(str(exc)) from exc
    if len(manifest["assets"]) > MAX_ASSETS:
        raise BundleError(f"A bundle can hold {MAX_ASSETS} attachments.")

    assets: dict[str, Asset] = {}
    listed = {"manifest.json", "document.json"}
    for a in manifest["assets"]:
        if not isinstance(a, dict) or not isinstance(a.get("path"), str) or not isinstance(a.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", a["sha256"]):
            raise BundleError("The bundle manifest lists an invalid attachment.")
        type_ = a.get("type")
        if type_ not in ASSET_TYPES:
            raise BundleError("The bundle contains an attachment type that is not allowed.")
        if a["path"] != asset_path(a["sha256"], type_):
            raise BundleError("The bundle manifest lists an unexpected attachment path.")
        body = files.get(a["path"])
        if body is None:
            raise BundleError("The bundle is missing an attachment listed in its manifest.")
        listed.add(a["path"])
        if len(body) > MAX_ASSET_BYTES or len(body) != a.get("bytes"):
            raise BundleError("A bundle attachment does not match its manifest.")
        if hashlib.sha256(body).hexdigest() != a["sha256"]:
            raise BundleError("A bundle attachment does not match its recorded hash.")
        if sniff_type(body, str(a.get("name", ""))) != type_:
            raise BundleError("A bundle attachment is not the type it claims to be.")
        assets["sha256:" + a["sha256"]] = Asset(body, clean_file_name(str(a.get("name", ""))), type_)
    for name in files:
        if name not in listed:
            raise BundleError(f"The bundle contains an unlisted file ({name}) and was refused.")
    warnings = []
    wanted = {a["asset"] for a in all_attachments(document)}
    missing = wanted - assets.keys()
    if missing:
        warnings.append(f"{len(missing)} attachment(s) are referenced but not included in the bundle.")
    stray = assets.keys() - wanted
    if stray:
        warnings.append(f"{len(stray)} included file(s) are not attached to any topic.")
    return Unpacked(document, assets, warnings)
