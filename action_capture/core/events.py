"""Event schema helpers and the JSONL sink.

Every event carries a schema_version, a globally monotonic seq (true creation
order, even though the sink may write enriched events slightly out of order),
and an ISO timestamp. Consumers can sort by seq or timestamp.
"""

import json
import datetime
import threading

SCHEMA_VERSION = 1

_seq_lock = threading.Lock()
_seq = 0


def next_seq():
    global _seq
    with _seq_lock:
        _seq += 1
        return _seq


def seed_seq(start):
    """Continue the seq counter from an existing log so it stays monotonic
    across daemon restarts (seq is otherwise a per-process counter)."""
    global _seq
    with _seq_lock:
        if start and start > _seq:
            _seq = start


def iso_now():
    return datetime.datetime.now().isoformat(timespec="milliseconds")


def new_event(event_type):
    """Base event dict. Agents fill in the rest, then hand it to the sink."""
    return {
        "schema_version": SCHEMA_VERSION,
        "seq": next_seq(),
        "timestamp": iso_now(),
        "event_type": event_type,
        "label": None,
    }


class JsonlWriter:
    """Thread-safe JSON Lines sink: one JSON object per line, flushed eagerly."""

    def __init__(self, path):
        self._f = open(path, "a", encoding="utf-8")
        self._lock = threading.Lock()

    def write(self, obj):
        line = json.dumps(obj, ensure_ascii=False)
        with self._lock:
            self._f.write(line + "\n")
            self._f.flush()

    def close(self):
        try:
            self._f.close()
        except Exception:
            pass
