# Integrations: wiring action-capture into an AI assistant

The MCP server is standard and both Claude Code and Codex support the same hook
events (`UserPromptSubmit`, `Stop`, ...), so the integration is symmetric.

## One-command setup

```bash
python install.py        # or double-click install.bat on Windows
```

It installs the package + dependencies (`pip install -e .`) and registers the
`action-capture` MCP server and the activity hooks **globally**, so they work
in every project:

- **Codex** → `~/.codex/config.toml` (MCP server) + `~/.codex/hooks.json`
  (`UserPromptSubmit` → inject, `Stop` → checkpoint).
- **Claude Code** → `~/.claude/settings.json` (hooks) + the MCP server via
  `claude mcp add -s user`.

All edits are merged, backed up (`.bak`), and idempotent. Flags: `--dry-run`,
`--no-install`, `--skip-codex`, `--skip-claude`. Config locations honor
`CODEX_HOME` / `CLAUDE_CONFIG_DIR`. Restart the client afterwards.

## Shared log

Everything reads/writes one user-level log: `~/.action_capture/events.jsonl`
(override with `ACTION_CAPTURE_LOG`, or the dir with `ACTION_CAPTURE_HOME`).
One human, one timeline, one daemon — across every tool and project. The
effect layer still scopes file-watching to each session's project directory.

## Project-scoped alternative (no global footprint)

If you'd rather not touch global config, the repo also ships project-scoped
files that work when you open *this repo* in either client:

- Claude Code: `.mcp.json` + `.claude/settings.json`
- Codex: `.codex/config.toml` + `.codex/hooks.json` (trust the project first)

You still need the package importable (`pip install -e .`, or `python -m` with
`PYTHONPATH`). **Use either the installer *or* the project files, not both** —
otherwise the hooks fire twice in this repo (duplicate injected context).

## How the turn loop works

1. You finish a turn → `Stop` hook runs `context_hook checkpoint`, marking the
   boundary "AI done, human's turn starts".
2. The human edits files / clicks / types (captured by the daemon).
3. Next prompt → `UserPromptSubmit` hook runs `context_hook inject`, which
   prints a compact summary (file diffs + action summary) since that
   checkpoint. Its stdout is added to the model context.
4. For detail beyond the summary, the assistant calls the MCP tools
   (`get_changes_since_last_turn`, etc.), guided by the `human-context` skill
   (Claude) or an `AGENTS.md` note (Codex).

The `Stop` checkpoint is what keeps the AI's own edits out of the next
injection window.

## Notes

- Capture is Windows-only (win32 + UIA). On other platforms the MCP server can
  still read an existing log, but nothing is captured and the daemon won't
  auto-start.
