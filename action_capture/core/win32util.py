"""Windows-specific, cheap, thread-safe helpers (foreground window, monitor,
window geometry, cursor shape, and a fast password-field check).

Everything here is safe to call from any thread and degrades to empty values
when pywin32 isn't available.
"""

import ctypes
from ctypes import wintypes

try:
    import win32gui
    import win32api
    import win32con
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


# --------------------------------------------------------------------------
# Foreground window / process / monitor
# --------------------------------------------------------------------------
def get_active_hwnd():
    if not HAS_WIN32:
        return 0
    try:
        return win32gui.GetForegroundWindow()
    except Exception:
        return 0


def get_process_name(pid):
    if not (HAS_PSUTIL and pid):
        return ""
    try:
        return psutil.Process(pid).name()
    except Exception:
        return ""


def get_foreground_info():
    """Return (window_title, process_exe_name)."""
    if not HAS_WIN32:
        return "", ""
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        proc = ""
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = get_process_name(pid)
        except Exception:
            pass
        return title, proc
    except Exception:
        return "", ""


def get_window(hwnd=None):
    """Return dict {hwnd, title, process, rect, state} for a window."""
    if not HAS_WIN32:
        return {"hwnd": 0, "title": "", "process": "", "rect": None, "state": ""}
    try:
        if hwnd is None:
            hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        proc = ""
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = get_process_name(pid)
        except Exception:
            pass
        rect = None
        state = "normal"
        try:
            l, t, r, b = win32gui.GetWindowRect(hwnd)
            rect = [l, t, r, b]
            # placement[1] is showCmd: 1 normal, 2 minimized, 3 maximized
            show = win32gui.GetWindowPlacement(hwnd)[1]
            state = {1: "normal", 2: "minimized", 3: "maximized"}.get(show, "normal")
        except Exception:
            pass
        return {"hwnd": int(hwnd), "title": title, "process": proc,
                "rect": rect, "state": state}
    except Exception:
        return {"hwnd": 0, "title": "", "process": "", "rect": None, "state": ""}


def get_modifiers():
    """Real modifier state from the OS, immune to missed key-up events.

    Tracking modifiers via pynput press/release is fragile: a missed release
    (Alt+Tab, focus changes) leaves a modifier stuck "down", turning every
    later keystroke into a bogus shortcut. Reading GetAsyncKeyState each time
    avoids that.

    AltGr (right Alt) is handled specially: on many layouts it equals
    Ctrl+Alt, so typing `@ { [ \\` would look like a shortcut. AltGr is
    excluded here, so those keystrokes are correctly treated as text.
    """
    if not HAS_WIN32:
        return []
    try:
        g = ctypes.windll.user32.GetAsyncKeyState
        g.restype = ctypes.c_short

        def down(vk):
            return bool(g(vk) & 0x8000)

        altgr = down(0xA5)                       # VK_RMENU (AltGr)
        ctrl = (down(0xA2) or down(0xA3)) and not altgr   # L/R Control
        alt = down(0xA4)                         # VK_LMENU (real left Alt)
        shift = down(0x10)                       # VK_SHIFT
        win = down(0x5B) or down(0x5C)           # L/R Win
        mods = []
        if ctrl:
            mods.append("ctrl")
        if alt:
            mods.append("alt")
        if shift:
            mods.append("shift")
        if win:
            mods.append("win")
        return mods
    except Exception:
        return []


def get_monitor_name(x, y):
    if not HAS_WIN32:
        return ""
    try:
        hmon = win32api.MonitorFromPoint((x, y), win32con.MONITOR_DEFAULTTONEAREST)
        return win32api.GetMonitorInfo(hmon).get("Device", "")
    except Exception:
        return ""


# --------------------------------------------------------------------------
# Cursor shape - reveals what the UI afforded (text / link / resize / busy)
# --------------------------------------------------------------------------
class _CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hCursor", wintypes.HANDLE),
        ("ptScreenPos", wintypes.POINT),
    ]


_STD_CURSORS = {
    "arrow": 32512, "ibeam": 32513, "wait": 32514, "cross": 32515,
    "sizenwse": 32642, "sizenesw": 32643, "sizewe": 32644, "sizens": 32645,
    "sizeall": 32646, "no": 32648, "hand": 32649, "appstarting": 32650,
}
_cursor_lookup = None


def _build_cursor_lookup():
    global _cursor_lookup
    if _cursor_lookup is not None:
        return _cursor_lookup
    _cursor_lookup = {}
    if not HAS_WIN32:
        return _cursor_lookup
    try:
        u = ctypes.windll.user32
        u.LoadCursorW.restype = wintypes.HANDLE
        u.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
        for name, cid in _STD_CURSORS.items():
            try:
                h = u.LoadCursorW(None, ctypes.c_wchar_p(cid))
                if h:
                    _cursor_lookup[int(h)] = name
            except Exception:
                pass
    except Exception:
        pass
    return _cursor_lookup


def get_cursor_shape():
    """Best-effort name of the current system cursor (e.g. 'ibeam', 'hand')."""
    if not HAS_WIN32:
        return ""
    try:
        info = _CURSORINFO()
        info.cbSize = ctypes.sizeof(_CURSORINFO)
        if not ctypes.windll.user32.GetCursorInfo(ctypes.byref(info)):
            return ""
        if not info.hCursor:
            return "hidden"
        return _build_cursor_lookup().get(int(info.hCursor), "otro")
    except Exception:
        return ""


# --------------------------------------------------------------------------
# Fast, synchronous password-field check (classic Win32 ES_PASSWORD)
# --------------------------------------------------------------------------
class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def focused_is_password_win32():
    """Does the focused control have ES_PASSWORD? Microseconds; safe per key.

    Covers native Win32 password boxes. Browser/Electron fields aren't Win32
    controls and are handled via UI Automation's IsPassword on click.
    """
    if not HAS_WIN32:
        return False
    try:
        u = ctypes.windll.user32
        hwnd_fg = u.GetForegroundWindow()
        tid = u.GetWindowThreadProcessId(hwnd_fg, None)
        info = _GUITHREADINFO()
        info.cbSize = ctypes.sizeof(_GUITHREADINFO)
        if not u.GetGUIThreadInfo(tid, ctypes.byref(info)):
            return False
        hwnd = info.hwndFocus
        if not hwnd:
            return False
        ES_PASSWORD = 0x0020
        GWL_STYLE = -16
        if u.GetWindowLongW(hwnd, GWL_STYLE) & ES_PASSWORD:
            return True
        EM_GETPASSWORDCHAR = 0x00D2
        return u.SendMessageW(hwnd, EM_GETPASSWORDCHAR, 0, 0) != 0
    except Exception:
        return False
