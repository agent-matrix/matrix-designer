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
2. **Design rules** — design-pack rule families:
   - `DESIGN-001` every batch is scoped (`allowed_files` + `acceptance`).
   - `DESIGN-003` dependencies reference real batches.
   - `DESIGN-004` the solution has functional acceptance.
   - `GAME-001…010` game rules (e.g. `GAME-006` a visual acceptance target is required —
     the exact gap that produced the flat Contract Quest v1).

A bundle with any `high`/`critical` violation is `needs-repair` and **cannot** seed Matrix Builder
candidates until fixed. Schema errors are `rejected`. This is the same fail-closed posture as
Matrix Builder's `mb check`, applied one layer earlier — to the design itself.

## Provenance

Every bundle is content-addressed (`provenance.design_digest = sha256(bundle\digest)`) and records
`created_by`, `ai_assisted`, and `model`. Blueprint candidates carry that digest, so the whole chain
— design → blueprint → bundle → commit — is auditable end to end.
