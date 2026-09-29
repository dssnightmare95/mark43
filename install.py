#!/usr/bin/env python3
"""Installer/uninstaller for the action-capture assistant integration.

action-capture is a *user-level* tool: one daemon captures your input, file
changes and UI context across every app and project into a single log
(~/.action_capture). So all of its configuration is registered globally — the
repo ships only source code, and this script is the single source of truth.

Clone the repo and run:

    python install.py                # install (idempotent, re-runnable)
    python install.py --uninstall    # remove everything it added

It installs the package (`pip install -e .`) and registers the `action-capture`
MCP server + activity hooks for Codex (~/.codex/config.toml, ~/.codex/hooks.json)
and Claude Code (~/.claude/settings.json + `claude mcp add`), and installs the
human-context skill for Claude. All edits are merged, backed up (.bak) and keyed
by a stable marker, so re-running replaces rather than duplicates.

Flags: --uninstall, --dry-run, --no-install, --skip-codex, --skip-claude.
Config locations honor CODEX_HOME and CLAUDE_CONFIG_DIR.
"""

import os
import sys
import json
import shutil
import argparse
import subprocess

REPO = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable  # exact interpreter, so configs don't depend on PATH

# Stable marker: our hooks are identified by this substring regardless of the
# interpreter path, so re-installing after a Python upgrade replaces cleanly.
MARKER = "action_capture.integrations.context_hook"
INJECT = f'"{PY}" -m {MARKER} inject'
CHECKPOINT = f'"{PY}" -m {MARKER} checkpoint'
MCP_HEADER = "[mcp_servers.action-capture]"


def log(msg):
    print(msg)


def backup(path):
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")


