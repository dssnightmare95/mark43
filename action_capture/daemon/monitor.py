"""Idle monitor: shuts the daemon down once no live session remains.

Polls the session registry. After a startup grace (so the session that spawned
us has time to register) it watches for an empty registry; if it stays empty
for the idle grace, it calls `on_idle` to trigger shutdown. PID-liveness in the
registry means a hard-killed MCP server is treated as gone too.
"""

import time
import threading

from . import coordination


class IdleMonitor(threading.Thread):
    def __init__(self, log_path, on_idle,
                 startup_grace=10.0, idle_grace=20.0, poll=5.0):
        super().__init__(daemon=True)
        self.log_path = log_path
        self.on_idle = on_idle
        self.startup_grace = startup_grace
        self.idle_grace = idle_grace
        self.poll = poll
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        start = time.monotonic()
        empty_since = None
        while not self._stop.wait(self.poll):
            if time.monotonic() - start < self.startup_grace:
                continue
            if coordination.live_count(self.log_path) == 0:
                empty_since = empty_since or time.monotonic()
                if time.monotonic() - empty_since >= self.idle_grace:
                    self.on_idle()
                    return
            else:
                empty_since = None
