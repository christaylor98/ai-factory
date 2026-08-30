"""
ai-factory MCP server.

Exposes ai-factory's library API over the Model Context Protocol (stdio).
"""
from .server import mcp, main

__all__ = ["mcp", "main"]
