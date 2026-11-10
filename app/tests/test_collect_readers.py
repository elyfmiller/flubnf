"""collect()'s faster readers give the old readers' numbers, bit for bit
(app/core/engines/pf.py _read_trajectory, app/core/engines/lwf.py
read_table).

Each reader tries np.loadtxt first and keeps the old reader for anything
loadtxt refuses: a private trajectory falls back to np.genfromtxt, and a
public table to the line-by-line float() parse, which keeps its refusal
messages word for word. read_table keeps loadtxt's array only when every
row has the header's width.

The old readers are kept here as the reference. collect() runs on the
public fixture (fixtures/lwf_alaska) and on private-format cells (a nan
token, a token that is not a number, one-row, empty and ragged files),
once with each pair of readers: the pooled arrays and pf_status.json must
be the same bytes.
"""
import json
import shutil
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np                                       # noqa: E402
import pytest                                            # noqa: E402

from app.core.engines import lwf                         # noqa: E402
from app.core.engines import pf                          # noqa: E402
from app.tests.test_engine_lwf import (                  # noqa: E402
    _cell, _record, _with_results)


def _old_read_table(path):
    """lwf.read_table before loadtxt: the reference."""
    try:
        lines = [ln for ln in Path(path).read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.startswith("#")]
    except OSError as e:
        raise lwf.Unreadable(f"{Path(path).name} unreadable ({e})") from None
    if len(lines) < 2:
        raise lwf.Unreadable(f"{Path(path).name} is torn "
                             f"({'empty' if not lines else 'a header alone'})")
    header = lines[0].split()
    try:
        rows = [[float(x) for x in ln.split()] for ln in lines[1:]]
    except ValueError as e:
        raise lwf.Unreadable(f"{Path(path).name} holds a value that is not a "
                             f"number ({e})") from None
    if any(len(r) != len(header) for r in rows):
        raise lwf.Unreadable(f"{Path(path).name} is ragged: not every row has "
                             f"the header's {len(header)} columns")
    return header, np.asarray(rows, dtype=float)


