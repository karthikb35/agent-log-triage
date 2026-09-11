# MCP Tools

The **Model Context Protocol (MCP)** gives agents a single, typed, sandboxed way to
reach the outside world instead of scattering database calls and API clients
through the code. This platform exposes its triage capabilities as MCP tools.

## The tools — `mcp/tools.py`

Every tool is a **pure, deterministic** function with a JSON-serialisable
signature, ready to publish as an MCP tool schema.

| Tool | Signature | Purpose |
| --- | --- | --- |
| `lookup_runbook` | `(category: str) -> {probable_cause, runbook}` | Map a failure category to institutional remediation knowledge. |
| `query_failures` | `(failures, service?, category?) -> failures` | Filter the failure set for an agent that wants a slice. |
| `open_ticket` | `(incident, dry_run=True) -> ticket` | Create (or simulate) a tracking ticket. Side effects gated behind `dry_run=False`. |

!!! note "Safe by default"
    `open_ticket` runs in **dry-run** unless explicitly told otherwise, so a triage
    run never has surprising side effects. Determinism and safety are the same
    property here.

## Why route knowledge through a tool?

The runbook mapping *could* be an `if` chain inside the root-cause agent. Putting it
behind `lookup_runbook` means:

- the **same** knowledge base serves the automated Job **and** an engineer's
  MCP-aware IDE;
- the agent's code stays about *orchestration*, not *content*;
- you can swap the static table for a real knowledge base (a wiki, a vector store)
  without touching a single agent.

## Optional: a real MCP server — `mcp/server.py`

The functions are usable directly (that is what the agents do). Installing the
optional extra publishes them over MCP:

```bash
pip install "agentic-log-triage[mcp]"
python -m triage.mcp.server
```

`build_server()` wraps each function with `FastMCP(...).tool()`. If the `mcp`
package is absent, the module still imports and raises a clear, actionable error
only when you try to start the server — the triage engine never depends on it.
