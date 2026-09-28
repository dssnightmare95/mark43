"""DPI awareness so click/screen coordinates are accurate on high-DPI setups."""

import ctypes


def set_dpi_awareness():
    """Make the process per-monitor DPI aware (best effort)."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE_V2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
