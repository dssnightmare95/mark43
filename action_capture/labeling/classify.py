"""Gesture intent classification and human-readable labels (pure functions)."""

import math

# UIA control type -> friendly noun.
CONTROL_LABELS = {
    "Button": "button", "SplitButton": "button",
    "TabItem": "tab", "Tab": "tab",
    "Edit": "text field", "Document": "document",
    "DataItem": "cell", "DataGrid": "table", "HeaderItem": "header",
    "MenuItem": "menu item", "Menu": "menu",
    "Hyperlink": "link", "CheckBox": "checkbox", "RadioButton": "radio button",
    "ComboBox": "dropdown", "ListItem": "list item", "List": "list",
    "TreeItem": "tree node", "Text": "text", "Image": "image",
    "Slider": "slider", "Spinner": "spinner",
    "ToolBar": "toolbar", "TitleBar": "title bar",
    "ScrollBar": "scrollbar", "Pane": "pane",
    "Window": "window", "Group": "group",
}

BUTTON_LABELS = {
    "Button.left": "left-click",
    "Button.right": "right-click",
    "Button.middle": "middle-click",
}

# --- Drag capture tuning ---------------------------------------------------
DRAG_SAMPLE_DIST = 3.0    # min px between sampled path points
DRAG_MIN_TRAVEL = 5.0     # below this total travel a press->release is a click
DRAG_MAX_POINTS = 8000    # hard cap on stored points per stroke

# --- Gesture intent --------------------------------------------------------
TEXT_CTRLS = {"Edit", "Document", "Text"}
ADJUST_CTRLS = {"Slider", "ScrollBar", "Spinner"}
ITEM_CTRLS = {"ListItem", "TreeItem", "DataItem"}
CONTAINER_CTRLS = {"List", "Tree", "DataGrid"}

# Drawing / image-editing apps: a drag over their canvas is a free-hand stroke.
CANVAS_PROCS = {
    "mspaint.exe", "paint.net.exe", "photoshop.exe", "gimp.exe", "gimp-2.10.exe",
    "krita.exe", "clipstudiopaint.exe", "mypaint.exe", "inkscape.exe",
    "firealpaca.exe", "medibangpaintpro.exe", "sai.exe", "sai2.exe",
    "blender.exe", "drawio.exe",
}
CANVAS_SURFACE_CTRLS = {"Pane", "Image", "Document", "Custom", ""}

KIND_LABELS = {
    "text_selection": "text selection",
    "control_adjust": "control adjust",
    "move_element": "move element",
    "marquee_selection": "marquee selection",
    "free_stroke": "free-hand stroke",
    "drag": "drag",
}


def classify_drag(ctype, name, proc=""):
    # Process-aware canvas override: inside a drawing app, a drag over the
    # canvas surface is a stroke even if UIA only reports a generic Pane.
    if proc and proc.lower() in CANVAS_PROCS and ctype in CANVAS_SURFACE_CTRLS:
        return "free_stroke"
    if ctype in TEXT_CTRLS:
        return "text_selection"
    if ctype in ADJUST_CTRLS:
        return "control_adjust"
    if ctype in ITEM_CTRLS:
        return "move_element"
    if ctype in CONTAINER_CTRLS and not name:
        return "marquee_selection"
    # A bare Pane/Image is too generic to call a free-hand stroke on its own.
    return "drag"


def stroke_metrics(path):
    """Compute length/bbox/duration from a path of [x, y, dt_ms] points."""
    if not path:
        return {"points": 0, "length_px": 0.0, "duration_ms": 0, "bbox": None}
    xs = [p[0] for p in path]
    ys = [p[1] for p in path]
    length = 0.0
    for (x0, y0, _), (x1, y1, _) in zip(path, path[1:]):
        length += math.hypot(x1 - x0, y1 - y0)
    return {
        "points": len(path),
        "length_px": round(length, 1),
        "duration_ms": path[-1][2],
        "bbox": [min(xs), min(ys), max(xs), max(ys)],
    }


# --- Label composition -----------------------------------------------------
def _target_str(ctype, name):
    noun = CONTROL_LABELS.get(ctype, ctype.lower() if ctype else "element")
    return f"{noun} '{name}'" if name else noun


def _selection_hint(modifiers):
    if "shift" in modifiers:
        return " [extend range]"
    if "ctrl" in modifiers:
        return " [toggle selection]"
    return ""


def describe_click(button, ctype, name, proc, count=1, modifiers=()):
    base = BUTTON_LABELS.get(button, button)
    prefix = {2: "double ", 3: "triple "}.get(count, "")
    where = f" [{proc}]" if proc else ""
    return (f"{prefix}{base} on {_target_str(ctype, name)}"
            f"{_selection_hint(modifiers)}{where}")


def describe_scroll(dx, dy, ctype, name, proc):
    direction = "down" if dy < 0 else "up" if dy > 0 else "sideways"
    where = f" [{proc}]" if proc else ""
    return f"scroll {direction} on {_target_str(ctype, name)}{where}"


def describe_drag(button, ctype, name, proc, metrics, kind, modifiers=(), dest=None):
    where = f" [{proc}]" if proc else ""
    size = f" ({metrics['length_px']} px, {metrics['points']} points)"
    if dest is not None:
        drop = _target_str(dest.get("control_type", ""), dest.get("name", ""))
        return (f"drag and drop {_target_str(ctype, name)} -> {drop}"
                f"{size}{where}")
    verb = KIND_LABELS.get(kind, "drag")
    return (f"{verb} on {_target_str(ctype, name)}"
            f"{_selection_hint(modifiers)}{size}{where}")


def describe_key(is_hotkey, combo, proc):
    where = f" in '{proc}'" if proc else ""
    return f"{'shortcut' if is_hotkey else 'key'} {combo}{where}"


def describe_text_input(text, proc):
    where = f" in '{proc}'" if proc else ""
    return f"typed '{text}'{where}"
