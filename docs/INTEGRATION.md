# Integrating with Matrix Builder & Matrix Definitions

Matrix Designer is **additive**: it strengthens Matrix Builder's *input* without changing the
fail-closed build loop.

## 1. Contracts package (`matrix-builder/packages/contracts`)

- Add `schemas/design-bundle.schema.json` (vendored here; copy in).
- Register it in `schema-registry.json`:
  ```json
  { "id": "https://matrixhub.io/schemas/matrix-designer/design-bundle.schema.json",
    "title": "design-bundle", "path": "packages/contracts/schemas/design-bundle.schema.json" }
  ```
  and add `"matrix-designer"` to `owned_by`.
- Extend `idea-request.schema.json` (additive):
  ```json
  "design_mode": { "type": "string", "enum": ["off", "design-first"], "default": "off" },
  "references": { "type": "array", "items": { "type": "object",
      "required": ["kind","ref"], "properties": {
        "kind": {"enum": ["image","pdf","url","repo","figma","text"]}, "ref": {"type":"string"} } } }
  ```
- Extend `blueprint-candidate.schema.json` (additive): `design_bundle_ref` (uri),
  `design_digest` (`^sha256:[a-fA-F0-9]{16,}$`).

## 2. Control plane (`services/api`)

Add a thin endpoint that proxies the MCP server (or imports `matrix_designer` directly):

```
POST /api/v1/design        { idea, references[], blueprint, quality } -> design-bundle + verdict
POST /api/v1/design/export  design-bundle -> { idea_request, blueprint_overlay, mb_next_sequence }
```

When `design_mode = design-first`, the blueprint step reads `mb_next_sequence` as the batch plan
instead of generating ad-hoc `generator_actions`.

## 3. Web UI (`apps/web`)

One quiet **“Design first”** toggle on the idea screen (+ optional file/image attach). Everything
else stays the same — the three candidates are now derived from the brain.

## 4. Matrix Definitions

Promote the design-packs here (`packs/*`) into signed Definitions packs, and add the `DESIGN-*` /
`GAME-*` / `APP-*` rule families so the Design Bundle is validated by the same authority that signs
code standards. `validate.py` here is the reference implementation of those checks.

## Backward compatibility

If `design_mode` is absent or `off`, Matrix Builder behaves exactly as today. Designer is strictly
opt-in.
