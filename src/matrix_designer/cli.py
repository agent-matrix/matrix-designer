"""`mdesign` — the Matrix Designer CLI.

    mdesign design  --idea "..." [--blueprint bp.json] [--quality production] -o design-bundle.json
    mdesign batches --idea "..." [--blueprint bp.json]      # just the roadmap (the batches guy)
    mdesign validate design-bundle.json                     # approved | needs-repair | rejected
    mdesign export   design-bundle.json -o mb-export.json   # -> Matrix Builder inputs
    mdesign mcp                                              # run the matrix-designer-mcp server
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

from .engine import DesignEngine
from .exporter import to_mb_export
from .graph import design_blueprints, refine, run_design
from .validate import verdict


def _load(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _emit(obj: Any, out: str | None) -> None:
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {out}")
    else:
        print(text)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mdesign", description="Matrix Designer — the Brain of the Matrix ecosystem.")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("design", "batches"):
        sp = sub.add_parser(name)
        sp.add_argument("--idea", required=True)
        sp.add_argument("--blueprint", help="chosen blueprint-candidate JSON")
        sp.add_argument("--quality", default="standard")
        sp.add_argument("-o", "--out")

    bp = sub.add_parser("blueprints")  # the LangGraph multi-agent brain → 3 blueprints
    bp.add_argument("--idea", required=True); bp.add_argument("-o", "--out")
    cp = sub.add_parser("chat")        # orchestrator chat → refine a blueprint
    cp.add_argument("--idea", required=True); cp.add_argument("--message", required=True)
    cp.add_argument("--candidate", default="standard")

    vp = sub.add_parser("validate"); vp.add_argument("bundle")
    ep = sub.add_parser("export"); ep.add_argument("bundle"); ep.add_argument("-o", "--out")
    dp = sub.add_parser("diagram", help="Generate a dmind/v1 diagram")
    dp.add_argument("--topic", required=True)
    dp.add_argument("--outline", help="UTF-8 text or Markdown file")
    dp.add_argument("--kind", choices=["mindmap", "flowchart", "system"], default="mindmap")
    dp.add_argument("--designer", action="store_true")
    dp.add_argument("--candidate", default="standard")
    dp.add_argument("-o", "--out")
    db = sub.add_parser("diagram-bundle", help="Design and validate from a dmind/v1 graph")
    db.add_argument("diagram")
    db.add_argument("--candidate", default="standard")
    db.add_argument("-o", "--out")
    pk = sub.add_parser("dmind-pack", help="Pack a diagram and attachments into a .dmind bundle")
    pk.add_argument("diagram")
    pk.add_argument("--attach", action="append", default=[], metavar="TOPIC_ID=FILE",
                    help="attach FILE (image, PDF, txt or md; max 5 MB) to a topic; repeatable")
    pk.add_argument("-o", "--out", required=True)
    up = sub.add_parser("dmind-unpack", help="Unpack a .dmind bundle into a folder")
    up.add_argument("bundle")
    up.add_argument("-d", "--dir", required=True)
    sub.add_parser("mcp")

    args = p.parse_args(argv)

    if args.cmd in ("dmind-pack", "dmind-unpack"):
        from .dmind_bundle_cli import pack, unpack
        try:
            return pack(args) if args.cmd == "dmind-pack" else unpack(args)
        except (ValueError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.cmd in ("diagram", "diagram-bundle"):
        from .dmind import diagram_handler, diagram_bundle_handler
        try:
            if args.cmd == "diagram":
                from pathlib import Path
                content = Path(args.outline).read_text(encoding="utf-8") if args.outline else ""
                result = diagram_handler(args.topic, content, args.kind, args.candidate, args.designer)
                out = result.get("diagram", result)
            else:
                from pathlib import Path
                from .dmind_file import read_dmind
                result = diagram_bundle_handler(read_dmind(Path(args.diagram).read_bytes()), args.candidate)
                out = result
            if result.get("error"):
                print(result["error"], file=sys.stderr)
                return 2
            if args.cmd == "diagram" and args.out and "schema_version" in out:
                from pathlib import Path
                from .dmind_file import write_dmind
                Path(args.out).write_bytes(write_dmind(out))  # a .dmind file
            else:
                _emit(out, args.out)
            return 0
        except (ValueError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.cmd == "blueprints":
        out = design_blueprints(args.idea); out.pop("_state", None)
        _emit(out, args.out)
        print(f"designed {len(out['candidates'])} blueprints; {len(out['violations'])} violations", file=sys.stderr)
        return 0

    if args.cmd == "chat":
        state = run_design(args.idea)
        out = refine(state, args.message, args.candidate); out.pop("_state", None)
        print(json.dumps({"reply": out["reply"], "chat_history": out["chat_history"],
                          "batches": out["details"][args.candidate]["batches"]}, indent=2, ensure_ascii=False))
        return 0

    if args.cmd in ("design", "batches"):
        blueprint = _load(args.blueprint) if args.blueprint else {"slug": "project", "stack": []}
        bundle = DesignEngine().design(args.idea, blueprint, quality_level=args.quality)
        d = bundle.to_dict()
        if args.cmd == "batches":
            _emit({"batch_roadmap": d["batch_roadmap"], "count": len(bundle.batch_roadmap)}, args.out)
        else:
            status, report = verdict(d)
            d.setdefault("governance", {})["validation_status"] = status
            _emit(d, args.out)
            print(f"validation: {report['summary']}", file=sys.stderr)
        return 0

    if args.cmd == "validate":
        status, report = verdict(_load(args.bundle))
        print(json.dumps(report, indent=2))
        return 0 if status == "approved" else (1 if status == "needs-repair" else 2)

    if args.cmd == "export":
        _emit(to_mb_export(_load(args.bundle)), args.out)
        return 0

    if args.cmd == "mcp":
        from .mcp_server import main as mcp_main
        mcp_main()
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
