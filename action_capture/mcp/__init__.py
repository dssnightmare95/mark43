"""MCP integration: exposes the captured action timeline to AI assistants.

`store`  - reads/filters the JSONL log and tracks checkpoints (pure, testable).
`server` - the FastMCP server that wires those functions to MCP tools.

Run the server with:  python -m action_capture.mcp
"""
