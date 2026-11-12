"""A stored snapshot changed by hand, read through the parsed-snapshot
cache (app/core/datasets/dataset.py; review 3 of #93, S3 16). The store
never does either: every write is a new file with all its columns.

  * a snapshot rewritten in place with its size, mtime and inode put back
    is read again, not served from memory (the key holds the time of the
    file's last change too, which a hand-set mtime moves);
  * a snapshot without a value, location_name or date column reads as the
    per-row read did before the cache: weeks() returns the weeks when it
    has its dates, and series() raises the same KeyError where that read
    raised, and nowhere else.
"""
from __future__ import annotations

import csv
import io
import os
import time
from datetime import date

import pytest

from app.core import datasets as D
from app.core.datasets import dataset as DM

from test_dataset_engines import grouped_bytes            # noqa: E402
from test_dataset_snapshot_reads import (                 # noqa: E402
    reference_series, versioned_bytes)


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    DM.clear_snapshot_cache()
    yield tmp_path / "datasets"
    DM.clear_snapshot_cache()


def reference_weeks(self):
    """Dataset.weeks before the cache, verbatim."""
    return sorted({r["date"] for r in self._final_rows()})


# ------------------------------------------ rewritten with its stat put back

def test_a_snapshot_rewritten_in_place_with_its_stat_put_back_is_read_again():
    ds = D.ingest(grouped_bytes(), "wave", kind="count")
    p = ds.final_path
    name = ds.groups[0]
    before = ds.series(name)
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    i = next(i for i, ln in enumerate(lines[1:], 1)
             if ln.split(",")[2] == name)
    f = lines[i].split(",")
    old = f[3]
    f[3] = str(int(old) + 1 if len(str(int(old) + 1)) == len(old)
               else int(old) - 1)
    lines[i] = ",".join(f)
    new = "".join(lines)
    assert len(new) == len(text) and new != text
    st = p.stat()
    time.sleep(0.05)
    with open(p, "w", encoding="utf-8", newline="") as fh:   # in place
        fh.write(new)
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
    now = p.stat()
    assert (now.st_size, now.st_mtime_ns, now.st_ino, now.st_dev) == \
        (st.st_size, st.st_mtime_ns, st.st_ino, st.st_dev)
    if now.st_ctime_ns == st.st_ctime_ns:
        pytest.skip("this file system kept the change time")
    after = D.get(ds.id).series(name)
    assert after == reference_series(D.get(ds.id), name)
    assert after != before
    assert float(f[3]) in after["values"]


# ----------------------------------------------- a column missing by hand

def _drop(path, cols) -> None:
    """Write the snapshot again without `cols` (a hand edit)."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
        head = [c for c in rows[0] if c not in cols]
    out = io.StringIO()
    w = csv.DictWriter(out, head, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    path.write_text(out.getvalue(), encoding="utf-8")


def _outcome(fn):
    try:
        return ("ok", fn())
    except Exception as e:                       # compared, not hidden
        return (type(e).__name__, e.args)


def _both(ds_id, fn):
    """fn(dataset) through the read before the cache and through this one,
    each on a fresh Dataset and an empty cache."""
    DM.clear_snapshot_cache()
    with pytest.MonkeyPatch.context() as m:
        m.setattr(DM.Dataset, "weeks", reference_weeks)
        m.setattr(DM.Dataset, "series", reference_series)
        old = _outcome(lambda: fn(D.get(ds_id)))
    DM.clear_snapshot_cache()
    new = _outcome(lambda: fn(D.get(ds_id)))
    return old, new


@pytest.mark.parametrize("cols", [("value",), ("location_name",),
                                  ("value", "location_name"), ("date",),
                                  ("date", "value"), ("weekly_rate",)])
@pytest.mark.parametrize("kind", ["final", "versioned"])
def test_a_snapshot_without_a_column_reads_as_before(kind, cols):
    ds = (D.ingest(grouped_bytes(), "wave", kind="count") if kind == "final"
          else D.ingest(versioned_bytes(), "snap", kind="count"))
    weeks = ds.forecast_dates()
    asofs = [None, weeks[0], weeks[len(weeks) // 2], weeks[-1]]
    names = ds.groups + ["not a group"]
    paths = ({ds.final_path} if kind == "final" else
             {ds.final_path, ds.vintage_path(asofs[2])})
    for p in paths:
        _drop(p, cols)
    seen = set()
    old, new = _both(ds.id, lambda d: d.weeks())
    assert new == old, ("weeks", old, new)
    seen.add(old[0])
    for a in asofs:
        for n in names:
            old, new = _both(ds.id, lambda d: d.series(n, a))
            assert new == old, (n, a, old, new)
            seen.add(old[0])
    if cols == ("weekly_rate",):
        assert seen == {"ok"}
    elif "date" not in cols:
        # the weeks are still read: what the review found raised
        assert _both(ds.id, lambda d: d.weeks())[1][0] == "ok"


def test_an_empty_or_header_only_snapshot_reads_as_before():
    ds = D.ingest(grouped_bytes(), "wave", kind="count")
    for text in ("", "date,location,location_name\n"):
        ds.final_path.write_text(text, encoding="utf-8")
        for fn in (lambda d: d.weeks(), lambda d: d.series("x"),
                   lambda d: d.series(ds.groups[0])):
            old, new = _both(ds.id, fn)
            assert new == old, (text, old, new)


def test_a_whole_snapshot_still_reads_through_the_cache_once():
    ds = D.ingest(grouped_bytes(), "wave", kind="count")
    DM.clear_snapshot_cache()
    for n in ds.groups:
        assert ds.series(n) == reference_series(ds, n)
    assert len(DM._SNAPS) == 1
    (entry,) = DM._SNAPS.values()
    assert entry[3] == frozenset()
    assert ds.weeks() == reference_weeks(ds)
    assert date.fromisoformat(ds.weeks()[0])
