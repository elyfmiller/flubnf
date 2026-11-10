"""A held Dataset reads one version of its final snapshot (review of #93,
re-check R9; app/core/datasets/dataset.py, Dataset._final).

  * the store never rewrites a stored file: the same upload again returns
    the dataset as it is, and another upload leaves it alone, so a stored
    snapshot changes only by hand;
  * after such a hand edit while an object is held, its weeks(), truth()
    and series() (final data at any as-of, and a versioned dataset's
    newest vintage) all read the version the object first read, whichever
    it read first; a new object (get) reads the file as it is then, and
    its truth() and series() agree too;
  * a versioned dataset's earlier snapshots are still read as they are at
    each call (test_dataset_snapshot_reads holds that);
  * truth() worked from a parsed snapshot (_truth_of, the edited case)
    gives what the per-row read gives, and raises the same KeyError on a
    file without one of its columns.
"""
from __future__ import annotations

import csv
import io
import os

import pytest

from app.core import datasets as D
from app.core.datasets import dataset as DM

from test_dataset_engines import grouped_bytes            # noqa: E402
from test_dataset_snapshot_reads import versioned_bytes   # noqa: E402


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    DM.clear_snapshot_cache()
    yield tmp_path / "datasets"
    DM.clear_snapshot_cache()


def row_truth(path) -> dict:
    """Dataset.truth() before the cache, verbatim, on one file."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return {(r["location_name"], r["date"]): float(r["value"])
            for r in rows if r["value"] != ""}


def hand_edit(path, name, week, value, *, drop_last=False) -> None:
    """Write the snapshot again (beside, then renamed over it, as an
    editor saving does) with `name`'s value at `week` set to `value`, and
    with `drop_last` its newest week left out."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        head, rows = reader.fieldnames, list(reader)
    last = max(r["date"] for r in rows)
    hit = 0
    for r in rows:
        if r["location_name"] == name and r["date"] == week:
            r["value"] = value
            hit += 1
    assert hit == 1
    if drop_last:
        rows = [r for r in rows if r["date"] != last]
    out = io.StringIO()
    w = csv.DictWriter(out, head, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    tmp = path.with_name(path.name + ".edit")
    tmp.write_text(out.getvalue(), encoding="utf-8")
    os.replace(tmp, path)


def views(ds, name, as_of) -> tuple:
    t = ds.truth()
    s, c = ds.series(name), ds.series(name, as_of)
    return (ds.weeks(), s, c,
            {d: v for (g, d), v in t.items() if g == name})


def agree(ds, name, as_of) -> tuple:
    """The views of one object, checked to be of one version: series()
    of the final data is truth()'s, week for week."""
    weeks, s, c, t = views(ds, name, as_of)
    assert dict(zip(s["dates"], s["values"])) == t
    assert c == {"dates": [d for d in s["dates"] if d <= as_of],
                 "values": [v for d, v in zip(s["dates"], s["values"])
                            if d <= as_of]}
    assert set(s["dates"]) <= set(weeks)
    return weeks, s, c, t


# ------------------------------------------------- the store's own writes

def _stats(ds) -> dict:
    out = {}
    for p in sorted(ds.path.rglob("*")):
        if p.is_file():
            st = p.stat()
            out[str(p)] = (p.read_bytes(), st.st_ino, st.st_mtime_ns,
                           st.st_ctime_ns)
    return out


def test_the_store_never_rewrites_a_stored_file():
    ds = D.ingest(grouped_bytes(), "wave", kind="count")
    snap = D.ingest(versioned_bytes(), "snap", kind="count")
    before = {**_stats(ds), **_stats(snap)}
    # the same uploads again: the datasets as they are, nothing written
    assert D.ingest(grouped_bytes(), "wave", kind="count").id == ds.id
    assert D.ingest(versioned_bytes(), "snap", kind="count").id == snap.id
    # another upload, and another name for the same bytes: new folders
    other = D.ingest(grouped_bytes(groups=("North", "South")), "two",
                     kind="count")
    twin = D.ingest(grouped_bytes(), "wave again", kind="count")
    assert len({ds.id, snap.id, other.id, twin.id}) == 4
    assert {**_stats(ds), **_stats(snap)} == before


# ------------------------------------------- one version per held object

@pytest.mark.parametrize("first", ["truth", "series", "weeks"])
def test_a_held_object_reads_the_version_it_first_read(first):
    ing = D.ingest(grouped_bytes(), "wave", kind="count")
    name, all_weeks = "Adult", ing.weeks()
    as_of, week = all_weeks[-3], all_weeks[-5]
    ds = D.get(ing.id)                   # a fresh object: nothing read yet
    {"truth": ds.truth, "series": lambda: ds.series(name),
     "weeks": ds.weeks}[first]()
    hand_edit(ds.final_path, name, week, "987654", drop_last=True)
    fresh = D.get(ds.id)
    # the held object: every view of the version it first read
    held = agree(ds, name, as_of)
    assert held[3][week] != 987654.0 and all_weeks[-1] in held[3]
    assert held[0] == all_weeks
    # a new object reads the file as it is now, every view alike
    new = agree(fresh, name, as_of)
    assert new[0] == all_weeks[:-1]
    assert new[3][week] == 987654.0 and new[3] == {
        d: v for (g, d), v in row_truth(ds.final_path).items() if g == name}
    assert all_weeks[-1] not in new[3]


@pytest.mark.parametrize("first", ["truth", "series"])
def test_a_held_versioned_object_reads_its_newest_vintage_once(first):
    ing = D.ingest(versioned_bytes(), "snap", kind="count")
    name, newest = "Alabama", ing.vintages()[-1]
    week = ing.series(name, newest)["dates"][-3]
    ds = D.get(ing.id)
    {"truth": ds.truth, "series": lambda: ds.series(name, newest)}[first]()
    hand_edit(ds.final_path, name, week, "987654")
    t, s = ds.truth(), ds.series(name, newest)
    assert t[(name, week)] != 987654.0
    assert dict(zip(s["dates"], s["values"])) == {
        d: v for (g, d), v in t.items() if g == name}
    assert s == ds.series(name)          # the newest vintage is the final
    fresh = D.get(ds.id)
    ft, fs = fresh.truth(), fresh.series(name, newest)
    assert ft[(name, week)] == 987654.0 == fs["values"][
        fs["dates"].index(week)]


def test_an_unedited_dataset_reads_as_before(monkeypatch):
    """No hand edit: truth() reads the rows once per object as it did,
    and the parsed snapshot gives the same mapping."""
    ds = D.ingest(grouped_bytes(), "wave", kind="count")
    ds = D.get(ds.id)
    t = ds.truth()
    assert t == row_truth(ds.final_path)
    assert list(t) == list(row_truth(ds.final_path))   # the same order too
    assert DM._truth_of(DM._entry(ds.final_path)) == t
    assert ds.__dict__["_final_rows_key"] == ds.__dict__["_final_held"][0]


def test_an_unedited_dataset_reads_its_rows_with_the_windows_key(monkeypatch):
    """Windows keys a snapshot by the opened file (fstat's ctime and a
    digest of its ends). The rows' key must be made the same way as the
    stored key, or truth() never reads the rows there: it reads the
    parsed snapshot, in another order. Run on every system."""
    monkeypatch.setattr(DM, "_CTIME_IN_KEY", False)
    ds = D.ingest(grouped_bytes(), "wave", kind="count")
    ds = D.get(ds.id)
    t = ds.truth()
    assert list(t) == list(row_truth(ds.final_path))
    assert ds.__dict__["_final_rows_key"] == ds.__dict__["_final_held"][0]


# ---------------------------------------- truth from the parsed snapshot

def _drop(path, cols) -> None:
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


#: hand damage: columns dropped from the stored snapshot, or its text
DAMAGE = [("cols", ()), ("cols", ("value",)), ("cols", ("location_name",)),
          ("cols", ("value", "location_name")), ("cols", ("date",)),
          ("cols", ("date", "value")), ("cols", ("date", "location_name")),
          ("text", ""), ("text", "date,location,location_name\n"),
          ("text", "date,location_name,value\n2024-01-06,A,\n"
                   "2024-01-06,B,\n"),
          ("text", "date,location_name,value\n2024-01-06,A,1\n"
                   "2024-01-06,B,x\n2024-01-13,B,y\n"),
          ("text", "date,location_name,value\n2024-01-06,A,1\n"
                   "2024-01-13,A\n"),
          ("text", "date,location_name,value\n2024-01-06,A,1\n"
                   "2024-01-06,A,2\n")]


@pytest.mark.parametrize("how,what", DAMAGE)
def test_truth_from_the_parsed_snapshot_is_the_per_row_read(how, what):
    ds = D.ingest(grouped_bytes(), "wave", kind="count")
    p = ds.final_path
    if how == "text":
        p.write_text(what, encoding="utf-8")
    elif what:
        _drop(p, what)
    DM.clear_snapshot_cache()
    old = _outcome(lambda: row_truth(p))
    new = _outcome(lambda: DM._truth_of(DM._entry(p)))
    assert new == old
    if how == "cols" and what:
        assert old[0] == "KeyError"


def test_two_bad_values_in_two_groups_raise_alike():
    """The one difference: the index holds a group's rows together, so
    with bad values in two groups the error may name the other one. Only
    a hand-damaged file edited again while an object holds it gets here."""
    ds = D.ingest(grouped_bytes(), "wave", kind="count")
    p = ds.final_path
    p.write_text("date,location_name,value\n2024-01-06,A,1\n"
                 "2024-01-06,B,x\n2024-01-13,A,y\n", encoding="utf-8")
    with pytest.raises(ValueError, match="'x'"):
        row_truth(p)
    with pytest.raises(ValueError, match="'y'"):
        DM._truth_of(DM._entry(p))
