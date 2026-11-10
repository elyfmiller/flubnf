"""A stored dataset as the console and the engines read it: the Dataset
adapter, the parsed snapshot files it reads through (snapshot_index, one
parse per file version), get/resolve/from_spec, list_datasets and
delete."""
from __future__ import annotations

import csv
import json
import os
import shutil
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Optional

#: the package itself: ROOT, get, resolve and MAX_SNAPSHOT_FILES are
#: read through it at call time, where tests monkeypatch them
from app.core import datasets as _pkg

from .parsing import parse_date, saturday_on_or_before
from .report import DatasetError
from .store import (
    LOCATIONS_FILE,
    META_FILE,
    SERIES_FILE,
    SOURCE_FILE,
    VINTAGE_DIR,
    VINTAGE_PREFIX,
    _dir,
    _root,
    valid_id,
)


# ---- parsed snapshot files ---------------------------------------------
#
# A replay asks for every group's series at every week, and the baseline
# scorer asks again: reading the snapshot CSV once per group made a
# 200-group replay spend most of its time re-reading one file. Each file is
# now parsed once into a per-group index, shared by every Dataset object
# and thread, and keyed on the file itself (path, size, mtime, inode,
# device, and the time of its last change, which a hand-set mtime moves
# on POSIX): a snapshot written again (ingest writes atomically, so a new
# inode) is a new key and is read afresh. Entries are read-only; series()
# builds new lists from them. Bounded in files and in rows held. A file
# edited by hand to lack a column reads as it did before the index
# (_missing): weeks() needs only the dates.
#
# The store never rewrites a stored file: a dataset is built in a folder
# beside the store and renamed into place, and the same upload again
# returns the dataset as it is. So a file changes only by hand. A Dataset
# object reads ONE version of its final snapshot, the first it read:
# weeks(), truth() and series() of the final data all read that version,
# even after a hand edit while the object is held (Dataset._final), so
# one object's truth() and series() never disagree. get() makes a new
# object, which reads the file as it is then (an engine resolves its own
# each week). A versioned dataset's earlier snapshots are read as they
# are at each call, as before.

#: at most this many parsed snapshot files are kept (least recently used
#: first out)
SNAPSHOT_CACHE_FILES = 8
#: and at most about this many rows across them (the newest file is kept
#: whatever its size)
SNAPSHOT_CACHE_ROWS = 2_000_000

_SNAP_LOCK = threading.Lock()
#: key -> (rows read, read-only index, every date the file holds)
_SNAPS: "OrderedDict[tuple, tuple]" = OrderedDict()


def _snap_key(path: str, st: os.stat_result) -> tuple:
    # st_ctime_ns: a rewrite in place with the size, mtime and inode put
    # back still moves it (POSIX; on Windows it is the creation time)
    return (path, st.st_size, st.st_mtime_ns, st.st_ino, st.st_dev,
            st.st_ctime_ns)


#: the columns weeks() and series() read
SNAPSHOT_COLUMNS = ("date", "location_name", "value")


def _parse_snapshot(fh) -> tuple:
    """(rows read, {group name: (dates, values)}, dates, columns missing):
    each group's rows with a value, in file order, as the strings the file
    holds, every date of every row (a blank value's too), and which of
    SNAPSHOT_COLUMNS the header lacks. series() applies the as-of cut and
    float() to these exactly as it once did to the rows, so a view is the
    same one a fresh read gives. A missing column reads as None here;
    _missing raises where the per-row read raised."""
    by: dict = {}
    seen_dates: dict = {}
    n = 0
    reader = csv.DictReader(fh)
    missing = frozenset(c for c in SNAPSHOT_COLUMNS
                        if c not in (reader.fieldnames or ()))
    rows = reader if not missing else (
        {**dict.fromkeys(missing), **r} for r in reader)
    for r in rows:
        n += 1
        name = r["location_name"]
        v = r["value"]
        d = r["date"]
        d = seen_dates.setdefault(d, d)          # one string per week
        if v == "":
            continue
        g = by.get(name)
        if g is None:
            g = by[name] = ([], [])
        g[0].append(d)
        g[1].append(v)
    return (n, MappingProxyType({k: (tuple(ds), tuple(vs))
                                 for k, (ds, vs) in by.items()}),
            frozenset(seen_dates), missing)


