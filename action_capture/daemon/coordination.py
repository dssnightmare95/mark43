"""Cross-process coordination for the capture daemon.

Uses Windows named mutexes as the source of truth for "is the daemon running"
and to guard the session registry, plus a JSON file listing live sessions
(pruned by PID liveness). Everything is keyed by the log-file path, so distinct
logs (e.g. different projects) get independent daemons.

Degrades gracefully on non-Windows: the mutex layer becomes a no-op and only
the PID-based checks apply (capture itself is Windows-only anyway).
"""

import os
import sys
import json
import time
import hashlib
import ctypes

IS_WIN = sys.platform == "win32"

try:
    import psutil
except ImportError:
    psutil = None

_ERROR_ALREADY_EXISTS = 183
_SYNCHRONIZE = 0x00100000


def _kernel32():
    from ctypes import wintypes
    k = ctypes.windll.kernel32
    k.CreateMutexW.restype = wintypes.HANDLE
    k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k.OpenMutexW.restype = wintypes.HANDLE
    k.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.ReleaseMutex.argtypes = [wintypes.HANDLE]
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    return k


def _key(log_path):
    ab = os.path.abspath(log_path).lower()
    return hashlib.md5(ab.encode("utf-8")).hexdigest()[:12]


def _daemon_mutex_name(log_path):
    return "action_capture_daemon_" + _key(log_path)


def _lock_mutex_name(log_path):
    return "action_capture_reglock_" + _key(log_path)


def state_dir(log_path):
    d = os.path.dirname(os.path.abspath(log_path))
    os.makedirs(d, exist_ok=True)
    return d


# --------------------------------------------------------------------------
# Single-instance guard (held by the daemon for its whole lifetime)
# --------------------------------------------------------------------------
class SingleInstance:
    """Acquire a named mutex; `acquired` is False if one already exists."""

    def __init__(self, log_path):
        self.name = _daemon_mutex_name(log_path)
        self._handle = None
        self.acquired = False

    def acquire(self):
        if not IS_WIN:
            self.acquired = True
            return True
        k = _kernel32()
        self._handle = k.CreateMutexW(None, True, self.name)
        self.acquired = k.GetLastError() != _ERROR_ALREADY_EXISTS and bool(self._handle)
        return self.acquired

    def release(self):
        if self._handle and IS_WIN:
            _kernel32().CloseHandle(self._handle)
            self._handle = None


def daemon_running(log_path):
    """True if a capture daemon holds the mutex for this log."""
    if not IS_WIN:
        return _daemon_pid_alive(log_path)
    k = _kernel32()
    h = k.OpenMutexW(_SYNCHRONIZE, False, _daemon_mutex_name(log_path))
    if h:
        k.CloseHandle(h)
        return True
    return False


# --------------------------------------------------------------------------
# Daemon PID file (informational + non-Windows liveness)
# --------------------------------------------------------------------------
def _pid_path(log_path):
    return os.path.join(state_dir(log_path), ".daemon.pid")


def write_daemon_pid(log_path):
    with open(_pid_path(log_path), "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))


def clear_daemon_pid(log_path):
    try:
        os.remove(_pid_path(log_path))
    except OSError:
        pass


def _daemon_pid_alive(log_path):
    try:
        with open(_pid_path(log_path), "r", encoding="utf-8") as f:
            return _pid_alive(int(f.read().strip()))
    except (OSError, ValueError):
        return False


# --------------------------------------------------------------------------
# Session registry (refcount), guarded by a lock mutex
# --------------------------------------------------------------------------
def _pid_alive(pid):
    if not pid:
        return False
    if psutil is not None:
        return psutil.pid_exists(pid)
    return True  # can't verify; assume alive


def _reg_path(log_path):
    return os.path.join(state_dir(log_path), ".sessions.json")


def _read_reg(log_path):
    try:
        with open(_reg_path(log_path), "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_reg(log_path, data):
    path = _reg_path(log_path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _with_lock(log_path, fn):
    if not IS_WIN:
        return fn()
    k = _kernel32()
    h = k.CreateMutexW(None, False, _lock_mutex_name(log_path))
    k.WaitForSingleObject(h, 5000)
    try:
        return fn()
    finally:
        k.ReleaseMutex(h)
        k.CloseHandle(h)


def register_session(log_path, pid=None, cwd=None):
    """Add this process as a live session; returns its session id.

    `cwd` is the session's working directory (the project being assisted),
    used to scope the filesystem effect layer.
    """
    pid = pid or os.getpid()
    cwd = cwd or os.getcwd()
    sid = f"{pid}-{int(time.time() * 1000)}"

    def upd():
        reg = _read_reg(log_path)
        reg.append({"id": sid, "pid": pid, "cwd": cwd, "started": time.time()})
        _write_reg(log_path, reg)

    _with_lock(log_path, upd)
    return sid


def unregister_session(log_path, sid):
    def upd():
        reg = [s for s in _read_reg(log_path) if s.get("id") != sid]
        _write_reg(log_path, reg)

    _with_lock(log_path, upd)


def live_sessions(log_path):
    """Sessions whose PID is still alive; prunes dead entries."""
    def upd():
        reg = _read_reg(log_path)
        alive = [s for s in reg if _pid_alive(s.get("pid"))]
        if len(alive) != len(reg):
            _write_reg(log_path, alive)
        return alive

    return _with_lock(log_path, upd)


def live_count(log_path):
    return len(live_sessions(log_path))


def live_roots(log_path):
    """Unique existing working directories of the live sessions."""
    roots = []
    for s in live_sessions(log_path):
        cwd = s.get("cwd")
        if cwd and cwd not in roots and os.path.isdir(cwd):
            roots.append(cwd)
    return roots
