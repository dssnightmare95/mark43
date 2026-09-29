"""Canonical file locations, shared by the daemon, MCP server and hooks.

A single user-level log (``~/.action_capture/events.jsonl``) means every AI
session — any tool, any project — reads and writes the same timeline, matching
the single-daemon design. Override with ACTION_CAPTURE_LOG (full path) or
ACTION_CAPTURE_HOME (the directory).
"""

import os


def data_dir():
    env = os.environ.get("ACTION_CAPTURE_HOME")
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), ".action_capture")


def default_log():
    env = os.environ.get("ACTION_CAPTURE_LOG")
    if env:
        return env
    return os.path.join(data_dir(), "events.jsonl")
