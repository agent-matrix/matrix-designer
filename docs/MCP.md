# matrix-designer-mcp — tools

Matrix Designer is exposed as an **MCP server** so Matrix Builder (or any MCP client: Claude Code,
Cursor, IBM Bob…) can invoke it **optionally** as a plugin, after a blueprint is chosen, to design
the full plan and all batches.

```bash
pip install "matrix-designer[mcp,agentic]"
python -m matrix_designer.mcp_server        # stdio server, name: "matrix-designer"
```

Register it in an MCP client (example):

```json
{
  "mcpServers": {
    "matrix-designer": { "command": "python", "args": ["-m", "matrix_designer.mcp_server"] }
  }
}
```

## Tools (1:1 with the design pipeline)

| Tool | Input | Output |
|---|---|---|
| `analyze_idea` | `idea`, `references[]` | `goal_analysis` (real goal, complexity, risks, missing decisions) |
| `decompose_reference` | `kind`, `ref` | `visual_target` + asset hints (vision LLM in agentic mode) |
| `propose_architecture` | `idea`, `blueprint` | `architecture` + entity/data `contracts` |
| **`generate_batches`** 🧩 | `idea`, `blueprint`, `quality_level` | the ordered **`batch_roadmap`** (the batches guy) |
| `assemble_design_bundle` | all of the above | full `design-bundle` + validation verdict |
| `validate_design` | `design_bundle` | `approved` / `needs-repair` / `rejected` + violations |
| `export_to_builder` | `design_bundle` | `idea_request`, `blueprint_overlay`, `mb_next_sequence[]` |

## Typical Matrix Builder flow ("Design first" toggle)

1. User describes an idea, optionally attaches an image/PDF/repo, enables **Design first**.
2. Matrix Builder calls `assemble_design_bundle(idea, blueprint, quality)` → a validated brain.
3. Matrix Builder calls `export_to_builder` → seeds its three candidates and the `mb next` sequence
   from the roadmap; each candidate carries `design_digest`.
4. The user still sees only **Minimal / Standard / Production** — but the plan underneath is the brain.

All tools also exist as plain Python callables (no MCP runtime required) for testing and embedding.
