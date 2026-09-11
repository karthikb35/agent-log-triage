"""MCP integration for the triage tools.

The tools themselves live in :mod:`triage.mcp.tools` as plain, deterministic
functions. :func:`build_server` wraps them in a real Model Context Protocol
server when the optional ``mcp`` extra is installed.
"""

from .tools import TOOLS  # noqa: F401

__all__ = ["TOOLS"]
