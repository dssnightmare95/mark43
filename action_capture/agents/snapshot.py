"""Accessibility-tree snapshot: a lightweight structured 'screenshot'.

Walks the UIA subtree of a window into a bounded nested dict so an AI can
reconstruct the on-screen scene without pixels. Bounded in depth and breadth
to keep cost and size reasonable.
"""


def _node(ctrl):
    try:
        rect = ctrl.BoundingRectangle
        box = [rect.left, rect.top, rect.right, rect.bottom]
    except Exception:
        box = None
    return {
        "control_type": getattr(ctrl, "ControlTypeName", "") or "",
        "name": (getattr(ctrl, "Name", "") or "")[:120],
        "automation_id": getattr(ctrl, "AutomationId", "") or "",
        "rect": box,
    }


def snapshot_control(ctrl, max_depth=4, max_children=25):
    """Return a nested dict tree rooted at ctrl (best effort)."""
    if ctrl is None:
        return None
    node = _node(ctrl)
    if max_depth <= 0:
        return node
    children = []
    try:
        kids = ctrl.GetChildren()
    except Exception:
        kids = []
    for i, child in enumerate(kids or []):
        if i >= max_children:
            node["children_truncated"] = True
            break
        try:
            children.append(snapshot_control(child, max_depth - 1, max_children))
        except Exception:
            pass
    if children:
        node["children"] = children
    return node


def snapshot_window(uia, hwnd, max_depth=4, max_children=25):
    """Snapshot the UIA subtree of a top-level window by handle."""
    if uia is None or not hwnd:
        return None
    try:
        ctrl = uia.ControlFromHandle(hwnd)
    except Exception:
        return None
    return snapshot_control(ctrl, max_depth, max_children)
