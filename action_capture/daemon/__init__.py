"""Daemon lifecycle: single-instance guard, session refcount, and launcher.

Ensures exactly ONE capture process runs regardless of how many AI sessions
are open. Each MCP server registers itself as a session; the daemon shuts
down once no live session remains.
"""
