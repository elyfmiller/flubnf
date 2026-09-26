"""data.exp from elsewhere: the hub archive (one location, settled or as
a vintage knew it), a stored custom dataset (app/core/datasets.py) or an
upload, always in calendar weeks, with the data.source.json sidecar that
records where the rows came from. app/core/sandbox.py is the facade;
every name here imports from it too. The hub modules are imported inside
the functions so the sandbox imports on a machine without a hub.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import time

from app.core import sandbox as _sb  # MODELS and locations: patched there
from app.core.sandbox import (
    DEFAULT_HEADER,
    SOURCE_FILE,
    UPLOAD_MAX_BYTES,
    SandboxError,
    _digest,
    _first_saturday,
    _fmt,
    _iso_date,
    check_name,
    model_dir,
    read_info,
    set_population,
)
from app.core.sandbox_bngl import sihrs_shaped

DEFAULT_WEEKS = 20


def default_range(vintage_dates: list, weeks: int = DEFAULT_WEEKS) -> dict:
    """The date inputs' starting values: the last `weeks` weeks ending on
    the newest vintage's date (a vintage archived on Saturday D carries
    the week ending D). Empty strings when no vintage is known."""
    newest = vintage_dates[0] if vintage_dates else ""
    try:
        end = dt.date.fromisoformat(str(newest))
    except (TypeError, ValueError):
        return {"start": "", "end": ""}
    start = end - dt.timedelta(days=7 * (max(int(weeks), 1) - 1))
    return {"start": start.isoformat(), "end": end.isoformat()}


def _check_range(start: str, end: str) -> tuple:
    a, b = _iso_date(start, "start"), _iso_date(end, "end")
    if a > b:
        raise SandboxError(f"start {a.isoformat()} is after end {b.isoformat()}")
    return a.isoformat(), b.isoformat()


def _window(got: dict, start: str, end: str) -> dict:
    """{"dates", "values", "dropped"} of a {date: value} map within a
    range; dropped counts the range's Saturdays with no value."""
    dates = sorted(d for d in got if start <= d <= end)
    d = dt.date.fromisoformat(_first_saturday(start))
    dropped = 0
    last = dt.date.fromisoformat(end)
    while d <= last:
        if d.isoformat() not in got:
            dropped += 1
        d += dt.timedelta(days=7)
    return {"dates": dates, "values": [float(got[d]) for d in dates],
            "dropped": dropped}


def series_for(location_name: str, start: str, end: str,
               asof: str | None = None) -> dict:
    """The weekly admissions of one location between two dates: the
    settled truth when asof is None, else what the vintage archived on
    asof held. {"dates": [...], "values": [...], "dropped": n}, where
    dropped counts the Saturdays in the range with no reported value.
    Missing weeks are dropped, never imputed."""
    start, end = _check_range(start, end)
    if asof is None:
        from app.core import scoring
        truth, n2f = scoring.load_truth()
        fips = n2f.get(str(location_name))
        if not fips:
            raise SandboxError(f"unknown location {location_name!r}")
        got = {d.strftime("%Y-%m-%d"): v for (f, d), v in truth.items()
               if f == fips}
    else:
        from app.core import data as data_mod
        s = data_mod.vintage_series(str(asof), str(location_name))
        got = dict(zip(s["dates"], s["values"]))
    return _window(got, start, end)


# ------------------------------------------------------ your own datasets
# A stored custom dataset (app/core/datasets.py: an uploaded grouped CSV
# or hubverse time series, validated and materialized in the FluSight
# archive shape) is a data source like the hub: one group's weekly
# values from its final snapshot.

def dataset_choices() -> list:
    """The stored datasets for the Load data form, newest first, as
    [{"id", "name", "kind", "groups": [{"name", "first", "last",
    "population"}]}]; empty when there are none or the store is unreadable."""
    try:
        from app.core import datasets
        return [{"id": d.id, "name": d.name, "kind": d.kind,
                 "pf": d.pf_eligible,
                 "groups": [{k: g.get(k) for k in ("name", "first", "last",
                                                   "population")}
                            for g in d.meta.get("groups", [])]}
                for d in datasets.list_datasets()]
    except Exception:
        return []


