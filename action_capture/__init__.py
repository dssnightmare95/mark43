"""
action_capture - modular computer-use dataset recorder for Windows.

Each capture concern is a separate "agent" that emits enriched events into a
single JSONL timeline, so an AI can later read *what* a human did and *how*.

Layout:
    core/       shared plumbing (event schema, sink, win32 helpers, state)
    labeling/   pure functions: gesture classification + human-readable labels
    agents/     one capturer per concern:
                  mouse       - clicks, drags, scroll, multi-click, paths
                  keyboard    - keys, shortcuts, typed-text aggregation
                  ui_context  - UIA element (type/name/state/ancestry), drops,
                                text selection, a11y snapshot (enrichment stage)
                  window      - foreground/app focus changes
    recorder    wires everything together (entry point)

Run with:  python -m action_capture
"""

__version__ = "0.1.0"
