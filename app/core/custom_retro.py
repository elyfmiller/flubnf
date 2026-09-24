"""RESEARCH: replay a week range on a user-supplied dataset.

The retrospective for custom data (app/core/datasets.py), modelled on
app/core/groundhog.run_season: for each as-of week it builds the spec
retro.run_week builds (engine 'retro', season start August 1, the week's
data) plus extra["dataset"], runs the Groundhog and, for an eligible
dataset on a ready engine, the plain SIHRS filter, and scores both with
custom_run's scorer against the in-house persistence baseline.

Vintage honesty is the dataset's: with as_of snapshots each week sees the
data as it stood then (vintage-true); without, each week reads the FINAL
series cut at the week (final data, not vintage-true: revisions leak, so
such a replay reads better than real time did, and every surface says so).

Kept apart from the hub seasons on purpose: stored under the dataset's own
folder (datasets/<id>/replays/<stamp>/), never under app/state/retro, never
beside a hub season and never on the public site. Stored per replay:
forecasts.json.gz, cells.csv.gz, coverage.csv.gz and run_meta.json (the
record, with a status the page polls).
"""
from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import time
from pathlib import Path

import pandas as pd

from app.core import custom_run as CR
from app.core import horizons as hz
from app.core.runs import RunSpec, default_season_start

#: (label, lower level, upper level, nominal): groundhog.BANDS' intervals
BANDS = (("50", 0.25, 0.75, 0.50), ("80", 0.10, 0.90, 0.80),
         ("95", 0.025, 0.975, 0.95))
REPLAYS = "replays"
META = "run_meta.json"
STAMP_RE = re.compile(r"\d{8}T\d{6}Z")
ENGINES = ("analogue", "all")
REPLAY_KINDS = {True: "vintage-true", False: "final data, not vintage-true"}


class Stopped(Exception):
    pass


def replay_root(ds) -> Path:
    return Path(ds.path) / REPLAYS


def valid_stamp(stamp) -> bool:
    return isinstance(stamp, str) and bool(STAMP_RE.fullmatch(stamp))


def replay_dir(ds, stamp: str) -> Path:
    """One replay's folder; refuses a malformed stamp (path safety)."""
    if not valid_stamp(stamp):
        raise ValueError(f"not a replay stamp: {stamp!r}")
    return replay_root(ds) / stamp


def new_stamp(ds=None) -> str:
    """A UTC stamp; with `ds`, one no replay of it uses yet (two replays
    started in the same second never share a folder)."""
    t = int(time.time())
    while True:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(t))
        if ds is None or not (replay_root(ds) / stamp).exists():
            return stamp
        t += 1


def read_meta(d: Path) -> dict:
    try:
        return json.loads((Path(d) / META).read_text())
    except Exception:
        return {}


def write_meta(d: Path, meta: dict) -> None:
    p = Path(d) / META
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(meta, indent=1) + "\n")
    os.replace(tmp, p)


def list_replays(ds) -> list:
    """[(stamp, meta)] newest first; a stale 'running' record whose worker
    is gone reads 'interrupted' (the caller passes the live stamp)."""
    root = replay_root(ds)
    if not root.is_dir():
        return []
    out = []
    for p in sorted(root.iterdir(), reverse=True):
        if p.is_dir() and valid_stamp(p.name):
            out.append((p.name, read_meta(p)))
    return out


def weeks_between(ds, first: str = "", last: str = "") -> list:
    """The dataset's forecast weeks within [first, last] (either blank =
    open)."""
    return [w for w in ds.forecast_dates()
            if (not first or w >= first) and (not last or w <= last)]


def week_spec(ds, asof: str, groups: list, engine: str, *,
              weeks_to_drop: int = 0, extra: dict | None = None,
              particles: int = 10_000, replicates: int = 3,
              jitter: float | None = None, season_start: str = "",
              drop_same_day: bool = False) -> RunSpec:
    """The spec retro.run_week builds for one week, on the dataset. The
    model-settings knobs a replay was given (app/core/knobs.py) ride in
    `extra` (their record, priors, initialization) and in the RunSpec
    fields (jitter, a fixed season start, the same-day week); none given,
    the spec is the shipped one."""
    x = {"dataset": ds.ref(), "oracle": "none",
         "dataset_final": not ds.vintage_true, **(extra or {})}
    return RunSpec(engine=engine if engine == "analogue" else "all",
                   forecast_date=asof, locations=list(groups),
                   season_start=season_start or default_season_start(asof),
                   weeks_to_drop=int(weeks_to_drop or 0),
                   replicates=int(replicates), particles=int(particles),
                   drop_same_day=bool(drop_same_day), extra=x,
                   **({} if jitter is None else {"jitter": float(jitter)}))


