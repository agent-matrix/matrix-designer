# Client-first plan — make the Blueprint Details workspace API-optional

## The problem with the previous plan

The integration (batches `00`–`12`) wired the Blueprint Details page through a **3-hop API chain**:

```
browser ─▶ control-plane /api/v1/blueprints/* ─▶ designer HTTP service ─▶ LangGraph brain
```

Even with a deterministic fallback at every hop, this couples a *live* design workspace to a backend:

- **Every hop is a connection that can refuse.** (The `ERR_CONNECTION_REFUSED` seen when driving the
  page headlessly is exactly this — the app reached for an API base that wasn't running.)
- **Static hosting has no backend.** The arcade games ship on **GitHub Pages**; a Pages-hosted
  Blueprint workspace can't call a control plane at all.
- **Latency on every keystroke-to-plan.** A "the plan evolves as you type" feel shouldn't wait on
  three network round-trips.
- **Config surface explodes.** Base URLs, CORS, auth headers, service discovery — each a failure mode.

The fallbacks made it *not crash*, but the architecture is still API-first.

## The fix: one client state object, AI + persistence as progressive enhancements

Invert the dependency. The page is a **self-contained client workspace** backed by a single live
state object (`BlueprintDetailsState`). All mutations happen locally in a **browser-bundled engine**;
the LLM and the server are **optional enhancements** that, when reachable, refine the local result —
never a requirement.

```
            ┌─────────────────────────────────────────────┐
 user chat ─▶│  blueprintStore  (single source of truth)   │─▶ every section renders
            │  + blueprint-engine (deterministic, in-browser)│
            └───────────────┬──────────────┬────────────────┘
                            │ optional      │ optional
                     LLM refine (any        server sync /
                     provider, 1 call)      persistence
```

- **Works fully offline / on GitHub Pages** — zero network needed.
- **Instant** — chat mutations apply locally first, then optionally get refined.
- **The 3-hop chain becomes optional**: the control-plane proxy + designer service stay as a *sync /
  enhancement* target behind a capability check, not a hard dependency.

## The new batches (client-first, API-optional)

| # | Batch | Purpose | No-API acceptance |
|---|---|---|---|
| **C0** | **Client state model** | `BlueprintDetailsState` + `blueprintStore` (the single source of truth) | sections render from the store with no fetch |
| **C1** | **Browser blueprint-engine** | TS port of the deterministic brain: `generate(idea)`, `apply(state, instruction)` → `{state, reply, updatedSections}` (insert/rename/reorder/split batches; update architecture, file plan, design brain) | pure functions; no network; unit-tested |
| **C2** | **Wire Details to store+engine** | chat calls `apply()` locally → sections patch instantly; remove the hard `fetch` from the render path | airplane mode: type "add a boss level" → batch appears, no request |
| **C3** | **Optional AI enhancement** | `refineWithAI(state, instruction)` does **one** call to OllaBridge/any provider; on timeout/error returns the local result | provider down → local result stands, UI never blocks |
| **C4** | **localStorage-first persistence** | autosave `BlueprintDetailsState` per build to localStorage; `Unsaved`/save reflect local state | reload restores the workspace with no server |
| **C5** | **Optional server bridge** | the existing `/api/v1/blueprints/*` becomes an *optional* sync/enhancement target behind `capabilities()` | with a server: syncs; without: identical UX |
| **C6** | **Proof: fully offline workspace** | e2e: load with network blocked → generate, chat-edit, persist, reload — all green | no request leaves the page |

### What changes vs. the old plan

- **Old C-path** `02/03/04/05` (control-plane proxy, typed client, candidates/details fetch) are
  **demoted to optional** (`C5`). They still exist and add value with a backend, but the page no
  longer *depends* on them.
- The brain's deterministic logic moves **into the browser** (`C1`) — the same tiered roadmap +
  refine semantics already shipped in `blueprint-client.ts`'s local derivation, promoted to a real
  engine module and made the primary path.
- The LLM is reached **directly and optionally** through the existing OllaBridge client (`C3`) — one
  hop, provider-agnostic — instead of a mandatory 3-hop chain.

### Why this is the right shape

It matches the product intent — *a live design workspace, not a static mockup* — **without** an API
dependency: the workspace is instant and offline by default, and gets *better* (shared, AI-refined,
cross-device) when a backend and a model happen to be available. Governance is unchanged: the
client engine emits the same governed `design-bundle`, still validated by the rule catalog.
