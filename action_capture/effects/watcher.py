"""Filesystem watcher agent: emits `file_change` events for session roots.

Polling-based (no extra dependency): every `interval` it rescans the union of
the current watch roots and diffs the snapshot against the previous one. For
text files it also attaches a unified diff, using a bounded in-memory content
cache seeded at startup so the very first change already shows a diff.

Universal by design: a `.sldprt` or a PNG simply reports "modified" (no diff);
a `.py` reports "modified" with the diff.
"""

import os
import threading

from ..core import events
from . import differ

EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".idea", ".vscode", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    ".tox", "dist", "build", ".eggs", "target", ".next", ".cache",
}
MAX_FILES = 20000          # safety cap per scan
MAX_CACHE_BYTES = 64_000_000   # cap total cached text content


class DirScanner:
    """Snapshots {path: (mtime, size)} under a set of roots, with excludes."""

    def snapshot(self, roots):
        snap = {}
        count = 0
        seen_roots = set()
        for root in roots:
            root = os.path.abspath(root)
            if root in seen_roots or not os.path.isdir(root):
                continue
            seen_roots.add(root)
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
                for fn in filenames:
                    p = os.path.join(dirpath, fn)
                    try:
                        st = os.stat(p)
                        snap[p] = (st.st_mtime, st.st_size)
                    except OSError:
                        continue
                    count += 1
                    if count >= MAX_FILES:
                        return snap
        return snap


class EffectsAgent(threading.Thread):
    def __init__(self, sink, roots_provider, interval=2.0, want_diff=True):
        super().__init__(daemon=True)
        self.sink = sink
        self.roots_provider = roots_provider
        self.interval = interval
        self.want_diff = want_diff
        self._scanner = DirScanner()
        self._stop = threading.Event()
        self._content = {}          # path -> cached text
        self._cache_bytes = 0
        self._prev = None

    def stop(self):
        self._stop.set()

    # -- text content cache -----------------------------------------------
    def _cache_text(self, path):
        if self._cache_bytes >= MAX_CACHE_BYTES:
            return
        if not differ.is_text_file(path):
            return
        text = differ.read_text(path)
        if text is None:
            return
        self._content[path] = text
        self._cache_bytes += len(text)

    def _diff_for(self, path, change):
        """Return (diff, truncated, is_text) for a created/modified file."""
        is_text = differ.is_text_file(path)
        if not (self.want_diff and is_text):
            return None, False, is_text
        old = self._content.get(path, "") if change == "modified" else ""
        new = differ.read_text(path)
        if new is None:
            return None, False, is_text
        self._content[path] = new
        diff, trunc = differ.unified_diff(old, new, path)
        return (diff or None), trunc, is_text

    # -- event emission ----------------------------------------------------
    def _emit(self, path, change, size):
        diff = truncated = None
        is_text = False
        if change in ("created", "modified"):
            diff, truncated, is_text = self._diff_for(path, change)
        elif change == "deleted":
            self._content.pop(path, None)
        ev = events.new_event("file_change")
        ev["file"] = {"path": path, "change": change, "size": size,
                      "is_text": is_text}
        if diff:
            ev["diff"] = diff
            ev["diff_truncated"] = bool(truncated)
        ev["label"] = f"{change} file {path}"
        self.sink.write(ev)

    def run(self):
        # Baseline scan: seed snapshot + text cache, emit nothing.
        self._prev = self._scanner.snapshot(self.roots_provider() or [])
        if self.want_diff:
            for path in self._prev:
                self._cache_text(path)

        while not self._stop.wait(self.interval):
            roots = self.roots_provider()
            if not roots:
                self._prev = {}
                continue
            cur = self._scanner.snapshot(roots)
            prev = self._prev
            for path, meta in cur.items():
                if path not in prev:
                    self._emit(path, "created", meta[1])
                elif meta != prev[path]:
                    self._emit(path, "modified", meta[1])
            for path in prev:
                if path not in cur:
                    self._emit(path, "deleted", None)
            self._prev = cur