def coverage(q_by_name: dict, ds, asof: str, cells: pd.DataFrame,
             truth: dict) -> pd.DataFrame:
    """One row per (cell, band) with a hit flag; `scored` marks the cells
    relWIS used, so the summary's coverage describes the same cells."""
    scored = (set(zip(cells.location, cells.horizon.astype(int)))
              if not cells.empty else set())
    T = pd.Timestamp(asof)
    rows = []
    for name, qs in q_by_name.items():
        for h in hz.HORIZONS:
            q = qs.get(h)
            if not q:
                continue
            end = (T + pd.Timedelta(days=7 * (int(h) + 1))).date().isoformat()
            actual = truth.get((name, end))
            if actual is None or actual <= 0:
                continue
            for label, lo, hi, _nom in BANDS:
                rows.append({"location": name, "horizon": int(h),
                             "band": label,
                             "hit": int(q[lo] <= actual <= q[hi]),
                             "scored": (name, int(h)) in scored,
                             "national": name == ds.national_group})
    return pd.DataFrame(rows, columns=["location", "horizon", "band", "hit",
                                       "scored", "national"])


def summarise(cells: pd.DataFrame, cov: pd.DataFrame) -> dict:
    """Per model: pooled relWIS (national group excluded) with coverage on
    the scored cells, the national group beside it, relWIS by horizon and
    by group."""
    out = {}
    if cells.empty:
        return out
    for m in sorted(set(cells.model)):
        c = cells[cells.model == m]
        v = cov[cov.model == m] if not cov.empty else cov

        def block(cc, vv):
            if cc.empty:
                return {"cells": 0, "relwis": None}
            b = {"cells": int(len(cc)), "weeks": int(cc["asof"].nunique()),
                 "relwis": float(cc.wis.sum() / cc.base_wis.sum())}
            vv = vv[vv.scored.astype(bool)] if not vv.empty else vv
            for label, _lo, _hi, _nom in BANDS:
                bb = vv[vv.band.astype(str) == label] if not vv.empty else vv
                if len(bb):
                    b[f"cov{label}"] = float(bb.hit.mean())
            return b
        nat = c.national.astype(bool)
        vnat = v.national.astype(bool) if not v.empty else None
        pooled = block(c[~nat], v[~vnat] if vnat is not None else v)
        national = (block(c[nat], v[vnat] if vnat is not None else v)
                    if nat.any() else None)
        pc = c[~nat]
        by_h = ({str(h): float(g.wis.sum() / g.base_wis.sum())
                 for h, g in pc.groupby("horizon")} if len(pc) else {})
        by_g = {str(n): {"relwis": float(g.wis.sum() / g.base_wis.sum()),
                         "cells": int(len(g))}
                for n, g in c.groupby("location")}
        out[m] = {"pooled": pooled, "national": national,
                  "by_horizon": by_h, "by_group": by_g}
    return out