# --------------------------------------------------------------------------
# file writers (dry-run aware, with backup)
# --------------------------------------------------------------------------
def write_text(path, text, dry, what):
    if dry:
        log(f"      (dry-run) would write {what} -> {path}")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    backup(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    log(f"      {what} -> {path}")


def write_json(path, data, dry, what):
    write_text(path, json.dumps(data, indent=2), dry, what)


def remove_file(path, dry, what):
    if not os.path.exists(path):
        return
    if dry:
        log(f"      (dry-run) would remove {what} -> {path}")
        return
    backup(path)
    os.remove(path)
    log(f"      removed {what} -> {path}")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


# --------------------------------------------------------------------------
# hook merging (marker-keyed: replace, never duplicate)
# --------------------------------------------------------------------------
def _strip_our_hooks(groups):
    cleaned = []
    for group in groups:
        kept = [h for h in group.get("hooks", []) if MARKER not in h.get("command", "")]
        if kept:
            g = dict(group)
            g["hooks"] = kept
            cleaned.append(g)
    return cleaned


def set_hook(root, event, command):
    events = root.setdefault("hooks", {}).setdefault(event, [])
    cleaned = _strip_our_hooks(events)
    cleaned.append({"hooks": [{"type": "command", "command": command}]})
    root["hooks"][event] = cleaned


def remove_hook(root, event):
    events = root.get("hooks", {}).get(event)
    if events is not None:
        root["hooks"][event] = _strip_our_hooks(events)


def apply_hooks(root, uninstall):
    if uninstall:
        remove_hook(root, "UserPromptSubmit")
        remove_hook(root, "Stop")
    else:
        set_hook(root, "UserPromptSubmit", INJECT)
        set_hook(root, "Stop", CHECKPOINT)


# --------------------------------------------------------------------------
# TOML block (remove our mcp table by its stable header)
# --------------------------------------------------------------------------
def remove_toml_block(text, header):
    out, skip = [], False
    for line in text.splitlines(keepends=True):
        s = line.strip()
        if s == header:
            skip = True
            continue
        if skip and s.startswith("["):
            skip = False
        if not skip:
            out.append(line)
    return "".join(out)


# --------------------------------------------------------------------------
# steps
# --------------------------------------------------------------------------
def pip_install(dry):
    log("\n[pip] Installing package + dependencies (pip install -e .)")
    if dry:
        log("      (dry-run) would run: pip install -e .")
        return
    subprocess.check_call([PY, "-m", "pip", "install", "-e", "."], cwd=REPO)


def codex(dry, uninstall):
    log("\n[Codex]")
    d = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    cfg, hooks = os.path.join(d, "config.toml"), os.path.join(d, "hooks.json")

    # MCP server in config.toml: always drop our block, re-add on install.
    text = ""
    if os.path.exists(cfg):
        with open(cfg, "r", encoding="utf-8") as f:
            text = f.read()
    new = remove_toml_block(text, MCP_HEADER)
    if not uninstall:
        block = (f"{MCP_HEADER}\ncommand = '{PY}'\n"
                 'args = ["-m", "action_capture.mcp"]\n')
        new = (new.rstrip("\n") + "\n\n" + block) if new.strip() else block
    if new != text:
        write_text(cfg, new, dry, "config.toml MCP")
    else:
        log("      config.toml: nothing to change")

    data = load_json(hooks)
    apply_hooks(data, uninstall)
    write_json(hooks, data, dry, "hooks.json")


def claude(dry, uninstall):
    log("\n[Claude Code]")
    d = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude")
    settings = os.path.join(d, "settings.json")

    data = load_json(settings)
    apply_hooks(data, uninstall)
    write_json(settings, data, dry, "settings.json hooks")

    # human-context skill (copy the repo's canonical copy)
    skill_src = os.path.join(REPO, ".claude", "skills", "human-context", "SKILL.md")
    skill_dst = os.path.join(d, "skills", "human-context", "SKILL.md")
    if uninstall:
        remove_file(skill_dst, dry, "skill")
    elif os.path.exists(skill_src):
        if dry:
            log(f"      (dry-run) would install skill -> {skill_dst}")
        else:
            os.makedirs(os.path.dirname(skill_dst), exist_ok=True)
            shutil.copy2(skill_src, skill_dst)
            log(f"      skill -> {skill_dst}")

    # MCP server via the claude CLI (user scope)
    if not shutil.which("claude"):
        log("      MCP: `claude` CLI not found; register manually with "
            "`claude mcp add -s user action-capture -- ...`")
        return
    if uninstall:
        cmd = ["claude", "mcp", "remove", "-s", "user", "action-capture"]
        if dry:
            log("      (dry-run) would run: " + " ".join(cmd))
        else:
            subprocess.run(cmd, capture_output=True, text=True)
            log("      MCP: removed via claude CLI")
    else:
        # remove-then-add makes it idempotent even if the path changed.
        add = ["claude", "mcp", "add", "-s", "user", "action-capture",
               "--", PY, "-m", "action_capture.mcp"]
        if dry:
            log("      (dry-run) would run: " + " ".join(add))
        else:
            subprocess.run(["claude", "mcp", "remove", "-s", "user",
                            "action-capture"], capture_output=True, text=True)
            r = subprocess.run(add, capture_output=True, text=True)
            log("      MCP: registered via claude CLI"
                if r.returncode == 0 else "      MCP: claude CLI add failed")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Install/uninstall action-capture")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-install", action="store_true")
    ap.add_argument("--skip-codex", action="store_true")
    ap.add_argument("--skip-claude", action="store_true")
    args = ap.parse_args(argv)

    verb = "Uninstalling" if args.uninstall else "Installing"
    log(f"action-capture — {verb}\n" + "=" * 40)

    if args.uninstall:
        pass  # never touch pip on uninstall
    elif args.no_install:
        log("\n[pip] skipped (--no-install)")
    else:
        pip_install(args.dry_run)

    if not args.skip_codex:
        codex(args.dry_run, args.uninstall)
    if not args.skip_claude:
        claude(args.dry_run, args.uninstall)

    log("\nDone." + (" (dry-run: nothing written)" if args.dry_run else ""))
    if not args.uninstall:
        log("Restart Codex / Claude Code to pick up the config.")


if __name__ == "__main__":
    main()
