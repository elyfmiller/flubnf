"""Walk-forward backtest of the auto-pipeline against held-out actuals.

For each week W in a season:

    1. Truncate observed data to weeks [0..W].
    2. Fit the SIR model (in-Python DE — see `flubnf.fitting`).
    3. Optionally (`adaptive=True`) run the analyzer on the previous fit and
       apply bounds/step recommendations before re-fitting.
    4. Forecast H_weekly for horizons 1..H.
    5. Score those forecasts against actual data at W+1..W+H.

Run with `adaptive=True` (treatment) and `adaptive=False` (control) to
quantify whether the automation improves forecast skill.

This is a *shadow* of the real PyBNF pipeline: same analyze/apply code path,
but the fit is in-Python (much faster than out-of-process PyBNF DE) so the
backtest can run on a laptop. When the new BNGsim in-process engine ships,
swap `fitting.fit` for the real PyBNF runner in the harness.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from . import bngl_files, conf_files
from .analysis import BoundsRecommendation, StateAnalysis, recommend_bounds, recommend_piecewise_step
from .auto import _count_beta_steps
from .conf_files import FreeParam
from .config import FluBNFConfig
from .fitting import FitResult, fit, write_sorted_params
from .baseline_forecast import persistence_quantile_forecast
from .paths import WorkspacePaths
from .quantiles import clip_forecast, diagnose_forecast
from .simulate import predict_weekly

log = logging.getLogger(__name__)


# ===========================================================================
# Forecast
# ===========================================================================
def forecast(
    params: dict, n_observed: int, horizons: Sequence[int],
    *, model_type: str = "sir_piecewise",
) -> dict[int, float]:
    """Predict H_weekly at `n_observed + h - 1` for each h in horizons.

    The convention follows FluSight: horizon h means "the value of the
    weekly hospitalization observation that will be reported h weeks from
    now". With our 0-indexed time grid, the prediction at horizon h
    corresponds to t = n_observed + h - 1.
    """
    max_h = max(horizons)
    n_total = n_observed + max_h
    full = predict_weekly(params, n_total, model_type=model_type)
    return {h: float(full[n_observed + h - 1]) for h in horizons}


# ===========================================================================
# Scoring
# ===========================================================================
@dataclass(frozen=True)
class Scores:
    mae: float                # mean absolute error across horizons
    rmse: float
    mape: float               # mean absolute percentage error
    per_horizon: dict[int, float]  # MAE per horizon


def score(forecast: dict[int, float], actual: dict[int, float]) -> Scores:
    """Score a horizon-keyed forecast against horizon-keyed actuals.

    Both dicts must have the same horizons. Missing actuals (NaN) are
    excluded from the metrics.
    """
    horizons = sorted(set(forecast) & set(actual))
    pairs = [(forecast[h], actual[h]) for h in horizons
             if actual[h] is not None and not (isinstance(actual[h], float)
                                                and np.isnan(actual[h]))]
    if not pairs:
        return Scores(mae=float("nan"), rmse=float("nan"),
                      mape=float("nan"), per_horizon={})
    p = np.array([pp for pp, _ in pairs])
    a = np.array([aa for _, aa in pairs])
    abs_err = np.abs(p - a)
    mae = float(np.mean(abs_err))
    rmse = float(np.sqrt(np.mean((p - a) ** 2)))
    safe_a = np.where(np.abs(a) < 1.0, 1.0, np.abs(a))
    mape = float(np.mean(abs_err / safe_a))
    per_h = {h: float(abs(forecast[h] - actual[h]))
             for h in horizons
             if actual[h] is not None and not (isinstance(actual[h], float)
                                                and np.isnan(actual[h]))}
    return Scores(mae=mae, rmse=rmse, mape=mape, per_horizon=per_h)


# ===========================================================================
# Walk-forward
# ===========================================================================
@dataclass
class BacktestRecord:
    state: str
    week: int             # the "now" week W (observations 0..W available)
    adaptive: bool        # treatment (True) or control (False)
    best_obj: float
    n_steps: int          # piecewise beta segment count at fit time
    bounds_changed: list[str] = field(default_factory=list)
    bounds_added: list[str] = field(default_factory=list)
    forecast: dict[int, float] = field(default_factory=dict)
    actual: dict[int, float] = field(default_factory=dict)
    scores: Optional[Scores] = None


@dataclass
class AdaptiveState:
    """Carries bounds / piecewise complexity across weeks for one state."""
    bounds: list[FreeParam]
    n_steps: int


def _default_bounds(n_steps: int = 1) -> list[FreeParam]:
    """Match the template Alabama.conf defaults. For K-step piecewise beta
    we append (bK, tK) ranges per added step."""
    base = [
        FreeParam("I0__FREE", 0.001, 0.01),
        FreeParam("b0__FREE", 0.1, 1.5),
        FreeParam("gamma__FREE", 0.01, 0.5),
        FreeParam("mult__FREE", 100, 8000),
        FreeParam("t0__FREE", 0, 12),
    ]
    for k in range(1, n_steps):
        base.append(FreeParam(f"b{k}__FREE", 0.05, 1.5))
        base.append(FreeParam(f"t{k}__FREE", 1, 12))
    return base


def walk_forward(
    state: str,
    observed_full: np.ndarray,
    *,
    start_week: int = 6,
    end_week: Optional[int] = None,
    horizons: Sequence[int] = (1, 2, 3, 4),
    adaptive: bool = True,
    popsize: int = 15,
    max_iter: int = 300,
    seed: int = 0,
    burn_in: int = 150,
    adaptive_iter: int = 150,
    pybnf_timeout: float = 900.0,
    initial_bounds: Optional[list[FreeParam]] = None,
    step_min_run_length: int = 4,
    step_min_relative_error: float = 0.35,
    require_aicc_improvement: bool = True,
    engine: str = "inproc",
    workspace_paths: Optional[WorkspacePaths] = None,
    config: Optional[FluBNFConfig] = None,
    quantile_horizons: bool = True,
    model_type: str = "sir_piecewise",
    population: Optional[float] = None,
    checkpoint_path: Optional[Path] = None,
    skip_weeks: Optional[set] = None,
) -> list[BacktestRecord]:
    """Run the walk-forward backtest for a single state.

    Args:
        state:           jurisdiction name (used for logging / output).
        observed_full:   full-season observed H_weekly (length = N).
        start_week:      first "now" week W (need >= ~6 weeks for a fit).
        end_week:        last W. Defaults to N - max(horizons) - 1.
        horizons:        forecast horizons (in weeks).
        adaptive:        True = run analyze + apply between weeks (treatment).
                         False = static bounds & complexity (control).
        popsize/max_iter/seed: DE settings.
        initial_bounds:  starting bounds + piecewise structure.
                         Defaults to a 1-step model with template bounds.
    """
    observed_full = np.asarray(observed_full, dtype=float)
    n_obs = len(observed_full)
    horizons = tuple(horizons)
    end_week = end_week if end_week is not None else (n_obs - max(horizons) - 1)
    if end_week < start_week:
        raise ValueError(
            f"end_week ({end_week}) must be >= start_week ({start_week})"
        )

    is_sirs = (model_type == "sirs_logistic")

    # State-adaptive initial bounds: scales `mult` to peak admissions seen so
    # far. Prevents the silent ceiling that hurt CA/TX in the prior backtest.
    from .bounds_init import (
        adaptive_initial_bounds, max_steps_for_state, max_transitions_for_state,
    )
    seed_obs = observed_full[: start_week + 1]
    if is_sirs:
        # Smooth-beta SIRS: a FIXED transition count per state (no reactive
        # add/remove — the smooth beta makes that machinery unnecessary). The
        # transition count is the decision layer's `n_steps`.
        n_trans = max(1, max_transitions_for_state(seed_obs))
        if initial_bounds is None:
            initial_bounds = adaptive_initial_bounds(
                seed_obs, model_type=model_type, population=population)
            # Append one signed amplitude db_k per transition beyond the first
            # (db1 is already in the SIRS template bounds).
            for k in range(2, n_trans + 1):
                initial_bounds.append(FreeParam(f"db{k}__FREE", -1.2, 1.2))
        max_K = n_trans
        start_n_steps = n_trans
    else:
        if initial_bounds is None:
            initial_bounds = adaptive_initial_bounds(seed_obs)
        max_K = max(1, max_steps_for_state(seed_obs))
        start_n_steps = 1
    log.info("[%s] model=%s initial bounds: %s; max_K=%d",
             state, model_type,
             ", ".join(f"{fp.name}:[{fp.low:.3g},{fp.high:.3g}]" for fp in initial_bounds),
             max_K)

    state_adaptive = AdaptiveState(
        bounds=list(initial_bounds or _default_bounds(1)),
        n_steps=start_n_steps,
    )

    # SIRS structural params (centers, width, N, omega) are NOT in the fitted
    # population PyBNF returns — they live in config. The BNGL fit and the
    # in-Python mirror MUST use the SAME centers each week. With
    # center_mode=="data_driven" the centers are placed on the observed surge
    # per week (flubnf.centers.place_centers); otherwise they are the
    # tier-constant config values. Either way they are FIXED at fit time, so
    # the free-parameter count is unchanged.
    use_data_centers = (
        is_sirs and config is not None
        and getattr(config.model, "center_mode", "fixed") == "data_driven"
    )
    _sw = float(config.model.transition_width) if (is_sirs and config is not None) else 2.5
    _omega = float(config.model.omega_fixed) if (is_sirs and config is not None) else 0.0

    def _centers_for_week(obs_w: np.ndarray) -> list[float]:
        """The 3 declared centers (tc1..tc3) for this week, padded; the first
        `max_K` are the ones beta() actually references."""
        if not is_sirs or config is None:
            return []
        if use_data_centers:
            from .centers import place_centers
            cs = place_centers(obs_w, max_K, _sw)
        else:
            cs = list(config.model.transition_centers)
        while len(cs) < 3:
            cs.append(cs[-1] if cs else 0.0)
        return [float(c) for c in cs[:3]]

    def _fixed_sirs(centers: list[float]) -> dict:
        d: dict[str, float] = {"sw": _sw, "omega": _omega}
        if population is not None:
            d["N"] = float(population)
        for k, tc in enumerate(centers, start=1):
            d[f"tc{k}"] = float(tc)
        return d

    def _fit_config_for(centers: list[float]):
        """Per-fit config whose transition_centers drive the BNGL materialization
        so the PyBNF sim uses the SAME centers as the in-Python mirror."""
        if not is_sirs or config is None:
            return config
        return config.model_copy(update={
            "model": config.model.model_copy(
                update={"transition_centers": list(centers)})
        })

    # In-memory decomp-act loop state. Mirrors what weekly_job does between
    # Tuesdays, but scoped to this single state's walk-forward. Mutations
    # to bounds + calibration_max_factor take effect on the NEXT week's fit
    # / forecast — the same temporal flow that production sees.
    from .calibration import CalibrationTracker as _CalTracker, apply_calibration as _apply_cal
    from .session import StateSession as _StateSession
    from . import decomp_act as _da
    tracker = _CalTracker()
    decomp_tuning: dict = {"calibration_max_factor": 1.5}
    decomp_log: list[tuple[int, str]] = []  # (week, notes)

    records: list[BacktestRecord] = []

    # Resume-from-disk: skip weeks already checkpointed, but ONLY when each
    # week's fit is independent of carried adaptive state. SIRS runs at a fixed
    # transition count (stateless across weeks); static (non-adaptive) runs are
    # also stateless. Piecewise-adaptive bounds/steps are path-dependent, so a
    # completed week cannot be skipped without its fit — there we re-run.
    stateless = is_sirs or (not adaptive)
    if skip_weeks and not stateless:
        log.warning("[%s] resume skip ignored: piecewise-adaptive is "
                    "path-dependent; re-running from start_week", state)
        skip_weeks = None

    for w in range(start_week, end_week + 1):
        if skip_weeks and w in skip_weeks:
            continue
        obs_w = observed_full[: w + 1]   # weeks 0..w inclusive
        # --- 1. Analyze previous fit and adapt (only after first iter) ---
        bounds_changed: list[str] = []
        bounds_added: list[str] = []

        # Always: rescan the mult bound against the latest peak. This is the
        # "state-adaptive bounds" fix — the upper bound grows as the outbreak
        # grows, so the DE never sits at the ceiling. SIRS `mult` is a fixed
        # ascertainment fraction, NOT peak-scaled, so this is piecewise-only.
        if adaptive and not is_sirs:
            new_bounds, did_rescan = _rescan_mult_bound(obs_w, state_adaptive.bounds)
            if did_rescan:
                state_adaptive.bounds = new_bounds
                bounds_changed.append("mult__FREE")
                log.info("  rescan: mult bound expanded (new peak observed)")

        # Decomp-act: read accumulated tracker signals (bias + cov_95) and
        # mutate bounds / tuning before the next fit. Only meaningful once a
        # few weeks of forecasts have been scored. Disabled for SIRS in this
        # first measurement cut: we are isolating the model-form change, and
        # the decomp-act triggers' WIS effect is itself still unproven.
        decomp_notes_this_week: list[str] = []
        if adaptive and not is_sirs and tracker.history:
            synth_sess = _StateSession(
                state=state,
                bounds=list(state_adaptive.bounds),
                n_steps=state_adaptive.n_steps,
                tuning=dict(decomp_tuning),
            )
            actions = _da.apply_to_session(tracker, synth_sess)
            if actions:
                state_adaptive.bounds = list(synth_sess.bounds)
                decomp_tuning.update(synth_sess.tuning)
                if actions.mult_tightened is not None:
                    bounds_changed.append("mult__FREE")
                decomp_notes_this_week.extend(actions.notes)
                decomp_log.append((w, "; ".join(actions.notes)))
                log.info("  [%s w=%d] decomp-act: %s",
                         state, w, "; ".join(actions.notes))
        # Tiny-state guard: for jurisdictions whose peak admissions is small
        # (max_K capped at 1), the model is already at the noise floor.
        # Bounds expansion just introduces variance — skip it entirely.
        # SIRS runs at a fixed transition count, so the piecewise step-add /
        # bounds-recommendation brain is bypassed entirely.
        skip_bounds_recs = (max_K <= 1) or is_sirs
        if adaptive and records and not skip_bounds_recs:
            prev = records[-1]
            # Use the previous fit to drive bounds/step recommendations.
            prev_pop = _make_population_df(
                getattr(prev, "_fit_result", None)
            )
            if prev_pop is not None:
                recs_bounds = recommend_bounds(
                    prev_pop, state_adaptive.bounds,
                )
                # Apply bounds changes.
                for r in recs_bounds:
                    if r.changed:
                        bounds_changed.append(r.param)
                        for i, fp in enumerate(state_adaptive.bounds):
                            if fp.name == r.param:
                                state_adaptive.bounds[i] = FreeParam(
                                    fp.name, r.new_low, r.new_high,
                                )
                # Run step recommendation using previous fit's best params
                # against the *previous week's* observed data.
                prev_obs = observed_full[: prev.week + 1]
                best = prev._fit_result.best_params if prev._fit_result else None
                if best is not None:
                    try:
                        pred = predict_weekly(best, len(prev_obs))
                        rec_step = recommend_piecewise_step(
                            predicted=pred, observed=prev_obs,
                            n_current_steps=state_adaptive.n_steps,
                            min_run_length=step_min_run_length,
                            min_relative_error=step_min_relative_error,
                        )
                        if rec_step.needs_new_step and state_adaptive.n_steps < max_K:
                            # Validation-based gate: hold out the last
                            # `holdout_weeks` weeks, fit K and K+1 on the rest,
                            # commit the step only if K+1 forecasts the
                            # holdout better. Directly aligned with the
                            # metric we care about (WIS / MAE on near-future).
                            ok_to_add = True
                            if require_aicc_improvement:
                                ok_to_add = _validation_gate_for_step(
                                    prev_obs, state_adaptive,
                                    popsize=popsize, max_iter=max_iter,
                                    seed=seed,
                                )
                            if ok_to_add:
                                state_adaptive.n_steps += 1
                                new_k = state_adaptive.n_steps - 1
                                # Warm-start: initialize t_K near the recent
                                # residual sign-change and b_K from the observed
                                # acceleration, instead of broad uniform priors.
                                t_init, b_init = _warm_start_for_new_step(
                                    prev_obs, pred, state_adaptive,
                                )
                                # b_K bounds stay broad — the DE finds the
                                # right transmission rate. Tightening these
                                # was making the AICc gate reject every step.
                                new_b = FreeParam(f"b{new_k}__FREE", 0.05, 1.5)
                                # t_K's range IS narrowed: residuals directly
                                # tell us where the switch-time should be.
                                new_t = FreeParam(f"t{new_k}__FREE",
                                                  max(1, t_init - 4),
                                                  max(4, t_init + 4))
                                state_adaptive.bounds.extend([new_b, new_t])
                                bounds_added.extend([new_b.name, new_t.name])
                                log.info("  warm-start b_K=[%.3g,%.3g] t_K=[%.1f,%.1f]",
                                         new_b.low, new_b.high, new_t.low, new_t.high)
                    except Exception as e:
                        log.warning("step rec failed at week %d: %s", w, e)

        # --- 2. Fit on data up through week w (engine choice) ---
        # Compute this week's transition centers ONCE and thread the SAME
        # values into the BNGL fit (via the per-fit config) and the in-Python
        # mirror (via week_fixed_sirs) — never recompute in two places.
        week_centers = _centers_for_week(obs_w)
        week_fixed_sirs = _fixed_sirs(week_centers) if is_sirs else {}
        week_fit_config = _fit_config_for(week_centers) if is_sirs else config
        if use_data_centers and week_centers:
            log.info("[%s w=%d] data-driven centers: %s",
                     state, w, [round(c, 1) for c in week_centers[:max_K]])
        fit_result = _fit_dispatch(
            engine=engine, state=state, observed=obs_w,
            bounds=state_adaptive.bounds, n_steps=state_adaptive.n_steps,
            paths=workspace_paths, config=week_fit_config,
            popsize=popsize, max_iter=max_iter, seed=seed,
            burn_in=burn_in, adaptive_iter=adaptive_iter,
            pybnf_timeout=pybnf_timeout,
        )
        if fit_result is None:
            log.warning("[%s w=%d] fit failed; skipping week", state, w)
            continue

        # --- 3. Forecast (point + quantile) ---
        point_params = ({**week_fixed_sirs, **fit_result.best_params}
                        if is_sirs else fit_result.best_params)
        fcst = forecast(point_params, n_observed=w + 1,
                        horizons=horizons, model_type=model_type)
        actual = {
            h: (float(observed_full[w + h]) if (w + h) < n_obs
                else float("nan"))
            for h in horizons
        }
        scores_obj = score(fcst, actual)
        record = BacktestRecord(
            state=state, week=w, adaptive=adaptive,
            best_obj=fit_result.best_obj,
            n_steps=state_adaptive.n_steps,
            bounds_changed=bounds_changed,
            bounds_added=bounds_added,
            forecast=fcst, actual=actual, scores=scores_obj,
        )
        # Stash the FitResult on the record so the next iter's analyzer can
        # see it. Not part of the public dataclass schema.
        record._fit_result = fit_result  # type: ignore[attr-defined]

        # Optionally compute quantile forecast + WIS scores per horizon.
        if quantile_horizons:
            try:
                from .wis import wis as wis_fn
                if engine == "amcmc" and workspace_paths is not None:
                    # Read PyBNF's noise-augmented trajectory directly.
                    from .amcmc import (read_traj_noise,
                                        quantile_forecast_from_amcmc)
                    traj = read_traj_noise(
                        workspace_paths.results_for(state), state,
                    )
                    if traj is None:
                        raise RuntimeError("no AMCMC traj_noise file")
                    # Anchor on the most recent observation (obs_w[-1]) so
                    # h=0 quantiles are coherent with what we already know.
                    qf = quantile_forecast_from_amcmc(
                        traj, n_observed=w + 1, horizons=horizons,
                        observed=obs_w, anchor=True,
                    )
                else:
                    from .quantiles import quantile_forecast
                    qf = quantile_forecast(
                        fit_result, n_observed=w + 1, horizons=horizons,
                        seed=seed,
                        observed=obs_w, anchor=True,
                    )
                # Apply the empirical-coverage rescale that decomp-act may
                # have widened via calibration_max_factor. Mirrors the
                # weekly_job production path.
                if adaptive:
                    qf = _apply_cal(
                        qf, tracker, state=state,
                        max_factor=float(decomp_tuning.get("calibration_max_factor", 1.5)),
                    )
                # Forecast-sanity clip: tame physically-impossible blowups from
                # an occasional unstable fit (stiff ODE / neg-bin noise) before
                # they dominate WIS or reach a submission. 20x the largest
                # observed week is far above any real surge; floored for tiny
                # early-season series.
                # Do NOT clip a blown-up forecast to the cap: that pushes every
                # quantile onto the same ceiling and yields a ZERO-WIDTH point
                # mass, which WIS punishes about as hard as the blowup. Measured
                # on the 2025-26 SIR backtest, 11 of 4784 cells saturated this
                # way (NY 20x3870=77400, LA 20x433=8660) and carried 49.4% of
                # ALL WIS. Detect instead, and substitute a real distribution.
                peak_so_far = float(np.nanmax(obs_w)) if len(obs_w) else 0.0
                cap = max(20.0 * peak_so_far, 1000.0)
                last_obs = float(obs_w[-1]) if len(obs_w) else None
                diag = diagnose_forecast(qf, cap=cap, last_observed=last_obs)
                if not diag.usable:
                    log.warning("[%s w=%d] unusable forecast (%s) -> persistence "
                                "fallback", state, w, "; ".join(diag.reasons[:2]))
                    try:
                        qf = persistence_quantile_forecast(
                            np.asarray(obs_w, dtype=float), horizons,
                            quantile_levels=qf.quantile_levels)
                        record.fallback = "persistence"  # type: ignore[attr-defined]
                    except Exception as exc:      # keep the backtest alive
                        log.warning("[%s w=%d] persistence fallback failed (%s); "
                                    "clipping as a last resort", state, w, exc)
                        qf = clip_forecast(qf, cap)
                        record.fallback = "clip"  # type: ignore[attr-defined]
                qf_dict = qf.to_dict()
                record.quantile_forecast = qf_dict  # type: ignore[attr-defined]
                wis_by_h: dict[int, float] = {}
                for h in horizons:
                    if not np.isnan(actual[h]):
                        wis_by_h[h] = wis_fn(qf_dict[h], actual[h]).wis
                record.wis = wis_by_h  # type: ignore[attr-defined]
                # Feed realized actuals back into the tracker so future
                # weeks' decomp-act has signal to act on. We use horizon=1
                # in calibration's sense (= h=0 FluSight horizon = the
                # observation in week W+1 vs the h=1 forecast we made at W).
                actuals_for_tracker = {
                    int(h): float(actual[h])
                    for h in horizons if not np.isnan(actual[h])
                }
                if actuals_for_tracker:
                    tracker.record_from_quantile_forecast(
                        state=state, qf=qf,
                        actuals=actuals_for_tracker,
                        reference_date=f"w{w:02d}",
                    )
                record.decomp_acts = list(decomp_notes_this_week)  # type: ignore[attr-defined]
            except Exception as e:
                log.warning("quantile/wis failed at w=%d: %s", w, e)

        records.append(record)
        # Checkpoint this week immediately so a kill (reboot / idle / crash)
        # mid-walk loses at most this single in-flight fit, not the whole run.
        if checkpoint_path is not None:
            try:
                append_record_csv(checkpoint_path, record)
            except Exception as e:
                log.warning("[%s w=%d] checkpoint append failed: %s",
                            state, w, e)
        wis_mean = (
            float(np.mean(list(getattr(record, "wis", {}).values())))
            if getattr(record, "wis", {}) else float("nan")
        )
        log.info(
            "[%s w=%2d %s] obj=%.1f K=%d MAE=%5.1f WIS=%5.1f changed=%s added=%s",
            state, w, "ADAPT" if adaptive else "STATIC",
            fit_result.best_obj, state_adaptive.n_steps,
            scores_obj.mae, wis_mean, bounds_changed, bounds_added,
        )
    return records


def _fit_dispatch(
    *, engine: str, state: str, observed: np.ndarray,
    bounds: list[FreeParam], n_steps: int,
    paths: Optional[WorkspacePaths], config: Optional[FluBNFConfig],
    popsize: int, max_iter: int, seed: int,
    burn_in: int = 150, adaptive_iter: int = 150,
    pybnf_timeout: float = 900.0,
):
    """Select an in-Python DE, real-PyBNF DE, or real-PyBNF AMCMC fit."""
    if engine in {"pybnf", "amcmc"}:
        from .pybnf_engine import PyBNFOptions, fit_with_pybnf
        if paths is None or config is None:
            raise ValueError("engine=pybnf/amcmc requires workspace_paths and config")
        method = "am" if engine == "amcmc" else "de"
        # AMCMC needs the simulation to cover the forecast horizons too,
        # since the noise trajectory is read from the simulated future weeks.
        forecast_horizon = 4 if engine == "amcmc" else 0
        return fit_with_pybnf(
            state, observed, bounds, paths, config,
            n_steps=n_steps,
            options=PyBNFOptions(
                method=method, popsize=popsize, max_iter=max_iter,
                burn_in=burn_in, adaptive=adaptive_iter,
                timeout_sec=float(pybnf_timeout),
            ),
            forecast_horizon=forecast_horizon,
        )
    return fit(state, observed, bounds,
               popsize=popsize, max_iter=max_iter, seed=seed)


def _resolve_columns_quick(df: pd.DataFrame, config: FluBNFConfig
                           ) -> tuple[str, str, str]:
    """Find the date/geo/value column names that exist in a CDC CSV header,
    among the aliases declared in `config.cdc.*_columns`."""
    cols = set(df.columns)
    def pick(aliases: list[str], kind: str) -> str:
        for a in aliases:
            if a in cols:
                return a
        raise ValueError(f"no {kind} column found in {sorted(cols)[:6]}")
    return (
        pick(config.cdc.geo_columns, "geo"),
        pick(config.cdc.date_columns, "date"),
        pick(config.cdc.value_columns, "value"),
    )


def _warm_start_for_new_step(
    observed: np.ndarray, predicted: np.ndarray, state_adaptive: "AdaptiveState",
) -> tuple[float, float]:
    """Pick reasonable starting values for (t_K, b_K) when adding a new
    piecewise segment.

    Heuristics:
      - t_init: index of the most recent residual sign-change (where pred
        starts systematically under- or over-shooting).
      - b_init: scaled current b_{K-1} adjusted by recent error sign. If we
        are under-predicting, push b_K above b_{K-1} (acceleration); if
        over-predicting, push below.
    """
    residuals = predicted[: len(observed)] - observed
    # Look backward for the latest sign-flip.
    sign = np.sign(residuals[-1]) if residuals[-1] != 0 else 1.0
    t_init = len(observed) - 1
    for i in range(len(residuals) - 2, -1, -1):
        if np.sign(residuals[i]) != sign:
            t_init = i + 1
            break

    # Find b_{K-1} from current bounds (midpoint).
    K = state_adaptive.n_steps
    b_prev_fp = next(
        (fp for fp in state_adaptive.bounds if fp.name == f"b{K-1}__FREE"),
        None,
    )
    b_prev_mid = (b_prev_fp.low + b_prev_fp.high) / 2.0 if b_prev_fp else 0.3
    # Under-prediction (residual < 0) -> need higher beta in new segment.
    # Over-prediction -> need lower.
    factor = 1.5 if sign < 0 else 0.6
    b_init = max(0.05, b_prev_mid * factor)
    # t_init is relative to season start = the actual time index.
    return float(t_init), float(b_init)


def _rescan_mult_bound(
    observed: np.ndarray, bounds: list[FreeParam],
) -> tuple[list[FreeParam], bool]:
    """If a new peak exceeds the current mult upper bound, expand it.
    Returns (new_bounds, did_change)."""
    from .bounds_init import adaptive_initial_bounds
    proposed = adaptive_initial_bounds(observed, base=bounds)
    changed = False
    out: list[FreeParam] = []
    for fp, np_ in zip(bounds, proposed):
        if fp.name == "mult__FREE" and np_.high > fp.high * 1.01:
            out.append(np_)
            changed = True
        else:
            out.append(fp)
    return out, changed


def _validation_gate_for_step(
    observed: np.ndarray,
    state_adaptive: "AdaptiveState",
    *, popsize: int, max_iter: int, seed: int,
    holdout_weeks: int = 2,
    score_metric: str = "wis",
) -> bool:
    """Validation-based step gate: fit K and K+1 on the data MINUS the last
    `holdout_weeks` weeks, then forecast those weeks. Return True iff the
    (K+1) model scores better on the holdout.

    `score_metric`:
      - "wis"  (default): proper scoring rule — directly matches the
                          FluSight evaluation metric. Generates DE-bootstrap
                          quantiles, computes WIS per holdout week, sums.
      - "mae"            : mean absolute error on point forecasts.
                          Cheaper, but only proxies WIS.

    More expensive than AICc (two extra DE fits) but metric-aligned.
    """
    if len(observed) < holdout_weeks + 6:
        return False  # Not enough data to validate.
    train = observed[: -holdout_weeks]
    holdout = observed[-holdout_weeks:]
    n_train = len(train)

    def _fit_and_score(label: str, bounds_list: list[FreeParam]) -> float:
        res = fit(label, train, bounds_list,
                  popsize=popsize, max_iter=max_iter, seed=seed)
        if score_metric == "mae":
            pred = predict_weekly(res.best_params, n_train + holdout_weeks)
            return float(np.mean(np.abs(pred[n_train:] - holdout)))
        # WIS path — proper scoring.
        from .quantiles import quantile_forecast, diagnose_forecast, clip_forecast
        from .wis import wis as wis_fn
        qf = quantile_forecast(
            res, n_observed=n_train,
            horizons=list(range(1, holdout_weeks + 1)),
            seed=seed,
            # Don't anchor on the holdout's last observed value — we're
            # trying to predict it; anchoring would leak the answer.
            observed=train, anchor=False,
        )
        qd = qf.to_dict()
        return float(np.mean([
            wis_fn(qd[h], float(holdout[h - 1])).wis
            for h in range(1, holdout_weeks + 1)
        ]))

    score_k = _fit_and_score("val-k", list(state_adaptive.bounds))
    new_k = state_adaptive.n_steps
    bounds_kp1 = list(state_adaptive.bounds) + [
        FreeParam(f"b{new_k}__FREE", 0.05, 1.5),
        FreeParam(f"t{new_k}__FREE", 1, 12),
    ]
    score_kp1 = _fit_and_score("val-kp1", bounds_kp1)

    log.info("  validation gate (%s): K=%.2f vs K+1=%.2f -> %s",
             score_metric, score_k, score_kp1,
             "K+1" if score_kp1 < score_k else "K")
    return score_kp1 < score_k


def _aicc_gate_for_step(
    observed: np.ndarray,
    state_adaptive: "AdaptiveState",
    *, popsize: int, max_iter: int, seed: int,
) -> bool:
    """Run a quick K vs K+1 comparison fit; return True iff (K+1) wins by AICc."""
    from .analysis import compare_models_aicc
    # Refit the current K-step model.
    res_k = fit("aicc-k", observed, state_adaptive.bounds,
                popsize=popsize, max_iter=max_iter, seed=seed)
    pred_k = predict_weekly(res_k.best_params, len(observed))
    # Synthesize bounds for the candidate K+1 model.
    new_k = state_adaptive.n_steps  # 0-indexed for the new segment
    bounds_kp1 = list(state_adaptive.bounds) + [
        FreeParam(f"b{new_k}__FREE", 0.05, 1.5),
        FreeParam(f"t{new_k}__FREE", 1, 12),
    ]
    res_kp1 = fit("aicc-kp1", observed, bounds_kp1,
                  popsize=popsize, max_iter=max_iter, seed=seed)
    pred_kp1 = predict_weekly(res_kp1.best_params, len(observed))
    n_params_k = sum(1 for fp in state_adaptive.bounds if fp.name.endswith("__FREE"))
    n_params_kp1 = n_params_k + 2
    cmp = compare_models_aicc(
        residuals_k=pred_k - observed,
        residuals_kp1=pred_kp1 - observed,
        n_params_k=n_params_k, n_params_kp1=n_params_kp1,
        delta_threshold=0.5,
    )
    log.info("  AICc gate: K=%d (%.1f) vs K+1=%d (%.1f) -> %s",
             n_params_k, cmp.aicc_k, n_params_kp1, cmp.aicc_kp1, cmp.favored)
    return cmp.favored == "K+1"


def _make_population_df(fit_result: Optional[FitResult]) -> Optional[pd.DataFrame]:
    """Convert a FitResult into the DataFrame shape `recommend_bounds` wants."""
    if fit_result is None:
        return None
    df = pd.DataFrame(fit_result.population, columns=list(fit_result.param_names))
    df.insert(0, "Obj", fit_result.objectives)
    return df.sort_values("Obj").reset_index(drop=True)


# ===========================================================================
# Aggregate reporting
# ===========================================================================
def append_record_csv(path: "Path", record: BacktestRecord) -> None:
    """Append one backtest record to a checkpoint CSV, aligning to any
    existing header. Enables resume-from-disk: a run killed mid-walk keeps
    every completed week. Safe for one writer per file (we use one part-file
    per state, written by that state's single worker thread)."""
    df1 = records_to_dataframe([record])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        header = pd.read_csv(path, nrows=0).columns.tolist()
        for c in header:
            if c not in df1.columns:
                df1[c] = np.nan
        df1 = df1.reindex(columns=header)
        df1.to_csv(path, mode="a", header=False, index=False)
    else:
        df1.to_csv(path, index=False)


def records_to_dataframe(records: Sequence[BacktestRecord]) -> pd.DataFrame:
    rows = []
    for r in records:
        wis_by_h = getattr(r, "wis", {})
        row = {
            "state": r.state, "week": r.week, "adaptive": r.adaptive,
            "best_obj": r.best_obj, "n_steps": r.n_steps,
            "mae": r.scores.mae if r.scores else None,
            "rmse": r.scores.rmse if r.scores else None,
            "mape": r.scores.mape if r.scores else None,
            "wis_mean": (float(np.mean(list(wis_by_h.values())))
                         if wis_by_h else None),
            "bounds_changed": ",".join(r.bounds_changed) or "-",
            "bounds_added": ",".join(r.bounds_added) or "-",
            "decomp_acts": " | ".join(getattr(r, "decomp_acts", []) or []) or "-",
        }
        for h, v in r.forecast.items():
            row[f"fcst_h{h}"] = v
        for h, v in r.actual.items():
            row[f"actual_h{h}"] = v
        for h, v in wis_by_h.items():
            row[f"wis_h{h}"] = v
        # Persist key PI bounds per horizon so empirical coverage /
        # calibration can be computed post-hoc without a refit.
        qf_dict = getattr(r, "quantile_forecast", None)
        if qf_dict:
            for h, qmap in qf_dict.items():
                def _q(q):
                    return qmap.get(q, qmap.get(float(q)))
                for ql, tag in ((0.025, "q025"), (0.25, "q25"), (0.5, "q50"),
                                (0.75, "q75"), (0.975, "q975")):
                    val = _q(ql)
                    if val is not None:
                        row[f"{tag}_h{h}"] = float(val)
        rows.append(row)
    return pd.DataFrame(rows)
