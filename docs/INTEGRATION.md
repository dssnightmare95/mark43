# Integrations: wiring action-capture into an AI assistant

The MCP server is standard, so it works for both Claude Code and Codex. The
difference is how each client *auto-injects* context and starts the daemon.

Log-path convention: with no `ACTION_CAPTURE_LOG` set, the MCP server, the
hooks and the spawned daemon all default to `./dataset/events.jsonl` relative
to the working directory — so as long as the client runs from the project
root, everything agrees. Set `ACTION_CAPTURE_LOG` (absolute) to override.

## Claude Code (fully wired in this repo)

Already configured:

- `.mcp.json` — registers the `action-capture` MCP server. On session start
  the server registers a session and (Windows) spawns the single capture
  daemon; on close it deregisters and the daemon stops when the last session
  goes away.
- `.claude/settings.json` — two hooks:
  - `UserPromptSubmit` → `context_hook inject`: injects a compact summary of
    the human's file changes + actions since the last turn.
  - `Stop` → `context_hook checkpoint`: marks the turn boundary when you finish,
    so the next injection only covers the human's subsequent work (not your
    own edits).
- `.claude/skills/human-context/SKILL.md` — tells the assistant when to call
  the MCP tools for detail beyond the injected summary.

Nothing else to do: open the project in Claude Code and approve the server.

## Codex

Codex speaks MCP but has no `UserPromptSubmit`/`Stop` hooks, so there is no
automatic injection — the agent calls the tools itself, guided by `AGENTS.md`.

1. Register the MCP server in `~/.codex/config.toml`:

   ```toml
   [mcp_servers.action-capture]
   command = "python"
   args = ["-m", "action_capture.mcp"]
   # Make the package importable and pin the log if Codex's cwd isn't the repo:
   env = { PYTHONPATH = "C:/path/to/mark43", ACTION_CAPTURE_LOG = "C:/path/to/mark43/dataset/events.jsonl" }
   ```

2. Add an instruction block to the project's `AGENTS.md` so the agent queries
   changes between turns:

   ```markdown
   ## Human activity
   An `action-capture` MCP server records what I do between your turns. When I
   reference something I changed, or before editing a file I may have touched,
   call `get_changes_since_last_turn` (file diffs + action summary). Call
   `checkpoint` after you finish acting.
   ```

Because there's no Stop hook, attribution relies on the agent calling
`checkpoint` after acting (or on the per-prompt checkpoint that `inject`
performs on Claude Code). This is the main gap versus the Claude Code path.

## Notes

- Capture is Windows-only (win32 + UIA). On other platforms the MCP server
  still reads an existing log, but nothing is captured.
- The `.mcp.json` daemon auto-start only spawns on Windows.
