"""load_truth parses the truth file once per content (P2, F12).

The season player called load_truth on every week it served, and a season
report once per week: each call parsed the 616 KB target file again. It
now keeps one parse, keyed on the two files it actually reads (the
settled target file or the vintage standing in for it, and the locations
list), chosen afresh on every call. Pinned here:

  * two calls parse once; a rewrite, a touch or a new locations list
    parses again;
  * every call hands back its own dicts (no caller can change the kept
    parse);
  * the result equals the unmemoised reader (frozen below), on a fixture
    hub and, opt-in (FLUBNF_TEST_HUB), on a real clone;
  * TRUTH_SOURCE and the fallback's stderr line on every call, the switch
    from the settled file to a vintage and back;
  * a failure is never kept;
  * racing first calls parse once.
"""
import os
import sys
import threading
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import data as core_data                     # noqa: E402
from app.core import scoring                               # noqa: E402

TARGET = "target-data/target-hospital-admissions.csv"
LOCS = "auxiliary-data/locations.csv"


# ------------------------------------------------- the reader before P2

def _old_load_truth(HUB) -> tuple:
    """scoring.load_truth as it stood before the memo (HUB passed in, the
    TRUTH_SOURCE writes left out): the reference every call must equal."""
    target = HUB / "target-data/target-hospital-admissions.csv"
    if not target.is_file():
        from app.core.data import vintage_path, vintages
        vs = vintages()
        if not vs:
            raise FileNotFoundError("no settled truth")
        target = vintage_path(vs[-1])
    t = pd.read_csv(target, dtype={"location": str})
    t["location"] = t["location"].str.zfill(2)
    t["date"] = pd.to_datetime(t["date"])
    locs_csv = HUB / "auxiliary-data/locations.csv"
    if not locs_csv.is_file():
        locs_csv = scoring.BUNDLED_LOCATIONS
    locs = pd.read_csv(locs_csv, dtype=str)
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    truth = {(r.location, r.date): float(r.value)
             for r in t.itertuples() if np.isfinite(r.value)}
    return truth, n2f


# ------------------------------------------------------------------ fixtures

def _csv(rows=8, extra=0.0) -> str:
    out = ["date,location,location_name,value"]
    for k in range(rows):
        d = (pd.Timestamp("2026-01-03") + pd.Timedelta(days=7 * k)).date()
        out.append(f"{d},39,Ohio,{100 + k + extra}")
        out.append(f"{d},6,California,{200 + k + extra}")   # zfill: "06"
        out.append(f"{d},US,US,{900 + k + extra}")
    out.append("2026-03-07,49,Utah,")                       # NaN: dropped
    return "\n".join(out) + "\n"


def _hub(tmp_path, monkeypatch) -> Path:
    hub = tmp_path / "hub"
    (hub / "target-data").mkdir(parents=True)
    (hub / "auxiliary-data").mkdir()
    (hub / TARGET).write_text(_csv())
    (hub / LOCS).write_text("location,location_name,abbreviation\n"
                            "39,Ohio,OH\n06,California,CA\nUS,US,US\n")
    monkeypatch.setattr(scoring, "HUB", hub)
    return hub


@pytest.fixture(autouse=True)
def _fresh_memo():
    """Each test starts with nothing kept (another module's parse of its
    own hub is keyed elsewhere anyway)."""
    scoring._TRUTH_MEMO.clear()
    yield
    scoring._TRUTH_MEMO.clear()


@pytest.fixture
def reads(monkeypatch):
    """Paths pd.read_csv was handed by scoring.load_truth, in order (the
    reference reader above reads too; its reads are not counted)."""
    seen = []
    real = pd.read_csv

    def spy(path, *a, **k):
        if sys._getframe(1).f_code is scoring.load_truth.__code__:
            seen.append(Path(path))
        return real(path, *a, **k)
    monkeypatch.setattr(pd, "read_csv", spy)
    return seen


def _n_target_reads(reads, path) -> int:
    return sum(1 for p in reads if p == Path(path))


# ------------------------------------------------------------- the memo

