#!/usr/bin/env python3
"""One-shot installer for the action-capture assistant integration.

Clone the repo and run:

    python install.py

It will:
  1. Install the package and its dependencies (pip install -e .).
  2. Register the `action-capture` MCP server + activity hooks globally for
     Codex (~/.codex/config.toml, ~/.codex/hooks.json) and Claude Code
     (~/.claude/settings.json, plus the MCP server via the `claude` CLI).

All edits are merged (never clobbered), backed up (.bak), and idempotent.

Flags:
    --dry-run       show what would change, write nothing
    --no-install    skip `pip install -e .`
    --skip-codex    don't touch Codex config
    --skip-claude   don't touch Claude config

Config locations honor CODEX_HOME and CLAUDE_CONFIG_DIR if set.
"""

import os
import sys
import json
import shutil
import argparse
import subprocess

REPO = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable  # exact interpreter, so configs don't depend on PATH

INJECT = f'"{PY}" -m action_capture.integrations.context_hook inject'
CHECKPOINT = f'"{PY}" -m action_capture.integrations.context_hook checkpoint'


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def log(msg):
    print(msg)


def backup(path):
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def add_command_hook(hooks_root, event, command):
    """Add {event: [{hooks:[{type:command, command}]}]} if not already there.

    Returns True if it added something. `hooks_root` is the object that holds
    the "hooks" key (Claude settings.json or Codex hooks.json).
    """
    events = hooks_root.setdefault("hooks", {}).setdefault(event, [])
    for group in events:
        for h in group.get("hooks", []):
            if h.get("command") == command:
                return False
    events.append({"hooks": [{"type": "command", "command": command}]})
    return True


# --------------------------------------------------------------------------
# steps
# --------------------------------------------------------------------------
def pip_install(dry):
    log("\n[1/3] Installing package + dependencies (pip install -e .)")
    if dry:
        log("      (dry-run) would run: pip install -e .")
        return
    subprocess.check_call([PY, "-m", "pip", "install", "-e", "."], cwd=REPO)


def configure_codex(dry):
    log("\n[2/3] Codex")
    codex_dir = os.environ.get("CODEX_HOME") or os.path.join(
        os.path.expanduser("~"), ".codex")
    cfg = os.path.join(codex_dir, "config.toml")
    hooks = os.path.join(codex_dir, "hooks.json")

    # -- MCP server (config.toml): append the block if absent --------------
    block = (
        "\n[mcp_servers.action-capture]\n"
        f"command = '{PY}'\n"
        'args = ["-m", "action_capture.mcp"]\n'
    )
    existing = ""
    if os.path.exists(cfg):
        with open(cfg, "r", encoding="utf-8") as f:
            existing = f.read()
    if "[mcp_servers.action-capture]" in existing:
        log(f"      config.toml: MCP already registered ({cfg})")
    elif dry:
        log(f"      (dry-run) would append MCP block to {cfg}")
    else:
        os.makedirs(codex_dir, exist_ok=True)
        backup(cfg)
        with open(cfg, "a", encoding="utf-8") as f:
            f.write(block)
        log(f"      config.toml: MCP registered -> {cfg}")

    # -- hooks.json --------------------------------------------------------
    data = load_json(hooks)
    changed = add_command_hook(data, "UserPromptSubmit", INJECT)
    changed |= add_command_hook(data, "Stop", CHECKPOINT)
    if not changed:
        log(f"      hooks.json: already configured ({hooks})")
    elif dry:
        log(f"      (dry-run) would write hooks to {hooks}")
    else:
        os.makedirs(codex_dir, exist_ok=True)
        backup(hooks)
        with open(hooks, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        log(f"      hooks.json: UserPromptSubmit+Stop -> {hooks}")


def configure_claude(dry):
    log("\n[3/3] Claude Code")
    claude_dir = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude")
    settings = os.path.join(claude_dir, "settings.json")

    # -- hooks (settings.json) --------------------------------------------
    data = load_json(settings)
    changed = add_command_hook(data, "UserPromptSubmit", INJECT)
    changed |= add_command_hook(data, "Stop", CHECKPOINT)
    if not changed:
        log(f"      settings.json: hooks already configured ({settings})")
    elif dry:
        log(f"      (dry-run) would write hooks to {settings}")
    else:
        os.makedirs(claude_dir, exist_ok=True)
        backup(settings)
        with open(settings, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        log(f"      settings.json: UserPromptSubmit+Stop -> {settings}")

    # -- MCP server via the claude CLI (user scope) ------------------------
    claude_cli = shutil.which("claude")
    add_cmd = ["claude", "mcp", "add", "-s", "user", "action-capture",
               "--", PY, "-m", "action_capture.mcp"]
    if not claude_cli:
        log("      MCP: `claude` CLI not found. Register it manually with:")
        log("        " + " ".join(add_cmd))
    elif dry:
        log("      (dry-run) would run: " + " ".join(add_cmd))
    else:
        r = subprocess.run(add_cmd, capture_output=True, text=True)
        if r.returncode == 0:
            log("      MCP: registered via claude CLI (user scope)")
        else:
            msg = (r.stderr or r.stdout or "").strip().splitlines()
            log("      MCP: claude CLI said: " + (msg[-1] if msg else "already set?"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Install action-capture integration")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-install", action="store_true")
    ap.add_argument("--skip-codex", action="store_true")
    ap.add_argument("--skip-claude", action="store_true")
    args = ap.parse_args(argv)

    log("action-capture installer")
    log("=" * 40)

    if not args.no_install:
        pip_install(args.dry_run)
    else:
        log("\n[1/3] Skipping pip install (--no-install)")

    if not args.skip_codex:
        configure_codex(args.dry_run)
    if not args.skip_claude:
        configure_claude(args.dry_run)

    log("\nDone." + (" (dry-run: nothing written)" if args.dry_run else ""))
    log("Restart Codex / Claude Code so they pick up the new config.")
    log("The capture daemon starts automatically on the next session (Windows).")


if __name__ == "__main__":
    main()
