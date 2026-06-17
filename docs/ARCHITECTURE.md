# Matrix Designer — Architecture

> The Brain. Idea → governed **Design Bundle** → Matrix Builder.

## The problem it solves

AI coders are fast; **control and design** are the hard parts. Matrix Builder already governs *the
build* (allow-listed batches, fail-closed validation). But its design input is thin: an
`idea-request` (one string + a few constraints) becomes three `blueprint-candidate`s (a stack + an
effort estimate + a flat action list). There is **no artifact** for art direction, entity contracts,
level/flow plans, asset manifests, a *visual* acceptance target, or a **batch dependency graph**. So
batches improvise. Matrix Designer supplies that missing authority.

## Position in the contract chain

```
idea-request ─▶ [ matrix-designer ] ─▶ design-bundle ─▶ blueprint-candidate(×3) ─▶ matrix-bundle ─▶ prompt-pack ─▶ validation-report
```

Additive, backward-compatible changes to Matrix Builder's schemas:

- `idea-request`: optional `references[]` (image/pdf/url/repo) + `design_mode: off|design-first`.
- `blueprint-candidate`: optional `design_bundle_ref` + `design_digest` (sha256).
- new schema `design-bundle.schema.json`, registered in `packages/contracts/schema-registry.json`
  with `owned_by += "matrix-designer"`.

## Components

```
matrix_designer/
  engine.py       DesignEngine — agentic (CrewAI/LangGraph) + deterministic fallback
  models.py       typed Design Bundle (mirror of the JSON schema; content-addressed)
  packs.py        design-pack loader (domain templates + rule ids)
  validate.py     schema + design-rule verdict (approved|needs-repair|rejected)
  exporter.py     design-bundle → Matrix Builder inputs (idea-request, blueprint overlay, mb next[])
  mcp_server.py   matrix-designer-mcp (7 tools)
  cli.py          `mdesign` CLI
schemas/          design-bundle.schema.json (source of truth)
packs/            web-game-platformer-v1, web-saas-product-v1, …
examples/         worked Contract Quest design bundle
```

## Execution modes (same output contract)

- **Agentic** — a CrewAI crew (Goal Analyst → Architect → Visual Director → **Batch Planner**)
  reasons over the idea + chosen blueprint + references and emits each section; the Batch Planner
  produces the ordered roadmap. Multi-agent **topologies** are swappable (sequential, hierarchical,
  or a LangGraph state machine) via `MATRIX_DESIGNER_BACKEND`.
- **Deterministic** — heuristic planner that always runs offline, seeds the agentic output, and
  guarantees the required fields exist. CI never depends on a live LLM.

The two are reconciled (`engine._merge`) so the agentic roadmap wins when present but the bundle is
always schema-complete.

## Governance

`validate.py` enforces the schema **and** the design-pack rules before a bundle can be marked
`approved`. This mirrors Matrix Builder's fail-closed `mb check`: **AI proposes the design; Matrix
Definitions enforce it.** The brain cannot approve itself.
