"""Machine-readable description of the event records, for AI consumers.

Exposed via the `describe_records` MCP tool so Codex/Claude can interpret the
fields returned by the other tools without guessing.
"""

SCHEMA = {
    "overview": (
        "The action log is JSON Lines: one JSON object per line, one per human "
        "action. Query it with the other tools; this describes the fields."
    ),
    "common_fields": {
        "schema_version": "int - record format version.",
        "seq": ("int - creation order WITHIN one daemon run; it RESETS when the "
                "daemon restarts, so do NOT compare seq across restarts. Order "
                "and filter by `timestamp` instead."),
        "timestamp": "ISO-8601 local time with milliseconds. Authoritative for ordering.",
        "event_type": ("one of: click, drag, scroll, key, hotkey, text_input, "
                       "window_focus, file_change."),
        "label": "human-readable one-line summary of the event.",
        "modifiers": "list of held modifiers, e.g. ['ctrl','shift'] (AltGr excluded).",
        "window": ("{process, title} = the active app/window when the event "
                   "happened. process is the exe name, e.g. 'Code.exe'."),
    },
    "ui_object": {
        "_desc": ("Present on click/drag: the UI Automation element under the "
                  "cursor, or null if it couldn't be resolved."),
        "control_type": ("UIA type with a 'Control' suffix, e.g. 'ButtonControl', "
                         "'TabItemControl', 'EditControl', 'DataItemControl'."),
        "name": "accessible name/label, e.g. 'Save' (may be empty for generic panes).",
        "automation_id": "app-defined element id (may be empty).",
        "class": "native window class name.",
        "rect": "[left, top, right, bottom] screen bounds.",
        "is_password": "true if a password field (its typed content is never logged).",
        "state": ("optional: {toggle: on/off/indeterminate, selected: bool, "
                  "expand: collapsed/expanded/..., value: <slider/range value>}."),
        "ancestry": "optional: list of ancestor {control_type, name} up to the window.",
    },
    "event_types": {
        "click": {
            "desc": "one mouse click (single row per click).",
            "fields": {
                "mouse": "{x, y, button: 'Button.left'|'Button.right'|'Button.middle', monitor}",
                "click_count": "1 = single, 2 = double, 3 = triple.",
                "cursor": "cursor shape, e.g. 'ibeam', 'hand', 'arrow'.",
                "ui": "see ui_object.",
            },
        },
        "drag": {
            "desc": "press-move-release gesture, classified by intent.",
            "fields": {
                "mouse": "{x, y (start point), button, start:[x,y], end:[x,y], monitor}",
                "drag_kind": ("text_selection | marquee_selection | move_element | "
                              "control_adjust | free_stroke | drag."),
                "path": "sampled trajectory: list of [x, y, dt_ms] since the press.",
                "metrics": "{points, length_px, duration_ms, bbox:[l,t,r,b]}",
                "ui": "element at the start point (see ui_object).",
                "ui_end": "element at the drop point (for drag-and-drop).",
                "selection_text": "selected text (only with --capture-text, never in password fields).",
            },
        },
        "scroll": {
            "desc": "mouse-wheel scroll.",
            "fields": {"mouse": "{x, y, scroll:[dx, dy], monitor}", "ui": "see ui_object."},
        },
        "key": {
            "desc": "a single non-text key (Enter, Tab, arrows, etc.).",
            "fields": {"key": "{value, combo}"},
        },
        "hotkey": {
            "desc": "a keyboard shortcut (a command modifier was held).",
            "fields": {"key": "{value, combo e.g. 'ctrl+c'}", "modifiers": "held modifiers."},
        },
        "text_input": {
            "desc": ("aggregated typed text into one field (many keystrokes -> one "
                     "event). Spaces are included; Enter/Tab flush it."),
            "fields": {
                "text": "the typed string (omitted in --mask-keys mode).",
                "key": "{length} instead of text when masked.",
            },
        },
        "window_focus": {
            "desc": "the foreground app/window changed (marks context switches).",
            "fields": {"window": "{process, title, hwnd, rect, state: normal/maximized/minimized}"},
        },
        "file_change": {
            "desc": ("a file under a session's project dir was created/modified/"
                     "deleted (the 'effect' of actions)."),
            "fields": {
                "file": ("{path, change: created/modified/deleted, size, is_text}. "
                         "A bulk op (build/checkout/dependency download) collapses "
                         "into one record: {change:'bulk', count, by_change, sample}."),
                "diff": "unified diff for text files (omitted for binary/CAD/images).",
                "diff_truncated": "true if the diff was cut for size.",
            },
        },
    },
    "notes": [
        "Order and filter by timestamp, not seq (seq resets on daemon restart).",
        "Binary files (PNG, CAD, ...) report only that they changed and the new "
        "size, never a visual diff.",
        "Electron/Chromium apps (Spotify, VS Code, ...) expose a poor UIA tree, so "
        "ui.control_type is often a generic 'GroupControl'/'PaneControl' with an "
        "empty name; the active app is still known from window.process.",
    ],
}
