# Governance — AI proposes, Matrix Definitions enforce

Matrix Designer uses AI to *propose* a design. It must never *approve* its own work. The rule:

```
AI may propose design.
Matrix Definitions validate design.
Matrix Builder governs implementation.
GitPilot writes code.
```

## What AI may do
visual analysis · architecture suggestions · batch planning · risk detection · acceptance criteria ·
framework comparison.

## What AI must not do
approve itself · change Matrix rules · bypass Matrix Builder · write uncontrolled code.

## How it's enforced

`validate.py` produces a verdict — **approved / needs-repair / rejected** — from two layers:

1. **Schema** — the bundle must satisfy `design-bundle.schema.json`.
2. **Design rules** — declared as signed-pack catalogs in `packs/*/rules.yaml` and enforced by
   `validate.py`. The rule families:

| Family | Pack | Examples |
|---|---|---|
| **DESIGN-*** | `design-rules-v1` | `001` every batch is scoped · `002` every batch has acceptance · `003` dependencies are real · `004` solution acceptance exists · `005` dependency graph is acyclic |
| **GAME-*** | `web-game-platformer-v1` | `001` design brain required · `004` asset manifest · `005` entity contracts · `006` **visual acceptance required** (the exact gap that produced the flat Contract Quest v1) · `009` original assets only |
| **APP-*** | `web-saas-product-v1` | `001` data model before screens · `002` auth flow · `004` accessibility acceptance · `005` always shippable |

The catalog is loaded by `rules.py` (one source of truth); the *checks* live in `validate.py`. A
bundle with any `high`/`critical` violation is `needs-repair` and **cannot** seed Matrix Builder
candidates until fixed. Schema errors are `rejected`. This is the same fail-closed posture as
Matrix Builder's `mb check`, applied one layer earlier — to the design itself.

> Promotion: these packs are the **reference implementation** to be promoted into
> `agent-matrix/matrix-definitions` as signed packs (batch-08 of the integration roadmap).

## Provenance

Every bundle is content-addressed (`provenance.design_digest = sha256(bundle\digest)`) and records
`created_by`, `ai_assisted`, and `model`. Blueprint candidates carry that digest, so the whole chain
— design → blueprint → bundle → commit — is auditable end to end.
