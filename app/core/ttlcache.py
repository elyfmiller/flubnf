"""One tiny time-to-live cache, shared by every cheap-but-repeated scan.

Several console pages answer the same filesystem question on every request:
how many weeks of a season are on disk, which workroots hold results, what
is archived. Each answer costs a directory walk that stats one file per
week, and the pages ask for it several times per render. Measured idle on
the development machine, /retro spent 68 ms of its 71 ms doing exactly that,
and the cost multiplies under load, because the interactive server is then
competing with the fitting processes for the CPU.

The remedy is deliberately small. A scan is cached for a couple of seconds,
which is short enough that a progress bar still feels live (the pollers run
at 2 to 3 seconds) and long enough that one page render asks the filesystem
once instead of a dozen times. Anything that CHANGES the underlying state
(starting or stopping a run, archiving, deleting) calls clear_all(), so the
interface never shows a stale count after a user action. Staleness is
therefore bounded by the TTL for background drift and is zero for anything
the user did.

Values are shared between callers, so a cached function must return data its
callers only read. Nothing here copies on the way out; a caller that needs to
mutate should build its own structure from the cached one.
"""
from __future__ import annotations

import functools
import threading
import time

#: Long enough to collapse the repeats inside one page render, short enough
#: that a progress readout still tracks a running fit.
DEFAULT_TTL_S = 2.5

_REGISTRY: list = []
_LOCK = threading.Lock()


def ttl_cache(ttl_s: float = DEFAULT_TTL_S, clock=time.monotonic):
    """Cache a function's result per argument tuple for `ttl_s` seconds.

    Arguments must be hashable, which every call site here satisfies (paths
    and season names). The wrapper gains cache_clear(), and every wrapper is
    registered so clear_all() can invalidate the lot after a state change.

    A monotonic clock by default: a system clock adjustment mid-run must not
    freeze a cache or expire one early.
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
            # computed outside the lock: a slow scan must not block every
            # other cached read in the process
            value = fn(*args)
            with _LOCK:
                store[args] = (now, value)
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
    """Invalidate every TTL cache in this process.

    Called from the actions that change what the caches describe: a run
    starting or stopping, a season archived or discarded, an archive
    deleted. It is cheap (a handful of dict clears), so erring toward
    calling it is always right: a stale count after a click is a bug, a
    redundant rescan is a millisecond.
    """
    for wrapper in list(_REGISTRY):
        wrapper.cache_clear()