def _missing(entry: tuple, name=None, *, weeks: bool = False) -> None:
    """Raise KeyError where the per-row read raised on a file without one
    of SNAPSHOT_COLUMNS (only a file edited by hand: the store writes all
    three), and nowhere else. weeks() read only the date of every row;
    series() read a row's group, then for its own group's rows the value,
    then for those with a value the date."""
    n, index, _, missing = entry
    if not missing or not n:
        return
    if weeks:
        if "date" in missing:
            raise KeyError("date")
        return
    if "location_name" in missing:
        raise KeyError("location_name")
    if name in index:            # a row of this group (with a value, when
        for c in ("value", "date"):          # the file has the column)
            if c in missing:
                raise KeyError(c)


def _entry(path) -> tuple:
    """The cache entry of one snapshot CSV, parsed once per file version
    (see above): (rows read, index, dates, columns missing). Raises as
    open() would for a missing file."""
    return _keyed_entry(path)[1]


def _truth_of(entry: tuple) -> dict:
    """Dataset.truth() from a parsed snapshot: the {(group name, date):
    value} the per-row read gives on the same file, raising the KeyError
    it raised on a file without one of SNAPSHOT_COLUMNS. Used only when
    a held object's final snapshot was edited by hand after it first read
    it (Dataset.truth)."""
    n, index, _, missing = entry
    if n and missing:
        if "value" in missing:               # the first row's value
            raise KeyError("value")
        if index:                            # the first row with a value
            for c in ("location_name", "date"):
                if c in missing:
                    raise KeyError(c)
    return {(name, d): float(v) for name, (dates, values) in index.items()
            for d, v in zip(dates, values)}


def _keyed_entry(path) -> tuple:
    """(the file version's key, _entry(path)): the version is what a
    held Dataset pins its final snapshot to (Dataset._final)."""
    path = os.path.abspath(path)
    key = _snap_key(path, os.stat(path))
    with _SNAP_LOCK:
        hit = _SNAPS.get(key)
        if hit is not None:
            _SNAPS.move_to_end(key)
            return key, hit
    with open(path, newline="", encoding="utf-8") as fh:
        # keyed on the file this handle read, not on the earlier stat
        key = _snap_key(path, os.fstat(fh.fileno()))
        entry = _parse_snapshot(fh)
    with _SNAP_LOCK:
        for k in [k for k in _SNAPS if k[0] == path and k != key]:
            del _SNAPS[k]                        # an older version of it
        _SNAPS[key] = entry
        _SNAPS.move_to_end(key)
        held = sum(e[0] for e in _SNAPS.values())
        while len(_SNAPS) > 1 and (len(_SNAPS) > SNAPSHOT_CACHE_FILES
                                   or held > SNAPSHOT_CACHE_ROWS):
            held -= _SNAPS.popitem(last=False)[1][0]
    return key, entry


def snapshot_index(path) -> MappingProxyType:
    """The read-only per-group index of one snapshot CSV: group name ->
    (dates, values), the rows with a value in file order, as strings."""
    return _entry(path)[1]


def clear_snapshot_cache() -> None:
    """Forget every parsed snapshot (tests; never needed for correctness:
    a changed file is a new key)."""
    with _SNAP_LOCK:
        _SNAPS.clear()


