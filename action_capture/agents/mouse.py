"""Mouse agent: clicks, scrolls, and drag gestures with sampled paths.

A gesture spans press -> (moves) -> release and produces ONE event: a click
(with double/triple detection) if the pointer barely moved, else a drag with
the full sampled trajectory. Raw events are submitted to the UI-context agent
for element enrichment, keeping this listener responsive so no points drop.
"""

import ctypes
import math
import time

from pynput import mouse

from ..core import events, win32util
from ..labeling.classify import (
    DRAG_SAMPLE_DIST, DRAG_MIN_TRAVEL, DRAG_MAX_POINTS, stroke_metrics,
)


class MouseAgent:
    def __init__(self, enrich, input_state):
        self.enrich = enrich          # callable(event) -> submit to worker
        self.st = input_state
        self.drags = {}               # button -> stroke state
        self.last_click = {}          # button -> [t_ms, x, y, count]
        try:
            self.DCLICK_MS = ctypes.windll.user32.GetDoubleClickTime() or 500
        except Exception:
            self.DCLICK_MS = 500
        self.DCLICK_DIST = 6
        self.listener = mouse.Listener(
            on_click=self._on_click, on_scroll=self._on_scroll, on_move=self._on_move)

    def start(self):
        self.listener.start()

    def stop(self):
        self.listener.stop()

    # -- helpers -----------------------------------------------------------
    def _click_count(self, btn, x, y):
        t = time.monotonic() * 1000
        prev = self.last_click.get(btn)
        if prev and (t - prev[0]) <= self.DCLICK_MS and \
           math.hypot(x - prev[1], y - prev[2]) <= self.DCLICK_DIST:
            count = min(prev[3] + 1, 3)
        else:
            count = 1
        self.last_click[btn] = [t, x, y, count]
        return count

    # -- handlers ----------------------------------------------------------
    def _on_click(self, x, y, button, pressed):
        if self.st.paused:
            return
        btn = str(button)
        if pressed:
            self.drags[btn] = {
                "t0": time.monotonic(),
                "window": win32util.get_window(),
                "monitor": win32util.get_monitor_name(x, y),
                "cursor": win32util.get_cursor_shape(),
                "start": (x, y),
                "path": [[x, y, 0]],
                "modifiers": self.st.mods_list(),
                "click_count": self._click_count(btn, x, y),
            }
            return

        d = self.drags.pop(btn, None)
        if d is None:
            return
        path = d["path"]
        metrics = stroke_metrics(path)
        is_drag = metrics["length_px"] >= DRAG_MIN_TRAVEL and len(path) > 1

        event = events.new_event("drag" if is_drag else "click")
        event["modifiers"] = d["modifiers"]
        event["window"] = d["window"]
        event["cursor"] = d["cursor"]
        # x, y = press point, so the worker resolves the element aimed at.
        event["mouse"] = {"x": d["start"][0], "y": d["start"][1],
                          "button": btn, "monitor": d["monitor"]}
        if is_drag:
            event["mouse"]["start"] = list(d["start"])
            event["mouse"]["end"] = [x, y]
            event["path"] = path
            event["metrics"] = metrics
        else:
            event["click_count"] = d.get("click_count", 1)
        self.enrich(event)

    def _on_scroll(self, x, y, dx, dy):
        if self.st.paused:
            return
        event = events.new_event("scroll")
        event["modifiers"] = self.st.mods_list()
        event["window"] = win32util.get_window()
        event["mouse"] = {"x": x, "y": y, "scroll": [dx, dy],
                          "monitor": win32util.get_monitor_name(x, y)}
        self.enrich(event)

    def _on_move(self, x, y):
        if self.st.paused or not self.drags:
            return
        for d in self.drags.values():
            path = d["path"]
            if len(path) >= DRAG_MAX_POINTS:
                continue
            lx, ly, _ = path[-1]
            if math.hypot(x - lx, y - ly) >= DRAG_SAMPLE_DIST:
                path.append([x, y, int((time.monotonic() - d["t0"]) * 1000)])
