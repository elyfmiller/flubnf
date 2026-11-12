"""The per-week national quantile cache's key and its temporary files
(review 3 of #93, findings 8 and 15).

  * playback_cache/us_quantiles/<week>.json holds while its key does. The
    key holds the samples file's mtime to the nanosecond and the bytes it
    holds once read (a gzip file's own record of them), so a week's
    samples replaced within the same second are read again, and reclaim's
    gzip (which keeps the mtime and the content) leaves the cache valid.
  * A process killed between writing a week's cache and renaming it
    leaves a .tmp file; the next recomputation removes it once it is
    old, never one a writer may still be renaming.

The season, its fixture hub and the reference construction are
test_season_cache.py's.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import retro, retro_store                    # noqa: E402
from app.tests import test_season_cache as _cache          # noqa: E402

# test_season_cache's season (its fixture), its names and its reference
season = _cache.season
LEVELS, WEEKS = _cache.LEVELS, _cache.WEEKS
old_national_aggregate, same = _cache.old_national_aggregate, _cache.same

NS = 1_000_000_000


def _replace_week(root: Path, asof: str, shift: float, same_size: bool,
                  mtime_ns: int) -> None:
    """Replace a stored plain week's samples with every draw and quantile
    moved by `shift` (as a restore of another replay of the week would),
    written beside and renamed over it, then given `mtime_ns`; padded with
    blanks to the old size when `same_size`."""
    sp = root / "weeks" / asof / "samples.json"
    old_size = sp.stat().st_size
    d = json.loads(sp.read_text(encoding="utf-8"))
    for loc, by_h in d["pf"].items():
        for h, draws in by_h.items():
            by_h[h] = [round(v + shift, 1) for v in draws]
    for loc, by_h in d["analogue"].items():
        for h, q in by_h.items():
            by_h[h] = {k: round(v + shift, 1) for k, v in q.items()}
    text = json.dumps(d)
    if same_size:
        assert len(text) <= old_size
        text += " " * (old_size - len(text))
    tmp = sp.with_name("samples.json.new")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, sp)
    os.utime(sp, ns=(mtime_ns, mtime_ns))
    assert (sp.stat().st_size == old_size) is same_size


def _rescore(root: Path):
    """The aggregate again, as a rescore asks for it."""
    (root / "playback_cache" / "us_aggregate.json").unlink()
    return retro.national_aggregate(root)


def test_a_week_replaced_in_the_same_second_is_read_again(season):
    """The same whole second, another nanosecond, the same size."""
    first = retro.national_aggregate(season)
    sp = season / "weeks" / WEEKS[1] / "samples.json"
    was = sp.stat().st_mtime_ns
    other = was - was % NS + (was % NS + NS // 2) % NS
    assert other // NS == was // NS and other != was
    _replace_week(season, WEEKS[1], 40.0, same_size=True, mtime_ns=other)
    got = _rescore(season)
    want = old_national_aggregate(season)
    assert not same(want, first)                   # the samples matter
    assert same(got, want)


def test_a_week_replaced_with_its_very_mtime_is_read_again(season):
    """A restore that keeps the time to the nanosecond (or a file system
    with coarse times): the bytes differ."""
    first = retro.national_aggregate(season)
    sp = season / "weeks" / WEEKS[1] / "samples.json"
    was = sp.stat().st_mtime_ns
    _replace_week(season, WEEKS[1], 40.0, same_size=False, mtime_ns=was)
    got = _rescore(season)
    want = old_national_aggregate(season)
    assert not same(want, first)
    assert same(got, want)


def test_a_week_gzipped_keeps_its_key(season):
    """Reclaim's gzip keeps the mtime and the content: the key is the
    plain file's, so the week is not read again (test_season_cache's
    test_compressing_a_week_keeps_its_cache)."""
    sp = season / "weeks" / WEEKS[0] / "samples.json"
    plain = retro._national_week_key(sp, LEVELS)
    gz = retro_store.compress_samples_file(sp)
    assert gz.name.endswith(".gz") and not sp.exists()
    assert retro._national_week_key(gz, LEVELS) == plain
    assert plain["bytes"] > 0 and plain["mtime_ns"] > 0


def test_a_killed_writers_temporary_files_go_on_the_next_recomputation(
        season):
    retro.national_aggregate(season)
    qd = season / "playback_cache" / retro.US_QUANTILES_DIRNAME
    old = time.time() - 2 * 3600                  # two hours
    stale = [qd / f"{WEEKS[0]}.json.4242.99.tmp",
             qd / f"{WEEKS[3]}.json.4243.12.tmp"]
    for p in stale:
        p.write_text("{")
        os.utime(p, (old, old))
    fresh = qd / f"{WEEKS[1]}.json.{os.getpid()}.7.tmp"
    fresh.write_text("{")                         # a writer at work
    got = _rescore(season)
    assert same(got, old_national_aggregate(season))
    assert not any(p.exists() for p in stale)
    assert fresh.exists()
    # a writer's file is a few milliseconds old: an hour is long dead
    assert retro._US_QUANTILES_TMP_STALE_S <= 3600
    # every week's own cache is kept
    assert sorted(p.stem for p in qd.glob("*.json")) == list(WEEKS)
