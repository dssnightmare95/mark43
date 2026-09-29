# Integrations: wiring action-capture into an AI assistant

action-capture is a **user-level** tool: one daemon captures your input, file
changes and UI context across every app and project into a single log
(`~/.action_capture/events.jsonl`). So all of its configuration is registered
**globally**, and the installer is the single source of truth — the repo ships
only source code, no per-project config to keep in sync or duplicate.

Both Claude Code and Codex support the same MCP protocol and the same hook
events (`UserPromptSubmit`, `Stop`), so the setup is symmetric.

## Setup

```bash
python install.py        # or double-click install.bat on Windows
python install.py --uninstall   # remove everything it added
```

`install.py`:

- runs `pip install -e .` (dependencies + the `action_capture` package);
- **Codex** → registers the MCP server in `~/.codex/config.toml`, the hooks in
  `~/.codex/hooks.json`, and an instruction block in `~/.codex/AGENTS.md` (so
  Codex knows to consult the MCP automatically — its equivalent of the skill);
- **Claude Code** → writes the hooks to `~/.claude/settings.json`, registers
  the MCP server via `claude mcp add -s user`, and installs the
  `human-context` skill into `~/.claude/skills/`.

Edits are merged, backed up (`.bak`), and keyed by a stable marker, so
re-running (e.g. after a Python upgrade) **replaces rather than duplicates**.
`--uninstall` removes exactly those entries. Flags: `--dry-run`, `--no-install`,
`--skip-codex`, `--skip-claude`. Config locations honor `CODEX_HOME` /
`CLAUDE_CONFIG_DIR`.

Restart the client afterwards so it reloads the config.

## Shared log

Everything reads/writes one user-level log: `~/.action_capture/events.jsonl`
(override with `ACTION_CAPTURE_LOG`, or the directory with
`ACTION_CAPTURE_HOME`). One human, one timeline, one daemon — across every tool
and project. The effect layer still scopes file-watching to each session's
project directory.

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

## Making it automatic

You should not have to say "check the MCP" — asking *"what did I change in
X.py?"* should be enough. Two layers make that work:

- **Passive injection** (both clients): the `UserPromptSubmit` hook injects a
  summary of recent changes every turn, so common cases need no tool call.
- **Active lookup**: for a specific file or a change from earlier in the
  session, the assistant calls `get_file_changes(path=...)`. It knows to do so
  from the `human-context` skill (Claude) or the `~/.codex/AGENTS.md` block
  (Codex) — both installed by `install.py` — reinforced by the tool
  descriptions. `get_file_changes` searches the **whole session**, not just the
  last turn, so late questions still work.

## Notes

- Capture is Windows-only (win32 + UIA). On other platforms the MCP server can
  still read an existing log, but nothing is captured and the daemon won't
  auto-start.
