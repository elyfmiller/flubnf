"""Own-data replay speed: a dataset's snapshot CSV is parsed once per file,
not once per group per week (app/core/datasets/dataset.py snapshot_index,
Dataset.series), and nothing a run computes or stores changes.

Held:
  * Dataset.series gives exactly what the per-group read gave
    (reference_series below is the old body, verbatim), for every group at
    every week, final data and as_of snapshots alike;
  * a replay and a dataset forecast store the same bytes with either read
    (gzip files compared after decompression, run_meta.json less its two
    clock fields);
  * the reads are counted: one parse per snapshot file however many groups
    and weeks ask, where the per-group read opened it for every call;
  * the cache is keyed on the file (a snapshot written again is read
    afresh, a deleted one is refused as before), bounded, read-only, and
    safe across threads.
"""
from __future__ import annotations

import builtins
import csv
import gzip
import json
import os
import sys
import threading
from datetime import date
from pathlib import Path

import pytest

from app.core import custom_retro as CX
from app.core import custom_run as CR
from app.core import datasets as D
from app.core.datasets import dataset as DM

from test_custom_run import hub_ts, spec_for            # noqa: E402
from test_dataset_engines import (                      # noqa: E402
    _curve, _saturdays, grouped_bytes)


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    DM.clear_snapshot_cache()
    yield tmp_path / "datasets"
    DM.clear_snapshot_cache()


