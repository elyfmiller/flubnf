"""The forecast run pipeline and the OS sleep guard.

_run_all is what POST /run and a re-run schedule as a background task: the
engines, the submissions, scoring, the weekly report and the forecast
archive, in one workroot with one ledger row. It calls its helpers
(_harvest_params, _sleep_guard, _pf_engine_state, _write_weekly_report,
_archive_run) bare, so a patch of pipeline.X reaches it. Other modules call
pipeline._run_all, pipeline._sleep_guard (the retro worker, the sandbox,
the dataset workers) and pipeline._pf_engine_state at call time.
"""
from __future__ import annotations

import html as _htmlmod
import shutil
import sys
from pathlib import Path

from app.core.runs import (Ledger, RunSpec, lease_workroot, settings_html,
                           spec_settings, version_pairs)
from app.ui import state, versions
from app.ui.forms import _knobs
from app.ui.shared import _invalidate_scans, _name_workroot, _phase
from app.ui.state import _status
from app.ui.versions import RUNNING_SHA, VERSIONS


# === Forecast pipeline: param harvest, sleep guard, weekly report, _run_all ===
def _harvest_params(workroot: Path) -> dict:
    """Per-location posterior medians of the fitted PF parameters, pooled
    across replicates (params_*.txt under each cell's out/Results/PF/Runs),
    stored as results.json 'params'. Unreadable cells are skipped."""
    import json as _json
    import numpy as _np
    try:
        cells = _json.loads((workroot / "cells.json").read_text())
    except Exception:
        return {}
    pooled: dict = {}
    for c in cells:
        try:
            loc = c["location"]
            runs = Path(c["dir"]) / "out" / "Results" / "PF" / "Runs"
            for pfile in sorted(runs.glob("params_*.txt")):
                with open(pfile) as fh:
                    names = fh.readline().replace("#", " ").split()
                arr = _np.atleast_2d(_np.loadtxt(str(pfile), skiprows=1))
                if arr.size == 0 or arr.shape[1] != len(names):
                    continue
                for j, name in enumerate(names):
                    col = arr[:, j]
                    col = col[_np.isfinite(col)]
                    if col.size:
                        pooled.setdefault(loc, {}).setdefault(
                            name.removesuffix("__FREE"), []).append(col)
        except Exception:
            continue
    return {loc: {name: float(_np.median(_np.concatenate(chunks)))
                  for name, chunks in by_name.items()}
            for loc, by_name in pooled.items()}


# SetThreadExecutionState flags: CONTINUOUS persists until cleared (clear =
# CONTINUOUS alone); SYSTEM_REQUIRED blocks idle sleep (caffeinate -i).
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


class _WinSleepGuard:
    """Windows sleep inhibitor with Popen's .terminate(). The flag is
    thread-affine: create and terminate on the same worker thread."""

    def __init__(self, kernel32):
        self._kernel32 = kernel32

    def terminate(self):
        try:
            self._kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
        except Exception:
            pass


