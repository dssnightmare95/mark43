# Improvements backlog

Status: the core flow (F1–F4 + installer + auto-consult) is functionally
complete. This tracks what's left, prioritized.

## 🔴 Should do before calling it "done"

### 1. Log rotation / size limit
The daemon is global and always-on, appending to a single
`~/.action_capture/events.jsonl` that **grows unbounded**. With unfiltered
capture this fills up fast. Add rotation by size/date (or prune old events),
and make readers (MCP, hooks) rotation-aware.

## 🟡 Robustness / quality

### 2. Human vs AI attribution on file changes
`get_file_changes` (whole-session, path-filtered) also returns edits the AI
made, not just the human's. The checkpoint windowing only separates them in
the per-turn flow; historical/file-centric queries don't. Currently heuristic —
consider tagging changes by whether human input events surround them.

### 3. Automated tests
Everything was verified manually. Add tests for the pure functions:
`mcp/store`, `effects/differ`, `labeling/classify`, `daemon/coordination`.

### 4. Assistant daemon doesn't capture selected text or a11y snapshots
The launcher starts the daemon with default flags (no `--capture-text`,
no `--a11y-snapshot`). If that extra context is wanted in the assistant flow,
make these configurable from the installer / an env var.

## 🟢 Future features (F5+)

### 5. Per-app adapters
SolidWorks API, Photoshop layers, Excel cells — the semantic "what changed"
for apps where the filesystem isn't enough.

### 6. OCR for canvas
Read text from a cropped region where UI Automation is blind (canvas, games).

### 7. PII redaction beyond passwords
Regex-based masking for cards, emails, tokens.

### 8. watchdog instead of polling
Replace the polling `EffectsAgent` with event-based `watchdog` for performance
on large repositories.

## Open diagnostic (verify, not implement)

Confirm **why Codex didn't see the changes**: the missing instruction (fixed by
the `~/.codex/AGENTS.md` block) vs. capture scope (the file was outside the
session's `cwd`, so the effect watcher never saw it). Inspect
`~/.action_capture/events.jsonl` for the expected `file_change` events.
