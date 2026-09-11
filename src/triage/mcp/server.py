"""Optional Model Context Protocol server exposing the triage tools.

Run with::

    python -m triage.mcp.server        # requires the `mcp` extra

If the ``mcp`` package is not installed this module still imports; it simply
raises a clear error when you try to start the server. The triage engine never
requires it -- the agents call the underlying functions directly.
"""

from __future__ import annotations

from typing import Any

from .tools import lookup_runbook, open_ticket, query_failures


def build_server() -> Any:
    """Build a FastMCP server that publishes the triage tools.

    Raises ``RuntimeError`` with an actionable message if the optional
    dependency is missing.
    """

    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised only without extra
        raise RuntimeError(
            "The MCP server needs the optional 'mcp' extra. "
            "Install it with: pip install 'agentic-log-triage[mcp]'"
        ) from exc

    server = FastMCP("triage-tools")

    # Re-export each deterministic tool as an MCP tool with the same signature.
    server.tool()(lookup_runbook)
    server.tool()(query_failures)
    server.tool()(open_ticket)
    return server


def main() -> None:  # pragma: no cover - runtime entrypoint
    build_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
