"""Text-file detection and unified diffs (pure functions)."""

import os
import difflib

# Extensions we always treat as text (fast path; sniffing covers the rest).
TEXT_EXTS = {
    ".txt", ".md", ".rst", ".log",
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".vue", ".mjs", ".cjs",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".java", ".kt", ".go", ".rs",
    ".rb", ".php", ".swift", ".m", ".r", ".lua", ".pl", ".scala", ".dart",
    ".sh", ".bat", ".ps1", ".psm1",
    ".html", ".htm", ".css", ".scss", ".less", ".xml", ".svg",
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".csv", ".tsv", ".sql", ".graphql", ".proto",
    ".gitignore", ".gitattributes", ".env", ".dockerfile", ".makefile",
}

MAX_TEXT_BYTES = 2_000_000     # don't read/diff files larger than this
_SNIFF = 2048


def is_text_file(path):
    """Heuristic: known text extension, else sniff for a NUL byte / UTF-8."""
    ext = os.path.splitext(path)[1].lower()
    base = os.path.basename(path).lower()
    if ext in TEXT_EXTS or base in TEXT_EXTS:
        return True
    if ext and ext not in TEXT_EXTS:
        # Unknown extension: sniff.
        pass
    try:
        with open(path, "rb") as f:
            chunk = f.read(_SNIFF)
    except OSError:
        return False
    if b"\x00" in chunk:
        return False
    try:
        chunk.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def read_text(path):
    """Read a text file, or None if too big / unreadable."""
    try:
        if os.path.getsize(path) > MAX_TEXT_BYTES:
            return None
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def unified_diff(old_text, new_text, path="", max_lines=400):
    """Return (diff_string, truncated). Empty string if identical."""
    old_lines = (old_text or "").splitlines()
    new_lines = (new_text or "").splitlines()
    diff = list(difflib.unified_diff(
        old_lines, new_lines, lineterm="", n=2,
        fromfile=f"{path} (before)", tofile=f"{path} (after)"))
    if not diff:
        return "", False
    truncated = False
    if len(diff) > max_lines:
        diff = diff[:max_lines]
        truncated = True
    return "\n".join(diff), truncated
