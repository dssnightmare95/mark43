"""FastMCP server exposing the human's captured action timeline to an AI.

Phase 1: read-only over the existing JSONL log. Daemon auto-start and the
effect layer (file diffs) come in later phases.

Run:  python -m action_capture.mcp        (stdio transport)

Configure the log path via the ACTION_CAPTURE_LOG environment variable in the
MCP client config; otherwise it defaults to ./dataset/events.jsonl.
"""

from typing import Optional

# The server class was renamed between MCP SDK majors; support both.
try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
except ModuleNotFoundError:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server

from . import store

mcp = _Server("action-capture")


@mcp.tool()
def checkpoint(label: str = "") -> dict:
    """Mark a turn boundary at the current end of the action log.

    Call this after you finish acting, so a later
    `get_actions_since_last_checkpoint` returns only what the human did next.
    Returns the recorded checkpoint {seq, timestamp, label}.
    """
    return store.set_checkpoint(label=label)


@mcp.tool()
def get_actions_since_last_checkpoint(process: Optional[str] = None,
                                      limit: int = 500) -> dict:
    """What the human did since the last checkpoint (the key context tool).

    Returns a compact summary plus the matching events (most recent `limit`).
    If no checkpoint has been set, returns everything so far. Optionally filter
    by `process` (e.g. "Code.exe").
    """
    events = store.actions_since_checkpoint(process=process, limit=limit)
    return {"summary": store.summarize(events), "events": events,
            "checkpoint": store.get_checkpoint()}


@mcp.tool()
def list_actions(since_seq: Optional[int] = None,
                 since_time: Optional[str] = None,
                 until_time: Optional[str] = None,
                 process: Optional[str] = None,
                 event_types: Optional[list[str]] = None,
                 limit: int = 200) -> dict:
    """Query the action log with filters.

    - `since_seq` / `since_time` / `until_time`: bound the range.
    - `process`: only events in that foreground app (e.g. "chrome.exe").
    - `event_types`: subset of
      click, drag, scroll, key, hotkey, text_input, window_focus.
    - `limit`: keep the most recent N after filtering.
    """
    events = store.read_events(
        since_seq=since_seq, since_time=since_time, until_time=until_time,
        process=process, event_types=event_types, limit=limit)
    return {"summary": store.summarize(events), "events": events}


@mcp.tool()
def summarize_session() -> dict:
    """High-level summary of the whole session: counts by type and by app."""
    return store.summarize(store.read_events(limit=None))


def main():
    mcp.run()


if __name__ == "__main__":
    main()