def _outcome(fn, *args):
    """What a reader gives: its array's shape, dtype and bytes (the header
    too, for a table), or its exception's type and words."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # numpy's empty-file warnings
        try:
            got = fn(*args)
        except Exception as e:
            return ("raised", type(e).__name__, str(e))
    if isinstance(got, tuple):
        header, arr = got
        return ("read", list(header), arr.shape, arr.dtype.str, arr.tobytes())
    return ("read", got.shape, got.dtype.str, got.tobytes())


def _pooled_bytes(by_loc: dict) -> dict:
    """collect()'s pools as bytes: every draw, nan's sign bit included."""
    return {loc: {h: np.asarray(v, dtype=float).tobytes()
                  for h, v in blocks.items()}
            for loc, blocks in by_loc.items()}


def _collect_both(monkeypatch, w: Path) -> tuple:
    """collect() on w with today's readers, then (status reset) with the
    old ones: (pools, pf_status.json) for each."""
    status = w / "pf_status.json"
    before = status.read_bytes() if status.is_file() else None

    def run():
        if before is None:
            status.unlink(missing_ok=True)
        else:
            status.write_bytes(before)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            by = pf.collect(w)
        return (_pooled_bytes(by),
                status.read_bytes() if status.is_file() else None)
    new = run()
    with monkeypatch.context() as m:
        m.setattr(pf, "_read_trajectory", np.genfromtxt)
        m.setattr(lwf, "read_table", _old_read_table)
        old = run()
    return new, old


# ------------------------------------------------------------ the public cells


def test_the_public_fixture_pools_the_same_bytes(monkeypatch, tmp_path):
    """The Alaska cell, and a copy of it whose forecasts.txt is torn: the
    same pools and the same recorded failure either way."""
    good = _cell(tmp_path, "Alaska_r0")
    _with_results(good)
    torn = _cell(tmp_path, "Alaska_r1")
    r = _with_results(torn)
    (r / "forecasts.txt").write_text("# note\n25\t26\t27\t28\n")
    (tmp_path / "cells.json").write_text(json.dumps(
        [_record(good), _record(torn, key="Alaska_r1", replicate=1)]))
    new, old = _collect_both(monkeypatch, tmp_path)
    assert new == old
    assert len(np.frombuffer(new[0]["Alaska"]["0"])) == 100   # its 100 particles
    assert "forecasts.txt is torn" in json.loads(new[1])["Alaska_r1"]


def test_the_public_fixture_tables_read_the_same(tmp_path):
    """Every table of the fixture, through both readers."""
    for f in sorted((Path(__file__).parent / "fixtures" / "lwf_alaska"
                     / "results").glob("*.txt")):
        if f.name == "summary.txt":
            continue                          # not a table read_table takes
        new, old = _outcome(lwf.read_table, f), _outcome(_old_read_table, f)
        assert new == old, f.name
        assert new[0] == "read", f.name


#: tables read_table must read, or refuse, exactly as before: (name, body
#: after the '# note' line and the header '1 2 3')
TABLES = [
    ("plain", "1 2 3\n4 5 6\n"),
    ("tabs", "1\t2\t3\n4\t5\t6\n"),
    ("one row", "1 2 3\n"),
    ("nan and inf", "nan -nan 1\ninf -inf +inf\n"),
    ("ragged", "1 2 3\n4 5\n"),
    ("short rows", "1 2\n3 4\n"),                # every row two wide
    ("long rows", "1 2 3 4\n5 6 7 8\n"),
    ("not a number", "1 2 x\n4 5 6\n"),
    ("inline note", "1 2 3 # x\n4 5 6\n"),
    ("indented note", "1 2 3\n  # x\n"),
    ("underscore", "1_0 2 3\n4 5 6\n"),
    ("hex", "0x10 2 3\n4 5 6\n"),
    ("nan payload", "nan(1) 2 3\n4 5 6\n"),
    ("unicode digits", "١ 2 3\n4 5 6\n"),
    ("non-breaking space", "1\xa02 3\n4 5 6\n"),
    ("crlf", "1 2 3\r\n4 5 6\r\n"),
    ("blank lines", "1 2 3\n\n   \n4 5 6\n"),
    ("17 digits", "0.42060336610775384 0.81398862957753715 "
                  "1.2217556331756356\n4.9406564584124654e-324 "
                  "1.7976931348623157e+308 2.2250738585072014e-308\n"),
]


@pytest.mark.parametrize("name, body", TABLES, ids=[t[0] for t in TABLES])
def test_read_table_reads_or_refuses_as_before(name, body, tmp_path):
    p = tmp_path / "predicted_counts.txt"
    p.write_text("# note\n1 2 3\n" + body, encoding="utf-8", newline="")
    assert _outcome(lwf.read_table, p) == _outcome(_old_read_table, p)


def test_read_table_with_one_column(tmp_path):
    p = tmp_path / "weight_ess.txt"
    p.write_text("# note\n7\n1.5\n2.5\n")
    new = _outcome(lwf.read_table, p)
    assert new == _outcome(_old_read_table, p)
    assert new[2] == (2, 1)


# ----------------------------------------------------------- the private cells

#: private trajectories: two particles over seven weeks (test_pf_hardening's
#: shape, the fit origin column 2), in the engine's '%.18e', with odd tokens
GOOD = "\n".join(" ".join("%.18e" % (v * (1 + p / 7)) for v in range(7))
                 for p in range(2)) + "\n"
TRAJECTORIES = {
    "good": GOOD,
    "nan token": "0 1 2 nan 4 5 6\n0 1 2 3 4 5 6\n",
    "minus nan": "0 1 2 3 -nan 5 6\n0 1 2 3 4 5 6\n",
    "not a number": "0 1 2 3 4 5 x\n0 1 2 3 4 5 6\n",
    "underscore": "0 1 2 3 4 5 1_0\n0 1 2 3 4 5 6\n",
    "header note": "# step weeks\n0 1 2 3 4 5 6\n0 1 2 3 4 5 6\n",
    "one row": "0 1 2 3 4 5 6\n",
    "empty": "",
    "ragged": "0 1 2 3 4 5 6\n0 1\n",
}


def _private_cell(w: Path, key: str, text: str) -> dict:
    d = w / key
    runs = d / "out" / "Results" / "PF" / "Runs"
    runs.mkdir(parents=True)
    (runs / "sim_traj_noise.txt").write_text(text)
    return {"key": key, "dir": str(d), "location": key.rsplit("_r", 1)[0],
            "n_obs": 3, "particles": 100, "last_observed": 10.0}


@pytest.mark.parametrize("name", list(TRAJECTORIES))
def test_a_trajectory_reads_as_genfromtxt_reads_it(name, tmp_path):
    p = tmp_path / "x_traj_noise.txt"
    p.write_text(TRAJECTORIES[name])
    assert _outcome(pf._read_trajectory, p) == _outcome(np.genfromtxt, p)


def test_the_private_cells_pool_the_same_bytes(monkeypatch, tmp_path):
    """Every trajectory above as a cell (good ones pooled, torn ones
    recorded): the same pools and the same pf_status.json either way."""
    cells = [_private_cell(tmp_path, f"L{i}_r0", text)
             for i, text in enumerate(TRAJECTORIES.values())]
    (tmp_path / "cells.json").write_text(json.dumps(cells))
    new, old = _collect_both(monkeypatch, tmp_path)
    assert new == old
    torn = ("one row", "empty", "ragged")
    assert set(json.loads(new[1])) == {
        f"L{i}_r0" for i, n in enumerate(TRAJECTORIES) if n in torn}
    assert set(new[0]) == {f"L{i}" for i, n in enumerate(TRAJECTORIES)
                           if n not in torn}


def test_a_big_private_trajectory_reads_the_same(tmp_path):
    """10,000 particles over 30 weeks in '%.18e', as the engine writes."""
    rng = np.random.default_rng(3)
    a = rng.lognormal(3.0, 1.5, size=(10_000, 30))
    a[17, 4] = np.nan
    p = tmp_path / "x_traj_noise.txt"
    np.savetxt(p, a)
    new = _outcome(pf._read_trajectory, p)
    assert new == _outcome(np.genfromtxt, p)
    assert new[1] == (10_000, 30)


def test_a_big_public_table_reads_the_same(tmp_path):
    """10,000 particles over 45 weeks, written as PyBNF writes them (repr,
    tab-separated, '#' notes, a header of times)."""
    rng = np.random.default_rng(4)
    a = rng.lognormal(1.0, 1.0, size=(10_000, 45))
    p = tmp_path / "predicted_counts.txt"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("# a note\n# another\n"
                 + "\t".join(str(t) for t in range(1, 46)) + "\n")
        for row in a:
            fh.write("\t".join(repr(float(x)) for x in row) + "\n")
    new = _outcome(lwf.read_table, p)
    assert new == _outcome(_old_read_table, p)
    assert new[2] == (10_000, 45)


def test_the_public_fixture_copied_with_crlf_reads_the_same(tmp_path):
    """A table that went through a Windows copy: CRLF line ends."""
    src = (Path(__file__).parent / "fixtures" / "lwf_alaska" / "results"
           / "predicted_counts.txt")
    p = tmp_path / "predicted_counts.txt"
    p.write_bytes(src.read_bytes().replace(b"\n", b"\r\n"))
    assert _outcome(lwf.read_table, p) == _outcome(_old_read_table, p)
    shutil.copy(src, tmp_path / "plain.txt")
    assert (_outcome(lwf.read_table, p)[1:]
            == _outcome(lwf.read_table, tmp_path / "plain.txt")[1:])
