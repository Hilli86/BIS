"""Prozesslokale Fan-out-Warteschlangen für SSE-Clients (Beleuchtung)."""

from __future__ import annotations

import json
import queue
import threading
from typing import Any

_sub_lock = threading.Lock()
_subscribers: list[queue.Queue] = []


def register_subscriber() -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=64)
    with _sub_lock:
        _subscribers.append(q)
    return q


def unregister_subscriber(q: queue.Queue) -> None:
    with _sub_lock:
        if q in _subscribers:
            _subscribers.remove(q)


def count_subscribers() -> int:
    with _sub_lock:
        return len(_subscribers)


def broadcast_dict(payload: dict[str, Any]) -> None:
    line = json.dumps(payload, ensure_ascii=False)
    with _sub_lock:
        qs = list(_subscribers)
    for q in qs:
        try:
            q.put_nowait(line)
        except queue.Full:
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(line)
            except queue.Full:
                pass