def run(ds, weeks: list, groups: list, *, engine: str = "analogue",
        weeks_to_drop: int = 0, extra: dict | None = None,
        out_dir: Path, pf_state: str = "absent", progress=None,
        stop_file: Path | None = None, particles: int = 10_000,
        replicates: int = 3, on_workroot=None, jitter: float | None = None,
        season_start: str = "", drop_same_day: bool = False) -> dict:
    """Replay `weeks` on `ds` into `out_dir`; returns the record.

    `engine`: 'analogue' (the Groundhog alone) or 'all' (plus the plain
    SIHRS filter when the dataset is eligible and the engine is ready).
    `progress(asof, i, n)` is called after each week; `stop_file`, when it
    appears, stops the replay between steps (the record says so).

    Model settings (app/core/knobs.py), as a dataset run takes them: the
    knobs record in `extra` (knobs.write_extra; the output floor's rate is
    read from it) and the RunSpec fields as arguments. A record off the
    shipped values is kept in run_meta.json as "knobs" (with its digest),
    as a hub replay's run record keeps it."""
    from app.core import knobs as K
    from app.core.engines import analogue as an_engine
    from app.core.engines import pf as pf_engine
    from app.core.floor import floor_quantiles, floor_samples

    if engine not in ENGINES:
        raise ValueError(f"engine must be one of {ENGINES}, not {engine!r}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    count = ds.kind == "count"
    want_pf = engine == "all"
    pf_ok = want_pf and ds.pf_eligible and pf_state == "ready"
    if want_pf and pf_state == "broken":
        raise RuntimeError(pf_engine.engine_missing_message())
    x0 = dict(extra or {})
    record = K.record_of({"extra": x0})
    lam = K.value_of(x0, "output.floor_lam")
    fkw = {} if lam is None else {"lam": float(lam)}
    meta = {
        "status": "running", "dataset": {**ds.ref(),
                                         "vintage_true": ds.vintage_true,
                                         "national_group": ds.national_group,
                                         "kind": ds.kind},
        "replay_kind": REPLAY_KINDS[ds.vintage_true],
        "engine": engine, "groups": list(groups), "weeks": list(weeks),
        "first": weeks[0] if weeks else None,
        "last": weeks[-1] if weeks else None,
        "weeks_to_drop": int(weeks_to_drop or 0),
        "analogue": CR.analogue_label(x0),
        "analogue_donors": CR.analogue_donors(x0),
        "pf": ("plain SIHRS particle filter (no Oracle step)" if pf_ok
               else None),
        "pf_skipped": (None if pf_ok or not want_pf else
                       "the dataset is not counts with a population"
                       if not ds.pf_eligible else
                       "engine venv not installed"),
        "baseline": CR.BASELINE, "weeks_completed": 0,
        "total_weeks": len(weeks), "started_utc": time.time(),
        "horizon_convention": "hub 0..3 (app.core.horizons), no anchor week",
        "abstained": {},
    }
    if pf_ok:
        meta.update({"particles": int(particles),
                     "replicates": int(replicates)})
    if record:
        meta["knobs"] = K.jsonable(record)
        meta["knobs_digest"] = K.digest(record)
    write_meta(out_dir, meta)
    truth = ds.truth()
    forecasts, cells, covs = {}, [], []
    try:
        for i, asof in enumerate(weeks):
            if stop_file is not None and Path(stop_file).exists():
                raise Stopped("stopped by user")
            spec = week_spec(ds, asof, groups, engine,
                             weeks_to_drop=weeks_to_drop, extra=x0,
                             particles=particles, replicates=replicates,
                             jitter=jitter, season_start=season_start,
                             drop_same_day=drop_same_day)
            members = {}
            an_q = an_engine.run(spec)
            if count:
                an_q = {n: floor_quantiles(q, **fkw)
                        for n, q in an_q.items()}
            members["analogue"] = an_q
            if pf_ok:
                wr = out_dir / "work" / asof
                if wr.exists():
                    shutil.rmtree(wr)
                if on_workroot:
                    on_workroot(wr)
                pf_engine.prepare(spec, wr)
                status = pf_engine.execute(wr)
                fails = {k: v for k, v in status.items() if v != "ok"}
                samples = pf_engine.collect(wr)
                if count:
                    samples = {n: floor_samples(s, n, asof, **fkw)
                               for n, s in samples.items()}
                pq = {n: CR.quantiles_from_samples(s)
                      for n, s in samples.items()}
                members["pf"] = {n: q for n, q in pq.items() if q}
                if fails:
                    meta.setdefault("pf_failures", {})[asof] = fails
                shutil.rmtree(wr, ignore_errors=True)
            forecasts[asof] = {
                m: {n: {h: {repr(float(L)): float(v) for L, v in lv.items()}
                        for h, lv in hq.items()} for n, hq in q.items()}
                for m, q in members.items()}
            for m, q in members.items():
                miss = sorted(set(groups) - set(q))
                if miss:
                    meta["abstained"].setdefault(m, {})[asof] = miss
                c = CR.score(q, ds, asof, weeks_to_drop=weeks_to_drop,
                             truth=truth)
                v = coverage(q, ds, asof, c, truth)
                for df in (c, v):
                    df["model"] = m
                    df["asof"] = asof
                cells.append(c)
                covs.append(v)
            meta["weeks_completed"] = i + 1
            write_meta(out_dir, meta)
            if progress:
                progress(asof, i + 1, len(weeks))
        meta["status"] = "done"
    except (Stopped, pf_engine.RunStopped):
        meta["status"] = "stopped"
    except Exception as e:
        meta["status"] = "error"
        meta["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    finally:
        shutil.rmtree(out_dir / "work", ignore_errors=True)
        cells_df = (pd.concat([c for c in cells if not c.empty],
                              ignore_index=True)
                    if any(not c.empty for c in cells) else pd.DataFrame(
                        columns=["location", "horizon", "wis", "base_wis",
                                 "rel", "national", "truth", "model",
                                 "asof"]))
        cov_df = (pd.concat([v for v in covs if not v.empty],
                            ignore_index=True)
                  if any(not v.empty for v in covs) else pd.DataFrame(
                      columns=["location", "horizon", "band", "hit",
                               "scored", "national", "model", "asof"]))
        with gzip.open(out_dir / "forecasts.json.gz", "wt",
                       encoding="utf-8") as f:
            json.dump({"meta": {k: meta[k] for k in
                                ("dataset", "replay_kind",
                                 "horizon_convention")},
                       "forecasts": forecasts}, f)
        cells_df.to_csv(out_dir / "cells.csv.gz", index=False)
        cov_df.to_csv(out_dir / "coverage.csv.gz", index=False)
        meta["summary"] = summarise(cells_df, cov_df)
        meta["finished_utc"] = time.time()
        write_meta(out_dir, meta)
    return meta


def load(d: Path) -> tuple:
    """(meta, forecasts, cells, coverage) of a stored replay."""
    d = Path(d)
    meta = read_meta(d)
    fc = {}
    try:
        with gzip.open(d / "forecasts.json.gz", "rt", encoding="utf-8") as f:
            fc = json.load(f).get("forecasts", {})
    except Exception:
        pass
    try:
        cells = pd.read_csv(d / "cells.csv.gz")
    except Exception:
        cells = pd.DataFrame()
    try:
        cov = pd.read_csv(d / "coverage.csv.gz")
    except Exception:
        cov = pd.DataFrame()
    return meta, fc, cells, cov