def test_two_calls_parse_once_and_a_rewrite_parses_again(tmp_path,
                                                         monkeypatch, reads):
    hub = _hub(tmp_path, monkeypatch)
    first = scoring.load_truth()
    second = scoring.load_truth()
    assert first == second == _old_load_truth(hub)
    assert _n_target_reads(reads, hub / TARGET) == 1
    assert _n_target_reads(reads, hub / LOCS) == 1

    # new truth (a different size): parsed again, and the new value served
    (hub / TARGET).write_text(_csv(rows=9))
    third = scoring.load_truth()
    assert _n_target_reads(reads, hub / TARGET) == 2
    assert third == _old_load_truth(hub) and len(third[0]) > len(first[0])

    # the same size, a moved mtime (an Update data that rewrote the same
    # bytes): parsed again; the key never trusts the size alone
    st = (hub / TARGET).stat()
    os.utime(hub / TARGET, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    scoring.load_truth()
    assert _n_target_reads(reads, hub / TARGET) == 3

    # a new locations list: parsed again
    (hub / LOCS).write_text("location,location_name,abbreviation\n"
                            "39,Ohio,OH\n")
    t, n2f = scoring.load_truth()
    assert n2f == {"Ohio": "39"}
    # every parse reads both files: four parses in all
    assert _n_target_reads(reads, hub / LOCS) == 4
    assert _n_target_reads(reads, hub / TARGET) == 4
    scoring.load_truth()
    assert _n_target_reads(reads, hub / TARGET) == 4


def test_every_call_hands_back_its_own_dicts(tmp_path, monkeypatch):
    hub = _hub(tmp_path, monkeypatch)
    truth, n2f = scoring.load_truth()
    key = ("39", pd.Timestamp("2026-01-03"))
    truth[key] = -1.0
    truth.clear()
    n2f["Ohio"] = "99"
    again, n2f2 = scoring.load_truth()
    assert again[key] == 100.0 and n2f2["Ohio"] == "39"
    assert again is not truth and n2f2 is not n2f
    assert (again, n2f2) == _old_load_truth(hub)


def test_the_memo_equals_the_unmemoised_reader(tmp_path, monkeypatch):
    hub = _hub(tmp_path, monkeypatch)
    for _ in range(3):
        assert scoring.load_truth() == _old_load_truth(hub)
    # no hub locations list: the bundled copy, keyed as the file read
    (hub / LOCS).unlink()
    for _ in range(2):
        assert scoring.load_truth() == _old_load_truth(hub)


@pytest.mark.skipif(not os.environ.get("FLUBNF_TEST_HUB"),
                    reason="opt-in: FLUBNF_TEST_HUB names a real hub clone")
def test_the_memo_equals_the_unmemoised_reader_on_a_real_hub(monkeypatch):
    hub = Path(os.environ["FLUBNF_TEST_HUB"])
    monkeypatch.setattr(scoring, "HUB", hub)
    old = _old_load_truth(hub)
    assert len(old[0]) > 1000
    assert scoring.load_truth() == old
    assert scoring.load_truth() == old              # from the memo


# ------------------------------------------- the source, said on every call

def test_the_source_and_the_fallback_line_on_every_call(tmp_path,
                                                        monkeypatch, capsys,
                                                        reads):
    hub = _hub(tmp_path, monkeypatch)
    settled = scoring.load_truth()
    assert scoring.TRUTH_SOURCE == "settled"

    # the settled file gone, a vintage present: the vintage is parsed
    # (a different file, so not the kept parse) and said on every call
    vfile = tmp_path / "target-hospital-admissions_2026-02-21.csv"
    vfile.write_text(_csv(rows=7, extra=0.5))
    (hub / TARGET).unlink()
    monkeypatch.setattr(core_data, "vintages", lambda: ["2026-02-21"])
    monkeypatch.setattr(core_data, "vintage_path", lambda d: vfile)
    capsys.readouterr()
    for _ in range(2):
        v = scoring.load_truth()
        assert scoring.TRUTH_SOURCE == "vintage 2026-02-21"
        assert "newest archived vintage (2026-02-21)" in \
            capsys.readouterr().err
    assert v == _old_load_truth(hub) and v != settled
    assert _n_target_reads(reads, vfile) == 1

    # the settled file back: settled again, its own values
    (hub / TARGET).write_text(_csv())
    assert scoring.load_truth() == settled
    assert scoring.TRUTH_SOURCE == "settled"
    assert capsys.readouterr().err == ""


def test_a_failure_is_never_kept(tmp_path, monkeypatch):
    hub = _hub(tmp_path, monkeypatch)
    (hub / TARGET).unlink()
    monkeypatch.setattr(core_data, "vintages", lambda: [])
    with pytest.raises(FileNotFoundError, match="no settled truth"):
        scoring.load_truth()
    assert not scoring._TRUTH_MEMO
    # a file that does not parse raises, and is not kept either
    (hub / TARGET).write_text("date,location,location_name,value\n"
                              "2026-01-03,39,Ohio,not-a-number\n")
    with pytest.raises(Exception):
        scoring.load_truth()
    assert not scoring._TRUTH_MEMO
    # the truth arriving later is read at once
    (hub / TARGET).write_text(_csv())
    assert scoring.load_truth() == _old_load_truth(hub)
    assert scoring.TRUTH_SOURCE == "settled"


def test_racing_first_calls_parse_once(tmp_path, monkeypatch, reads):
    hub = _hub(tmp_path, monkeypatch)
    want = _old_load_truth(hub)
    reads.clear()
    got, errors = [], []
    go = threading.Barrier(8)

    def call():
        try:
            go.wait(5)
            got.append(scoring.load_truth())
        except Exception as e:                   # pragma: no cover
            errors.append(e)
    threads = [threading.Thread(target=call) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not errors and len(got) == 8
    assert all(g == want for g in got)
    assert _n_target_reads(reads, hub / TARGET) == 1
    # eight callers, eight distinct dicts
    assert len({id(g[0]) for g in got}) == 8
