"""Effect layer: what changed on disk as a result of the human's actions.

Adaptive by design:
- Any file (binary, CAD, canvas): a `file_change` event (path/size/change).
- Text files: an additional unified diff.
- Complex GUI apps: the semantic "what" already comes from the UIA process
  layer; this module is the file-level complement.

`differ`  - text detection + unified diffs (pure, testable).
`watcher` - the polling agent that emits file_change events for session roots.
"""
