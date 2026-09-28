"""Launcher used by the MCP server to keep exactly one capture daemon alive.

On session start: register the session and spawn the daemon (detached) if none
is running. On session end: unregister; the daemon notices the empty registry
and shuts itself down.
"""

import os
import sys
import time
import subprocess

from . import coordination

# Repo root = parent of the action_capture package, so a detached
# `python -m action_capture` can import the package via its cwd.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200


def ensure_daemon(log_path):
    """Spawn the capture daemon detached if it isn't already running.

    Returns True if a daemon is running by the time we return.
    """
    if not coordination.IS_WIN:
        return False  # capture is Windows-only
    if coordination.daemon_running(log_path):
        return True

    out_dir = os.path.dirname(os.path.abspath(log_path))
    creationflags = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(
            [sys.executable, "-m", "action_capture", "--daemon", "--out", out_dir],
            cwd=_REPO_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
    except Exception:
        return coordination.daemon_running(log_path)

    # Wait briefly for the daemon to grab its mutex.
    for _ in range(50):
        if coordination.daemon_running(log_path):
            return True
        time.sleep(0.1)
    return coordination.daemon_running(log_path)


def acquire_session(log_path):
    """Register this process as a session and make sure the daemon is up."""
    sid = coordination.register_session(log_path)
    ensure_daemon(log_path)
    return sid


def release_session(log_path, sid):
    """Deregister this session (daemon stops when none remain)."""
    coordination.unregister_session(log_path, sid)
