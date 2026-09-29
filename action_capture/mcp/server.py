"""MCP server exposing the human's captured action timeline to an AI.

Reads the shared JSONL log and, on startup, registers a session and ensures
the single capture daemon is running (releasing on exit via refcount).

Run:  python -m action_capture.mcp        (stdio transport)

The log path follows ACTION_CAPTURE_LOG / ACTION_CAPTURE_HOME, else
~/.action_capture/events.jsonl.
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
def get_file_changes(since_seq: Optional[int] = None,
                     limit: int = 100) -> dict:
    """File changes the human made (the effect layer).

    Returns `file_change` events (created/modified/deleted) with a unified diff
    for text files. `since_seq` bounds the range; defaults to the last
    checkpoint if one is set.
    """
    if since_seq is None:
        cp = store.get_checkpoint()
        since_seq = cp["seq"] if cp else None
    events = store.read_events(since_seq=since_seq,
                               event_types=["file_change"], limit=limit)
    return {"count": len(events), "changes": events}


@mcp.tool()
def get_changes_since_last_turn(limit: int = 300) -> dict:
    """Everything the human did since the last checkpoint: the headline tool.

    Combines the file changes (what changed, with diffs) and a summary of the
    input actions (how it was done). Call `checkpoint()` after you act so this
    reflects only the human's subsequent work.
    """
    cp = store.get_checkpoint()
    since_seq = cp["seq"] if cp else None
    all_events = store.read_events(since_seq=since_seq, limit=limit)
    file_changes = [e for e in all_events if e.get("event_type") == "file_change"]
    actions = [e for e in all_events if e.get("event_type") != "file_change"]
    return {
        "checkpoint": cp,
        "file_changes": file_changes,
        "actions_summary": store.summarize(actions),
        "actions": actions,
    }


@mcp.tool()
def summarize_session() -> dict:
    """High-level summary of the whole session: counts by type and by app."""
    return store.summarize(store.read_events(limit=None))


def main():
    # Register this session and ensure a single capture daemon is running.
    # On exit, deregister so the daemon can stop when the last session closes.
    import atexit
    from ..daemon import launcher

    log_path = store.DEFAULT_LOG
    session_id = launcher.acquire_session(log_path)
    atexit.register(launcher.release_session, log_path, session_id)

    mcp.run()


if __name__ == "__main__":
    main()
