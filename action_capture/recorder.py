"""Wires the agents together and runs the capture session.

Run:  python -m action_capture [--out DIR] [--mask-keys] [--capture-text]
                             [--no-aggregate] [--a11y-snapshot]

Controls:  Esc = stop    Ctrl+Alt+P = pause/resume
"""

import os
import sys
import argparse
import threading

from .core.dpi import set_dpi_awareness
from .core.paths import data_dir
from .core.events import JsonlWriter
from .core.secure import SecureState
from .core.state import InputState
from .core.win32util import HAS_WIN32
from .agents.ui_context import UIContextAgent
from .agents.mouse import MouseAgent
from .agents.keyboard import KeyboardAgent
from .agents.window import WindowAgent
from .daemon import coordination
from .daemon.monitor import IdleMonitor
from .effects.watcher import EffectsAgent


def build_parser():
    ap = argparse.ArgumentParser(
        prog="action_capture",
        description="Modular computer-use dataset recorder for Windows")
    ap.add_argument("--out", default=None,
                    help="output directory (default: ~/.action_capture)")
    ap.add_argument("--mask-keys", action="store_true",
                    help="log key categories instead of actual characters")
    ap.add_argument("--capture-text", action="store_true",
                    help="record selected text on text-selection gestures "
                         "(never for password/secure fields)")
    ap.add_argument("--no-aggregate", action="store_true",
                    help="log every keystroke instead of aggregating typed text")
    ap.add_argument("--a11y-snapshot", action="store_true",
                    help="attach an accessibility-tree snapshot on each click")
    ap.add_argument("--daemon", action="store_true",
                    help="run as a single-instance background daemon that stops "
                         "when no MCP session remains (used by the launcher)")
    ap.add_argument("--no-effects", action="store_true",
                    help="disable the filesystem effect layer (file changes/diffs)")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)

    # Live-feedback prints include window titles, which may contain characters
    # the console codepage (e.g. cp1252) can't encode. Force UTF-8 so a stray
    # character can't crash an agent thread. (The JSONL sink is UTF-8 already.)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    set_dpi_awareness()
    out = args.out or data_dir()
    os.makedirs(out, exist_ok=True)
    jsonl_path = os.path.join(out, "events.jsonl")

    # Continue seq from the existing log so it stays monotonic across restarts.
    try:
        from .mcp.store import latest as _latest
        from .core import events as _events
        _events.seed_seq(_latest(jsonl_path)[0])
    except Exception:
        pass

    # Daemon mode: enforce a single instance across all sessions.
    instance = None
    if args.daemon:
        instance = coordination.SingleInstance(jsonl_path)
        if not instance.acquire():
            print("Capture daemon already running; exiting.")
            return
        coordination.write_daemon_pid(jsonl_path)

    sink = JsonlWriter(jsonl_path)

    secure_state = SecureState()
    input_state = InputState()
    stop_event = threading.Event()

    worker = UIContextAgent(sink, secure_state, capture_text=args.capture_text,
                            a11y_snapshot=args.a11y_snapshot)
    keyboard_agent = KeyboardAgent(
        sink, secure_state, input_state,
        mask_keys=args.mask_keys, aggregate_text=not args.no_aggregate,
        on_stop=stop_event.set)
    mouse_agent = MouseAgent(worker.submit, input_state)
    window_agent = WindowAgent(sink, input_state,
                               on_focus_change=keyboard_agent.flush_text)

    # Effect layer: watch the session roots (daemon) or the cwd (interactive).
    effects_agent = None
    if not args.no_effects:
        if args.daemon:
            def roots_provider():
                return coordination.live_roots(jsonl_path)
        else:
            def roots_provider():
                return [os.getcwd()]
        effects_agent = EffectsAgent(sink, roots_provider)

    print(f"Recording -> {jsonl_path}")
    print("  mode:", "daemon" if args.daemon else "interactive",
          "| keys:", "masked" if args.mask_keys else "raw",
          "| aggregate:", "off" if args.no_aggregate else "on",
          "| selected text:", "on" if args.capture_text else "off",
          "| a11y:", "on" if args.a11y_snapshot else "off")
    print("  Esc = stop   |   Ctrl+Alt+P = pause/resume")
    if not HAS_WIN32:
        print("  WARNING: pywin32 not installed - no window/monitor context.")

    # In daemon mode, stop automatically once no MCP session remains. The
    # monitor stops the keyboard listener, which unblocks the join below.
    idle_monitor = None
    if args.daemon:
        idle_monitor = IdleMonitor(jsonl_path,
                                   on_idle=keyboard_agent.listener.stop)
        idle_monitor.start()

    worker.start()
    window_agent.start()
    mouse_agent.start()
    keyboard_agent.start()
    if effects_agent:
        effects_agent.start()

    try:
        # The keyboard listener returns False (stops) on Esc or when the idle
        # monitor stops it; wait for that.
        keyboard_agent.listener.join()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        if idle_monitor:
            idle_monitor.stop()
        if effects_agent:
            effects_agent.stop()
        mouse_agent.stop()
        window_agent.stop()
        keyboard_agent.stop()      # flushes pending typed text
        worker.stop()
        worker.join(timeout=3)
        sink.close()
        if instance:
            coordination.clear_daemon_pid(jsonl_path)
            instance.release()
        print("Stopped. Dataset saved in", out)


if __name__ == "__main__":
    main()
