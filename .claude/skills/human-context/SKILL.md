---
name: human-context
description: >
  Use when the user implies they changed something themselves (edited a file,
  drew, adjusted a setting, "I just...", "look at what I did", "I moved/renamed",
  "check my changes") or when you're about to edit a file the human may have
  touched. Pulls the human's recent actions and file changes from the
  action-capture MCP so you act on the current state, not a stale one.
---

# Human context (action-capture)

An MCP server named `action-capture` records what the human does between your
turns — file changes (with diffs) and input actions (clicks, typing, app
focus). A hook already injects a short summary on each prompt, but use these
tools when you need detail or the summary wasn't enough.

## When to query

- The user references work they did ("I fixed X", "I renamed the function",
  "see my edits", "I changed the diagram").
- Before editing a file, to check whether the human just modified it.
- When the user's request only makes sense given something they did in another
  app (e.g. exported from SolidWorks, edited an image, changed a setting).

## Tools

- `get_changes_since_last_turn()` — start here. File changes (the *what*, with
  diffs) plus an action summary (the *how*) since the last checkpoint.
- `get_file_changes(since_seq, limit)` — just the file changes/diffs.
- `get_window_timeline(since_time, limit)` — which app/window (GUI) was active
  over time, with dwell durations. Use for "what apps did I use", "which window
  was I in", "how long was I on X".
- `list_actions(since_seq, since_time, process, event_types, limit)` — filtered
  raw actions; use `process` to focus on one app (e.g. `"Code.exe"`).
- `summarize_session()` — high-level counts for the whole session.
- `checkpoint(label)` — call after you finish acting, so the next query shows
  only what the human did next. (The Stop hook also does this automatically.)

## How to use the result

- Treat file diffs as the source of truth for *what changed*; re-read the file
  if you need full context.
- Use the action timeline to understand *how* and *why* (e.g. the human
  selected text then deleted it, or dragged on a canvas).
- Don't dump the raw events back to the user — summarize what they did and act
  on it.