@dataclass
class Dataset:
    """A stored dataset: its manifest plus the paths and adapters an engine
    needs. ``vintages``/``vintage_path`` mirror app/core/data.py."""
    path: Path
    meta: dict

    @property
    def id(self) -> str:
        return self.meta["id"]

    @property
    def name(self) -> str:
        return self.meta["name"]

    @property
    def kind(self) -> str:
        return self.meta["kind"]

    @property
    def has_population(self) -> bool:
        return bool(self.meta["has_population"])

    @property
    def has_as_of(self) -> bool:
        return bool(self.meta["has_as_of"])

    @property
    def groups(self) -> list:
        return [g["name"] for g in self.meta["groups"]]

    @property
    def name2key(self) -> dict:
        return {g["name"]: g["key"] for g in self.meta["groups"]}

    @property
    def populations(self) -> dict:
        """Latest population per group name (the particle filter's N);
        empty when the upload had none."""
        return ({g["name"]: g["population"] for g in self.meta["groups"]}
                if self.has_population else {})

    @property
    def national_group(self) -> Optional[str]:
        """The group read as the dataset's national row, or None."""
        return self.meta.get("national_group") or None

    @property
    def pf_eligible(self) -> bool:
        """Counts with a population: what the SIHRS filter needs."""
        return self.kind == "count" and self.has_population

    @property
    def source_path(self) -> Path:
        return self.path / SOURCE_FILE

    @property
    def series_path(self) -> Path:
        return self.path / SERIES_FILE

    @property
    def locations_csv(self) -> Path:
        """The locations table in the flubnf/data/locations.csv shape."""
        return self.path / LOCATIONS_FILE

    def vintages(self) -> list:
        """Every materialized vintage key (Saturday), ascending."""
        return list(self.meta["vintages"])

    def vintage_path(self, date: str) -> Path:
        """Exact vintage or a LOUD error naming nearby ones (rule 5)."""
        p = self.path / VINTAGE_DIR / f"{VINTAGE_PREFIX}{date}.csv"
        if str(date) in self.meta["vintages"] and not p.is_file():
            raise FileNotFoundError(
                f"The snapshot file for {date} of dataset {self.name!r} is "
                f"missing: {p}")
        if str(date) not in self.meta["vintages"]:
            vs = self.vintages()
            try:
                t = saturday_on_or_before(parse_date(str(date))[0])
                near = [v for v in vs
                        if abs((date_fromiso(v) - t).days) <= 45]
            except (TypeError, ValueError, AttributeError):
                near = []
            raise FileNotFoundError(
                f"No vintage for {date} in dataset {self.name!r}. "
                f"Nearby: {near or vs[-3:]}")
        return p

    @property
    def final_path(self) -> Path:
        """The newest vintage (the final data when there is no as_of)."""
        return self.vintage_path(self.meta["vintages"][-1])

    def reference_dates(self) -> list:
        """The retrospective reference dates: every distinct week except
        the first (a forecast needs one observed week), from the final
        data."""
        return self.weeks()[1:]

    # ---- the engines' view (later stages): one path per as-of -------------

    @property
    def vintage_true(self) -> bool:
        """True when the upload carried as_of snapshots: a forecast at a
        key sees the data as it stood then. Otherwise every as-of reads
        the final series truncated at the as-of (final data, not
        vintage-true)."""
        return self.has_as_of

    def _final(self, path=None) -> tuple:
        """(version key, parsed entry) of the final snapshot as this object
        reads it: the version it first read (see "ONE version" at the top
        of this module). The file is looked up at each call as before (a
        deleted one is refused, one the cache let go is parsed again);
        when it is no longer that version, a hand edit while the object is
        held, the version first read is kept. `path`: final_path, when the
        caller has it."""
        key, entry = _keyed_entry(self.final_path if path is None else path)
        held = self.__dict__.get("_final_held")
        if held is None or held[0] == key:
            held = self.__dict__["_final_held"] = (key, entry)
        return held

    def _final_rows(self) -> list:
        """The final snapshot's rows, read once per Dataset object; the
        version they are of is kept beside them (truth() reads them only
        when it is the one _final holds)."""
        rows = self.__dict__.get("_final_cache")
        if rows is None:
            p = self.final_path
            with open(p, newline="", encoding="utf-8") as fh:
                key = _snap_key(os.path.abspath(p), os.fstat(fh.fileno()))
                rows = list(csv.DictReader(fh))
            self.__dict__["_final_rows_key"] = key
            self.__dict__["_final_cache"] = rows
        return rows

    def weeks(self) -> list:
        """Every distinct week (Saturday, ISO) in the final data, ascending
        (a new list each call). Worked out once per Dataset object from
        the parsed final snapshot, so an engine that resolves the dataset
        afresh each week does not read the file again for it. The version
        series() and truth() read (_final)."""
        weeks = self.__dict__.get("_weeks_cache")
        if weeks is None:
            entry = self._final()[1]
            _missing(entry, weeks=True)
            weeks = tuple(sorted(entry[2]))
            self.__dict__["_weeks_cache"] = weeks
        return list(weeks)

    def forecast_dates(self) -> list:
        """The as-of weeks a forecast may anchor on: every vintage key when
        versioned; otherwise every week but the first (the reference
        dates: a forecast needs one observed week)."""
        return self.vintages() if self.vintage_true else self.reference_dates()

    def truth_path(self, as_of: str) -> Path:
        """The archive-shaped CSV an engine reads for one as-of. Versioned:
        that key's snapshot (exact, rule 5). Unversioned: the final data,
        which every engine truncates at the as-of; a week the data does
        not hold is refused loudly, naming nearby weeks."""
        as_of = str(as_of)
        if self.vintage_true:
            return self.vintage_path(as_of)
        weeks = self.weeks()
        if as_of not in weeks:
            try:
                t = date_fromiso(as_of)
                near = [w for w in weeks
                        if abs((date_fromiso(w) - t).days) <= 45]
            except (TypeError, ValueError):
                near = []
            raise FileNotFoundError(
                f"No week {as_of} in dataset {self.name!r}. "
                f"Nearby: {near or weeks[-3:]}")
        return self.final_path

    def series(self, name: str, as_of: Optional[str] = None) -> dict:
        """{"dates": [...], "values": [...]} for one group as it stood at
        `as_of` (the newest vintage when None), truncated at the as-of so
        final data never leaks later weeks into a view; the shape of
        data.vintage_series. The snapshot is parsed once per file
        (snapshot_index), not once per group: a replay asks for every
        group at every week. The final snapshot (unversioned data at any
        as-of, or the newest vintage) is read at the version weeks() and
        truth() read (_final)."""
        if as_of is None:
            path, final = self.final_path, True
        else:
            path = self.truth_path(as_of)
            final = (not self.vintage_true
                     or str(as_of) == self.meta["vintages"][-1])
        entry = self._final(path)[1] if final else _entry(path)
        _missing(entry, name)
        dates, values = entry[1].get(name, ((), ()))
        cut = None if as_of is None else str(as_of)
        out = sorted((d, float(v)) for d, v in zip(dates, values)
                     if cut is None or d <= cut)
        return {"dates": [d for d, _ in out], "values": [v for _, v in out]}

    def truth(self) -> dict:
        """{(group name, ISO date): value} from the final data: what a
        dataset forecast is scored against. The version weeks() and
        series() read (_final): from the rows (read once per object) when
        they are of it, else, after a hand edit while the object is held,
        from that version's parsed snapshot (_truth_of)."""
        key, entry = self.__dict__.get("_final_held") or self._final()
        rows = self._final_rows()
        if self.__dict__.get("_final_rows_key") != key:
            return _truth_of(entry)
        return {(r["location_name"], r["date"]): float(r["value"])
                for r in rows if r["value"] != ""}

    def population_series(self, name: str) -> list:
        """[(date, population)] for one group from the final snapshot,
        oldest first (population may vary by date); [] without one."""
        final_as_of = self.meta["as_of_used"][self.meta["vintages"][-1]] or ""
        out = []
        with open(self.series_path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if (r["location_name"] == name and r["as_of"] == final_as_of
                        and r["population"]):
                    out.append((r["date"], float(r["population"])))
        return sorted(out)

    def ref(self) -> dict:
        """What a run spec pins: id, digest prefix, name."""
        return {"id": self.id, "digest": self.meta["digest"][:16],
                "name": self.name}


def date_fromiso(s: str) -> date:
    return date.fromisoformat(str(s)[:10])


def get(dataset_id: str) -> Dataset:
    """The stored dataset; DatasetError for a bad or unknown id."""
    d = _dir(dataset_id)
    mp = d / META_FILE
    if not mp.is_file():
        raise DatasetError(f"No dataset {dataset_id!r}.")
    meta = json.loads(mp.read_text(encoding="utf-8"))
    return Dataset(d, meta)


def resolve(ref: Optional[dict]) -> Optional[Dataset]:
    """The dataset a spec's ref names, None for no ref; raises when it is
    gone or its digest no longer matches (never a silent substitute)."""
    if not ref:
        return None
    ds = _pkg.get(ref.get("id"))
    if not ds.meta["digest"].startswith(str(ref.get("digest") or "?")):
        raise DatasetError(f"Dataset {ds.id!r} no longer matches the "
                           "digest this run pinned.")
    return ds


def from_spec(spec) -> Optional[Dataset]:
    """The dataset a run spec (RunSpec, or its dict) names in
    ``extra["dataset"]``, else None WITHOUT touching the store: the hub
    path's call is a dictionary lookup and nothing more. A named dataset
    that is gone or changed raises (never a silent substitute)."""
    extra = (spec.get("extra") if isinstance(spec, dict)
             else getattr(spec, "extra", None))
    ref = extra.get("dataset") if isinstance(extra, dict) else None
    if not ref:
        return None
    return _pkg.resolve(ref)


def list_datasets() -> list:
    """Every readable stored dataset, newest first."""
    root = _root()
    if not root.is_dir():
        return []
    out = []
    for p in root.iterdir():
        if not valid_id(p.name) or not (p / META_FILE).is_file():
            continue
        try:
            out.append(_pkg.get(p.name))
        except (DatasetError, ValueError, OSError):
            continue
    return sorted(out, key=lambda d: (d.meta.get("created", ""), d.id),
                  reverse=True)


def delete(dataset_id: str) -> None:
    """Remove a dataset folder. Refuses malformed ids, ids resolving
    outside the store, and folders that are not datasets."""
    d = _dir(dataset_id)
    if d.is_symlink() or not (d / META_FILE).is_file():
        raise DatasetError(f"No dataset {dataset_id!r}.")
    shutil.rmtree(d)