class UploadRefused(SandboxError):
    """An upload the dataset store refused; problems holds each reason."""

    def __init__(self, message: str, problems: list):
        super().__init__(message)
        self.problems = list(problems)


def display_name(filename) -> str:
    """A client's file name reduced to something safe to show: the last
    path part, letters, digits and ._- and space only, at most 80
    characters. It is never used as a path."""
    base = re.split(r"[\\/]", str(filename or ""))[-1]
    return re.sub(r"[^A-Za-z0-9._ -]", "", base)[:80].strip(" .")


def ingest_upload(fileobj, filename: str, kind: str = "",
                  max_bytes: int = UPLOAD_MAX_BYTES):
    """Validate and store one uploaded CSV through the dataset store
    (a grouped CSV or a hubverse time series, read as leniently as the
    console's upload box reads it); the stored Dataset. ``kind`` '' takes
    the kind the values show. Refusals carry the validator's problems,
    each in words."""
    from app.core import datasets
    shown = display_name(filename)
    stem = shown.rsplit(".", 1)[0] if "." in shown else shown
    try:
        return datasets.ingest(fileobj, stem or "upload", kind=kind or None,
                               limits=datasets.Limits(max_bytes=max_bytes),
                               filename=shown)
    except datasets.DatasetError as e:
        raise UploadRefused(str(e), [str(p) for p in e.problems]) from None


