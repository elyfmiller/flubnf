"""PRODUCTION: the short TTL cache behind the server's repeated filesystem
scans.

One tiny time-to-live cache, shared by every cheap-but-repeated scan.

Console pages ask the same filesystem questions (weeks on disk, workroots
with results, archives) several times per render; idle, /retro spent 68 of
its 71 ms on them. A 2.5 s TTL collapses one render's repeats yet keeps
progress bars live (pollers run at 2-3 s). State-changing actions call
clear_all(), so staleness is zero for anything the user did.

Values are shared between callers and not copied: never mutate them.
"""
from __future__ import annotations

import functools
import threading
import time

DEFAULT_TTL_S = 2.5

_REGISTRY: list = []
_LOCK = threading.Lock()


def ttl_cache(ttl_s: float = DEFAULT_TTL_S, clock=time.monotonic):
    """Cache a function's result per argument tuple for `ttl_s` seconds.

    Arguments must be hashable. The wrapper gains cache_clear() and is
    registered for clear_all(). Monotonic clock: a wall-clock adjustment must
    not freeze or expire a cache.
    """
    def deco(fn):
        store: dict = {}

        @functools.wraps(fn)
        def wrapper(*args):
            now = clock()
            with _LOCK:
                hit = store.get(args)
                if hit is not None and (now - hit[0]) < ttl_s:
                    return hit[1]
            # outside the lock: a slow scan must not block other cached reads
            value = fn(*args)
            with _LOCK:
                # stamp on completion: a scan slower than the TTL would
                # otherwise be born expired and never cached (under load)
                store[args] = (clock(), value)
            return value

        def cache_clear() -> None:
            with _LOCK:
                store.clear()

        wrapper.cache_clear = cache_clear
        wrapper.ttl_s = ttl_s
        _REGISTRY.append(wrapper)
        return wrapper
    return deco


def clear_all() -> None:
    """Invalidate every TTL cache in this process. Cheap: call it after any
    action that changes what the caches describe (run start/stop, archive,
    delete)."""
    for wrapper in list(_REGISTRY):
        wrapper.cache_clear()
