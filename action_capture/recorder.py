"""Wires the agents together and runs the capture session.

Run:  python -m action_capture [--out DIR] [--mask-keys] [--capture-text]
                             [--no-aggregate] [--a11y-snapshot]

Controls:  Esc = stop    Ctrl+Alt+P = pause/resume
"""

import os
import argparse
import threading

from .core.dpi import set_dpi_awareness
from .core.events import JsonlWriter
from .core.secure import SecureState
from .core.state import InputState
from .core.win32util import HAS_WIN32
from .agents.ui_context import UIContextAgent
from .agents.mouse import MouseAgent
from .agents.keyboard import KeyboardAgent
from .agents.window import WindowAgent


def build_parser():
    ap = argparse.ArgumentParser(
        prog="action_capture",
        description="Modular computer-use dataset recorder for Windows")
    ap.add_argument("--out", default="dataset", help="output directory")
    ap.add_argument("--mask-keys", action="store_true",
                    help="log key categories instead of actual characters")
    ap.add_argument("--capture-text", action="store_true",
                    help="record selected text on text-selection gestures "
                         "(never for password/secure fields)")
    ap.add_argument("--no-aggregate", action="store_true",
                    help="log every keystroke instead of aggregating typed text")
    ap.add_argument("--a11y-snapshot", action="store_true",
                    help="attach an accessibility-tree snapshot on each click")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)

    set_dpi_awareness()
    os.makedirs(args.out, exist_ok=True)
    jsonl_path = os.path.join(args.out, "events.jsonl")
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

    print(f"Recording -> {jsonl_path}")
    print("  keys:", "masked" if args.mask_keys else "raw",
          "| aggregate:", "off" if args.no_aggregate else "on",
          "| selected text:", "on" if args.capture_text else "off",
          "| a11y:", "on" if args.a11y_snapshot else "off")
    print("  Esc = stop   |   Ctrl+Alt+P = pause/resume")
    if not HAS_WIN32:
        print("  WARNING: pywin32 not installed - no window/monitor context.")

    worker.start()
    window_agent.start()
    mouse_agent.start()
    keyboard_agent.start()

    try:
        # The keyboard listener returns False (stops) on Esc; wait for that.
        keyboard_agent.listener.join()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        mouse_agent.stop()
        window_agent.stop()
        keyboard_agent.stop()      # flushes pending typed text
        worker.stop()
        worker.join(timeout=3)
        sink.close()
        print("Stopped. Dataset saved in", args.out)


if __name__ == "__main__":
    main()
