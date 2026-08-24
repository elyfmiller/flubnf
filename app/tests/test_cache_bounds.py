"""The two long-lived caches must stay bounded.

Both hold one entry per season root, and season roots are not a fixed set:
every archived replay adds one, and every rescore mints a fresh content key
for a root already cached. A parsed scores.json frame costs about 11 MB
resident (measured, 2.56 MB file), so an unbounded parse cache is a memory
plateau in a process that also has to leave room for the fitting engines.

These pin the policy, not the numbers: least-recently-used, capped, and
evicting one entry at a time rather than flushing every warm entry at once.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd                                          # noqa: E402

from app.core import retro                                   # noqa: E402
from app.ui import server as srv                             # noqa: E402


def _root(tmp_path: Path, i: int, cells: int = 3) -> Path:
    """A season root carrying a scoreable scores.json."""
    r = tmp_path / f"root{i:02d}"
    r.mkdir()
    df = pd.DataFrame([{"model": "ensemble", "location": "Ohio",
                        "fips": "39", "asof": "2025-11-15", "horizon": h,
                        "wis": 1.0 + h + i, "base_wis": 2.0, "rel": 0.5}
                       for h in range(cells)])
    (r / "scores.json").write_text(df.to_json())
    return r


def test_scores_frames_is_lru_and_capped(tmp_path):
    srv._SCORES_FRAMES.clear()
    cap = srv._SCORES_FRAMES_MAX
    roots = [_root(tmp_path, i) for i in range(cap + 5)]
    for r in roots:
        assert srv._scores_df(r) is not None
        assert len(srv._SCORES_FRAMES) <= cap        # never exceeds, ever

    # the cap is a plateau, not a sawtooth: after the sweep it is FULL, where
    # a clear-the-whole-dict policy would have just thrown everything away
    assert len(srv._SCORES_FRAMES) == cap
    # and what it kept is the most recent, not the oldest
    kept = {k[0] for k in srv._SCORES_FRAMES}
    assert kept == {str(r / "scores.json") for r in roots[-cap:]}

    # touching an old entry promotes it: re-reading the newest then adding
    # one more must evict the one in the middle, not the one just used
    srv._scores_df(roots[-cap])                      # promote to most-recent
    srv._scores_df(_root(tmp_path, 99))
    kept = {k[0] for k in srv._SCORES_FRAMES}
    assert str(roots[-cap] / "scores.json") in kept
    srv._SCORES_FRAMES.clear()


def test_scores_frames_still_serves_the_same_frame_from_cache(tmp_path):
    """Bounding must not change what a hit returns: same object, no reparse."""
    srv._SCORES_FRAMES.clear()
    r = _root(tmp_path, 0)
    first = srv._scores_df(r)
    assert srv._scores_df(r) is first                # identity, not a reparse
    srv._SCORES_FRAMES.clear()


def test_scores_frames_invalidates_on_rewrite(tmp_path):
    """Content-keyed: a rescore must not be served the stale frame."""
    srv._SCORES_FRAMES.clear()
    r = _root(tmp_path, 0, cells=3)
    assert len(srv._scores_df(r)) == 3
    df = pd.DataFrame([{"model": "ensemble", "location": "Ohio", "fips": "39",
                        "asof": "2025-11-15", "horizon": h, "wis": 1.0,
                        "base_wis": 2.0, "rel": 0.5} for h in range(7)])
    sf = r / "scores.json"
    st = sf.stat()
    sf.write_text(df.to_json())
    # a same-second rewrite still differs in size or mtime_ns; assert the key
    # actually moved rather than trusting the clock
    assert (sf.stat().st_mtime_ns, sf.stat().st_size) != (st.st_mtime_ns,
                                                          st.st_size)
    assert len(srv._scores_df(r)) == 7
    srv._SCORES_FRAMES.clear()


def test_summary_cache_is_lru_and_capped(tmp_path, monkeypatch):
    """run_summary's cache grew one entry per root forever. Entries are
    small, so the cap is generous; what matters is that it exists."""
    monkeypatch.setattr(retro, "_SUMMARY_CACHE_MAX", 4)
    retro._SUMMARY_CACHE.clear()
    roots = [_root(tmp_path, i) for i in range(9)]
    for r in roots:
        s = retro.run_summary(r)
        assert s["scored"] is True
        assert s["headline_rel"] is not None
        assert len(retro._SUMMARY_CACHE) <= 4
    assert len(retro._SUMMARY_CACHE) == 4
    assert set(retro._SUMMARY_CACHE) == {str(r) for r in roots[-4:]}
    retro._SUMMARY_CACHE.clear()


def test_summary_cache_hit_still_matches_a_cold_read(tmp_path):
    """Correctness is unchanged: the cached headline equals the fresh one."""
    retro._SUMMARY_CACHE.clear()
    r = _root(tmp_path, 0)
    cold = retro.run_summary(r)["headline_rel"]
    warm = retro.run_summary(r)["headline_rel"]
    retro._SUMMARY_CACHE.clear()
    again = retro.run_summary(r)["headline_rel"]
    assert cold == warm == again
    # and the key still carries its invalidation inputs
    scored_at = (r / "scores.json").stat().st_mtime
    key = retro._SUMMARY_CACHE[str(r)][0]
    assert key[0] == scored_at
    retro._SUMMARY_CACHE.clear()


def test_summary_cache_invalidates_when_scores_change(tmp_path):
    retro._SUMMARY_CACHE.clear()
    r = _root(tmp_path, 0)
    first = retro.run_summary(r)["headline_rel"]
    df = pd.DataFrame([{"model": "ensemble", "location": "Ohio", "fips": "39",
                        "asof": "2025-11-15", "horizon": 0, "wis": 9.0,
                        "base_wis": 2.0, "rel": 4.5}])
    sf = r / "scores.json"
    sf.write_text(df.to_json())
    import os
    os.utime(sf, (sf.stat().st_atime, sf.stat().st_mtime + 10))
    assert retro.run_summary(r)["headline_rel"] != first
    retro._SUMMARY_CACHE.clear()


def test_caches_are_ordered_so_eviction_is_possible():
    """A plain dict cannot express least-recently-used. Guard the type."""
    from collections import OrderedDict
    assert isinstance(srv._SCORES_FRAMES, OrderedDict)
    assert isinstance(retro._SUMMARY_CACHE, OrderedDict)
    assert srv._SCORES_FRAMES_MAX >= 1 and retro._SUMMARY_CACHE_MAX >= 1
    # the scores frames are the large ones; they must be capped tighter
    assert srv._SCORES_FRAMES_MAX < retro._SUMMARY_CACHE_MAX
    json.dumps({"cap": srv._SCORES_FRAMES_MAX})   # plain ints, not surprises
