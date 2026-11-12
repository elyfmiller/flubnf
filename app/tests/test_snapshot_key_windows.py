"""The snapshot cache key on Windows moves for a rewrite in place at the
same size with the mtime put back (the re-check of #93 at 099907c,
finding 4; app/core/datasets/dataset.py _handle_key).

On Windows ctime from os.stat (the creation time) is not in the key, so
the key had nothing such a rewrite moves: a new Dataset read the old
series() for the life of the process. There both keys now come from the
opened file: fstat's ctime (the last change from Python 3.12 on) and a
digest of the file's first and last bytes. Windows is simulated here
(_CTIME_IN_KEY off); "3.11" also holds fstat's ctime still, as the
creation time there is, so only the digest can see the rewrite. The POSIX
key is unchanged.
"""
from __future__ import annotations

import csv
import os
import types

import pytest

from app.core import datasets as D
from app.core.datasets import dataset as DM

from test_dataset_snapshot_reads import (_count_parses, _make,  # noqa: F401
                                         reference_series, store)


def _frozen_ctime(monkeypatch):
    """os.fstat as Windows before Python 3.12 gives it: st_ctime is the
    creation time, which a rewrite in place leaves as it was."""
    real_os = DM.os

    class _Os(types.ModuleType):
        def __getattr__(self, name):
            return getattr(real_os, name)

        @staticmethod
        def fstat(fd):
            st = real_os.fstat(fd)
            fields = {k: getattr(st, k) for k in dir(st)
                      if k.startswith("st_")}
            fields["st_ctime_ns"] = 1_000_000_000
            return types.SimpleNamespace(**fields)
    monkeypatch.setattr(DM, "os", _Os("os"))


def _rewrite_in_place(p, *, at_end: bool):
    """One value of the snapshot changed by one, the file rewritten in
    place (same inode) at the same size, its mtime put back: (group, date,
    new value). The row is the last (at_end) or the first with a value
    that keeps its width."""
    raw = p.read_bytes()
    text = raw.decode("utf-8")
    lines = text.splitlines(keepends=True)
    head = next(csv.reader([lines[0]]))
    vi, ni, di = (head.index("value"), head.index("location_name"),
                  head.index("date"))
    order = range(len(lines) - 1, 0, -1) if at_end else range(1, len(lines))
    for i in order:
        f = lines[i].rstrip("\r\n").split(",")
        try:
            old = int(f[vi])
        except ValueError:
            continue
        nv = old + 1 if len(str(old + 1)) == len(f[vi]) else old - 1
        if nv >= 0 and len(str(nv)) == len(f[vi]):
            end = lines[i][len(lines[i].rstrip("\r\n")):]
            f[vi] = str(nv)
            lines[i] = ",".join(f) + end
            break
    else:                                         # pragma: no cover
        raise AssertionError("no value to change")
    new = "".join(lines).encode("utf-8")
    assert new != raw and len(new) == len(raw)
    st = p.stat()
    with open(p, "r+b") as fh:                    # in place: same inode
        fh.write(new)
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
    now = p.stat()
    assert (now.st_size, now.st_mtime_ns, now.st_ino, now.st_dev) == \
        (st.st_size, st.st_mtime_ns, st.st_ino, st.st_dev)
    return f[ni], f[di], float(nv)


@pytest.mark.parametrize("python", ["3.12", "3.11"])
@pytest.mark.parametrize("at_end", [True, False])
def test_a_rewrite_in_place_with_the_mtime_put_back_is_read_again(
        monkeypatch, python, at_end):
    monkeypatch.setattr(DM, "_CTIME_IN_KEY", False)
    if python == "3.11":
        _frozen_ctime(monkeypatch)
    ds = _make("versioned")
    w = ds.forecast_dates()[2]
    p = ds.vintage_path(w)
    names = ds.groups
    before = {n: ds.series(n, w) for n in names}
    name, day, nv = _rewrite_in_place(p, at_end=at_end)
    fresh = D.get(ds.id)
    got = fresh.series(name, w)
    assert got == reference_series(fresh, name, w)
    assert got["values"][got["dates"].index(day)] == nv
    assert got != before[name]
    # one entry for the file: the older version is dropped
    assert sum(k[0] == os.path.abspath(p) for k in DM._SNAPS) == 1


def test_on_windows_an_unchanged_snapshot_is_still_parsed_once(monkeypatch):
    """The lookup reads the file's ends, not the whole file, and finds the
    stored entry: one parse per snapshot however often it is asked."""
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


def test_the_key_reads_the_ends_and_leaves_the_handle_at_the_start(
        monkeypatch, tmp_path):
    monkeypatch.setattr(DM, "_CTIME_IN_KEY", False)
    p = tmp_path / "s.csv"
    body = b"date,location_name,value\n" + b"2024-01-06,A,1\n" * 20_000
    p.write_bytes(body)
    with open(p, newline="", encoding="utf-8") as fh:
        k1 = DM._handle_key(str(p), fh.fileno())
        assert fh.read() == body.decode()        # read whole, from byte 0
    assert DM._lookup_key(str(p)) == k1
    # a byte in the middle is past the ends (the limit the comment states)
    mid = bytearray(body)
    mid[len(body) // 2] = ord("9") if mid[len(body) // 2] != ord("9") else 48
    p.write_bytes(bytes(mid))
    assert DM._lookup_key(str(p))[-1] == k1[-1]
    # one at either end is not
    for i in (0, len(body) - 2):
        b = bytearray(body)
        b[i] = ord("x")
        p.write_bytes(bytes(b))
        assert DM._lookup_key(str(p))[-1] != k1[-1], i


def test_the_posix_key_is_as_it_was(tmp_path):
    if not DM._CTIME_IN_KEY:
        pytest.skip("the POSIX key")
    p = tmp_path / "s.csv"
    p.write_bytes(b"date,location_name,value\n2024-01-06,A,1\n")
    st = os.stat(p)
    want = (str(p), st.st_size, st.st_mtime_ns, st.st_ino, st.st_dev,
            st.st_ctime_ns)
    assert DM._lookup_key(str(p)) == want
    with open(p, "rb") as fh:
        assert DM._handle_key(str(p), fh.fileno()) == want
