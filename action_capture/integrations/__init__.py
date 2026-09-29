"""Integrations that connect the capture data to AI assistants.

`context_hook` is a CLI used by Claude Code hooks:
- `inject`     (UserPromptSubmit): print a compact summary of what the human
               did since the last turn; its stdout is added to the AI context.
- `checkpoint` (Stop): mark a turn boundary so the next `inject` window covers
               only the human's subsequent work (not the AI's own edits).
"""
