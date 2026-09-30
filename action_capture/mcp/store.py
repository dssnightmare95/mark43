"""Reading, filtering and summarizing the captured action log (JSONL).

Pure functions plus a small checkpoint state file, so this module is fully
testable without the MCP runtime. The log is append-only, so reads are safe
while the capture daemon keeps writing.
"""

import os
import json
import datetime
import collections

from ..core.paths import default_log

# Shared user-level log (override with ACTION_CAPTURE_LOG / ACTION_CAPTURE_HOME).
DEFAULT_LOG = default_log()

# Events that carry no window context / are pure UI noise for summaries.
_MOUSE_TYPES = {"click", "drag", "scroll"}


def _state_path(log_path):
    return os.path.join(os.path.dirname(os.path.abspath(log_path)),
                        ".mcp_state.json")


def iter_events(log_path):
    """Yield parsed events, skipping blank/corrupt lines."""
    if not os.path.exists(log_path):
        return
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _process_of(event):
    return (event.get("window") or {}).get("process", "") or ""


def read_events(log_path=DEFAULT_LOG, *, since_seq=None, since_time=None,
                until_time=None, process=None, event_types=None, limit=None):
    """Return events matching the filters (oldest first).

    `limit` keeps the most recent N after filtering.
    """
    types = set(event_types) if event_types else None
    proc = process.lower() if process else None
    out = []
    for ev in iter_events(log_path):
        if since_seq is not None and ev.get("seq", 0) <= since_seq:
            continue
        if since_time and ev.get("timestamp", "") <= since_time:
            continue
        if until_time and ev.get("timestamp", "") > until_time:
            continue
        if proc and _process_of(ev).lower() != proc:
            continue
        if types and ev.get("event_type") not in types:
            continue
        out.append(ev)
    if limit is not None and limit >= 0:
        out = out[-limit:]
    return out


def latest(log_path=DEFAULT_LOG):
    """Return (max_seq, last_timestamp) seen in the log, or (0, "")."""
    max_seq = 0
    last_ts = ""
    for ev in iter_events(log_path):
        seq = ev.get("seq", 0)
        if seq > max_seq:
            max_seq = seq
        ts = ev.get("timestamp", "")
        if ts > last_ts:
            last_ts = ts
    return max_seq, last_ts


def set_checkpoint(log_path=DEFAULT_LOG, label=""):
    """Record a turn boundary at the current tail of the log."""
    max_seq, last_ts = latest(log_path)
    cp = {"seq": max_seq, "timestamp": last_ts, "label": label,
          "created": datetime.datetime.now().isoformat(timespec="milliseconds")}
    with open(_state_path(log_path), "w", encoding="utf-8") as f:
        json.dump(cp, f)
    return cp


def get_checkpoint(log_path=DEFAULT_LOG):
    """Return the stored checkpoint, or None if none set yet."""
    path = _state_path(log_path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def actions_since_checkpoint(log_path=DEFAULT_LOG, *, process=None, limit=None):
    """Events recorded after the last checkpoint (all events if none set).

    Filters by timestamp, not seq: seq is a per-process counter that resets on
    daemon restart, so a stored seq can't be compared across restarts.
    """
    cp = get_checkpoint(log_path)
    since_time = cp["timestamp"] if cp else None
    return read_events(log_path, since_time=since_time, process=process, limit=limit)


def file_changes(log_path=DEFAULT_LOG, *, path=None, since_seq=None, limit=None):
    """file_change events, optionally filtered by a path substring.

    Searches the whole log by default (not just since the last checkpoint), so
    it answers "what did I change in X" even several turns later.
    """
    out = []
    needle = path.lower() if path else None
    for ev in read_events(log_path, since_seq=since_seq,
                          event_types=["file_change"]):
        if needle and needle not in (ev.get("file", {}).get("path", "").lower()):
            continue
        out.append(ev)
    if limit is not None and limit >= 0:
        out = out[-limit:]
    return out


def _seconds_between(start, end):
    try:
        return round((datetime.datetime.fromisoformat(end)
                      - datetime.datetime.fromisoformat(start)).total_seconds(), 1)
    except (ValueError, TypeError):
        return None


def window_timeline(log_path=DEFAULT_LOG, *, since_time=None, limit=None):
    """Which app/window (GUI) was active over time, with dwell durations.

    Built from window_focus events; each segment lasts until the next focus
    change (the last one until the most recent event in the log).
    """
    focus = read_events(log_path, since_time=since_time,
                        event_types=["window_focus"])
    if not focus:
        return []
    _, last_ts = latest(log_path)
    segments = []
    for i, e in enumerate(focus):
        w = e.get("window", {})
        start = e.get("timestamp", "")
        end = focus[i + 1].get("timestamp", "") if i + 1 < len(focus) else last_ts
        segments.append({
            "process": w.get("process", ""),
            "title": w.get("title", ""),
            "start": start,
            "end": end,
            "seconds": _seconds_between(start, end),
        })
    if limit is not None and limit >= 0:
        segments = segments[-limit:]
    return segments


def summarize(events):
    """Aggregate a list of events into a compact summary dict."""
    by_type = collections.Counter()
    by_process = collections.Counter()
    first_ts = last_ts = ""
    for ev in events:
        by_type[ev.get("event_type", "?")] += 1
        proc = _process_of(ev)
        if proc:
            by_process[proc] += 1
        ts = ev.get("timestamp", "")
        if ts:
            if not first_ts or ts < first_ts:
                first_ts = ts
            if ts > last_ts:
                last_ts = ts
    return {
        "total": len(events),
        "by_event_type": dict(by_type),
        "by_process": dict(by_process.most_common()),
        "time_range": {"from": first_ts, "to": last_ts},
    }
