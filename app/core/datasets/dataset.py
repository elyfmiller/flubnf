"""A stored dataset as the console and the engines read it: the Dataset
adapter, get/resolve/from_spec, list_datasets and delete."""
from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
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
        if str(date) not in self.meta["vintages"] or not p.is_file():
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

    def _final_rows(self) -> list:
        """The final snapshot's rows, read once per Dataset object."""
        rows = self.__dict__.get("_final_cache")
        if rows is None:
            with open(self.final_path, newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.__dict__["_final_cache"] = rows
        return rows

    def weeks(self) -> list:
        """Every distinct week (Saturday, ISO) in the final data, ascending."""
        return sorted({r["date"] for r in self._final_rows()})

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
        data.vintage_series."""
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

    def truth(self) -> dict:
        """{(group name, ISO date): value} from the final data: what a
        dataset forecast is scored against."""
        return {(r["location_name"], r["date"]): float(r["value"])
                for r in self._final_rows() if r["value"] != ""}

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