def dataset_series(dataset_id: str, group: str, start: str = "",
                   end: str = "") -> dict:
    """One group's weekly values from a stored dataset's final snapshot,
    within start..end (each defaulting to the group's own first or last
    week): series_for's shape plus "start", "end", "population" and the
    dataset's "ref" (id, digest prefix, name)."""
    from app.core import datasets
    try:
        ds = datasets.get(dataset_id)
    except datasets.DatasetError as e:
        raise SandboxError(str(e)) from None
    grp = next((g for g in ds.meta.get("groups", []) if g["name"] == group), None)
    if grp is None:
        raise SandboxError(f"dataset {ds.name!r} has no group {group!r}; it "
                           f"has {', '.join(ds.groups[:6])}")
    start, end = _check_range(start or grp["first"], end or grp["last"])
    got = {}
    with open(ds.final_path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("location_name") == group:
                try:
                    got[r["date"]] = float(r["value"])
                except (KeyError, TypeError, ValueError):
                    continue
    out = _window(got, start, end)
    out.update(start=start, end=end, ref=ds.ref(), kind=ds.kind,
               population=ds.populations.get(group))
    return out


def week_origin(name: str, start: str) -> str:
    """The date t = 0 counts from: the model's season_start (model.json)
    when it records one, since a seasonal model's phase is anchored there,
    else the first Saturday of the range."""
    info = read_info(name)
    if info.get("season_start"):
        return _iso_date(info["season_start"], "season_start").isoformat()
    return _first_saturday(start)


def calendar_offsets(dates: list, origin: str) -> list:
    """Whole weeks from origin to each date: a missing week leaves a gap
    in t (rule 10, as the console's resolve_state keeps it), never a
    renumbered row that would integrate one week where two elapsed."""
    o = dt.date.fromisoformat(origin)
    out = []
    for d in dates:
        days = (dt.date.fromisoformat(d) - o).days
        if days < 0:
            raise SandboxError(f"week {d} is before t = 0 ({origin})")
        # whole weeks, floored as resolve_state counts them: a season
        # start on a Sunday to Tuesday (1 August 2023) must not put its
        # first Saturday at t = 1
        out.append(days // 7)
    return out


def fill_data(name: str, location_name: str, start: str, end: str,
              asof: str | None = None, *, dataset: str | None = None,
              set_pop: bool = False) -> dict:
    """Rewrite a model's data.exp from the hub archive, or with dataset=
    from one group (location_name) of a stored dataset: the file's own
    header line if it has one (else '# time H_weekly'), then one 't value'
    row per reported week, t the whole weeks since week_origin, so a
    missing week is a gap in t. Writes the sidecar data.source.json
    beside it (with the origin and each row's date) and returns its
    contents. Refuses an unknown location or group, a range with no
    reported week, and start after end; a dataset's range defaults to the
    group's own weeks. With set_pop, the model's N line becomes the
    location's (or group's) population (set_population's refusals hold,
    checked before anything is written)."""
    d = model_dir(name)
    if set_pop and sihrs_shaped((d / "model.bngl").read_text(
            encoding="utf-8", errors="replace")):
        set_population(name, 1)                  # raises its refusal
    extra = {}
    if dataset:
        s = dataset_series(dataset, str(location_name), start, end)
        start, end = s["start"], s["end"]
        extra = {"dataset": s["ref"], "kind": s["kind"]}
        if s.get("population"):
            extra["population"] = s["population"]
        where = f" in dataset {s['ref']['name']}"
    else:
        start, end = _check_range(start, end)
        known = {l["name"] for l in _sb.locations()}
        if str(location_name) not in known:
            raise SandboxError(f"unknown location {location_name!r}: the "
                               "hub's locations table does not name it")
        s = series_for(location_name, start, end, asof)
        where = f" in the vintage of {asof}" if asof else ""
    if not s["values"]:
        raise SandboxError(f"no reported week for {location_name} between "
                           f"{start} and {end}{where}")
    pop = None
    if set_pop:
        pop = (extra.get("population") if dataset
               else hub_population(str(location_name)))
        if not pop:
            raise SandboxError(f"no population is known for {location_name}; "
                               "N was not changed and nothing was loaded")
    origin = week_origin(name, start)
    ts = calendar_offsets(s["dates"], origin)
    header = DEFAULT_HEADER
    exp = d / "data.exp"
    if exp.is_file():
        for line in exp.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                if line.lstrip().startswith("#"):
                    header = line.rstrip()
                break
    text = header + "\n" + "\n".join(
        f"{t} {_fmt(v)}" for t, v in zip(ts, s["values"])) + "\n"
    exp.write_text(text, encoding="utf-8", newline="\n")
    info = {"location": str(location_name), "start": start, "end": end,
            "asof": ("dataset" if dataset else str(asof) if asof
                     else "settled"),
            "rows": len(s["values"]), "dropped": int(s["dropped"]),
            "origin": origin, "dates": list(s["dates"]), **extra,
            "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "digest": _digest(text)}
    (d / SOURCE_FILE).write_text(json.dumps(info, indent=1) + "\n",
                                 encoding="utf-8", newline="\n")
    if pop:
        set_population(name, int(pop))
        info["population_set"] = int(pop)
    return info


def hub_population(location_name: str) -> int | None:
    """A hub location's population from the locations table, or None."""
    try:
        import pandas as pd

        from app.core import data as data_mod
        locs = pd.read_csv(data_mod.LOCATIONS, dtype=str)
        row = locs[locs.location_name == str(location_name)]
        return int(float(row.iloc[0]["population"])) if not row.empty else None
    except Exception:
        return None


def read_data_source(name: str) -> dict | None:
    """The sidecar of a model, or None: none written, unreadable, or
    data.exp edited since (its digest no longer matches), so the page
    never says the file holds archive rows it no longer holds."""
    try:
        d = _sb.MODELS / check_name(name)
        info = json.loads((d / SOURCE_FILE).read_text(encoding="utf-8"))
        if not isinstance(info, dict):
            return None
        cur = (d / "data.exp").read_text(encoding="utf-8", errors="replace")
        if info.get("digest") and info["digest"] != _digest(cur):
            return None
        return info
    except Exception:
        return None