def reference_series(self, name, as_of=None):
    """Dataset.series before the snapshot index, verbatim: the snapshot
    read again for every call."""
    if as_of is None:
        rows = self._final_rows()
    else:
        with open(self.truth_path(as_of), newline="",
                  encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    out = sorted((r["date"], float(r["value"])) for r in rows
                 if r["location_name"] == name and r["value"] != ""
                 and (as_of is None or r["date"] <= str(as_of)))
    return {"dates": [d for d, _ in out], "values": [v for _, v in out]}


def versioned_bytes(names=("Alabama", "Alaska", "Arizona"),
                    snapshots=16) -> bytes:
    """as_of snapshots for the last `snapshots` weeks of four and a half
    seasons (enough donors for the Groundhog), each holding every week to
    its date. A snapshot's two newest weeks read low and are revised up in
    later ones, so two vintages of one week differ."""
    w = list(_saturdays(date(2019, 8, 3), date(2024, 2, 24)))
    rows = []
    for k in range(len(w) - snapshots, len(w)):
        for i, d in enumerate(w[:k + 1]):
            for j, nm in enumerate(names):
                v = _curve(i, j, 3.0 + j)
                if k - i < 2:
                    v = max(0.0, v - 3 * (2 - (k - i)))
                rows.append(f"{w[k]},{d},{j + 1:02d},{nm},{v:g}")
    return ("as_of,target_end_date,location,location_name,observation\n"
            + "\n".join(rows) + "\n").encode()


_MAKE = {"final": lambda: D.ingest(grouped_bytes(), "wave", kind="count"),
         "national": lambda: D.ingest(hub_ts(), "hub", kind="count"),
         "versioned": lambda: D.ingest(versioned_bytes(), "snap",
                                       kind="count")}


def _make(kind):
    return _MAKE[kind]()


def _count_opens(monkeypatch, *modules) -> list:
    """Every file dataset.py (and `modules`) opens from now on: their
    module-level open."""
    opened = []

    def counting(file, *a, **k):
        opened.append(os.path.abspath(file))
        return builtins.open(file, *a, **k)
    for mod in (DM, *modules):
        monkeypatch.setattr(mod, "open", counting, raising=False)
    return opened


def _count_parses(monkeypatch) -> list:
    parsed = []
    real = DM._parse_snapshot

    def counting(fh):
        parsed.append(os.path.abspath(fh.name))
        return real(fh)
    monkeypatch.setattr(DM, "_parse_snapshot", counting)
    return parsed


# ------------------------------------------------------------ same views

@pytest.mark.parametrize("kind", ["final", "national", "versioned"])
def test_every_series_matches_the_per_group_read(kind):
    ds = _make(kind)
    assert ds.vintage_true == (kind == "versioned")
    # the week list too: the old body, on the final rows
    assert ds.weeks() == sorted({r["date"] for r in ds._final_rows()})
    for as_of in [None] + ds.forecast_dates():
        for name in ds.groups + ["not a group"]:
            got = ds.series(name, as_of)
            want = reference_series(ds, name, as_of)
            assert got == want, (name, as_of)
            # the same types and digits, not only equal numbers
            assert json.dumps(got) == json.dumps(want)
            assert all(type(v) is float for v in got["values"])


def test_two_vintages_of_one_week_still_differ():
    ds = _make("versioned")
    a, b = ds.forecast_dates()[0], ds.forecast_dates()[-1]
    sa, sb = ds.series("Alabama", a), ds.series("Alabama", b)
    wk = sa["dates"][-1]
    assert wk in sb["dates"]
    assert sa["values"][-1] != sb["values"][sb["dates"].index(wk)]


def test_the_baseline_and_observed_views_are_unchanged(monkeypatch):
    ds = _make("national")
    weeks = ds.forecast_dates()[-30:]
    new = {(w, n, k): CR.baseline_quantiles(ds, n, w, k)
           for w in weeks for n in ds.groups for k in (0, 1)}
    obs = {w: CR.observed(ds, w, ds.groups, drop_same_day=True)
           for w in weeks}
    monkeypatch.setattr(DM.Dataset, "series", reference_series)
    assert new == {(w, n, k): CR.baseline_quantiles(ds, n, w, k)
                   for w in weeks for n in ds.groups for k in (0, 1)}
    assert obs == {w: CR.observed(ds, w, ds.groups, drop_same_day=True)
                   for w in weeks}


# ------------------------------------------------- same stored files

def _stored(out: Path) -> dict:
    """A replay's stored files as bytes: gzip decompressed (the header
    carries a clock), run_meta.json less started_utc and finished_utc."""
    files = {f: gzip.decompress((out / f).read_bytes())
             for f in ("forecasts.json.gz", "cells.csv.gz",
                       "coverage.csv.gz")}
    meta = json.loads((out / CX.META).read_text(encoding="utf-8"))
    for k in ("started_utc", "finished_utc"):
        assert isinstance(meta.pop(k), float)
    files[CX.META] = json.dumps(meta, sort_keys=True).encode()
    return files


@pytest.mark.parametrize("kind,k", [("final", 0), ("national", 1),
                                    ("versioned", 0)])
def test_a_replay_stores_the_same_bytes(kind, k, tmp_path, monkeypatch):
    ds = _make(kind)
    weeks = ds.forecast_dates()[-9:]
    m_new = CX.run(ds, weeks, ds.groups, out_dir=tmp_path / "new",
                   weeks_to_drop=k)
    assert m_new["status"] == "done"
    assert m_new["summary"]["analogue"]["pooled"]["cells"] > 0
    monkeypatch.setattr(DM.Dataset, "series", reference_series)
    m_old = CX.run(ds, weeks, ds.groups, out_dir=tmp_path / "old",
                   weeks_to_drop=k)
    assert _stored(tmp_path / "new") == _stored(tmp_path / "old")
    assert m_new["summary"] == m_old["summary"]


def test_a_dataset_forecast_stores_the_same_bytes(tmp_path, monkeypatch):
    ds = _make("national")
    fd = ds.forecast_dates()[-12]

    def run(wr):
        wr.mkdir()
        outcome, _ = CR.run(spec_for(ds, fd=fd), ds, wr)
        # names with "/" on every platform (str() gives "\" on Windows)
        return outcome, {p.relative_to(wr).as_posix(): p.read_bytes()
                         for p in sorted(wr.rglob("*")) if p.is_file()}
    o_new, f_new = run(tmp_path / "new")
    monkeypatch.setattr(DM.Dataset, "series", reference_series)
    o_old, f_old = run(tmp_path / "old")
    assert "results.json" in f_new and "scores_custom.json" in f_new
    assert any(n.startswith("export/") for n in f_new)
    assert f_new == f_old
    assert {k: v for k, v in o_new.items() if k != "exports"} == \
        {k: v for k, v in o_old.items() if k != "exports"}


# ------------------------------------------------------- counted reads

def test_one_object_opens_each_file_once_for_every_view(monkeypatch):
    ds = _make("final")
    ds = D.get(ds.id)                    # a fresh object: nothing read yet
    DM.clear_snapshot_cache()
    opened = _count_opens(monkeypatch)
    weeks = ds.forecast_dates()
    calls = 0
    for w in [None] + weeks:
        for n in ds.groups:
            ds.series(n, w)
            calls += 1
    assert calls > 600
    # final data: one parse serves the week list and every view
    assert opened == [os.path.abspath(ds.final_path)]
    # a second object (an engine resolves one each week) reads nothing
    again = D.get(ds.id)
    again.forecast_dates()
    again.series(ds.groups[0], weeks[-1])
    assert opened == [os.path.abspath(ds.final_path)]
    # the rows truth() reads stay per object, read once
    again.truth()
    again.truth()
    assert len(opened) == 2


def test_a_versioned_dataset_parses_each_snapshot_once(monkeypatch):
    ds = _make("versioned")
    DM.clear_snapshot_cache()
    parsed = _count_parses(monkeypatch)
    # as a replay asks: week by week, every group (here three times over)
    for w in ds.forecast_dates():
        for _ in range(3):
            for n in ds.groups:
                ds.series(n, w)
    assert len(ds.forecast_dates()) == 16
    assert parsed == [os.path.abspath(ds.vintage_path(w))
                      for w in ds.forecast_dates()]


def test_a_snapshot_is_parsed_once_where_stat_and_fstat_disagree(monkeypatch):
    """Windows with Python 3.12: os.stat gives the creation time as
    st_ctime and os.fstat the last change, so a key holding ctime never
    met itself and every call parsed the snapshot again. With ctime out of
    the key there (_CTIME_IN_KEY off), a stat and an fstat that disagree
    on ctime alone still find one entry."""
    import types
    real_os = DM.os

    class _Os(types.ModuleType):
        def __getattr__(self, name):
            return getattr(real_os, name)

        @staticmethod
        def fstat(fd):
            st = real_os.fstat(fd)
            fields = {k: getattr(st, k) for k in dir(st)
                      if k.startswith("st_")}
            fields["st_ctime_ns"] = st.st_ctime_ns + 12_345
            return types.SimpleNamespace(**fields)
    monkeypatch.setattr(DM, "os", _Os("os"))
    monkeypatch.setattr(DM, "_CTIME_IN_KEY", False)
    ds = _make("versioned")
    DM.clear_snapshot_cache()
    parsed = _count_parses(monkeypatch)
    for w in ds.forecast_dates():
        for _ in range(3):
            for n in ds.groups:
                ds.series(n, w)
    assert parsed == [os.path.abspath(ds.vintage_path(w))
                      for w in ds.forecast_dates()]


@pytest.mark.parametrize("kind", ["final", "versioned"])
def test_a_replay_reads_each_snapshot_once(kind, tmp_path, monkeypatch):
    ds = _make(kind)
    # weeks with settled truth four weeks on: every group is scored, so
    # every group asks for its baseline series every week
    weeks = ds.forecast_dates()[-14:-6]
    groups = ds.groups
    want = ([os.path.abspath(ds.final_path)] if kind == "final" else
            [os.path.abspath(ds.vintage_path(w)) for w in weeks])
    # the per-group read: a snapshot opened for every series asked for
    calls = []

    def ref(self, name, as_of=None):
        calls.append((name, as_of))
        return reference_series(self, name, as_of)
    with monkeypatch.context() as m:
        m.setattr(DM.Dataset, "series", ref)
        opened_old = _count_opens(m, sys.modules[__name__])
        CX.run(ds, weeks, groups, out_dir=tmp_path / "old")
    # a group abstains on a week now and then; most are scored
    assert len(calls) >= (len(groups) - 1) * len(weeks)
    assert sum(p in set(want) for p in opened_old) >= len(calls)
    # the index: one parse per snapshot file the replay used
    DM.clear_snapshot_cache()
    opened = _count_opens(monkeypatch)
    parsed = _count_parses(monkeypatch)
    meta = CX.run(ds, weeks, groups, out_dir=tmp_path / "new")
    assert meta["status"] == "done"
    assert meta["summary"]["analogue"]["pooled"]["cells"] > 0
    assert parsed == want
    # what is left: one parse per file, and at most the replay's truth()
    # rows (read once per object; this object read them in the first run)
    assert len(opened) <= len(want) + 1
    assert set(opened) <= set(want) | {os.path.abspath(ds.final_path)}
    assert _stored(tmp_path / "new") == _stored(tmp_path / "old")


# ------------------------------------------------ keyed on the file itself

def _rewrite(path: Path, text: str, *, atomic: bool, ns: int) -> None:
    # bytes, as the store writes them: a text-mode write turns each "\n"
    # into "\r\n" on Windows, and the file would change size
    data = text.encode("utf-8")
    if atomic:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
    else:
        path.write_bytes(data)
    os.utime(path, ns=(ns, ns))


@pytest.mark.parametrize("atomic", [True, False])
def test_a_snapshot_written_again_is_read_again(atomic):
    ds = _make("versioned")
    w = ds.forecast_dates()[2]
    p = ds.vintage_path(w)
    before = ds.series("Alabama", w)
    text = p.read_bytes().decode("utf-8")        # the file's own line ends
    # the as-of week's Alabama value, changed by one, same file size
    lines = text.splitlines(keepends=True)
    i = next(i for i, ln in enumerate(lines)
             if ln.startswith(f"{w},") and ln.split(",")[2] == "Alabama")
    f = lines[i].split(",")
    old = int(f[3])
    nv = old + 1 if len(str(old + 1)) == len(f[3]) else old - 1
    f[3] = str(nv)
    lines[i] = ",".join(f)
    new = "".join(lines)
    assert new != text and len(new) == len(text)
    assert before["dates"][-1] == w and before["values"][-1] == old
    st = p.stat()
    _rewrite(p, new, atomic=atomic, ns=st.st_mtime_ns + 1_000_000_000)
    assert p.stat().st_size == st.st_size
    assert (p.stat().st_ino == st.st_ino) or atomic
    after = ds.series("Alabama", w)
    assert after["values"][:-1] == before["values"][:-1]
    assert after["values"][-1] == float(nv)
    assert after == reference_series(ds, "Alabama", w)
    # the older version is dropped, not kept beside it
    assert sum(k[0] == os.path.abspath(p) for k in DM._SNAPS) == 1


def test_a_deleted_snapshot_is_refused_not_served_from_memory():
    ds = _make("versioned")
    w = ds.forecast_dates()[1]
    ds.series("Alabama", w)
    ds.vintage_path(w).unlink()
    with pytest.raises(FileNotFoundError, match="missing"):
        ds.series("Alabama", w)
    with pytest.raises(FileNotFoundError):
        DM.snapshot_index(ds.path / "vintages" / "gone.csv")


def test_views_are_copies_and_the_index_is_read_only():
    ds = _make("final")
    w = ds.forecast_dates()[40]
    s = ds.series("Adult", w)
    keep = json.dumps(s)
    s["dates"].append("2099-01-02")
    s["values"][0] = -1.0
    assert json.dumps(ds.series("Adult", w)) == keep
    idx = DM.snapshot_index(ds.final_path)
    with pytest.raises(TypeError):
        idx["Adult"] = ((), ())
    dates, values = idx["Adult"]
    assert isinstance(dates, tuple) and isinstance(values, tuple)
    wk = ds.weeks()
    wk.clear()
    assert ds.weeks() and ds.weeks() == sorted(ds.weeks())


def test_the_cache_is_bounded_in_files_and_rows(monkeypatch):
    ds = _make("versioned")
    dates = ds.forecast_dates()
    monkeypatch.setattr(DM, "SNAPSHOT_CACHE_FILES", 3)
    for w in dates:
        ds.series("Alaska", w)
    assert len(DM._SNAPS) == 3
    assert [k[0] for k in DM._SNAPS] == [os.path.abspath(ds.vintage_path(w))
                                         for w in dates[-3:]]
    # a row cap below one file keeps only the newest file
    monkeypatch.setattr(DM, "SNAPSHOT_CACHE_ROWS", 1)
    ds.series("Alaska", dates[0])
    assert [k[0] for k in DM._SNAPS] == [os.path.abspath(
        ds.vintage_path(dates[0]))]
    assert ds.series("Alaska", dates[1]) == reference_series(
        ds, "Alaska", dates[1])


def test_threads_share_one_index_and_agree():
    ds = _make("national")
    weeks = ds.forecast_dates()[-20:]
    want = {(n, w): reference_series(ds, n, w)
            for n in ds.groups for w in weeks}
    DM.clear_snapshot_cache()
    got, errors = [], []
    start = threading.Barrier(8)

    def work(i):
        try:
            start.wait()
            mine = D.get(ds.id)          # an object per thread, one file
            for w in (weeks if i % 2 else weeks[::-1]):
                for n in ds.groups:
                    got.append(((n, w), mine.series(n, w)))
        except Exception as e:           # pragma: no cover: reported below
            errors.append(e)
    ts = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors
    assert len(got) == 8 * len(want)
    assert all(s == want[k] for k, s in got)
    assert len(DM._SNAPS) == 1
