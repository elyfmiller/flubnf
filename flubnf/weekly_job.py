"""One-shot weekly competition workflow (LEGACY, DE era).

SCOPE: this is the legacy one-shot built on PyBNF differential evolution,
kept for the CLI loop. It is superseded for the live season: the shipped
competition engine is the sequential particle filter, driven from the
console (app/core/runs.py). Do not prepare a submission week from here.

Threads together everything needed for a single FluSight submission day:

    1. Fetch latest CDC data (or use a provided CSV).
    2. Build / refresh per-state .exp from that CSV.
    3. For each state:
       a. Read previous-run results (if present) and analyze.
       b. Apply bounds expansion + step-add recommendations.
       c. Fit (PyBNF DE) with state-adaptive bounds.
       d. Generate FluSight quantile forecasts.
    4. Aggregate into one submission CSV.

The function returns a `WeeklyJobResult` capturing every step's status.
The UI / CLI can call this end-to-end with a single click; if anything
fails on one state, the others continue.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Callable, Iterable, Optional

import numpy as np
import pandas as pd
import pymmwr as pm

from . import analysis, bngl_files, conf_files, exp_files, fetch as fetch_mod
from .bounds_init import adaptive_initial_bounds, max_steps_for_state
from .config import FluBNFConfig
from .conf_files import FreeParam
from .constants import JURISDICTIONS, STATE_TO_ABBREV
from .paths import WorkspacePaths
from .pybnf_engine import PyBNFOptions, fit_with_pybnf
from .quantiles import quantile_forecast
from .results import read_de_results
from .session import (StateSession, load_session, record_step, save_session)
from .simulate import predict_weekly
from .submit import StateForecast, build_submission_dataframe, write_submission

log = logging.getLogger(__name__)


@dataclass
class StateResult:
    state: str
    status: str                 # "ok", "fit-failed", "no-data", "skipped"
    best_obj: Optional[float] = None
    n_steps: int = 1
    bounds_changed: list[str] = field(default_factory=list)
    bounds_added: list[str] = field(default_factory=list)
    notes: str = ""
    fringe_cases: list[str] = field(default_factory=list)


@dataclass
class WeeklyJobResult:
    reference_date: date
    csv_source: Optional[Path]
    submission_csv: Optional[Path] = None
    states: list[StateResult] = field(default_factory=list)

    @property
    def n_ok(self) -> int:
        return sum(1 for s in self.states if s.status == "ok")


def run_weekly_job(
    config: FluBNFConfig,
    paths: WorkspacePaths,
    *,
    reference_date: Optional[date] = None,
    csv: Optional[Path] = None,
    states: Iterable[str] = JURISDICTIONS,
    method: str = "am",
    popsize: int = 1,
    max_iter: int = 800,
    burn_in: int = 150,
    adaptive: int = 150,
    parallel: int = 1,
    resume: bool = True,
    on_progress: Optional[Callable[[str, str], None]] = None,
) -> WeeklyJobResult:
    """End-to-end: fetch (optional) → exp → fit per state → submission CSV.

    Args:
        config / paths:    FluBNF config + workspace.
        reference_date:    FluSight submission Saturday; defaults to upcoming.
        csv:               Override the data source (else uses latest cache).
        states:            Subset of jurisdictions to forecast.
        popsize/max_iter:  DE settings per state.
        parallel:          Number of concurrent PyBNF subprocesses (states fit
                           in parallel; each PyBNF run is single-threaded here).
        on_progress:       Optional callback(state, status) for UI updates.
    """
    paths.ensure()

    # 1. Fetch (or use override).
    if csv is None:
        try:
            res = fetch_mod.fetch_cdc_data(config, force=False)
            csv = res.csv_path
        except Exception as e:
            log.error("fetch failed: %s", e)
            return WeeklyJobResult(
                reference_date=reference_date or date.today(),
                csv_source=None,
            )

    # 2. .exp files for all requested states.
    exp_results = exp_files.generate_exp_files(csv, paths, config, states=states)
    obs_by_state = {
        r.state: pd.read_csv(r.path, sep="\t")["H_weekly"].to_numpy(dtype=float)
        for r in exp_results if r.n_weeks > 0
    }
    if not obs_by_state:
        log.error("no states have data; aborting")
        return WeeklyJobResult(
            reference_date=reference_date or date.today(),
            csv_source=csv,
        )

    # 3. Per-state fit. Capture FitResult for quantile gen.
    fit_results: dict = {}
    state_records: list[StateResult] = []

    # Resume support: figure out which states already have a fresh fit
    # for this reference_date (so a re-run picks up where it left off).
    ref_iso = (reference_date.isoformat()
               if reference_date is not None else None)

    def _state_already_done(state: str) -> bool:
        if not resume:
            return False
        sess = load_session(paths.root, state)
        if sess is None or sess.last_reference_date != ref_iso:
            return False
        # Must also have a traj_noise (AMCMC) or sorted_params_final (DE).
        results_dir = paths.results_for(state) / "Results"
        if method == "am":
            return any((results_dir / "A_MCMC" / "Runs").glob(
                "traj_noise_*_chain_0.txt"
            )) if (results_dir / "A_MCMC" / "Runs").exists() else False
        return (results_dir / "sorted_params_final.txt").exists()

    def _fit_one(state: str):
        obs = obs_by_state.get(state)
        if obs is None or len(obs) == 0:
            return state, None, None, StateResult(state=state, status="no-data")

        # Resume: if this state's fit is already fresh for this
        # reference_date, skip refit but still load fit + session so
        # quantile gen runs.
        if _state_already_done(state):
            sess = load_session(paths.root, state)
            log.info("[%s] resume: reusing existing fit for %s", state, ref_iso)
            # We need a FitResult to feed quantile_forecast on the non-AM path.
            # For AM path quantile gen reads traj_noise directly; pass None.
            from .results import read_de_results
            de = read_de_results(paths.results_for(state), state)
            fit_obj = None
            if de is not None and not de.population.empty:
                from .fitting import FitResult
                pop = de.population[list(de.param_names)].to_numpy(dtype=float)
                obj = de.population["Obj"].to_numpy(dtype=float)
                import numpy as _np
                fit_obj = FitResult(
                    state=state, param_names=tuple(de.param_names),
                    population=pop, objectives=obj,
                    best_idx=int(_np.argmin(obj)),
                )
            return state, fit_obj, sess, StateResult(
                state=state, status="ok",
                best_obj=fit_obj.best_obj if fit_obj else None,
                n_steps=sess.n_steps if sess else 1,
                notes="resumed (cached fit)",
            )

        # Load any persisted session from prior weeks; otherwise start
        # fresh. For a fresh start, blend the data-driven adaptive bounds
        # with any historical priors we have for this state (typically
        # populated by retrospective backtests of previous seasons).
        sess = load_session(paths.root, state)
        if sess is None or not sess.bounds:
            initial = adaptive_initial_bounds(obs)
            try:
                from .historical_priors import (load_history,
                                                 informed_initial_bounds)
                hp_dir = paths.root.parent.parent / "data" / "historical_priors"
                hist = load_history(hp_dir, state) if hp_dir.exists() else None
                if hist and hist.seasons:
                    initial = informed_initial_bounds(
                        initial, hist, blend_weight=0.4,
                    )
                    log.info("[%s] used %d season(s) of historical priors",
                             state, len(hist.seasons))
            except Exception as e:
                log.warning("historical priors unavailable for %s: %s", state, e)
            sess = StateSession(
                state=state,
                bounds=initial,
                n_steps=1,
            )

        # Analyze previous run (if its results dir exists) and apply.
        bounds_changed, bounds_added = _analyze_and_adapt(
            state, obs, sess, paths,
        )

        # Always: rescan mult ceiling against the latest peak.
        new_init = adaptive_initial_bounds(obs, base=sess.bounds)
        for i, fp in enumerate(sess.bounds):
            if fp.name == "mult__FREE" and new_init[i].high > fp.high * 1.01:
                sess.bounds[i] = new_init[i]
                if "mult__FREE" not in bounds_changed:
                    bounds_changed.append("mult__FREE")

        try:
            fit = fit_with_pybnf(
                state, obs, sess.bounds, paths, config,
                n_steps=sess.n_steps,
                options=PyBNFOptions(
                    method=method, popsize=popsize, max_iter=max_iter,
                    burn_in=burn_in, adaptive=adaptive,
                ),
                forecast_horizon=4 if method == "am" else 0,
            )
        except Exception as e:
            log.exception("fit %s failed", state)
            return state, None, sess, StateResult(
                state=state, status="fit-failed", notes=str(e)[:80],
                bounds_changed=bounds_changed, bounds_added=bounds_added,
            )
        if fit is None:
            return state, None, sess, StateResult(
                state=state, status="fit-failed",
                bounds_changed=bounds_changed, bounds_added=bounds_added,
            )

        # Post-fit diagnostics + REACTIVE RETRY:
        # - expand_bound actions update the session for next week.
        # - refit_new_seed / refit_more_iters trigger a single in-place
        #   retry with adjusted settings (capped to one extra fit so
        #   we don't loop forever).
        if method == "am":
            from .diagnostics import compute_diagnostics, react_to_diagnostics
            try:
                report = compute_diagnostics(
                    paths.results_for(state), state, bounds=sess.bounds,
                )
                if report is not None:
                    actions = react_to_diagnostics(report)
                    notes_parts = []
                    should_refit = False
                    new_max_iter = max_iter
                    new_seed_offset = 0
                    for a in actions:
                        if a.kind == "expand_bound" and a.param:
                            for i, fp in enumerate(sess.bounds):
                                if fp.name == a.param:
                                    rng = fp.high - fp.low
                                    if a.factor > 0:
                                        sess.bounds[i] = FreeParam(
                                            fp.name, fp.low,
                                            fp.high + abs(a.factor) * rng,
                                        )
                                    else:
                                        new_lo = max(0.0,
                                                     fp.low - abs(a.factor) * rng)
                                        sess.bounds[i] = FreeParam(
                                            fp.name, new_lo, fp.high,
                                        )
                                    notes_parts.append(
                                        f"diag:expanded {a.param}"
                                    )
                                    break
                        elif a.kind == "refit_more_iters":
                            new_max_iter = int(max_iter * 2)
                            should_refit = True
                            notes_parts.append(
                                f"diag:retry max_iter={new_max_iter}"
                            )
                        elif a.kind == "refit_new_seed":
                            # Bump the seed by 1 to break out of stuck modes.
                            new_seed_offset = 1
                            should_refit = True
                            notes_parts.append("diag:retry new seed")
                    if notes_parts:
                        log.info("[%s] %s", state, "; ".join(notes_parts))
                    if should_refit:
                        # One-shot reactive retry. Cap at one to avoid
                        # runaway compute on degenerate states.
                        try:
                            log.info("[%s] reactive refit triggered", state)
                            retry_fit = fit_with_pybnf(
                                state, obs, sess.bounds, paths, config,
                                n_steps=sess.n_steps,
                                options=PyBNFOptions(
                                    method=method, popsize=popsize + new_seed_offset,
                                    max_iter=new_max_iter,
                                    burn_in=burn_in, adaptive=adaptive,
                                ),
                                forecast_horizon=4 if method == "am" else 0,
                            )
                            if retry_fit is not None:
                                fit = retry_fit
                                notes_parts.append("diag:retry-ok")
                            else:
                                notes_parts.append("diag:retry-failed")
                        except Exception as e:
                            log.warning(
                                "reactive refit for %s failed: %s",
                                state, e,
                            )
                            notes_parts.append(f"diag:retry-err {e}")
            except Exception as e:
                log.warning("diagnostics failed for %s: %s", state, e)

        # Fringe-case evaluation — surface known failure modes per state.
        try:
            from .fringe_cases import triggered_cases
            fired = triggered_cases(obs, sess)
            fringe_names = [m.case_name for m in fired]
            if fired:
                log.info("[%s] fringe cases fired: %s", state, fringe_names)
        except Exception as e:
            log.warning("fringe case evaluation failed for %s: %s", state, e)
            fringe_names = []

        return state, fit, sess, StateResult(
            state=state, status="ok", best_obj=fit.best_obj,
            n_steps=sess.n_steps,
            bounds_changed=bounds_changed, bounds_added=bounds_added,
            fringe_cases=fringe_names,
        )

    if reference_date is None:
        reference_date = _default_reference_date()

    def _post_fit(s, fit, sess, rec):
        if fit is not None:
            fit_results[s] = fit
        if sess is not None:
            record_step(
                sess, reference_date=reference_date,
                bounds_changed=rec.bounds_changed,
                bounds_added=rec.bounds_added,
                best_obj=rec.best_obj,
            )
            save_session(paths.root, sess)
        state_records.append(rec)
        if on_progress:
            on_progress(s, rec.status)

    if parallel <= 1:
        for s in states:
            if s not in obs_by_state:
                state_records.append(StateResult(state=s, status="no-data"))
                continue
            if on_progress:
                on_progress(s, "fitting")
            _, fit, sess, rec = _fit_one(s)
            _post_fit(s, fit, sess, rec)
    else:
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futures = {
                pool.submit(_fit_one, s): s for s in states if s in obs_by_state
            }
            for fut in as_completed(futures):
                s, fit, sess, rec = fut.result()
                _post_fit(s, fit, sess, rec)

    # 4. Quantile forecasts + submission CSV.
    # Load (or initialize) the calibration tracker for this workspace.
    from .calibration import CalibrationTracker, apply_calibration
    cal_path = paths.root / "calibration.json"
    tracker = CalibrationTracker.load(cal_path)
    # Ingest realized actuals from previous submissions for which the
    # observed series has now caught up — this is the closed-loop step
    # that builds calibration over time.
    _ingest_realized_actuals(paths, tracker, obs_by_state, config)

    # Act on accumulated bias / coverage signals: tighten `mult__FREE` upper
    # on chronic over-prediction; widen the calibration max_factor cap on
    # chronic under-coverage. These mutations persist via save_session so
    # they take effect next week (and on the current forecast for the
    # max_factor knob, since apply_calibration reads it below).
    from . import decomp_act as _da
    for s in states:
        sess = load_session(paths.root, s)
        if sess is None:
            continue
        actions = _da.apply_to_session(tracker, sess)
        if actions:
            save_session(paths.root, sess)
            log.info("[%s] decomp-act: %s", s, "; ".join(actions.notes))

    forecasts = []
    for state, fit in fit_results.items():
        obs = obs_by_state[state]
        # Read per-state tuning (calibrated hyperparameters persisted in
        # the session). Falls back to defaults when not specified.
        sess = load_session(paths.root, state)
        tuning = sess.tuning if sess else {}
        slope_blend = float(tuning.get("slope_blend", 0.0))
        anchor_lookback = int(tuning.get("anchor_lookback", 3))
        phase_aware = bool(tuning.get("phase_aware", True))
        calibration_max_factor = float(tuning.get("calibration_max_factor", 1.5))
        try:
            if method == "am":
                from .amcmc import (read_traj_noise,
                                    quantile_forecast_from_amcmc)
                traj = read_traj_noise(paths.results_for(state), state)
                if traj is None:
                    raise RuntimeError("no traj_noise produced by AMCMC")
                qf = quantile_forecast_from_amcmc(
                    traj, n_observed=len(obs), horizons=[1, 2, 3, 4],
                    observed=obs, anchor=True,
                    anchor_slope_blend=slope_blend,
                    anchor_lookback=anchor_lookback,
                    phase_aware=phase_aware,
                )
            else:
                qf = quantile_forecast(
                    fit, n_observed=len(obs), horizons=[1, 2, 3, 4],
                    observed=obs, anchor=True,
                    anchor_slope_blend=slope_blend,
                    anchor_lookback=anchor_lookback,
                    phase_aware=phase_aware,
                )
            # Apply empirical-coverage rescale to widen / narrow intervals.
            # The per-state max_factor cap may have been raised by
            # decomp_act when chronic under-coverage was detected.
            qf = apply_calibration(qf, tracker, state=state,
                                    max_factor=calibration_max_factor)
        except Exception as e:
            log.warning("quantile gen failed for %s: %s", state, e)
            continue
        forecasts.append(StateForecast(state=state, forecast=qf))
    tracker.save(cal_path)

    sub_df = build_submission_dataframe(
        forecasts, reference_date=reference_date, config=config,
    )
    out_dir = paths.root / "submissions"
    sub_csv = write_submission(sub_df, reference_date, out_dir) if not sub_df.empty else None

    return WeeklyJobResult(
        reference_date=reference_date,
        csv_source=csv,
        submission_csv=sub_csv,
        states=state_records,
    )


def _ingest_realized_actuals(
    paths: WorkspacePaths,
    tracker: "CalibrationTracker",
    obs_by_state: dict,
    config: FluBNFConfig,
) -> int:
    """Ingest previous submissions' (forecast, actual) pairs into the
    calibration tracker.

    For every submission CSV in `<workspace>/submissions/`, look up its
    reference_date and check if the observed series now has data for
    each forecast horizon (h=0..3 in FluSight terms). If so, record
    coverage. Idempotent — duplicates skipped at the record level.

    Returns the number of records added.
    """
    submissions_dir = paths.root / "submissions"
    if not submissions_dir.exists():
        return 0
    from .constants import load_locations
    from datetime import datetime as _dt
    try:
        locs = load_locations(config.locations_csv)
        fips_to_state = {info.fips: name for name, info in locs.items()}
    except Exception:
        fips_to_state = {}

    # We need observed values aligned by Saturday date. Build a per-state
    # mapping: state -> {Saturday ISO date: observed value}.
    # Use the season's onset/end window via the .exp file's #time index
    # mapped back to weekly dates. The simplest robust path: derive the
    # Saturday of each observed week from the season onset.
    import pymmwr as pm
    from datetime import timedelta as _td
    onset_sat = pm.epiweek_to_date(pm.Epiweek(
        config.season.year, config.season.onset_week))
    # `onset_sat` is the Saturday-aligned date for week 0.

    def _date_for_week_idx(idx: int) -> str:
        return (onset_sat + _td(days=7 * idx)).isoformat()

    state_to_dated_obs: dict[str, dict[str, float]] = {}
    for state, obs in obs_by_state.items():
        state_to_dated_obs[state] = {
            _date_for_week_idx(i): float(obs[i]) for i in range(len(obs))
            if obs is not None and i < len(obs)
        }

    added = 0
    import pandas as _pd
    for csv_path in sorted(submissions_dir.glob("*.csv")):
        try:
            sub = _pd.read_csv(csv_path, dtype={"location": str})
        except Exception:
            continue
        if sub.empty:
            continue
        sub["location"] = sub["location"].str.zfill(2).where(
            sub["location"] != "US", sub["location"])
        ref = str(sub["reference_date"].iloc[0])

        for (fips, h), group in sub[sub["output_type"] == "quantile"].groupby(
                ["location", "horizon"]):
            state_name = fips_to_state.get(fips)
            if state_name is None or state_name not in state_to_dated_obs:
                continue
            target_end = str(group["target_end_date"].iloc[0])
            actual = state_to_dated_obs[state_name].get(target_end)
            if actual is None:
                continue   # observed not in yet
            qmap = dict(zip(group["output_type_id"].astype(float),
                            group["value"].astype(float)))
            try:
                qf_dict = {
                    "q025": qmap[0.025], "q05": qmap[0.05],
                    "q25": qmap[0.25], "q50": qmap[0.5], "q75": qmap[0.75],
                    "q95": qmap[0.95], "q975": qmap[0.975],
                }
            except KeyError:
                continue
            from .calibration import CoverageRecord
            tracker.record(CoverageRecord(
                state=state_name, horizon=int(h) + 1,   # FluSight h0→bt h1
                reference_date=ref, **qf_dict,
                actual=float(actual),
            ))
            added += 1
    return added


def _analyze_and_adapt(
    state: str,
    obs: "np.ndarray",
    session: StateSession,
    paths: WorkspacePaths,
    *,
    top_n: int = 50,
    min_run_length: int = 4,
    min_relative_error: float = 0.35,
) -> tuple[list[str], list[str]]:
    """Read last week's PyBNF results (if present), recommend bounds/step
    changes, and mutate `session.bounds` / `session.n_steps` in place.

    Returns (bounds_changed, bounds_added).
    """
    bounds_changed: list[str] = []
    bounds_added: list[str] = []

    # 1. Read previous run's DE results.
    state_results = paths.results_for(state)
    de = read_de_results(state_results, state)
    if de is None or de.population.empty:
        return bounds_changed, bounds_added

    # Tiny-state guard: skip bounds expansion + step addition for
    # jurisdictions whose peak admissions is small. The model is already at
    # the noise floor; adaptation just introduces variance.
    max_K = max_steps_for_state(obs)
    if max_K <= 1:
        return bounds_changed, bounds_added

    # 2. Bounds expansion recommendation.
    recs = analysis.recommend_bounds(de.population, session.bounds, top_n=top_n)
    for r in recs:
        if not r.changed:
            continue
        for i, fp in enumerate(session.bounds):
            if fp.name == r.param:
                session.bounds[i] = FreeParam(fp.name, r.new_low, r.new_high)
                bounds_changed.append(r.param)
                break

    # 3. Step-add recommendation (gated by max_K for this state's volume).
    if session.n_steps < max_K:
        best = dict(zip(de.param_names, de.population.iloc[0][list(de.param_names)]))
        try:
            pred = predict_weekly(best, len(obs))
            step_rec = analysis.recommend_piecewise_step(
                predicted=pred, observed=obs,
                n_current_steps=session.n_steps,
                min_run_length=min_run_length,
                min_relative_error=min_relative_error,
            )
            if step_rec.needs_new_step:
                # Warm-start the new segment from residual signal.
                residuals = pred - obs
                sign = 1.0 if residuals[-1] >= 0 else -1.0
                t_init = len(obs) - 1
                for i in range(len(residuals) - 2, -1, -1):
                    if (residuals[i] > 0) != (sign > 0):
                        t_init = i + 1
                        break
                new_k = session.n_steps
                # b_K: scale current b_{K-1} midpoint by 1.5 if under-prediction.
                b_prev = next(
                    (fp for fp in session.bounds if fp.name == f"b{new_k-1}__FREE"),
                    None,
                )
                b_prev_mid = (b_prev.low + b_prev.high) / 2.0 if b_prev else 0.3
                factor = 1.5 if sign < 0 else 0.6
                b_init = max(0.05, b_prev_mid * factor)
                session.bounds.extend([
                    FreeParam(f"b{new_k}__FREE",
                              max(0.01, b_init * 0.5), max(0.05, b_init * 2.0)),
                    FreeParam(f"t{new_k}__FREE",
                              max(1, t_init - 4), max(4, t_init + 4)),
                ])
                bounds_added.extend([f"b{new_k}__FREE", f"t{new_k}__FREE"])
                session.n_steps += 1
        except Exception as e:
            log.warning("step recommendation failed for %s: %s", state, e)

    # 4. Bidirectional K control — if a piecewise segment is redundant
    # (b_K posterior overlaps b_{K-1}), remove it for next week. Helps
    # small-state and post-peak cases where the AICc gate may have
    # added a step that didn't end up doing anything.
    if session.n_steps > 1:
        try:
            rm_rec = analysis.recommend_remove_step(de.population)
            if rm_rec.needs_removal and rm_rec.step_to_remove is not None:
                k = rm_rec.step_to_remove
                # Remove b{k} and t{k} from bounds; renumber any higher
                # segments down by 1.
                surviving: list[FreeParam] = []
                for fp in session.bounds:
                    if fp.name in (f"b{k}__FREE", f"t{k}__FREE"):
                        continue
                    # Renumber b{k+1}/t{k+1}... → b{k}/t{k}...
                    new_name = fp.name
                    for higher in range(k + 1, session.n_steps):
                        if fp.name == f"b{higher}__FREE":
                            new_name = f"b{higher - 1}__FREE"
                        elif fp.name == f"t{higher}__FREE":
                            new_name = f"t{higher - 1}__FREE"
                    surviving.append(FreeParam(new_name, fp.low, fp.high))
                session.bounds = surviving
                session.n_steps -= 1
                bounds_added.append(f"~removed_b{k}_t{k}")
                log.info("[%s] removed redundant step: %s",
                         state, rm_rec.reason)
        except Exception as e:
            log.warning("step removal check failed for %s: %s", state, e)

    return bounds_changed, bounds_added


def _today_eastern() -> date:
    """The submission calendar's "today", never the machine's.

    FluSight deadlines are stated on the hub's own clock, America/New_York.
    A machine east of that zone crosses into Saturday hours before the
    deadline zone does, so near the Friday/Saturday midnight boundary
    date.today() there is already Saturday while the FluSight week is still
    Friday's, and the defaulted reference_date lands one week late
    (2026-09-01 final pass). The wall clock enters the job only here, so
    the deadline-zone constraint has one home.
    """
    return datetime.now(ZoneInfo("America/New_York")).date()


def _default_reference_date() -> date:
    return _next_saturday(_today_eastern())


def _next_saturday(d: date) -> date:
    days_until = (5 - d.weekday()) % 7
    days_until = days_until or 7
    from datetime import timedelta
    return d + timedelta(days=days_until)
