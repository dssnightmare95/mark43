"""UI-context enrichment agent (the worker stage).

Consumes raw mouse events from a queue, resolves the UI Automation element
under the pointer (type, name, AutomationId, state, ancestry), classifies the
gesture, resolves drop targets, optionally reads selected text and an a11y
snapshot, composes a label, then writes the enriched event to the sink.

Runs on its own thread initialized as COM MTA so cross-process UIA queries
never require a message pump (which would otherwise hang this worker).
"""

import sys
import queue
import threading

from ..labeling.classify import (
    classify_drag, describe_click, describe_scroll, describe_drag,
    TEXT_CTRLS, base_control_type,
)
from .snapshot import snapshot_window


class UIContextAgent(threading.Thread):
    def __init__(self, sink, secure_state, capture_text=False,
                 want_state=True, want_ancestry=True, a11y_snapshot=False):
        super().__init__(daemon=True)
        self.q = queue.Queue()
        self.sink = sink
        self.secure_state = secure_state
        self.capture_text = capture_text
        self.want_state = want_state
        self.want_ancestry = want_ancestry
        self.a11y_snapshot = a11y_snapshot
        self._stop = threading.Event()
        self._uia = None

    # -- lifecycle ---------------------------------------------------------
    def _lazy_init(self):
        try:
            import comtypes
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except Exception:
            pass
        try:
            import uiautomation as auto
            try:
                auto.SetGlobalSearchTimeout(0.5)
            except Exception:
                pass
            self._uia = auto
        except Exception:
            self._uia = None

    def submit(self, event):
        self.q.put(event)

    def stop(self):
        self._stop.set()
        self.q.put(None)

    def run(self):
        self._lazy_init()
        while not self._stop.is_set():
            event = self.q.get()
            if event is None:
                break
            try:
                self._enrich_and_write(event)
            except Exception as exc:
                print(f"[ui_context] error: {exc}", file=sys.stderr)

    # -- UIA property readers ---------------------------------------------
    def _is_password(self, ctrl):
        try:
            v = ctrl.GetPropertyValue(self._uia.PropertyId.IsPasswordPropertyId)
            return bool(v)
        except Exception:
            pass
        try:
            return bool(ctrl.IsPassword)
        except Exception:
            return False

    def _element_state(self, ctrl):
        """Toggle / selected / expand / range-value state (best effort)."""
        st = {}
        try:
            tp = ctrl.GetTogglePattern()
            v = getattr(tp, "ToggleState", getattr(tp, "CurrentToggleState", None))
            if v is not None:
                st["toggle"] = {0: "off", 1: "on", 2: "indeterminate"}.get(int(v), str(v))
        except Exception:
            pass
        try:
            sp = ctrl.GetSelectionItemPattern()
            v = getattr(sp, "IsSelected", getattr(sp, "CurrentIsSelected", None))
            if v is not None:
                st["selected"] = bool(v)
        except Exception:
            pass
        try:
            ep = ctrl.GetExpandCollapsePattern()
            v = getattr(ep, "ExpandCollapseState",
                        getattr(ep, "CurrentExpandCollapseState", None))
            if v is not None:
                st["expand"] = {0: "collapsed", 1: "expanded",
                                2: "partially", 3: "leaf"}.get(int(v), str(v))
        except Exception:
            pass
        try:
            rp = ctrl.GetRangeValuePattern()
            v = getattr(rp, "Value", getattr(rp, "CurrentValue", None))
            if v is not None:
                st["value"] = v
        except Exception:
            pass
        return st

    def _ancestry(self, ctrl, max_up=6):
        path = []
        cur = ctrl
        try:
            for _ in range(max_up):
                cur = cur.GetParentControl()
                if cur is None:
                    break
                ct = getattr(cur, "ControlTypeName", "") or ""
                path.append({"control_type": ct,
                             "name": (getattr(cur, "Name", "") or "")[:80]})
                if ct == "Window":
                    break
        except Exception:
            pass
        path.reverse()
        return path

    def _element_at(self, x, y, full=False):
        """Return (info_dict, ctrl). full=True adds state + ancestry."""
        if self._uia is None:
            return None, None
        try:
            ctrl = self._uia.ControlFromPoint(x, y)
            if ctrl is None:
                return None, None
            rect = ctrl.BoundingRectangle
            info = {
                "control_type": getattr(ctrl, "ControlTypeName", "") or "",
                "name": (getattr(ctrl, "Name", "") or "")[:200],
                "automation_id": getattr(ctrl, "AutomationId", "") or "",
                "class": getattr(ctrl, "ClassName", "") or "",
                "rect": [rect.left, rect.top, rect.right, rect.bottom],
                "is_password": self._is_password(ctrl),
            }
            if full and self.want_state:
                state = self._element_state(ctrl)
                if state:
                    info["state"] = state
            if full and self.want_ancestry:
                info["ancestry"] = self._ancestry(ctrl)
            return info, ctrl
        except Exception:
            return None, None

    def _text_ok(self, ctype, ui):
        if base_control_type(ctype) not in TEXT_CTRLS:
            return False
        if ui and ui.get("is_password"):
            return False
        return not self.secure_state.is_secure()

    def _selected_text(self, ctrl):
        if ctrl is None:
            return ""
        try:
            tp = ctrl.GetTextPattern()
        except Exception:
            tp = None
        if not tp:
            return ""
        parts = []
        try:
            for rng in tp.GetSelection():
                try:
                    parts.append(rng.GetText(200))
                except Exception:
                    pass
        except Exception:
            return ""
        return " ".join(p for p in parts if p).strip()[:500]

    # -- main enrichment ---------------------------------------------------
    def _enrich_and_write(self, event):
        ui = None
        try:
            m = event["mouse"]
            ui, ctrl = self._element_at(m["x"], m["y"], full=True)
            ctype = ui["control_type"] if ui else ""
            name = ui["name"] if ui else ""
            proc = event["window"].get("process", "")
            mods = event.get("modifiers", [])
            etype = event["event_type"]

            if etype == "click":
                self.secure_state.set_from_click(bool(ui and ui.get("is_password")))
                count = event.get("click_count", 1)
                if self.capture_text and count >= 2 and self._text_ok(ctype, ui):
                    sel = self._selected_text(ctrl)
                    if sel:
                        event["selection_text"] = sel
                if self.a11y_snapshot:
                    snap = snapshot_window(self._uia, event["window"].get("hwnd"))
                    if snap:
                        event["a11y"] = snap
                event["label"] = describe_click(m.get("button", ""), ctype, name,
                                                 proc, count, mods)

            elif etype == "drag":
                kind = classify_drag(ctype, name, proc)
                event["drag_kind"] = kind
                dest = None
                end = m.get("end")
                if end:
                    ui_end, _ = self._element_at(end[0], end[1])
                    event["ui_end"] = ui_end
                    if kind == "move_element" and ui_end and \
                       ui_end.get("rect") != (ui.get("rect") if ui else None):
                        dest = ui_end
                if self.capture_text and kind == "text_selection" and \
                   self._text_ok(ctype, ui):
                    sel = self._selected_text(ctrl)
                    if sel:
                        event["selection_text"] = sel
                event["label"] = describe_drag(m.get("button", ""), ctype, name,
                                               proc, event["metrics"], kind, mods, dest)

            elif etype == "scroll":
                dx, dy = m.get("scroll", [0, 0])
                event["label"] = describe_scroll(dx, dy, ctype, name, proc)
        except Exception as exc:
            print(f"[ui_context] enrich failed: {exc}", file=sys.stderr)
        finally:
            event["ui"] = ui
            self.sink.write(event)
            print(f"{event['timestamp']}  ->  {event['label']}")