def _windows_sleep_guard(kernel32=None):
    """SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) on the
    calling (worker) thread; returns a guard with .terminate() or None on
    any failure. `kernel32` is injectable for tests on other platforms."""
    try:
        if kernel32 is None:
            import ctypes
            kernel32 = ctypes.windll.kernel32
        prev = kernel32.SetThreadExecutionState(
            _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
        if not prev:                    # 0 means the call failed
            return None
        return _WinSleepGuard(kernel32)
    except Exception:
        return None


def _sleep_guard():
    """Keep the machine awake during a long run: macOS `caffeinate -i -w
    <pid>`, Windows _windows_sleep_guard. Returns an object with
    .terminate(), or None elsewhere or on failure (no run depends on it)."""
    import os
    import subprocess
    if sys.platform == "darwin":
        try:
            return subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
        except Exception:
            return None
    if sys.platform == "win32":
        return _windows_sleep_guard()
    return None


def _write_weekly_report(spec, workroot: Path, pf_samples: dict, obs: dict,
                         df, locs, n2f: dict, elapsed_s: float,
                         outcome: dict, an_q: dict | None = None,
                         ens_q: dict | None = None) -> None:
    """Step 5b of _run_all: build the report inputs bundle, save it as
    report_inputs.json, then render report.html FROM it (one render path,
    so _report_for_serving can rebuild after a design change).

    Map cards for every model (pf reduced to the 23-level grid; an_q =
    Groundhog quantiles, loc -> horizon -> {level: value}) come from the
    one quantile-CDF path; the map renders PF-first and cards_model records
    which. State drill-down fans are PF's. `ens_q` (retired blend) is
    accepted and ignored. Mutates `outcome`; the caller contains failures."""
    import json as _json
    from datetime import date as _dd
    from datetime import timedelta as _tdd

    import numpy as _np
    import pandas as pd

    from app.core import ensemble as _ens
    from app.core import report_v2
    from app.core.report import (categorical_probs,
                                 categorical_probs_from_quantiles)
    from app.core.report_v2 import CATS
    from app.core.scoring import summary_table_html
    n2a = dict(zip(locs.location_name, locs.abbreviation))
    n2p = dict(zip(locs.location_name, locs.population.astype(float)))
    # the national population from the same table (the hub's "US" row)
    _us_row = locs[locs.location.astype(str) == "US"]
    us_pop = (int(float(_us_row.population.iloc[0])) if len(_us_row)
              else 340_000_000)
    # cells.json is read only when there are fitted samples
    cells = (_json.loads((workroot / "cells.json").read_text())
             if pf_samples else [])
    ens_q = ens_q or {}
    an_q = an_q or {}
    # PF on the members' 23-level grid, so its cards use the same CDF path
    pf_q = {loc: _ens.member_quantiles_from_samples(s)
            for loc, s in pf_samples.items()}

    def _last_obs(loc):
        o = obs.get(loc) or []
        if o:
            return float(o[-1][1])
        for c in cells:               # degraded runs: cells.json still
            if c.get("location") == loc:  # knows the anchor value
                return float(c.get("last_observed", 0.0))
        return None

    def _q1_of(qd):
        q1 = (qd or {}).get("0", (qd or {}).get(0))   # one week ahead
        return q1 if isinstance(q1, dict) and q1 else None

    def _q_cards(q_by_loc):
        """abbr -> hover card from ONE model's quantiles."""
        out = {}
        for loc, qd in (q_by_loc or {}).items():
            q1 = _q1_of(qd)
            lo = _last_obs(loc)
            if q1 is None or lo is None or loc not in n2a:
                continue
            probs = categorical_probs_from_quantiles(
                q1, lo, int(n2p.get(loc, 0)), 0)
            if not probs:
                continue
            med1 = float(min(q1.items(),
                             key=lambda kv: abs(float(kv[0]) - 0.5))[1])
            # hover_html reaches innerHTML: escape the name
            hover = (f"<b>{_htmlmod.escape(loc)}</b><br>current: {lo:.0f}"
                     f"<br>1-wk median: {med1:.0f}<br>" +
                     "<br>".join(f"{c.replace('_',' ')}: "
                                 f"{probs.get(c,0):.0%}" for c in CATS))
            out[n2a[loc]] = {"probs": probs, "name": loc,
                             "abbr": n2a[loc], "fips": n2f.get(loc, ""),
                             "hover_html": hover}
        return out

    def _q_nat_card(q_by_loc):
        """The national card from the SAME model's quantiles (never
        cross-filled from another member)."""
        us_names = [n for n in (q_by_loc or {}) if n2f.get(n) == "US"] or \
                   [n for n in (q_by_loc or {})
                    if "US" in n or "national" in n.lower()]
        un = us_names[0] if us_names else None
        q1 = _q1_of((q_by_loc or {}).get(un)) if un else None
        lo_us = _last_obs(un) if un else None
        if q1 is None or lo_us is None:
            return None
        probs_us = categorical_probs_from_quantiles(
            q1, lo_us, us_pop, 0)
        if not probs_us:
            return None
        med_us = float(min(q1.items(),
                           key=lambda kv: abs(float(kv[0]) - 0.5))[1])
        hover_us = ("<b>United States</b><br>current: "
                    f"{lo_us:.0f}<br>1-wk median: {med_us:.0f}")
        return {"probs": probs_us, "name": "United States",
                "abbr": "US", "fips": "US", "hover_html": hover_us}

    cards_by_model = {}
    nat_cards = {}
    for model, q_by_loc in (("pf", pf_q), ("analogue", an_q)):
        c = _q_cards(q_by_loc)
        if c:
            cards_by_model[model] = c
            nc = _q_nat_card(q_by_loc)
            if nc:
                nat_cards[model] = nc
    # PF colors the rendered map; the toggle offers the Groundhog
    cards_model = next((m for m in ("pf", "analogue")
                        if m in cards_by_model), "pf")
    cards = dict(cards_by_model.get(cards_model, {}))
    for name, abbr in n2a.items():
        cards.setdefault(abbr, {"name": name, "abbr": abbr,
                                "fips": n2f.get(name, "")})
    # in-scope states without a card: a reporting gap only when the state
    # has no reported data; otherwise the model made no forecast, and the
    # run's own record says why (the Output page's words)
    from app.core.coverage import missing_reason
    _in_scope = [l for l in spec.locations
                 if n2f.get(l) and n2f.get(l) != "US"]
    gap_fips = sorted({n2f[l] for l in _in_scope if _last_obs(l) is None})
    no_forecast = {}
    for model in ("pf", "analogue"):
        if model != cards_model and model not in cards_by_model:
            continue
        have = cards_by_model.get(model, {})
        why = {n2f[l]: missing_reason(outcome, model, "", l)
               for l in _in_scope
               if n2f[l] not in gap_fips and n2a.get(l) not in have}
        if why:
            no_forecast[model] = why
    wis_html = ("<div class='card'><h2>forecast accuracy "
                "(retrospective)</h2>" + summary_table_html(df)
                + "</div>")
    # settled outcomes for backdated runs: the LATEST vintage's values
    # past the forecast origin, framed to the 4-week horizon
    settled_by_loc = {}
    try:
        _vs_all = state.data_mod.vintages()
        if _vs_all and _vs_all[-1] > spec.forecast_date:
            _lim = (_dd.fromisoformat(spec.forecast_date)
                    + _tdd(days=28)).isoformat()
            ldf = pd.read_csv(state.data_mod.vintage_path(_vs_all[-1]),
                              dtype={"location": str})
            ldf["location"] = ldf["location"].str.zfill(2)
            for loc in spec.locations:
                g = ldf[(ldf.location == n2f.get(loc, "")) &
                        (ldf.date > spec.forecast_date) &
                        (ldf.date <= _lim)].sort_values("date")
                pts = [(str(r.date)[:10], float(r.value))
                       for r in g.itertuples()
                       if pd.notna(r.value)]
                if pts:
                    settled_by_loc[loc] = pts
    except Exception:
        settled_by_loc = {}
    # state pages as DATA; render_bundle draws the figures
    details = {}
    for loc, s in pf_samples.items():
        fips_l = n2f.get(loc, "")
        obs_pairs = (obs.get(loc) or [])[-12:]
        o_t = [d for d, _ in obs_pairs]
        o_v = [v for _, v in obs_pairs]
        # canonical horizons are AS-OF relative: hub label h is h+1 weeks
        # past the as-of week (the files' target_end_date), whatever the
        # newest observed week (an unreported or trimmed week moves it back)
        _base = _dd.fromisoformat(spec.forecast_date)
        f_t = [(_base + _tdd(days=7 * (h + 1))).isoformat()
               for h in (0, 1, 2, 3)]
        samples_h = {f_t[h]: s[str(h)] for h in (0, 1, 2, 3)}
        try:
            q_by_t = report_v2.fan_quantiles(f_t, samples_h)
            lo_l = o_v[-1] if o_v else 0.0
            # one week ahead = canonical "0", matching the fan above
            probs_l = categorical_probs(
                _np.asarray(s["0"], float), lo_l,
                us_pop if fips_l == "US" else int(n2p.get(loc, 1e6)), 0)
            key = "US" if fips_l == "US" else n2a.get(loc, loc)
            meds = [q_by_t[t]["0.5"] for t in f_t]
            note = ("Off-season: the model finds no sustained "
                    "transmission. This forecast reflects the recent "
                    "reporting background, not epidemic growth."
                    if max(meds) <= 2 else "")
            details[key] = {
                "name": "United States" if fips_l == "US" else loc,
                "note": note,
                "fan": {"observed_times": o_t, "observed": o_v,
                        "forecast_times": f_t, "quantiles": q_by_t,
                        "title": f"{loc}: weekly admissions",
                        "settled": settled_by_loc.get(loc)},
                "cat_probs": probs_l,
                "table_rows": [(d, v) for d, v in obs_pairs[-6:]]}
        except Exception:
            continue
    # national card from the same model as the rendered state cards
    nat_card = nat_cards.get(cards_model)
    bundle = {"version": report_v2.BUNDLE_VERSION,
              "reference_date": spec.forecast_date,
              # v2: which model computed the map cards
              "cards_model": cards_model,
              "cards": cards, "details": details,
              # v4: states this run covered (reporting gap vs never fitted)
              "fitted_fips": sorted({n2f.get(l) for l in spec.locations
                                     if n2f.get(l) and n2f.get(l) != "US"}),
              # v5: whether US was among the run's locations
              "national_in_run": any(n2f.get(l) == "US"
                                     for l in spec.locations),
              # v6: the only reporting gaps (in scope, no reported data),
              # and each model's reason for an in-scope state it left blank
              "gap_fips": gap_fips, "no_forecast": no_forecast,
              # v3: every model's cards (the outlook toggle's data)
              "cards_by_model": cards_by_model,
              "national_map_cards": nat_cards,
              "national": {"summary_html": wis_html},
              "national_map_card": nat_card,
              "elapsed_s": elapsed_s,
              # run settings, app build and engine versions
              "settings_html": settings_html(
                  spec_settings(spec, outcome)
                  + version_pairs(RUNNING_SHA, VERSIONS))}
    try:
        bp = report_v2.save_bundle(bundle, workroot)
        outcome["report_inputs_bytes"] = bp.stat().st_size
    except Exception as e:    # the report is never hostage to its bundle
        outcome["report_inputs_error"] = str(e)[:200]
    report_v2.render_bundle(bundle, workroot / "report.html")
    outcome["report"] = str(workroot / "report.html")


def _pf_engine_state() -> str:
    """This machine's PF engine in one word:

      absent   no engine venv/fork: analogue-only Tier A, the run proceeds
      broken   venv + fork path but no pybnf/pf.py: every fit would fail
      ready    the fork provides fit_type = pf

    Installed-ness is defined once, in app.core.engines.pf.engine_available.
    """
    from flubnf.settings import PY_ENGINE, PYBNF
    from app.core.engines import pf as pf_engine
    if not (PY_ENGINE.exists() and PYBNF.exists()):
        return "absent"
    return "ready" if pf_engine.engine_available() else "broken"


def _optional_rows(spec, workroot: Path, pf_samples: dict, an_q: dict,
                   locs, n2f: dict, minus1: bool, pmf: bool,
                   floor_kw: dict, vintage=None) -> tuple:
    """(pf rows, Groundhog rows, {model: counts}) for a run with an
    optional-output knob on: each location's quantile rows (horizon -1
    included when `minus1`), then its rate-change pmf rows when `pmf`.
    The rules per model are app/core/optional_outputs.py's. `vintage` is
    the observed file the run read (the live target file on submission
    day, before the dated archive copy exists); None = the dated one."""
    from app.core import optional_outputs as OPT
    from app.core.data import vintage_path
    from app.core.engines import analogue as an_engine
    from app.core.floor import floor_quantiles
    from app.core.horizons import ORIGIN
    from app.core.submit import (HORIZONS, HORIZONS_WITH_MINUS1,
                                 quantile_rows, rate_change_rows,
                                 rows_from_quantiles)
    asof = spec.forecast_date
    hzs = HORIZONS_WITH_MINUS1 if minus1 else HORIZONS
    pops = dict(zip(locs.location_name, locs.population.astype(float)))
    reported = OPT.reported_counts(
        vintage if vintage is not None else vintage_path(asof), asof)
    pf_k = OPT.pf_weeks_dropped(workroot, spec, reported,
                                {l: n2f[l] for l in pf_samples})
    counts = {"pf": {"m1": 0, "pmf": 0},
              "analogue": {"m1": 0, "pmf": 0, "groundhog": True}}
    pf_rows = []
    for loc, s in pf_samples.items():
        fips = n2f[loc]
        rows = quantile_rows(s, fips, asof, horizons=hzs)
        counts["pf"]["m1"] += any(r["horizon"] == -1 for r in rows)
        if pmf:
            probs = OPT.pf_rate_change(s, reported.get(fips),
                                       pops.get(loc, 0.0), pf_k.get(loc, 0))
            rows += rate_change_rows(probs, fips, asof)
            counts["pf"]["pmf"] += bool(probs)
        pf_rows += rows
    now = an_engine.nowcast(spec) if an_q else {}
    an_rows = []
    for loc, q in an_q.items():
        fips = n2f[loc]
        info = now.get(loc)
        qs = dict(q)
        if minus1 and info and info.get("q"):
            # the as-of week under the anchor key, floored like the rest
            qs[ORIGIN] = floor_quantiles({ORIGIN: info["q"]},
                                         **floor_kw)[ORIGIN]
        rows = rows_from_quantiles(qs, fips, asof, horizons=hzs)
        counts["analogue"]["m1"] += any(r["horizon"] == -1 for r in rows)
        if pmf:
            probs = OPT.groundhog_rate_change(q, info, reported.get(fips),
                                              asof, pops.get(loc, 0.0))
            rows += rate_change_rows(probs, fips, asof)
            counts["analogue"]["pmf"] += bool(probs)
        an_rows += rows
    return pf_rows, an_rows, counts


def _run_all(spec: RunSpec) -> None:
    """The competition path: engines in ascending cost, then the two
    standalone submissions (no blend; each under its own hub identity,
    submit.MODEL_ABBR), scoring and the weekly report. One workroot, one
    ledger row."""
    import pandas as pd
    from app.core import scoring
    from app.core.engines import analogue as an_engine
    from app.core.engines import pf as pf_engine
    from app.core.submit import (hub_model_id, quantile_rows,
                                 rows_from_quantiles, write_submission)

    import time as _time
    ledger = Ledger()
    run_id = None
    outcome = {}
    guard = _sleep_guard()          # macOS: no idle sleep mid-run
    # the route starts the clock on click; direct calls (scripts, tests) here
    if not _status.get("started_utc"):
        _status["started_utc"] = _time.time()
    t_start = float(_status["started_utc"])
    # the same scope wording as the route's queued label
    from app.ui.routes.forecast import _scope_label
    _status["run_label"] = (
        f"{spec.forecast_date} · {_scope_label(spec.locations)}")
    # also set by the route; here so direct calls are described too
    _status["settings"] = spec_settings(spec)
    try:
        # setup INSIDE the try so a failed insert/lease releases the claim;
        # the row's engine_versions (not this process's) is "Produced by"
        run_id = ledger.open_run(
            spec, Path("pending"),
            versions._engine_versions_for_ledger("pf,analogue"))
        workroot = lease_workroot(run_id)
        ledger.set_workroot(run_id, workroot)   # the row must name the real one
        if _name_workroot(workroot, f"all:{run_id}"):
            # Stop pressed while starting: end as stopped, nothing fitted
            raise pf_engine.RunStopped("stopped before fitting")
        # a run with modified model settings records them beside its files
        # (knobs.json; none for a shipped run, whose files are unchanged)
        _knobs_mod = _knobs.modified(spec)
        if _knobs_mod:
            _knobs.write_record(workroot / "knobs.json", spec)
            outcome["knobs"] = _knobs.summary(_knobs.record_of(spec),
                                              _knobs.override_reason(spec))
        # the output-floor knob: passed only when set (shipped calls unchanged)
        _lam = _knobs.value_of(spec.extra, "output.floor_lam")
        _fkw = {} if _lam is None else {"lam": float(_lam)}
        # 1. PF (primary); absent on Tier-A machines, where the run proceeds
        # with the analogue (see _pf_engine_state)
        fails = {}
        # the observed file every step reads, resolved ONCE (the dated
        # vintage, or the live target file for a real-time run) and recorded
        # with its sha256 and newest week
        # (a missing file is recorded here; each engine then refuses it
        # loudly in its own words, as before)
        from app.core import data as _data
        try:
            src_path, src_kind = _data.spec_source(spec)
            outcome["data_source"] = _data.source_record(src_path, src_kind)
            # a copy in the workroot, pinned for the run: Update data may
            # rewrite the hub while the filter runs, and every later step
            # (Groundhog, Oracle step, optional rows) must read what the
            # record names
            _snap = workroot / "observed" / Path(src_path).name
            _snap.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src_path, _snap)
            src_path = _snap
            _data.pin_source(spec, src_path, src_kind)
        except OSError as e:
            src_path, src_kind = None, None
            outcome["data_source_error"] = str(e)[:300]
        # observed admissions per location (vintage-true): floor, report, run page
        obs = {}
        try:
            from flubnf.settings import LOCATIONS as _LOCCSV
            _lo = pd.read_csv(_LOCCSV, dtype=str)
            _n2fo = dict(zip(_lo.location_name, _lo.location.str.zfill(2)))
            tdf = pd.read_csv(src_path if src_path is not None
                              else _data.vintage_path(spec.forecast_date),
                              dtype={"location": str})
            tdf = tdf[tdf["date"].astype(str).str[:10]
                      <= str(spec.forecast_date)].copy()
            tdf["location"] = tdf["location"].str.zfill(2)
            # nowcast rule: the engines treat the same-day row as unreported,
            # so obs must not see it (else cards announce a spurious surge)
            if getattr(spec, "drop_same_day", False):
                tdf = tdf[tdf["date"].astype(str).str[:10]
                          != str(spec.forecast_date)]
            import numpy as _npo
            for loc in spec.locations:
                g = tdf[tdf.location == _n2fo.get(loc, "")].sort_values("date").tail(15)
                obs[loc] = [[str(r.date)[:10], float(r.value)]
                            for r in g.itertuples()
                            if _npo.isfinite(r.value)]
        except Exception:
            pass
        pf_samples = {}
        params: dict = {}     # fitted-parameter medians per member/location
        pf_wanted = spec.engine in ("all", "pf")
        pf_state = _pf_engine_state()
        # A broken install is refused, not skipped: an analogue-only ship
        # would hide the fault. The reason is recorded so the run page names
        # the path and the fix.
        if pf_wanted and pf_state == "broken":
            msg = pf_engine.engine_missing_message()
            outcome["pf_engine_broken"] = msg
            raise RuntimeError(msg)
        if pf_wanted and pf_state == "ready":
            _phase("materializing models (BNG network generation)")
            pf_engine.prepare(spec, workroot)
            _phase(f"filtering {len(spec.locations)} location(s) × "
                   f"{spec.replicates} replicate(s)")
            status = pf_engine.execute(workroot)
            fails = {k: v for k, v in status.items() if v != "ok"}
            outcome["pf_cells"] = len(status)
            outcome["pf_failures"] = fails
            # fit origins moved back by an unreported newest week, or
            # abstentions (prepare's notes; absent on a shipped run)
            _pf_notes = pf_engine.read_anchor_notes(workroot)
            if _pf_notes:
                outcome["pf_anchor_notes"] = _pf_notes
            pf_samples = pf_engine.collect(workroot)
            # collect() records a torn trajectory in pf_status.json after
            # execute's status was read: carry it into the run record, so
            # a location missing from the file is named with its reason
            try:
                import json as _jcf
                _st = _jcf.loads((workroot / "pf_status.json").read_text())
                fails.update({k: str(v) for k, v in _st.items()
                              if v != "ok" and k not in fails})
                outcome["pf_failures"] = fails
            except Exception:
                pass
            # the Oracle step (app/core/oracle.py), before anything downstream
            # and before the floor. oracle = none is research: file withheld
            # in step 4, oracle.json records the step did not run.
            from app.core import oracle as oracle_mod
            if oracle_mod.wanted(spec.extra):
                _phase("the Oracle step: the donor bank from the vintage")
                pf_raw = pf_samples
                pf_samples, oprov = oracle_mod.apply_week(
                    pf_raw, spec.forecast_date, workroot, extra=spec.extra,
                    vintage=src_path, source_kind=src_kind,
                    weeks_to_drop=int(spec.weeks_to_drop or 0),
                    drop_same_day=bool(getattr(spec, "drop_same_day", False)))
                outcome["oracle"] = oprov["bank"]["label"]
                try:
                    oracle_mod.write_filter_record(workroot, spec.forecast_date,
                                                   pf_raw)
                except Exception:
                    pass      # the kept copy is a courtesy; the member stands
            else:
                oracle_mod.write_not_applied(
                    workroot, spec.forecast_date,
                    "the run asked for the plain filter (oracle = none)")
                outcome["oracle"] = "none"
            try:
                params["pf"] = _harvest_params(workroot)
            except Exception:
                pass
            # output floor: no cell leaves as a point mass (see app/core/floor.py)
            from app.core.floor import floor_samples
            pf_samples = {loc: floor_samples(
                              s, loc, spec.forecast_date,
                              recent=[v for _, v in obs.get(loc, [])],
                              **_fkw)
                          for loc, s in pf_samples.items()}
        else:
            outcome["pf_skipped"] = ("analogue-only run"
                                     if spec.engine == "analogue"
                                     else "engine venv not installed (Tier A)")
            (workroot / "cells.json").write_text("[]")
        # 1b. RESEARCH third member: the two-strain SIHRS (members=3, no UI
        # control), in a pf2s subdir of the same workroot (one row, one archive)
        pf2s_samples = {}
        if ((spec.extra or {}).get("members") == 3
                and pf_wanted and pf_state == "ready"):
            from dataclasses import replace as _dc_replace
            spec2s = _dc_replace(spec, extra={**(spec.extra or {}),
                                              "variant": "2strain"})
            w2 = workroot / "pf2s"
            w2.mkdir()
            _phase("materializing the two-strain member (BNG network generation)")
            pf_engine.prepare(spec2s, w2)
            _phase(f"fitting the two-strain member: {len(spec.locations)} "
                   f"location(s) × {spec.replicates} replicate(s)")
            status2s = pf_engine.execute(w2)
            fails2s = {k: v for k, v in status2s.items() if v != "ok"}
            outcome["pf2s_cells"] = len(status2s)
            outcome["pf2s_failures"] = fails2s
            fails.update({f"pf2s:{k}": v for k, v in fails2s.items()})
            pf2s_samples = pf_engine.collect(w2)
            try:
                params["pf2s"] = _harvest_params(w2)
            except Exception:
                pass
            from app.core.floor import floor_samples as _floor2s
            pf2s_samples = {loc: _floor2s(
                                s, loc, spec.forecast_date,
                                recent=[v for _, v in obs.get(loc, [])],
                                **_fkw)
                            for loc, s in pf2s_samples.items()}
        # 2. the Groundhog: calendar analogue + the aux donors _run_extra put
        # in spec.extra (none = research bare analogue). Always runs (instant);
        # its FILE is written only when the run asked for it.
        _phase("consulting the Groundhog")
        from app.core.floor import floor_quantiles
        # anchors moved back by an unreported newest week, or abstentions,
        # are recorded per location (the engine's notes); the missing-data
        # rules (app/core/missing.py) are recorded only when one is set, so
        # a shipped run's outcome is unchanged
        import inspect as _inspect
        from app.core import missing as _missing
        _rules = _missing.rules_of(spec.extra)
        _gh_flags: list = []
        an_notes: dict = {}
        _an_kw = ({"notes": an_notes} if "notes" in
                  _inspect.signature(an_engine.run).parameters else {})
        if _rules:
            _an_kw["flags"] = _gh_flags
        an_q = {loc: floor_quantiles(q, **_fkw)
                for loc, q in an_engine.run(spec, **_an_kw).items()}
        if an_notes:
            outcome["analogue_anchor_notes"] = an_notes
        if _rules:
            _pf_flags = []
            try:
                import json as _jfl
                for c in _jfl.loads((workroot / "cells.json").read_text()):
                    if c.get("replicate") == 0:
                        _pf_flags += [{"location": c["location"], **r}
                                      for r in c.get("data_flags") or ()]
            except Exception:
                pass
            outcome["data_flags"] = {"analogue": _gh_flags, "pf": _pf_flags}
        outcome["analogue_aux"] = str(
            (spec.extra or {}).get("analogue_aux") or "")
        # 3. no blend: each member is its own submission; PF failures are just
        # absent from its file (the row's failure count names them)
        _phase("writing submissions")
        # 4. submissions (identity in the path)
        locs = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
        n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
        subs = {}
        # model keys are submit.MODEL_ABBR's (model-output/<team>-<model>/);
        # the writer refuses a file date its rows do not carry
        from app.core.runs import is_research as _is_research
        _research = _is_research(spec)
        # modified model settings without the override: every file carries
        # the non-hub name (<hub id>-modified), so it can never pass for the
        # registered model; the app exports, the operator submits
        _suffix = "" if _knobs.hub_names(spec) else _knobs.MODIFIED_SUFFIX

        def _withhold(reason: str) -> None:
            # one outcome key, every withheld file named in it
            prior = outcome.get("submission_withheld")
            outcome["submission_withheld"] = (f"{prior}; {reason}" if prior
                                              else reason)
        # the optional hub rows (knobs output.horizon_minus1 and
        # output.rate_change_pmf, app/core/optional_outputs.py); both off by
        # default, and then the rows below are exactly the shipped ones
        _m1 = _knobs.optional_output(spec, "output.horizon_minus1")
        _pmf = _knobs.optional_output(spec, "output.rate_change_pmf")
        if _m1 or _pmf:
            pf_rows, an_rows, _opt_counts = _optional_rows(
                spec, workroot, pf_samples, an_q, locs, n2f, _m1, _pmf, _fkw,
                vintage=src_path)
            from app.core.optional_outputs import notes as _opt_notes
            outcome["optional_rows"] = _opt_notes(
                {hub_model_id(m) + _suffix: c
                 for m, c in _opt_counts.items()}, _m1, _pmf)
        else:
            pf_rows = [r for loc, s in pf_samples.items()
                       for r in quantile_rows(s, n2f[loc], spec.forecast_date)]
            an_rows = [r for loc, q in an_q.items()
                       for r in rows_from_quantiles(q, n2f[loc],
                                                    spec.forecast_date)]
        for model, rows in (("pf", pf_rows), ("analogue", an_rows)):
            if not rows:
                continue
            if model == "analogue" and spec.engine == "pf":
                # Oracle SIHRS-only run: Groundhog consulted for pages only
                continue
            if model == "analogue" and not (spec.extra or {}).get("aux_pools"):
                # bare analogue is research: no hub-named file (audit rr-1)
                _withhold(
                    "Groundhog: the run carried no auxiliary donors, so "
                    "this is the bare calendar analogue and does not ship "
                    "under the Groundhog's hub name")
                continue
            if model == "pf" and outcome.get("oracle") == "none":
                # plain filter is research too: no hub-named file
                _withhold(
                    "Oracle SIHRS: the run asked for the plain filter "
                    "(oracle = none), a research configuration that does "
                    "not ship under the Oracle SIHRS hub name")
                continue
            # contained per model: a writer refusal (rows the hub would
            # bounce) costs that file, never the run; recorded for the run page
            # a location whose rows alone fail the checks is dropped and
            # the file written with the rest (recorded by name, per file)
            _dropped: dict = {}
            try:
                subs[hub_model_id(model) + _suffix] = str(write_submission(
                    rows, model, spec.forecast_date,
                    workroot / "submission",
                    **({"suffix": _suffix} if _suffix else {}),
                    dropped=_dropped))
            except Exception as e:
                outcome.setdefault("submission_errors", {})[
                    hub_model_id(model) + _suffix] = str(e)[:400]
            if _dropped:
                _f2n = {f: n for n, f in n2f.items()}
                outcome.setdefault("submission_dropped", {})[
                    hub_model_id(model) + _suffix] = {
                        _f2n.get(f, f): why for f, why in _dropped.items()}
        outcome["submissions"] = subs
        if "optional_rows" in outcome:
            outcome["optional_rows"] = {k: v for k, v in
                                        outcome["optional_rows"].items()
                                        if k in subs}
        # 5. retrospective scoring (once truth exists); contained, like 5b
        df = pd.DataFrame()
        try:
            truth, name2fips = scoring.load_truth()
            df = scoring.score_samples(pf_samples, spec.forecast_date,
                                       name2fips, truth)
            # stamp the truth source now: a later load_truth elsewhere could
            # swap the module global before the WIS card renders
            df.attrs["truth_source"] = scoring.TRUTH_SOURCE
            if not df.empty:
                # POOLED_INCLUDES_US gate (us_national.pooled_frame): the fitted
                # US cell is the sum of the others and would dominate
                from app.core.us_national import pooled_frame
                pdf = pooled_frame(df)
                if not pdf.empty:
                    outcome["pf_relwis"] = round(
                        float(pdf["wis"].sum() / pdf["base_wis"].sum()), 3)
                    outcome["pf_relwis_cells"] = int(len(pdf))
            df.to_json(workroot / "scores_pf.json")
            # the Groundhog, same formula and gate
            from app.core.us_national import pooled_frame as _pooled
            for mname, qs in (("analogue", an_q),):
                try:
                    mdf = scoring.score_quantiles(qs or {}, spec.forecast_date,
                                                  name2fips, truth)
                    if not mdf.empty:
                        mp = _pooled(mdf)
                        if not mp.empty:
                            outcome[f"{mname}_relwis"] = round(
                                float(mp["wis"].sum() / mp["base_wis"].sum()), 3)
                            outcome[f"{mname}_relwis_cells"] = int(len(mp))
                        mdf.to_json(workroot / f"scores_{mname}.json")
                except Exception as e:
                    outcome[f"{mname}_score_error"] = str(e)[:200]
        except Exception as e:
            outcome["score_error"] = str(e)[:200]
        # 5b. weekly report from its inputs bundle; contained
        try:
            _write_weekly_report(spec, workroot, pf_samples, obs, df, locs,
                                 n2f, _time.time() - t_start, outcome,
                                 an_q=an_q)
        except Exception as e:
            outcome["report_error"] = str(e)[:200]
        # 6. results index for the run page
        import json as _json
        import numpy as _np
        from app.core import horizons as _hz
        def _qs_from_samples(s):
            out = {}
            for h in _hz.HORIZONS:
                a = _np.asarray(s.get(h, []), float); a = a[_np.isfinite(a)]
                if a.size:
                    out[h] = {q: float(_np.quantile(a, float(q)))
                              for q in ("0.1", "0.25", "0.5", "0.75", "0.9")}
            return out
        def _qs_from_q(qd):
            return {h: {q: qd[h][float(q)]
                        for q in ("0.1", "0.25", "0.5", "0.75", "0.9")}
                    for h in qd}
        from app.core.horizons import models_to_stored as _hz_stored
        import os as _os
        _tmp = workroot / "results.json.tmp"
        _tmp.write_text(_json.dumps({
            "spec": spec.to_json(), "forecast_date": spec.forecast_date,
            "research": _research,
            # bank as stream@digest8, or "none"; full record in oracle.json
            "oracle": outcome.get("oracle"),
            # modified model settings only (a shipped results.json is unchanged)
            **({"knobs": outcome["knobs"]} if "knobs" in outcome else {}),
            "observed": obs,
            "params": params,
            # STORED horizon convention (old workroots use it too); readers
            # go through horizons.models_to_canonical
            "models": _hz_stored({
                "pf": {loc: _qs_from_samples(s) for loc, s in pf_samples.items()},
                "analogue": {loc: _qs_from_q(q) for loc, q in an_q.items()},
                **({"pf2s": {loc: _qs_from_samples(s)
                             for loc, s in pf2s_samples.items()}}
                   if pf2s_samples else {}),
            })}))
        _os.replace(_tmp, workroot / "results.json")   # readers never see a half-write
        # 7. forecast archive: one folder per date, latest run wins; only the
        # shipped product's full run archives (audit rr-1)
        if _research:
            outcome["archived"] = "skipped: research run"
        elif _suffix:
            outcome["archived"] = ("skipped: modified model settings (files "
                                   "carry the non-hub name)")
        elif spec.engine in ("analogue", "pf"):
            outcome["archived"] = (f"skipped: {'analogue' if spec.engine == 'analogue' else 'Oracle SIHRS'}"
                                   "-only run is not the date's forecast")
        else:
            # no downgrade: only a complete run (finished ok, both files
            # written whole, no submission error) replaces an archived one
            _complete = (not fails
                         and not outcome.get("submission_errors")
                         and not outcome.get("submission_withheld")
                         and not outcome.get("submission_dropped")
                         and {hub_model_id("pf"), hub_model_id("analogue")}
                         <= set(subs))
            try:
                outcome["archived"] = (
                    _archive_run(workroot, spec.forecast_date) if _complete
                    else _archive_run(workroot, spec.forecast_date,
                                      complete=False))
            except Exception as e:
                outcome["archive_error"] = str(e)[:200]
        # the pipeline completed: fit failures make it "partial" (the chips
        # count them); "failed"/"error" are reserved for runs that died
        ledger.close_run(run_id, "partial" if fails else "ok", outcome)
        # prune per-cell fit trees once the record is on disk; a run with
        # failures keeps them as evidence. Never fatal.
        if not fails:
            try:
                from app.core import reclaim
                reclaim.prune_workroot(workroot)
            except Exception:
                pass
        _status["log"].append(
            f"{run_id}: pf {len(pf_samples)} loc, groundhog {len(an_q)}"
            + (f", pf2s {len(pf2s_samples)}" if pf2s_samples else "")
            + "".join(f", {m} relWIS {outcome[k]}" for m, k in
                      (("pf", "pf_relwis"), ("groundhog", "analogue_relwis"))
                      if k in outcome))
    except Exception as e:
        from app.core.engines.pf import RunStopped
        if run_id is None:
            _status["log"].append(f"run setup failed: {str(e)[:200]}")
        elif isinstance(e, RunStopped):
            ledger.close_run(run_id, "stopped", outcome)
            _status["log"].append("run stopped by user")
        else:
            ledger.close_run(run_id, "error", {"error": str(e)[:300], **outcome})
            _status["log"].append(f"{run_id}: ERROR {e}")
    finally:
        try:
            from app.core import data as _data_fin
            _data_fin.unpin_source(spec)
        except Exception:
            pass
        if guard is not None:
            try:
                guard.terminate()
            except Exception:
                pass
        _invalidate_scans()
        _status["running"] = None
        _status.pop("stop_requested", None)
        _status["phase"] = ""
        _status["settings"] = []
        _status["workroot"] = None
        _status["run_label"] = ""
        _status["expected_total"] = None
        _status["started_utc"] = None


