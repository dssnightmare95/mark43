"""CLI used by Claude Code hooks to inject human-activity context.

Usage (from a hook `command`):
    python -m action_capture.integrations.context_hook inject
    python -m action_capture.integrations.context_hook checkpoint

`inject` prints a compact, bounded markdown summary of what the human did
since the last checkpoint (file changes with short diffs + an action summary),
then advances the checkpoint. Empty output means "nothing to inject".

`checkpoint` just advances the checkpoint (used on the Stop hook, when the AI
finishes, so the next window excludes the AI's own edits).

The log path follows ACTION_CAPTURE_LOG / ACTION_CAPTURE_HOME, else
~/.action_capture/events.jsonl — the same resolution the MCP server and daemon
use, so all three agree.
"""

import sys
import argparse

from ..mcp import store

MAX_FILES = 10          # files listed in the injection
MAX_DIFF_LINES = 30     # diff lines per file in the injection


def _format_actions(actions):
    if not actions:
        return ""
    s = store.summarize(actions)
    types = ", ".join(f"{k}x{v}" for k, v in s["by_event_type"].items())
    procs = ", ".join(list(s["by_process"].keys())[:5])
    tail = f" - in {procs}" if procs else ""
    return f"**Input actions:** {types}{tail}"


def build_injection(events):
    """Return a bounded markdown summary, or "" if there's nothing to say."""
    if not events:
        return ""
    file_changes = [e for e in events if e.get("event_type") == "file_change"]
    actions = [e for e in events if e.get("event_type") != "file_change"]

    lines = ["## Human activity since your last turn", ""]
    if file_changes:
        lines.append(f"**Files changed ({len(file_changes)}):**")
        for e in file_changes[:MAX_FILES]:
            f = e.get("file", {})
            lines.append(f"- `{f.get('path')}` ({f.get('change')})")
            diff = e.get("diff")
            if diff:
                dl = diff.splitlines()[:MAX_DIFF_LINES]
                lines.append("```diff")
                lines.extend(dl)
                lines.append("```")
        if len(file_changes) > MAX_FILES:
            lines.append(f"- ...and {len(file_changes) - MAX_FILES} more")
        lines.append("")

    action_line = _format_actions(actions)
    if action_line:
        lines.append(action_line)
    return "\n".join(lines).strip()


def _run(mode):
    log = store.DEFAULT_LOG
    if mode == "checkpoint":
        store.set_checkpoint(log, label="turn-boundary")
        return

    cp = store.get_checkpoint(log)
    # Filter by timestamp, not seq: seq resets when the daemon restarts.
    since_time = cp["timestamp"] if cp else None
    events = store.read_events(log, since_time=since_time)
    out = build_injection(events)
    if out:
        print(out)
    # Advance the checkpoint so the next injection is incremental even if the
    # Stop hook doesn't fire.
    store.set_checkpoint(log, label="prompt-submit")


def main(argv=None):
    # Force UTF-8 stdout: window titles / paths may contain characters the
    # console codepage can't encode, which would otherwise crash the hook.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(prog="context_hook")
    ap.add_argument("mode", choices=["inject", "checkpoint"])
    args = ap.parse_args(argv)

    # Consume the hook JSON payload from stdin without failing if absent.
    try:
        sys.stdin.read()
    except Exception:
        pass

    # A hook must never break the user's turn: swallow any error and exit 0.
    try:
        _run(args.mode)
    except Exception as exc:
        print(f"[context_hook] skipped: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
