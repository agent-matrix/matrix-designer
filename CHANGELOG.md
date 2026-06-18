# Changelog

## 0.3.0 — Designer HTTP service (batch-01)
- New `matrix_designer.service` (FastAPI): `POST /design/blueprints`, `POST /design/refine`,
  `GET /healthz` — the brain over HTTP for Matrix Builder's control plane, alongside the MCP
  server. Core handlers are plain functions (testable without FastAPI).
- watsonx-only `provider_guard`: a non-approved LLM provider is refused; deterministic runner
  answers when none is set. `[service]` extra + `matrix-designer-service` entry point.

## 0.2.0 — LangGraph multi-agent brain
- New **LangGraph `StateGraph`** of specialist agents (Planner → Requirements → Architect →
  UI/UX → Batch Planner → Quality → Synthesizer) that designs the **top-3 blueprints**
  (Minimal → Standard → Production, simplest → hardest) and populates the full Blueprint
  Details (overview, architecture, batches, file plan, Matrix rules) in one run.
- **Orchestrator chat** (`refine`) — human-in-the-loop modifications ("add a boss level",
  "reduce scope", "add audit logging"); the contract changes only on save.
- New MCP tools `generate_blueprints` + `refine_design`; CLI `mdesign blueprints` + `mdesign chat`.
- BlueprintDetails data model matching the Matrix Builder Details page; deterministic runner
  fallback so the brain always runs offline. `docs/AGENTS.md` documents the topology.

## 0.1.0 — first commit
- The Brain of the Matrix ecosystem: idea + chosen blueprint → governed **Design Bundle**.
- Agentic design engine (CrewAI crew: Goal Analyst → Architect → Visual Director → Batch Planner),
  with a deterministic offline fallback and pluggable LangGraph/Langflow backends.
- `matrix-designer-mcp` server (7 tools) — usable as a plugin in Matrix Builder.
- `design-bundle.schema.json` governed artifact; `mdesign` CLI; design-packs; design-rule validator
  (AI proposes, Matrix Definitions enforce); worked Contract Quest example.
