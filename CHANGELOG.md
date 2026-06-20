# Changelog

## 0.6.2 — packaging fix + CI + service hardening (non-breaking)
- **Fix `pip install matrix-designer`** (critical): the schema and design-packs now ship
  **inside the package** (`matrix_designer/_data`) via `package-data`, so a wheel install no
  longer crashes `validate`/`verdict` with `FileNotFoundError` and no longer silently degrades
  packs to `generic-v1` (0 rules). A new `_resources.py` resolver finds the data in the wheel,
  via `MATRIX_DESIGNER_DATA`/`MATRIX_DESIGNER_PACKS`, or the legacy repo-root — editable
  checkouts and existing deployments are unchanged.
- **CI** (`.github/workflows/ci.yml`): ruff + pytest on Python 3.10–3.12, plus a **wheel-smoke**
  job that installs the built wheel in a clean env and asserts the schema + packs are packaged
  (the gate that catches this class of bug). Added a `[tool.ruff]` config.
- **Service hardening (all default-off; production behaviour unchanged):** typed request models
  (empty/oversized `idea` → `422`), an empty-idea guard in the core handlers, and optional
  `MATRIX_DESIGNER_API_KEY` auth + `MATRIX_DESIGNER_CORS_ORIGINS`. Documented the trust boundary.
- **Robust agentic parsing:** LLM `batch_roadmap` JSON with extra/loose keys no longer raises
  (filtered + coerced); added unit tests for the previously-untested agentic parse path.
- Added a standalone **`Dockerfile`** and a packaging-regression test. Version → 0.6.2.

## 0.6.1 — Makefile + version fix
- Add a Makefile: `make install` / `make test` / `make run` (HTTP service) / `make run-mcp` — servers
  ready in three commands. README documents it and the Hugging Face co-deployment.
- Fix the in-process `__version__` (health endpoint) to match the package version.

## 0.6.0 — Integration shipped (batch-12)
- Matrix Designer is wired end-to-end into Matrix Builder's Blueprint Details page: real
  multi-agent output (overview, architecture, batches, file plan, Matrix rules), a Design Brain
  panel, and a live Talk-to-blueprint chat — with a deterministic fallback at every hop.
- docs/INTEGRATION_ROADMAP.md marked 00-11 done (09 dropped: provider-agnostic); README gains a
  "Live in Matrix Builder" section with before/after screenshots (docs/img/).

## 0.5.0 — provider-agnostic + E2E proof (batch-11)
- Provider-agnostic: Matrix Designer works with OllaBridge or ANY LLM provider. The watsonx-only
  guard is relaxed to an optional operator allow-list (MATRIX_DESIGNER_ALLOWED_PROVIDERS); unset
  allows all. (Skips the watsonx-only governance.)
- batch-11 E2E proof (tests/e2e/test_design_to_build.py): Contract Quest idea → multi-agent design
  → approved bundle → ordered, scoped, acyclic mb-next sequence targeting a real Phaser/Vite project.

## 0.4.0 — Design rules as signed packs (batch-08)
- Formalize the rule catalog in `packs/*/rules.yaml`: DESIGN-* (cross-domain), GAME-* (web-game),
  APP-* (saas). New `rules.py` loader is one source of truth; `validate.py` adds DESIGN-005
  (acyclic dependency graph) and surfaces `rules_catalog` in the verdict.
- Tests: unscoped batch → rejected; game without visual acceptance → needs-repair; dependency
  cycle → needs-repair. `docs/GOVERNANCE.md` documents the families (to be promoted to
  matrix-definitions).

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
