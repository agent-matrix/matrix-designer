<div align="center">

<h1>🧠 Matrix Designer</h1>
<h3>The Brain of the Matrix ecosystem — <i>the batches guy</i>.</h3>

<p>Give it an idea and the <b>chosen blueprint</b>, and an <b>agentic LLM crew</b> designs the
<b>full proposal</b> — framework decision, visual/UX target, architecture, entity contracts, asset
manifest, acceptance criteria (including <i>visual</i>), and an ordered, dependency-aware
<b>batch roadmap with all details</b> — as one governed <b>Design Bundle</b>. Then
<a href="https://github.com/agent-matrix/matrix-builder">Matrix Builder</a> turns that brain into
controlled, validated batches and <a href="https://gitpilot.ruslanmv.com">GitPilot</a> builds them.</p>

<p>
  <img src="https://img.shields.io/badge/role-the_Brain-8A63D2?style=flat-square&labelColor=1C1C1F" alt="the Brain">
  <img src="https://img.shields.io/badge/agentic-CrewAI_·_LangGraph-10a37f?style=flat-square&labelColor=1C1C1F" alt="agentic">
  <img src="https://img.shields.io/badge/interface-MCP_server-ffb000?style=flat-square&labelColor=1C1C1F" alt="MCP">
  <img src="https://img.shields.io/badge/output-Design_Bundle-0f62fe?style=flat-square&labelColor=1C1C1F" alt="Design Bundle">
  <img src="https://img.shields.io/badge/license-MIT-3ddc97?style=flat-square&labelColor=1C1C1F" alt="MIT">
</p>

</div>

---

## Why this exists

The hardest part of building a game or any project with AI is **not writing code** — it's
**knowing what the whole solution should become *before* splitting it into batches**. When there is
no authoritative design, every batch improvises: no art direction, no level architecture, no asset
plan, no entity system, no visual acceptance target, no batch ownership map. The result is a
primitive prototype, no matter how good the coder is.

**Matrix Designer is that missing brain.** It does **not** replace Matrix Builder — it prepares the
full design first, so when Matrix Builder mounts the puzzle, every piece fits.

```text
Matrix Designer designs the solution.
Matrix Builder controls the build.
GitPilot writes the code.
Matrix Definitions enforce the rules.
```

## Where it fits in the pipeline

Matrix Builder's contract chain today is `idea-request → blueprint-candidate(×3) → matrix-bundle →
prompt-pack → validation`. Matrix Designer adds **one node and one artifact**, additively:

```text
idea-request ─▶ [ MATRIX DESIGNER ] ─▶ design-bundle ─▶ blueprint-candidate(×3) ─▶ matrix-bundle ─▶ prompt-pack ─▶ validation
                  (agentic crew)         (the brain)         (now derived from the brain via design_digest)
```

Nothing downstream changes. `idea-request` gains optional `references[]` + `design_mode`;
`blueprint-candidate` gains optional `design_bundle_ref` + `design_digest` so each blueprint is
**provably derived** from a signed design. See [`docs/INTEGRATION.md`](docs/INTEGRATION.md).

## The agentic crew (the batches guy)

Given the chosen blueprint, a small **CrewAI** crew collaborates — and the **Batch Planner** owns the
roadmap:

| Agent | Produces |
|---|---|
| **Goal Analyst** | the real goal, complexity, risks, missing decisions |
| **Solution Architect** | scenes/routes, systems, services, entity/data contracts |
| **Visual & UX Director** | the visual target + asset/UI manifest (so *done* has a LOOK) |
| **Batch Planner** 🧩 | the ordered, dependency-aware **batch roadmap** — `allowed_files`, `acceptance`, `must_not_change` per batch |

LangGraph / Langflow back-ends are pluggable behind the same `DesignEngine` API
(`MATRIX_DESIGNER_BACKEND=crewai|langgraph|langflow|off`). A **deterministic planner** always runs
when no LLM is configured, so CI and offline use never break.

> **AI proposes; Matrix Definitions enforce.** The Design Bundle is validated against design-packs
> (`GAME-001…010`, `APP-001…`) — the brain never approves itself.

## Quickstart

```bash
pip install matrix-designer            # core (deterministic, offline)
pip install "matrix-designer[agentic,mcp]"   # + CrewAI crew + MCP server

# 1) Generate just the batches for a chosen blueprint (the batches guy)
mdesign batches --idea "An 8-episode arcade platformer for the web" \
                --blueprint blueprint.json --quality production

# 2) Or the full Design Bundle, validated
mdesign design  --idea "..." --blueprint blueprint.json -o design-bundle.json

# 3) Validate / export to Matrix Builder
mdesign validate design-bundle.json
mdesign export   design-bundle.json -o mb-export.json   # idea-request + blueprint overlay + mb next[]
```

### As an MCP server (how Matrix Builder calls it)

```bash
python -m matrix_designer.mcp_server        # stdio MCP server: matrix-designer
```

Tools: `analyze_idea · decompose_reference · propose_architecture · generate_batches ·
assemble_design_bundle · validate_design · export_to_builder`. In the Matrix Builder UI this is a
single quiet **“Design first”** toggle; the user still picks **Minimal / Standard / Production** —
but each candidate is now derived from the brain. See [`docs/MCP.md`](docs/MCP.md).

## The Design Bundle

The governed output artifact ([`schemas/design-bundle.schema.json`](schemas/design-bundle.schema.json)):
`goal_analysis · framework_decision · visual_target · architecture · contracts · asset_manifest ·
acceptance · batch_roadmap · governance · provenance` (content-addressed by `design_digest`).

A complete worked example — the brain that *would* have produced the premium Contract Quest instead
of the flat prototype — is in
[`examples/contract-quest/design-bundle.json`](examples/contract-quest/design-bundle.json).

## The ecosystem

| Project | Role |
|---|---|
| **Matrix Designer** | 🧠 the Brain — idea → governed Design Bundle (this repo) |
| **Matrix Builder** | the Contract Architect — bundle → batches → validate |
| **agent-generator** | the deterministic engine (blueprints, prompts, validation, repair) |
| **Matrix Definitions** | the Law — signed standards + design-packs |
| **GitPilot** | the Worker — a Matrix-native AI coder |
| **MatrixHub** | the Registry of validated bundles |

---

<div align="center"><sub>🧠 <b>Matrix Designer</b> · Created by <a href="https://ruslanmv.com">Ruslan Magana Vsevolodovna</a> · MIT licensed</sub></div>
