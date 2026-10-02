# dmind interoperability

The additive dmind API converts diagrams into reviewable system designs without starting a build. All previous blueprint, bundle, review, MCP and CLI contracts remain available.

The paired DayPilot feature is named **dmind**, under **Diagrams**. See [the complete development plan](DMIND_DEVELOPMENT_PLAN.md) for delivered scope, future phases and acceptance gates.

## Quick start

```bash
mdesign diagram --topic 'Order processing system' --outline ideas.md --kind system -o order.dmind.json
mdesign diagram --topic 'Inventory web application' --designer -o design.dmind.json
mdesign diagram-bundle order.dmind.json -o proposal-with-validation.json
```

`diagram` writes a raw `dmind/v1` document. `diagram-bundle` writes the same envelope as HTTP/MCP: `bundle`, `validation`, `source_diagram_id`, `source_digest`. Extract the `bundle` member to use existing `mdesign validate` or builder importers. A successful proposal is not a build approval: inspect its validation status and report.

Use `POST /design/diagrams` with `{topic, content, kind, use_designer, candidate_id}`. Default `use_designer=false` parses an indented outline offline. Designer mode returns a system diagram of actual batches and dependencies. `kind` applies to local outline mode; a designer-generated bundle is always a system graph.

`POST /design/diagrams/import-bundle {bundle}` visualizes a schema-valid Design Bundle, preserves its original content in `metadata.design_bundle`, and reports the independently computed validation status in metadata. Missing/invalid graph IDs, unsupported versions, dangling links or branch cycles are rejected by the graph validator. Non-branch feedback loops are supported.

`POST /design/diagrams/bundle {diagram, candidate_id}` treats the complete edited graph as untrusted reference data, creates a new Design Bundle using the existing provider configuration, retains the reference/hash and returns its independently computed verdict. Diagram metadata cannot confer approval; even an unchanged original bundle is not reused as an approved edited design. The deterministic fallback produces its existing scaffold roadmap, with the full graph retained as reference; it does not claim semantic compilation of arbitrary algorithms.

MCP tools: `generate_diagram(topic, content, kind, use_designer, candidate_id)` and `design_from_diagram(diagram, candidate_id)`.

All HTTP routes use the existing optional `MATRIX_DESIGNER_API_KEY` protection. Outline mode makes no provider call; designer mode follows the same provider guard as existing design endpoints.

The packaged schema is `_data/schemas/dmind.schema.json`; [the golden order-system fixture](../examples/dmind/order-system.dmind.json) is mirrored in DayPilot. Both validators enforce encoded JSON and graph limits, unique IDs, existing endpoints and forest constraints in addition to the JSON Schema. Keep these validators and fixtures synchronized in cross-repository changes.