# === Forecast archive ===
def _archive_run(workroot: Path, forecast_date: str,
                 complete: bool = True) -> str:
    """Copy the run's deliverables to app/state/archive/<forecast_date>/,
    replacing any earlier archive for the date. Built beside, then swapped:
    a crash mid-copy costs this attempt, never the existing record.

    Never a downgrade (app/core/archive_record.py): an archive marked
    submitted is never replaced, and an incomplete run (`complete` False)
    does not replace an archive that holds a complete one. Then nothing
    is copied, the run's files stay in its own folder, and the answer is
    "kept: <why>". The archive records which run it holds (archive.json)."""
    import os
    import shutil
    from app.core import archive_record as _ar
    from app.core.report_v2 import BUNDLE_NAME
    from app.core.runs import APP_STATE
    arch = APP_STATE / "archive" / forecast_date
    build = arch.with_name(arch.name + ".building")
    old = arch.with_name(arch.name + ".old")
    arch.parent.mkdir(parents=True, exist_ok=True)
    if build.exists():          # an interrupted attempt's half-built tree
        shutil.rmtree(build)
    if old.exists():
        if arch.exists():       # both present: the old copy is surplus
            shutil.rmtree(old)
        else:                   # crashed between the two renames below:
            os.replace(old, arch)   # the parked previous archive comes back
    keep = _ar.keep_reason(arch, complete)
    if keep:
        return f"kept: {keep}"
    build.mkdir(parents=True)
    try:
        # the report travels with its inputs bundle (rebuildable)
        # knobs.json exists only for a modified run (by override)
        for name in ("results.json", "report.html", BUNDLE_NAME, "knobs.json"):
            if (workroot / name).is_file():
                shutil.copy2(workroot / name, build / name)
        if (workroot / "submission").is_dir():
            shutil.copytree(workroot / "submission", build / "submission")
        _ar.write_record(build, Path(workroot).name, complete)
    except BaseException:
        shutil.rmtree(build, ignore_errors=True)
        raise
    if arch.exists():
        os.replace(arch, old)   # park the previous archive
    os.replace(build, arch)
    if old.exists():
        shutil.rmtree(old, ignore_errors=True)
    return str(arch)
