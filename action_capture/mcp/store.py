"""Reading, filtering and summarizing the captured action log (JSONL).

Pure functions plus a small checkpoint state file, so this module is fully
testable without the MCP runtime. The log is append-only, so reads are safe
while the capture daemon keeps writing.
"""

import os
import json
import datetime
import collections

# Default log location. Clients should set ACTION_CAPTURE_LOG to an absolute
# path; otherwise we fall back to ./dataset/events.jsonl relative to the cwd.
DEFAULT_LOG = os.environ.get("ACTION_CAPTURE_LOG") or os.path.join(
    "dataset", "events.jsonl")

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
    """Events recorded after the last checkpoint (all events if none set)."""
    cp = get_checkpoint(log_path)
    since_seq = cp["seq"] if cp else None
    return read_events(log_path, since_seq=since_seq, process=process, limit=limit)


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
