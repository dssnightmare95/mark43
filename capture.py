#!/usr/bin/env python3
"""capture.py — entry point for the `action_capture` dataset recorder.

Runs the full modular system (mouse, keyboard, UI context and window focus) and
writes a JSONL timeline. All logic lives in the `action_capture` package; this
file just launches it, so `python capture.py` works from a clean checkout
without installing anything.

    python capture.py --help
    python capture.py --capture-text --a11y-snapshot

Equivalent module form:  python -m action_capture
"""

import sys
from pathlib import Path

# Allow running the script from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from action_capture.recorder import main

if __name__ == "__main__":
    main()
