"""FluBNF command-line interface.

Each subcommand is a thin wrapper around a module function so that:
  - the Streamlit UI calls the same module functions directly
  - everything is scriptable / testable
  - no business logic lives in this file
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

# ---------------------------------------------------------------------------
# Deferred imports (startup-freeze fix, measured 2026-08-22)
#
# The science modules below pull pandas and scipy, and importing them here
# cost the console launch 10.5 s cold (1.0 s warm) BEFORE `flubnf app`
# could even begin opening its window -- the single largest stage of the
# measured startup profile. None of them is needed by the app/window
# commands, so each resolves on first real use instead. A module-level
# __getattr__ (PEP 562) cannot serve name lookups inside function bodies,
# so the deferral is a small proxy that resolves once and then replaces
# its own global binding, making every later reference direct.
# ---------------------------------------------------------------------------
class _Lazy:
    __slots__ = ("_mod", "_attr", "_name")

    def __init__(self, mod: str, attr: str = "", name: str = ""):
        self._mod, self._attr = mod, attr
        self._name = name or attr or mod.rsplit(".", 1)[-1]

    def _resolve(self):
        import importlib
        obj = importlib.import_module(self._mod)
        if self._attr:
            obj = getattr(obj, self._attr)
        globals()[self._name] = obj      # later lookups skip the proxy
        return obj

    def __getattr__(self, item):
        return getattr(self._resolve(), item)

    def __call__(self, *a, **k):
        return self._resolve()(*a, **k)

    def __iter__(self):
        return iter(self._resolve())

    def __len__(self):
        return len(self._resolve())

    def __getitem__(self, key):
        return self._resolve()[key]

    def __contains__(self, key):
        return key in self._resolve()


auto = _Lazy("flubnf.auto", name="auto")
bt = _Lazy("flubnf.backtest", name="bt")
bngl_files = _Lazy("flubnf.bngl_files")
cmp_mod = _Lazy("flubnf.compare", name="cmp_mod")
conf_files = _Lazy("flubnf.conf_files")
exp_files = _Lazy("flubnf.exp_files")
fetch = _Lazy("flubnf.fetch")
flusight = _Lazy("flubnf.flusight")
runs = _Lazy("flubnf.runs")
wjmod = _Lazy("flubnf.weekly_job", name="wjmod")
FluBNFConfig = _Lazy("flubnf.config", "FluBNFConfig")
JURISDICTIONS = _Lazy("flubnf.constants", "JURISDICTIONS")
STATE_TO_ABBREV = _Lazy("flubnf.constants", "STATE_TO_ABBREV")
WorkspacePaths = _Lazy("flubnf.paths", "WorkspacePaths")
WorkspaceState = _Lazy("flubnf.state", "WorkspaceState")

app = typer.Typer(
    add_completion=False,
    help="FluBNF — automated weekly PyBNF workflow for CDC FluSight.",
    no_args_is_help=True,
)
console = Console()


def _trace(msg: str) -> None:
    """Startup-sequence trace: a timestamped line to stderr and, when
    FLUBNF_STARTUP_TRACE names a file, appended there. Free when the
    variable is unset. The windowed launch involves four actors (this
    process, the uvicorn thread, the warm thread, WKWebView) whose
    ORDERING is the whole diagnosis, so the trace is permanent and
    env-gated rather than something re-invented at each regression."""
    import os
    import sys as _sys
    import time as _time
    path = os.environ.get("FLUBNF_STARTUP_TRACE")
    if not path:
        return
    t = _time.time()
    line = (f"{t:.3f} {_time.strftime('%H:%M:%S', _time.localtime(t))}"
            f".{int(t * 1000) % 1000:03d} [pid {os.getpid()} cli] {msg}")
    try:
        with open(path, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line, file=_sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Globals (resolved once per invocation)
# ---------------------------------------------------------------------------
def _load(config_path: Optional[Path], workspace: Optional[str]) -> tuple[
    FluBNFConfig, WorkspacePaths, WorkspaceState
]:
    cfg = FluBNFConfig.load(config_path=config_path)
    paths = WorkspacePaths(root=cfg.workspace(workspace)).ensure()
    state = WorkspaceState.load_or_create(
        paths.state_file,
        workspace=workspace or f"season_{cfg.season.year}",
        season_year=cfg.season.year,
    )
    return cfg, paths, state


CONFIG_OPT = typer.Option(None, "--config", "-c", help="Override config YAML.")
WORKSPACE_OPT = typer.Option(
    None, "--workspace", "-w",
    help="Workspace name (defaults to season_{year}).",
)


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------
@app.command()
def init(
    config: Optional[Path] = CONFIG_OPT,
    workspace: Optional[str] = WORKSPACE_OPT,
    force: bool = typer.Option(False, "--force", "-f",
                               help="Re-materialize template files."),
):
    """Create / refresh per-state .bngl and .conf files for the workspace."""
    cfg, paths, state = _load(config, workspace)
    bngl_files.materialize_all(JURISDICTIONS, paths, cfg, force=force)
    conf_files.materialize_all(JURISDICTIONS, paths, cfg, force=force)
    state.record("init", n_states=len(JURISDICTIONS), force=force)
    state.save(paths.state_file)
    console.print(
        f"[green]initialized[/] workspace [bold]{paths.root}[/] "
        f"with {len(JURISDICTIONS)} jurisdictions."
    )


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------
@app.command(name="fetch")
def fetch_cmd(
    config: Optional[Path] = CONFIG_OPT,
    workspace: Optional[str] = WORKSPACE_OPT,
    force: bool = typer.Option(False, "--force", "-f",
                               help="Bypass cache and redownload."),
    source: str = typer.Option("socrata", "--source", "-s",
                               help='"socrata" or "flusight".'),
):
    """Fetch the latest CDC weekly hospitalization CSV."""
    cfg, paths, state = _load(config, workspace)
    result = fetch.fetch_cdc_data(cfg, force=force, prefer=source)
    state.last_data_as_of = result.as_of.isoformat()
    state.record("fetch", source=result.source,
                 as_of=result.as_of.isoformat(),
                 rows=result.rows, cached=result.cached,
                 path=str(result.csv_path))
    state.save(paths.state_file)
    console.print(
        f"[green]fetched[/] {result.source} (as_of={result.as_of}, "
        f"rows={result.rows}, cached={result.cached})\n  -> {result.csv_path}"
    )


# ---------------------------------------------------------------------------
# update-exp
# ---------------------------------------------------------------------------
@app.command("update-exp")
def update_exp(
    config: Optional[Path] = CONFIG_OPT,
    workspace: Optional[str] = WORKSPACE_OPT,
    csv: Optional[Path] = typer.Option(
        None, "--csv", help="Specific CSV to use (default: latest in data_cache).",
    ),
):
    """Regenerate per-state .exp files from a CDC CSV."""
    cfg, paths, state = _load(config, workspace)
    csv_path = csv or _latest_cached_csv(cfg.data_cache)
    if csv_path is None:
        raise typer.BadParameter(
            "No CDC CSV available; run `flubnf fetch` first or pass --csv.")
    results = exp_files.generate_exp_files(csv_path, paths, cfg)
    n_ok = sum(1 for r in results if r.n_weeks > 0)
    state.record("update-exp", csv=str(csv_path),
                 n_states=len(results), n_with_data=n_ok)
    state.save(paths.state_file)
    table = Table(title=f"exp files from {csv_path.name}")
    table.add_column("state"); table.add_column("weeks"); table.add_column("last date")
    for r in results:
        table.add_row(r.state, str(r.n_weeks),
                      r.last_date.isoformat() if r.last_date else "-")
    console.print(table)


# ---------------------------------------------------------------------------
# update-files (placeholder for future bounds/beta updates)
# ---------------------------------------------------------------------------
@app.command("update-files")
def update_files(
    config: Optional[Path] = CONFIG_OPT,
    workspace: Optional[str] = WORKSPACE_OPT,
    force: bool = typer.Option(False, "--force", "-f",
                               help="Re-materialize template files."),
):
    """Ensure per-state .bngl and .conf files exist (idempotent)."""
    cfg, paths, state = _load(config, workspace)
    bngl_files.materialize_all(JURISDICTIONS, paths, cfg, force=force)
    conf_files.materialize_all(JURISDICTIONS, paths, cfg, force=force)
    state.record("update-files", n_states=len(JURISDICTIONS), force=force)
    state.save(paths.state_file)
    console.print(f"[green]ensured[/] {len(JURISDICTIONS)} bngl + conf files.")


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------
@app.command()
def analyze(
    config: Optional[Path] = CONFIG_OPT,
    workspace: Optional[str] = WORKSPACE_OPT,
    apply: bool = typer.Option(
        False, "--apply",
        help="Actually edit .conf / .bngl files based on recommendations.",
    ),
    only: Optional[str] = typer.Option(
        None, "--only",
        help="Comma-separated subset of states to analyze.",
    ),
):
    """Analyze last run's results and recommend (or apply) changes.

    Default is dry-run: prints what *would* change. Pass --apply to write."""
    cfg, paths, state = _load(config, workspace)
    states = (
        [s.strip() for s in only.split(",")] if only else list(JURISDICTIONS)
    )
    analyses = auto.analyze_all(paths, cfg, states=states)
    df = auto.analyses_to_dataframe(analyses)
    table = Table(title="analysis summary" + (" [APPLY]" if apply else " [dry-run]"))
    for col in ["state", "best_obj", "n_pop", "n_bounds_changes",
                "needs_new_step", "bounds_summary", "notes"]:
        table.add_column(col)
    for _, row in df.iterrows():
        table.add_row(
            str(row["state"]),
            f"{row['best_obj']:.3g}" if row["best_obj"] is not None else "-",
            str(row["n_pop"]),
            str(row["n_bounds_changes"]),
            str(row["needs_new_step"]),
            str(row["bounds_summary"])[:60],
            str(row["notes"])[:40],
        )
    console.print(table)

    if apply:
        changes = auto.apply_recommendations(analyses, paths, cfg)
        n_with_changes = sum(
            1 for c in changes
            if c.bounds_changed or c.bounds_added
        )
        state.record("analyze-apply", n_changed=n_with_changes)
        state.save(paths.state_file)
        console.print(
            f"[green]applied[/] changes to {n_with_changes} state(s)."
        )
    else:
        state.record("analyze", n_analyzed=len(analyses))
        state.save(paths.state_file)


# ---------------------------------------------------------------------------
# backtest
# ---------------------------------------------------------------------------
@app.command()
def backtest(
    config: Optional[Path] = CONFIG_OPT,
    workspace: Optional[str] = WORKSPACE_OPT,
    states: str = typer.Option(
        "Alabama", "--states", "-s",
        help="Comma-separated state names (e.g. Alabama,Arizona,Texas).",
    ),
    start_week: int = typer.Option(6, help="First 'now' week W."),
    end_week: Optional[int] = typer.Option(
        None, help="Last 'now' week W (defaults to N - max_horizon - 1).",
    ),
    horizons: str = typer.Option("1,2,3,4", help="Forecast horizons in weeks."),
    mode: str = typer.Option(
        "both", "--mode", "-m",
        help="'adaptive', 'static', or 'both' (runs both for comparison).",
    ),
    popsize: int = typer.Option(15, help="DE population size (= AMCMC chain count when -e amcmc)."),
    max_iter: int = typer.Option(300, help="DE max iterations / AMCMC samples."),
    burn_in: int = typer.Option(150, "--burn-in", help="AMCMC burn-in iterations."),
    adaptive_iter: int = typer.Option(150, "--adaptive-iter", help="AMCMC adaptive-proposal iterations."),
    parallel: int = typer.Option(1, "--parallel", help="Number of states fit concurrently (ThreadPool)."),
    pybnf_timeout: float = typer.Option(
        900.0, "--pybnf-timeout",
        help="Per-fit PyBNF subprocess timeout in seconds. Production AMCMC "
             "settings (8000 iter / 2000 burn / 2000 adapt) need ≥3600s.",
    ),
    model_type: Optional[str] = typer.Option(
        None, "--model-type",
        help="Override config model.model_type: 'sir_piecewise' (default) or "
             "'sirs_logistic'. Lets the bake-off select the SIRS model without "
             "editing config files.",
    ),
    resume: bool = typer.Option(
        True, "--resume/--no-resume",
        help="Resume from per-state checkpoint part-files next to --out: skip "
             "already-completed weeks so a killed run (reboot/idle/crash) "
             "continues where it left off. --no-resume starts fresh.",
    ),
    omega: Optional[float] = typer.Option(
        None, "--omega",
        help="Override the fixed SIRS waning rate (per week) for an omega "
             "sensitivity sweep. Only meaningful with --model-type sirs_logistic.",
    ),
    center_mode: Optional[str] = typer.Option(
        None, "--center-mode",
        help="SIRS transition-center placement: 'fixed' (tier-constant) or "
             "'data_driven' (placed on the observed surge per week). Overrides "
             "config.model.center_mode.",
    ),
    seed: int = typer.Option(0, help="DE seed."),
    engine: str = typer.Option(
        "inproc", "--engine", "-e",
        help="'inproc' (scipy DE, fast), 'pybnf' (real PyBNF DE), or 'amcmc' (real PyBNF AMCMC).",
    ),
    no_quantiles: bool = typer.Option(
        False, "--no-quantiles",
        help="Skip quantile forecasts + WIS (faster for quick MAE-only runs).",
    ),
    csv: Optional[Path] = typer.Option(
        None, "--csv",
        help="CDC CSV to source observed data from. "
             "Defaults to latest in the data cache.",
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", "-o",
        help="Path to write per-week records CSV.",
    ),
    record_season: bool = typer.Option(
        False, "--record-season",
        help="After the backtest finishes, snapshot the most recent fit "
             "and observed peak for each state into the historical priors "
             "ledger. Use only on full-season runs.",
    ),
    season_year: Optional[int] = typer.Option(
        None, "--season-year",
        help="Season year tag for --record-season (defaults to config "
             "season.year).",
    ),
):
    """Walk-forward backtest of the auto-pipeline against held-out actuals."""
    import pandas as pd
    cfg, paths, state = _load(config, workspace)
    if model_type is not None or omega is not None or center_mode is not None:
        _mu = {}
        if model_type is not None:
            _mu["model_type"] = model_type
        if omega is not None:
            _mu["omega_fixed"] = omega
        if center_mode is not None:
            _mu["center_mode"] = center_mode
        cfg = cfg.model_copy(update={"model": cfg.model.model_copy(update=_mu)})
    state_list = (
        list(JURISDICTIONS) if states.strip().lower() == "all"
        else [s.strip() for s in states.split(",")]
    )
    horizon_list = [int(h) for h in horizons.split(",")]
    csv_path = csv or _latest_cached_csv(cfg.data_cache)
    if csv_path is None:
        raise typer.BadParameter(
            "No CDC CSV available; run `flubnf fetch` first or pass --csv."
        )
    modes: list[bool] = (
        [True, False] if mode == "both"
        else [True] if mode == "adaptive"
        else [False] if mode == "static"
        else _bad_mode(mode)
    )
    all_records: list[bt.BacktestRecord] = []
    df_raw = pd.read_csv(csv_path)
    geo_col, date_col, val_col = bt._resolve_columns_quick(df_raw, cfg)  # type: ignore[attr-defined]

    # Resolve every state up front so the parallel pool has no shared
    # pandas/df work in flight per worker.
    state_obs: list[tuple[str, "np.ndarray"]] = []  # noqa: F821
    for s in state_list:
        abbrev = STATE_TO_ABBREV.get(s)
        if abbrev is None:
            console.print(f"[yellow]unknown state {s}, skipping[/]")
            continue
        observed = _observed_for_state(
            df_raw, abbrev, cfg, geo_col, date_col, val_col,
        )
        console.print(
            f"[cyan]{s}[/]: {len(observed)} observed weeks "
            f"(peak={observed.max():.0f} at week {int(observed.argmax())})"
        )
        state_obs.append((s, observed))

    # Per-state population (for SIRS absolute-scaling); harmless for piecewise.
    from .constants import load_locations
    _locs = load_locations(cfg.locations_csv)
    model_type = cfg.model.model_type

    # Resume-from-disk: one checkpoint part-file per state, written
    # incrementally by that state's worker. On startup we read any existing
    # part-file and skip weeks already completed (per adaptive mode).
    parts_dir = (out.parent / f"{out.stem}_parts") if out else None
    if parts_dir is not None:
        parts_dir.mkdir(parents=True, exist_ok=True)
        if not resume:
            for s, _ in state_obs:
                p = parts_dir / f"{s}.csv"
                if p.exists():
                    p.unlink()

    def _done_weeks(part_path: Path, adaptive: bool) -> set:
        if part_path is None or not part_path.exists() or part_path.stat().st_size == 0:
            return set()
        try:
            dfp = pd.read_csv(part_path)
            sub = dfp[dfp["adaptive"] == adaptive]
            return set(int(w) for w in sub["week"].tolist())
        except Exception:
            return set()

    def _run_one(s: str, observed) -> list[bt.BacktestRecord]:
        out_records: list[bt.BacktestRecord] = []
        pop = _locs[s].population if s in _locs else None
        cp = (parts_dir / f"{s}.csv") if parts_dir is not None else None
        for adaptive in modes:
            tag = "ADAPT" if adaptive else "STATIC"
            skip = _done_weeks(cp, adaptive) if resume else set()
            if skip:
                console.print(f"  [{s}] {tag} resume: skipping {len(skip)} "
                              f"already-done weeks")
            console.print(f"  [{s}] running {tag} ({model_type})...")
            records = bt.walk_forward(
                s, observed,
                start_week=start_week, end_week=end_week,
                horizons=horizon_list, adaptive=adaptive,
                popsize=popsize, max_iter=max_iter, seed=seed,
                burn_in=burn_in, adaptive_iter=adaptive_iter,
                pybnf_timeout=pybnf_timeout,
                engine=engine,
                workspace_paths=paths if engine in {"pybnf", "amcmc"} else None,
                config=cfg if engine in {"pybnf", "amcmc"} else None,
                quantile_horizons=not no_quantiles,
                model_type=model_type, population=pop,
                checkpoint_path=cp, skip_weeks=skip,
            )
            out_records.extend(records)
        return out_records

    if parallel <= 1:
        for s, observed in state_obs:
            all_records.extend(_run_one(s, observed))
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futs = {pool.submit(_run_one, s, observed): s for s, observed in state_obs}
            for fut in as_completed(futs):
                s = futs[fut]
                try:
                    all_records.extend(fut.result())
                except Exception as e:
                    console.print(f"[red]{s} failed:[/] {e}")

    # Build the consolidated frame from the per-state checkpoint part-files
    # (the durable source of truth — includes weeks completed on prior,
    # since-killed runs). Fall back to in-memory records if no parts exist.
    df_out = bt.records_to_dataframe(all_records)
    if parts_dir is not None:
        part_frames = []
        for s, _ in state_obs:
            p = parts_dir / f"{s}.csv"
            if p.exists() and p.stat().st_size > 0:
                try:
                    part_frames.append(pd.read_csv(p))
                except Exception:
                    pass
        if part_frames:
            merged = pd.concat(part_frames, ignore_index=True)
            # Dedupe (state, week, adaptive), keeping the most recent fit.
            merged = merged.drop_duplicates(
                subset=["state", "week", "adaptive"], keep="last"
            ).reset_index(drop=True)
            df_out = merged
    # Write the per-week records CSV FIRST so that a downstream summary
    # crash (e.g. empty groupby when every fit timed out) does not wipe
    # the data the user just spent hours computing.
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        df_out.to_csv(out, index=False)
        console.print(f"[green]wrote[/] {out} ({len(df_out)} rows)")
    # Summary table — only if we have records with a `state` column.
    if not df_out.empty and "state" in df_out.columns:
        agg = {
            "n_weeks": ("week", "count"),
            "mean_mae": ("mae", "mean"),
            "mean_rmse": ("rmse", "mean"),
            "mean_mape": ("mape", "mean"),
            "final_n_steps": ("n_steps", "last"),
        }
        if "wis_mean" in df_out.columns:
            agg["mean_wis"] = ("wis_mean", "mean")
        summary = df_out.groupby(["state", "adaptive"]).agg(**agg).reset_index()
        console.print(summary.to_string(index=False))
    else:
        console.print(
            "[yellow]no records to summarise — every fit was skipped or "
            "failed. Check the log for `pybnf timeout` or `fit failed` "
            "lines.[/]"
        )
    state.record("backtest", n_states=len(state_list),
                 modes=mode, weeks=f"{start_week}..{end_week or 'auto'}")
    state.save(paths.state_file)

    # Auto-record season summaries to the historical priors ledger when
    # requested. We only auto-record from the *adaptive* run (true=, the
    # one we'd actually submit) and use the most-recent fit per state.
    if record_season and engine in {"amcmc", "pybnf"}:
        from .historical_priors import record_season as _rs
        from .results import read_de_results, read_amcmc_chain
        hp_dir = paths.root.parent.parent / "data" / "historical_priors"
        yr = season_year if season_year is not None else cfg.season.year
        n_recorded = 0
        for s in state_list:
            abbrev = STATE_TO_ABBREV.get(s)
            if abbrev is None:
                continue
            de = read_de_results(paths.results_for(s), s)
            chain = read_amcmc_chain(paths.results_for(s), s)
            pop = (chain if chain is not None and not chain.empty
                   else (de.population if de is not None else None))
            if pop is None or pop.empty:
                continue
            try:
                obs = _observed_for_state(
                    df_raw, abbrev, cfg, geo_col, date_col, val_col,
                )
                _rs(hp_dir, s, yr, pop, obs,
                    n_steps_final=int(df_out[df_out["state"] == s]
                                       ["n_steps"].max()))
                n_recorded += 1
            except Exception as e:
                console.print(f"[yellow]record-season failed for {s}: {e}[/]")
        console.print(
            f"[green]recorded[/] {n_recorded} state season(s) "
            f"for {yr} -> `{hp_dir}`."
        )


def _bad_mode(mode: str):
    raise typer.BadParameter(f"unknown mode: {mode}")


def _observed_for_state(df, abbrev, cfg, geo_col, date_col, val_col):
    import pandas as pd
    import numpy as np
    import pymmwr as pm
    sub = df[df[geo_col] == abbrev].copy()
    sub["_d"] = pd.to_datetime(sub[date_col]) - pd.Timedelta(days=1)
    sub = sub.sort_values("_d")
    onset = pm.epiweek_to_date(pm.Epiweek(cfg.season.year, cfg.season.onset_week))
    end = pm.epiweek_to_date(pm.Epiweek(
        cfg.season.year + cfg.season.end_year_offset, cfg.season.end_week))
    in_season = sub[(sub["_d"].dt.date >= onset) & (sub["_d"].dt.date < end)]
    y = in_season[val_col].to_numpy(dtype=float)
    if np.any(np.isnan(y)):
        y = y[: int(np.argmax(np.isnan(y)))]
    return y


# ---------------------------------------------------------------------------
# weekly-job — the one-click "do everything for this week" command
# ---------------------------------------------------------------------------
@app.command("weekly-job")
def weekly_job(
    config: Optional[Path] = CONFIG_OPT,
    workspace: Optional[str] = WORKSPACE_OPT,
    states: str = typer.Option(
        "all", "--states", "-s",
        help="Comma-separated state names, or 'all' for every jurisdiction.",
    ),
    reference_date: Optional[str] = typer.Option(
        None, "--reference-date", "-d",
        help="FluSight reference Saturday (YYYY-MM-DD). Defaults to upcoming.",
    ),
    csv: Optional[Path] = typer.Option(
        None, "--csv", help="Override CDC CSV source (else fetch latest).",
    ),
    method: str = typer.Option(
        "am", "--method",
        help="'am' (AMCMC, default — beats team WIS) or 'de' (faster).",
    ),
    popsize: int = typer.Option(
        1, help="DE pop / AMCMC parallel chains (AM default 1 for laptop).",
    ),
    max_iter: int = typer.Option(
        800, help="DE iterations / AMCMC total iterations.",
    ),
    burn_in: int = typer.Option(150, help="AMCMC burn-in iterations."),
    adaptive_iter: int = typer.Option(150, help="AMCMC adaptive-proposal iterations."),
    parallel: int = typer.Option(1, "--parallel", "-p"),
    no_resume: bool = typer.Option(
        False, "--no-resume",
        help="Disable resume — refit every state from scratch even if a "
             "fresh fit already exists for this reference_date.",
    ),
):
    """One-click weekly FluSight workflow: fetch -> exp -> fit -> submission."""
    from datetime import date as _date
    cfg, paths, state_obj = _load(config, workspace)
    state_list = (
        list(JURISDICTIONS) if states == "all"
        else [s.strip() for s in states.split(",")]
    )
    ref = _date.fromisoformat(reference_date) if reference_date else None

    def _progress(state: str, status: str):
        color = {"fitting": "yellow", "ok": "green", "fit-failed": "red"}.get(status, "dim")
        console.print(f"  [{color}]{status:11s}[/] {state}")

    res = wjmod.run_weekly_job(
        cfg, paths,
        reference_date=ref, csv=csv, states=state_list,
        method=method,
        popsize=popsize, max_iter=max_iter,
        burn_in=burn_in, adaptive=adaptive_iter,
        parallel=parallel,
        resume=not no_resume,
        on_progress=_progress,
    )
    console.print(
        f"\n[bold]done[/]  reference_date={res.reference_date}  "
        f"ok={res.n_ok}/{len(res.states)}  "
        f"submission={res.submission_csv}"
    )
    state_obj.record("weekly-job", n_ok=res.n_ok, n_states=len(res.states),
                     submission=str(res.submission_csv) if res.submission_csv else None)
    state_obj.save(paths.state_file)


# ---------------------------------------------------------------------------
# score-team
# ---------------------------------------------------------------------------
@app.command("score-team")
def score_team(
    config: Optional[Path] = CONFIG_OPT,
    submission_dir: Path = typer.Option(
        Path("data/flusight"), help="Directory containing team submission CSVs.",
    ),
    target: Path = typer.Option(
        Path("data/flusight_target/target-hospital-admissions.csv"),
        help="FluSight target-data CSV (ground truth).",
    ),
    out: Path = typer.Option(
        Path("backtest_results/flusight_team_scored.csv"),
        "--out", "-o", help="Where to write per-row scored output.",
    ),
):
    """Score team FluSight submissions against ground truth (WIS)."""
    cfg = FluBNFConfig.load(config_path=config)
    paths_in = sorted(submission_dir.glob("*.csv"))
    if not paths_in:
        raise typer.BadParameter(f"no CSVs found in {submission_dir}")
    if not target.exists():
        raise typer.BadParameter(f"target file missing: {target}")
    df = flusight.score_all_submissions(paths_in, target)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    console.print(f"[green]scored[/] {len(df)} rows from {len(paths_in)} files -> {out}")
    by_horizon = df.groupby("horizon")["wis"].agg(["count", "mean", "median"]).round(2)
    console.print(by_horizon.to_string())


# ---------------------------------------------------------------------------
# validate-submission
# ---------------------------------------------------------------------------
@app.command("validate-submission")
def validate_submission_cmd(
    csv_path: Path = typer.Argument(
        ..., help="Path to a FluSight-format submission CSV.",
    ),
    strict: bool = typer.Option(
        False, "--strict",
        help="Exit non-zero on any error (suitable for CI / pre-commit).",
    ),
):
    """Validate a submission CSV against the FluSight hub schema."""
    from .validate import validate_submission_csv
    if not csv_path.exists():
        raise typer.BadParameter(f"file not found: {csv_path}")
    report = validate_submission_csv(csv_path)
    table = Table(title=f"validation: {csv_path.name}")
    table.add_column("level")
    table.add_column("message")
    for w in report.warnings:
        table.add_row("[yellow]warning[/]", w)
    for e in report.errors:
        table.add_row("[red]error[/]", e)
    if not report.warnings and not report.errors:
        table.add_row("[green]ok[/]", "all checks passed")
    console.print(table)
    if not report.ok and strict:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# clean-cache
# ---------------------------------------------------------------------------
@app.command("clean-cache")
def clean_cache_cmd(
    config: Optional[Path] = CONFIG_OPT,
    keep: int = typer.Option(
        5, "--keep", "-k",
        help="Number of most-recent cache CSVs to retain.",
    ),
    workspaces: bool = typer.Option(
        False, "--workspaces",
        help="Also remove stale workspaces with no submissions or "
             "sessions in the last 30 days.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Print what would be deleted without actually removing.",
    ),
):
    """Remove old CDC CSV cache files and (optionally) stale workspaces."""
    import time
    cfg = FluBNFConfig.load(config_path=config)
    removed: list[Path] = []
    if cfg.data_cache.exists():
        csvs = sorted(cfg.data_cache.glob("*.csv"))
        if len(csvs) > keep:
            for p in csvs[:-keep]:
                removed.append(p)
                if not dry_run:
                    p.unlink()
    if workspaces and cfg.workspace_root.exists():
        cutoff = time.time() - 30 * 24 * 3600
        for ws in cfg.workspace_root.iterdir():
            if not ws.is_dir():
                continue
            # Latest mtime across submissions + sessions.
            latest = max(
                (p.stat().st_mtime for p in
                 list((ws / "submissions").glob("*.csv")) +
                 list((ws / "sessions").glob("*.json"))),
                default=0,
            )
            if latest and latest < cutoff:
                removed.append(ws)
                if not dry_run:
                    import shutil
                    shutil.rmtree(ws)
    if removed:
        verb = "would remove" if dry_run else "removed"
        console.print(f"[yellow]{verb}[/] {len(removed)} item(s):")
        for p in removed:
            console.print(f"  • {p}")
    else:
        console.print("[green]nothing to clean[/]")


# ---------------------------------------------------------------------------
# record-season
# ---------------------------------------------------------------------------
@app.command("record-season")
def record_season_cmd(
    config: Optional[Path] = CONFIG_OPT,
    workspace: Optional[str] = WORKSPACE_OPT,
    state: str = typer.Option(..., "--state", "-s",
                              help="State name (Underscore_form)."),
    season_year: int = typer.Option(..., "--season-year",
                                    help="Season start year (e.g. 2025)."),
    csv: Optional[Path] = typer.Option(
        None, "--csv",
        help="CDC CSV to source the full-season observed series from. "
             "Defaults to the latest in the data cache.",
    ),
    n_steps_final: int = typer.Option(1, help="Final piecewise step count."),
):
    """Snapshot the most recent fit + observed peak for one state into
    `data/historical_priors/<state>.json` so next year's run uses it
    as an informed prior."""
    import pandas as pd
    from .historical_priors import record_season
    from .results import read_de_results
    cfg, paths, state_obj = _load(config, workspace)
    de = read_de_results(paths.results_for(state), state)
    if de is None or de.population.empty:
        raise typer.BadParameter(
            f"no fit results for {state} in workspace; run weekly-job "
            f"or backtest first."
        )
    # Pull the observed full-season series.
    csv_path = csv or _latest_cached_csv(cfg.data_cache)
    if csv_path is None:
        raise typer.BadParameter("no CDC CSV cached; run flubnf fetch first.")
    df_raw = pd.read_csv(csv_path)
    geo_col, date_col, val_col = bt._resolve_columns_quick(df_raw, cfg)
    obs = _observed_for_state(
        df_raw, STATE_TO_ABBREV[state], cfg, geo_col, date_col, val_col,
    )
    hp_dir = paths.root.parent.parent / "data" / "historical_priors"
    hist = record_season(
        hp_dir, state, season_year, de.population, obs,
        n_steps_final=n_steps_final,
    )
    console.print(
        f"[green]recorded[/] season {season_year} for {state} "
        f"(peak={hist.seasons[-1].peak_admissions:.0f}, "
        f"K_final={n_steps_final}). "
        f"History now has {len(hist.seasons)} season(s)."
    )


# ---------------------------------------------------------------------------
# backfill-priors — bulk-record legacy PyBNF runs into historical_priors/
# ---------------------------------------------------------------------------
@app.command("backfill-priors")
def backfill_priors_cmd(
    config: Optional[Path] = CONFIG_OPT,
    workspace: Optional[str] = WORKSPACE_OPT,
    source: Path = typer.Option(
        ..., "--source",
        help="Directory containing per-state PyBNF results "
             "(<source>/<State>/Results/sorted_params_final.txt).",
    ),
    season_year: int = typer.Option(
        ..., "--year",
        help="Season start year these fits represent (e.g. 2024 for the "
             "2024-25 season).",
    ),
    target_csv: Optional[Path] = typer.Option(
        None, "--target",
        help="FluSight target-hospital-admissions.csv. Defaults to the "
             "cached copy at <FluBNF>/data/flusight_target/target-"
             "hospital-admissions.csv if it exists.",
    ),
    states: str = typer.Option(
        "all", "--states",
        help="Comma-separated state names, or 'all' for everything found "
             "under --source.",
    ),
    n_steps_final: int = typer.Option(
        1, "--n-steps-final",
        help="Final piecewise-K to tag for the recorded entries.",
    ),
    force: bool = typer.Option(
        False, "--force",
        help="Overwrite an existing entry for this season year (default: skip).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Print what would be written without touching disk.",
    ),
):
    """Bulk-import legacy PyBNF posteriors into `data/historical_priors/`.

    Saves you from running `record-season` once per state. Idempotent —
    re-runs skip states that already have an entry for this --year, unless
    --force is passed.
    """
    from . import backfill_priors as bp
    from .constants import load_locations

    cfg, paths, _ = _load(config, workspace)

    if target_csv is None:
        # Fall back to the bundled / previously-fetched FluSight target.
        default_target = (
            paths.root.parent.parent / "data" / "flusight_target"
            / "target-hospital-admissions.csv"
        )
        target_csv = default_target
    if not target_csv.exists():
        raise typer.BadParameter(
            f"target CSV not found at {target_csv}; pass --target or "
            f"run `flubnf fetch` first."
        )

    locations = load_locations(cfg.locations_csv)
    hp_dir = paths.root.parent.parent / "data" / "historical_priors"

    wanted: Optional[list[str]] = None
    if states.strip().lower() != "all":
        wanted = [s.strip() for s in states.split(",") if s.strip()]

    outcomes = bp.backfill_all(
        hp_dir,
        season_year=season_year,
        results_root=source,
        target_csv=target_csv,
        locations=locations,
        states=wanted,
        onset_week=cfg.season.onset_week,
        end_year_offset=cfg.season.end_year_offset,
        end_week=cfg.season.end_week,
        n_steps_final=n_steps_final,
        force=force,
        dry_run=dry_run,
    )

    if not outcomes:
        console.print(
            f"[yellow]no states found under {source} (looked for "
            f"<state>/Results/sorted_params_final.txt).[/]"
        )
        return

    tbl = Table(title=f"backfill-priors — season {season_year}"
                + (" (dry-run)" if dry_run else ""))
    for col in ("state", "status", "peak", "n_params", "note"):
        tbl.add_column(col)
    counts: dict[str, int] = {}
    for o in outcomes:
        counts[o.status] = counts.get(o.status, 0) + 1
        color = {
            "ok": "green", "skipped-exists": "dim",
            "no-fit": "yellow", "no-observed": "yellow",
            "error": "red",
        }.get(o.status, "")
        status_s = f"[{color}]{o.status}[/]" if color else o.status
        tbl.add_row(
            o.state, status_s,
            f"{o.peak:.0f}" if o.peak else "—",
            str(o.n_params) if o.n_params else "—",
            o.message or "",
        )
    console.print(tbl)
    summary = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    console.print(f"\n[bold]done[/]  {summary}")


# ---------------------------------------------------------------------------
# tune-slope
# ---------------------------------------------------------------------------
def _tune_slope_for_state(
    state: str,
    *,
    sub_df,
    df_raw,
    cfg,
    locs,
    paths,
    geo_col: str,
    date_col: str,
    val_col: str,
):
    """Per-state sweep helper. Returns (status, result, recommendation).

    status ∈ {"ok", "no-traj", "no-rows", "no-observed", "no-actuals"}.
    result is the SlopeTuneResult (may be empty rows) or None when status
    is non-ok. recommendation is the picked blend or None.
    """
    import numpy as _np
    import pandas as _pd  # noqa: F401  (kept for parity with caller imports)
    from datetime import timedelta as _td
    import pymmwr as pm
    from .amcmc import read_traj_noise
    from .slope_tune import recommend_blend, sweep_slope_blend

    traj = read_traj_noise(paths.results_for(state), state)
    if traj is None:
        return "no-traj", None, None

    fips = locs[state].fips
    sub_state = sub_df[sub_df["location"].astype(str).str.zfill(2) == fips]
    sub_state = sub_state[sub_state["output_type"] == "quantile"]
    if sub_state.empty:
        return "no-rows", None, None
    ref_date = str(sub_state["reference_date"].iloc[0])

    obs = _observed_for_state(
        df_raw, locs[state].abbreviation, cfg, geo_col, date_col, val_col,
    )
    if obs is None or len(obs) == 0:
        return "no-observed", None, None

    onset_sat = pm.epiweek_to_date(pm.Epiweek(
        cfg.season.year, cfg.season.onset_week))
    obs_by_date = {(onset_sat + _td(days=7 * i)).isoformat(): float(obs[i])
                   for i in range(len(obs)) if _np.isfinite(obs[i])}

    actuals: dict[int, float] = {}
    for h_idx, group in sub_state.groupby("horizon"):
        target_end = str(group["target_end_date"].iloc[0])
        v = obs_by_date.get(target_end)
        if v is not None:
            actuals[int(h_idx) + 1] = v   # FluSight h0 -> internal h1
    if not actuals:
        return "no-actuals", None, None

    n_observed = sum(1 for d in obs_by_date if d <= ref_date)
    res = sweep_slope_blend(
        traj, _np.asarray(obs[:n_observed], dtype=float),
        actuals, state=state,
    )
    rec = recommend_blend(res)
    return "ok", res, rec


def _render_sweep_table(res) -> Table:
    import numpy as _np
    table = Table(title=f"slope_blend sweep — {res.state}")
    table.add_column("slope_blend"); table.add_column("mean WIS")
    table.add_column("per-horizon"); table.add_column("n_h")
    for r in res.rows:
        sb_label = "adaptive" if r.slope_blend == -1.0 else f"{r.slope_blend:.2f}"
        per_h_str = " ".join(
            f"{v:.1f}" if _np.isfinite(v) else "nan"
            for v in r.per_horizon_wis
        )
        table.add_row(sb_label, f"{r.mean_wis:.2f}", per_h_str, str(r.n_horizons))
    return table


@app.command("tune-slope")
def tune_slope_cmd(
    config: Optional[Path] = CONFIG_OPT,
    workspace: Optional[str] = WORKSPACE_OPT,
    state: Optional[str] = typer.Option(
        None, "--state", "-s",
        help="State name (Underscore_form). Required unless --all-states.",
    ),
    all_states: bool = typer.Option(
        False, "--all-states",
        help="Sweep every jurisdiction with submissions+actuals on disk. "
             "Prints a one-line-per-state summary; mutually exclusive with "
             "--state.",
    ),
    apply: bool = typer.Option(
        False, "--apply",
        help="Persist the recommended slope_blend into each state's session "
             "tuning. Without this, prints sweep results only.",
    ),
    min_improvement: float = typer.Option(
        0.05, "--min-improvement",
        help="Mean-WIS reduction below this is treated as noise.",
    ),
):
    """Sweep slope_blend candidates against last week's now-observed actuals.

    Uses the existing AMCMC trajectory on disk — does NOT re-fit. The sweep
    is cheap; running it weekly after actuals come in is the intended use.
    With --all-states, loops every jurisdiction and prints a summary table.
    """
    import pandas as _pd
    from .constants import load_locations
    from .session import load_session, save_session
    from .slope_tune import recommend_blend

    if all_states and state:
        raise typer.BadParameter("--state and --all-states are mutually exclusive.")
    if not all_states and not state:
        raise typer.BadParameter("provide --state NAME or --all-states.")

    cfg, paths, _ = _load(config, workspace)

    sub_dir = paths.root / "submissions"
    subs = sorted(sub_dir.glob("*.csv")) if sub_dir.exists() else []
    if not subs:
        raise typer.BadParameter(
            f"no submissions in {sub_dir}; can't pull actuals for scoring."
        )
    sub_df = _pd.read_csv(subs[-1], dtype={"location": str})

    csv_path = _latest_cached_csv(cfg.data_cache)
    if csv_path is None:
        raise typer.BadParameter("no CDC CSV cached; run flubnf fetch first.")
    df_raw = _pd.read_csv(csv_path)
    geo_col, date_col, val_col = bt._resolve_columns_quick(df_raw, cfg)
    locs = load_locations(cfg.locations_csv)

    def _apply_for(s: str, rec: float) -> str:
        sess = load_session(paths.root, s)
        if sess is None:
            return "no-session"
        sess.tuning["slope_blend"] = float(rec)
        save_session(paths.root, sess)
        return "applied"

    if not all_states:
        status, res, rec = _tune_slope_for_state(
            state, sub_df=sub_df, df_raw=df_raw, cfg=cfg, locs=locs,
            paths=paths, geo_col=geo_col, date_col=date_col, val_col=val_col,
        )
        _reason = {
            "no-traj": "no AMCMC trajectory on disk — run weekly-job first.",
            "no-rows": "no rows for this state in the latest submission.",
            "no-observed": "no observed series for this state.",
            "no-actuals": "no actuals observed yet for the most-recent "
                          "submission's horizons; come back next week.",
        }
        if status != "ok":
            raise typer.BadParameter(_reason[status])

        console.print(_render_sweep_table(res))
        # Re-apply the user's threshold (helper used the default).
        rec = recommend_blend(res, min_improvement=min_improvement)
        if rec is None:
            console.print(
                f"\n[dim]no recommendation — improvement below threshold "
                f"({min_improvement}) or insufficient horizons[/]"
            )
            return
        delta = res.improvement_vs_baseline()
        console.print(
            f"\n[green]recommended slope_blend = {rec}[/] "
            f"(improvement vs baseline: {delta:.2f} WIS units)"
        )
        if apply:
            outcome = _apply_for(state, rec)
            if outcome == "applied":
                console.print(f"[green]applied[/] slope_blend={rec} to session for {state}")
            else:
                console.print("[yellow]no session on disk; nothing applied[/]")
        return

    # --all-states branch
    summary = Table(title="slope_blend sweep — all states")
    for col in ("state", "status", "baseline WIS", "best WIS",
                "best blend", "Δ WIS", "recommended", "action"):
        summary.add_column(col)

    n_recommended = 0
    n_applied = 0
    n_ok = 0
    for s in JURISDICTIONS:
        status, res, _rec_default = _tune_slope_for_state(
            s, sub_df=sub_df, df_raw=df_raw, cfg=cfg, locs=locs,
            paths=paths, geo_col=geo_col, date_col=date_col, val_col=val_col,
        )
        if status != "ok":
            summary.add_row(s, status, "—", "—", "—", "—", "—", "—")
            continue
        n_ok += 1
        base = res.baseline
        best = res.best
        rec = recommend_blend(res, min_improvement=min_improvement)
        base_w = f"{base.mean_wis:.2f}" if base and base.mean_wis == base.mean_wis else "nan"
        best_w = f"{best.mean_wis:.2f}" if best and best.mean_wis == best.mean_wis else "nan"
        best_sb = ("adaptive" if best and best.slope_blend == -1.0
                   else f"{best.slope_blend:.2f}" if best else "—")
        delta = res.improvement_vs_baseline()
        delta_s = f"{delta:+.2f}" if delta is not None else "—"
        rec_s = (
            "adaptive" if rec == -1.0
            else f"{rec:.2f}" if rec is not None
            else "[dim]hold[/]"
        )
        action = "—"
        if rec is not None:
            n_recommended += 1
            if apply:
                outcome = _apply_for(s, rec)
                action = "[green]applied[/]" if outcome == "applied" else outcome
                if outcome == "applied":
                    n_applied += 1
        summary.add_row(s, status, base_w, best_w, best_sb, delta_s, rec_s, action)

    console.print(summary)
    console.print(
        f"\n[bold]done[/]  swept={n_ok}/{len(JURISDICTIONS)}  "
        f"recommended={n_recommended}  applied={n_applied}"
    )


# ---------------------------------------------------------------------------
# baseline-score — score persistence/rolling baselines alongside our model
# ---------------------------------------------------------------------------
@app.command("baseline-score")
def baseline_score_cmd(
    config: Optional[Path] = CONFIG_OPT,
    workspace: Optional[str] = WORKSPACE_OPT,
    target_csv: Optional[Path] = typer.Option(
        None, "--target",
        help="FluSight target-hospital-admissions.csv (defaults to "
             "<FluBNF>/data/flusight_target/target-hospital-admissions.csv).",
    ),
    rolling_window: int = typer.Option(4, "--rolling-window"),
    persistence_lookback: int = typer.Option(6, "--persistence-lookback"),
    horizon: Optional[int] = typer.Option(
        None, "--horizon",
        help="Restrict the table to one horizon (0..3). Defaults to all.",
    ),
):
    """Score every submission in this workspace against the persistence
    and rolling-mean baselines.

    A per-(state, horizon) table — if `model_vs_persistence` is negative,
    our model is doing *worse* than just predicting last week's value, a
    strong red flag for that state.
    """
    from . import baseline_forecast as bf
    from .constants import load_locations

    cfg, paths, _ = _load(config, workspace)
    sub_dir = paths.root / "submissions"
    if not sub_dir.exists() or not list(sub_dir.glob("*.csv")):
        raise typer.BadParameter(
            f"no submissions in {sub_dir}; run weekly-job first."
        )
    if target_csv is None:
        target_csv = (paths.root.parent.parent / "data" / "flusight_target"
                      / "target-hospital-admissions.csv")
    if not target_csv.exists():
        raise typer.BadParameter(
            f"target CSV not found at {target_csv}; pass --target or fetch."
        )

    locations = load_locations(cfg.locations_csv)
    long_df = bf.score_submissions_vs_baselines(
        sub_dir, target_csv, locations,
        rolling_window=rolling_window,
        persistence_lookback=persistence_lookback,
    )
    if long_df.empty:
        console.print(
            "[yellow]no scored rows — no submissions had matching actuals "
            "in the target CSV.[/]"
        )
        return
    agg = bf.aggregate_baseline_comparison(long_df)
    if horizon is not None:
        agg = agg[agg["horizon"] == int(horizon)]

    tbl = Table(title="baseline comparison — model vs persistence vs rolling")
    for col in ("state", "h", "n", "model", "persist", "rolling",
                "Δ(persist−model)", "Δ(rolling−model)"):
        tbl.add_column(col)
    for _, r in agg.iterrows():
        delta_p = r["model_vs_persistence"]
        delta_r = r["model_vs_rolling"]
        color_p = "green" if delta_p > 0 else "red"
        color_r = "green" if delta_r > 0 else "red"
        tbl.add_row(
            r["state"], str(int(r["horizon"])), str(int(r["n_cells"])),
            f"{r['model_wis']:.2f}",
            f"{r['persistence_wis']:.2f}",
            f"{r['rolling_wis']:.2f}",
            f"[{color_p}]{delta_p:+.2f}[/]",
            f"[{color_r}]{delta_r:+.2f}[/]",
        )
    console.print(tbl)

    wins_p = int((agg["model_vs_persistence"] > 0).sum())
    wins_r = int((agg["model_vs_rolling"] > 0).sum())
    console.print(
        f"\n[bold]summary[/]  cells={len(agg)}  "
        f"model beats persistence: {wins_p}/{len(agg)}  "
        f"model beats rolling: {wins_r}/{len(agg)}"
    )


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------
@app.command()
def doctor(
    config: Optional[Path] = CONFIG_OPT,
    workspace: Optional[str] = WORKSPACE_OPT,
    online: bool = typer.Option(
        False, "--online",
        help="Include network checks (CDC reachability).",
    ),
    pre_studio: bool = typer.Option(
        False, "--pre-studio",
        help="Add extra readiness checks meaningful before a long Mac "
             "Studio run: historical-priors schema, locations.csv schema, "
             "all state templates, fringe detectors, FluSight target "
             "archive, submission validator, BNG2.pl executable.",
    ),
):
    """Diagnose the environment, dependencies, and workspace state.

    Catches the common showstoppers — broken venv, missing BNG2.pl,
    NumPy 2.0 / pybnf incompat patch missing, CDC schema drift — before
    they bite mid-run. `--pre-studio` adds extra Mac-Studio-readiness
    checks (cheap; failing one now beats failing 6 hours in).
    """
    from . import doctor as docmod
    cfg = FluBNFConfig.load(config_path=config)
    rep = docmod.run_doctor(
        cfg, workspace=workspace, online=online, pre_studio=pre_studio,
    )

    table = Table(title="FluBNF doctor")
    table.add_column("status"); table.add_column("check"); table.add_column("detail")
    color = {
        docmod.Status.OK: "green",
        docmod.Status.WARN: "yellow",
        docmod.Status.FAIL: "red",
    }
    for c in rep.checks:
        table.add_row(
            f"[{color[c.status]}]{c.status.value}[/]",
            c.name, c.detail,
        )
    console.print(table)

    # Surface hints below the table for any WARN/FAIL.
    hints = [c for c in rep.checks if c.hint and c.status is not docmod.Status.OK]
    if hints:
        console.print("\n[bold]hints[/]")
        for c in hints:
            console.print(f"  • [{color[c.status]}]{c.name}[/]: {c.hint}")

    console.print(
        f"\n[bold]summary:[/] "
        f"{len(rep.checks) - rep.n_fail - rep.n_warn} ok, "
        f"[yellow]{rep.n_warn} warn[/], "
        f"[red]{rep.n_fail} fail[/]"
    )
    if rep.n_fail:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------
@app.command()
def compare(
    config: Optional[Path] = CONFIG_OPT,
    workspace: Optional[str] = WORKSPACE_OPT,
    state: str = typer.Option("Alabama", "--state", "-s",
                              help="State to compare."),
    backtest_csv: Path = typer.Option(
        ..., "--backtest", "-b",
        help="Per-week backtest CSV from `flubnf backtest -o ...`.",
    ),
    team_csv: Path = typer.Option(
        Path("backtest_results/flusight_team_scored.csv"),
        "--team",
        help="Team-scored CSV from `flubnf score-team`.",
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", "-o", help="Write the per-row alignment to a CSV.",
    ),
):
    """Side-by-side: our backtest WIS vs team's actual WIS, per (week, horizon)."""
    cfg = FluBNFConfig.load(config_path=config)
    df = cmp_mod.align_backtest_with_team(backtest_csv, team_csv, state, cfg)
    summary = cmp_mod.summarize_alignment(df)
    console.print(f"\n[bold]{state} — per-horizon summary[/]")
    console.print(summary.round(2).to_string(index=False))
    if "our_wis_adapt" in df.columns and "team_wis" in df.columns:
        delta = df["our_wis_adapt"] - df["team_wis"]
        wins = (delta < 0).sum()
        console.print(
            f"\nadaptive vs team: ours WINS on "
            f"{wins} / {len(df)} (state, horizon, week) cells "
            f"(mean delta = {delta.mean():.2f})"
        )
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        console.print(f"[green]wrote[/] {out}")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------
@app.command()
def run(
    config: Optional[Path] = CONFIG_OPT,
    workspace: Optional[str] = WORKSPACE_OPT,
    only: Optional[str] = typer.Option(
        None, "--only", help="Comma-separated subset of states to run.",
    ),
    parallel: int = typer.Option(
        1, "--parallel", "-p",
        help="Number of concurrent PyBNF subprocesses.",
    ),
    pybnf_command: str = typer.Option(
        "pybnf", "--pybnf", help="PyBNF executable name or path.",
    ),
    skip_fresh: bool = typer.Option(
        True, "--skip-fresh/--rerun-fresh",
        help="Skip states whose Results/sorted_params_final.txt already exists.",
    ),
):
    """Launch PyBNF for the requested states."""
    cfg, paths, state = _load(config, workspace)
    states = (
        [s.strip() for s in only.split(",")] if only else list(JURISDICTIONS)
    )
    if skip_fresh:
        before = len(states)
        states = [s for s in states if runs.needs_rerun(s, paths)]
        console.print(f"[dim]skipping {before - len(states)} states with fresh fits[/]")
    if not states:
        console.print("[yellow]nothing to do[/]")
        return
    console.print(f"running {len(states)} states with parallel={parallel}...")
    results = runs.run_many(
        states, paths, cfg, parallel=parallel, pybnf_command=pybnf_command,
    )
    table = Table(title="run results")
    table.add_column("state"); table.add_column("rc"); table.add_column("seconds"); table.add_column("log")
    for r in results:
        table.add_row(r.state, str(r.returncode), f"{r.seconds:.1f}",
                      str(r.log.relative_to(paths.root)))
    console.print(table)
    state.record("run", n_states=len(results),
                 n_ok=sum(1 for r in results if r.ok),
                 parallel=parallel)
    state.save(paths.state_file)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------
@app.command()
def status(
    config: Optional[Path] = CONFIG_OPT,
    workspace: Optional[str] = WORKSPACE_OPT,
):
    """Show workspace status."""
    cfg, paths, state = _load(config, workspace)
    console.print(f"[bold]workspace:[/] {paths.root}")
    console.print(f"[bold]season:[/] {cfg.season.year}")
    console.print(f"[bold]last fetch:[/] {state.last_data_as_of or '-'}")
    n_bngl = len(list(paths.bngl_dir.glob("*.bngl")))
    n_conf = len(list(paths.conf_dir.glob("*.conf")))
    n_exp = len(list(paths.exp_dir.glob("*_flu.exp")))
    console.print(f"[bold]files:[/] bngl={n_bngl}  conf={n_conf}  exp={n_exp}")
    if state.stages:
        table = Table(title="recent stages")
        table.add_column("ts"); table.add_column("stage"); table.add_column("status"); table.add_column("details")
        for s in state.stages[-10:]:
            table.add_row(s.ts, s.name, s.status, ", ".join(f"{k}={v}" for k, v in s.details.items()))
        console.print(table)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _latest_cached_csv(cache_dir: Path) -> Optional[Path]:
    if not cache_dir.exists():
        return None
    csvs = sorted(cache_dir.glob("*.csv"))
    return csvs[-1] if csvs else None


@app.callback()
def _root(verbose: bool = typer.Option(False, "--verbose", "-v")):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


if __name__ == "__main__":
    app()


# ---------------------------------------------------------------------------
# Console launch survival: single instance, free-port fallback, load watchdog
# ---------------------------------------------------------------------------
# A relaunched console could bind its window to a dying predecessor's server
# (the port probe passes, then the old process exits) or lose the port to it
# outright, leaving a randomly dead window. Three guards, all field-driven:
# take over from the predecessor via a pidfile, fall back to a nearby free
# port when the preferred one stays bound, and watch the window's loaded
# event so a page that never arrived is reloaded instead of shown dead.

# the pidfile lives with the app's other state, next to retro/ and ledger
APP_PID_FILE = (Path(__file__).resolve().parents[1]
                / "app" / "state" / "app.pid")
# the predecessor check requires one of these substrings in the process
# command line before anything is signalled. They are command-shaped on
# purpose: a bare "flubnf" would match ANY process started from this venv
# (the interpreter path contains it), so a recycled pid landing on, say, a
# multi-hour PyBNF fit could be killed. "flubnf app" and "flubnf window"
# cover every launch path (FluBNF.command's `.venv/bin/flubnf app`, a
# manual `flubnf window`, extra flags after the command). The .exe forms
# are the same entry points as Windows spells them (FluBNF.bat launches
# `.venv\Scripts\flubnf.exe app`); they never match elsewhere.
APP_ENTRY_MARKERS = ("flubnf app", "flubnf window",
                     "flubnf.exe app", "flubnf.exe window")

# shown by the load watchdog when every reload attempt fails; loaded with
# window.load_html because pywebview 6.2.1 misroutes data: URLs (its
# is_local_url treats them as file paths and spins up an internal server)
_SERVER_FAIL_PAGE = """<!doctype html><html><head><title>FluBNF</title></head>
<body style="font-family:-apple-system,Helvetica,sans-serif;background:#101223;
color:#E9EAF4;padding:2.5rem;max-width:34rem">
<h2>The console server did not start</h2>
<p>The FluBNF window opened, but the local server behind it never answered.
Close this window and relaunch FluBNF. If it happens again, start it from
Terminal (<code>.venv/bin/flubnf app</code>) to see the error output.</p>
</body></html>"""


def _pid_cmdline_windows(pid: int) -> str:
    """Windows: the command line via WMI -- wmic where present, PowerShell
    CIM otherwise (wmic is removed from newer Windows 11 builds). An empty
    result fails safe: the takeover only ever signals a process whose
    command line matched an entry marker, so "could not inspect" means
    "do not touch", and the relaunch falls back to a nearby free port
    instead of killing a possibly-recycled pid."""
    import subprocess
    queries = (
        ["wmic", "process", "where", f"ProcessId={int(pid)}",
         "get", "CommandLine", "/format:list"],
        ["powershell", "-NoProfile", "-Command",
         f"(Get-CimInstance Win32_Process -Filter "
         f"'ProcessId={int(pid)}').CommandLine"],
    )
    for q in queries:
        try:
            out = subprocess.run(q, capture_output=True, text=True,
                                 timeout=10)
        except Exception:
            continue
        if out.returncode != 0:
            continue
        text = out.stdout.strip()
        if text.startswith("CommandLine="):     # wmic /format:list shape
            text = text.split("=", 1)[1]
        text = text.strip()
        if text:
            return text
    return ""


def _pid_cmdline(pid: int) -> str:
    """The command line of a live process, or '' when it does not exist
    (or cannot be inspected). Linux reads the kernel's own record
    (/proc/<pid>/cmdline, exact and immune to ps formatting or zombie
    <defunct> rewriting, which broke the takeover on CI); Windows asks WMI
    (see _pid_cmdline_windows); everywhere else falls back to ps, which
    ships with macOS. No psutil dependency."""
    import os
    import subprocess
    if os.name == "nt":
        return _pid_cmdline_windows(pid)
    proc_path = Path(f"/proc/{int(pid)}/cmdline")
    try:
        if proc_path.exists():
            raw = proc_path.read_bytes()
            return raw.replace(b"\0", b" ").decode(errors="replace").strip()
    except Exception:
        pass
    try:
        out = subprocess.run(["ps", "-p", str(int(pid)), "-o", "command="],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def _pid_alive_windows(pid: int, kernel32=None) -> bool:
    """Windows liveness via OpenProcess + GetExitCodeProcess. Signal 0 is
    not an option there: os.kill(pid, 0) on Windows calls TerminateProcess
    unconditionally, so the POSIX probe would KILL the probed process.
    `kernel32` is injectable for tests on other platforms."""
    try:
        import ctypes
        import ctypes.wintypes as wintypes
        if kernel32 is None:
            kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        ERROR_ACCESS_DENIED = 5
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            # access denied: the pid exists but belongs to someone else --
            # alive, though never ours to signal (its cmdline comes back
            # empty, so the takeover leaves it alone)
            return kernel32.GetLastError() == ERROR_ACCESS_DENIED
        try:
            code = wintypes.DWORD()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return False


def _pid_alive(pid: int) -> bool:
    """Signal-0 liveness: true for running OR zombie; the takeover's wait
    loop pairs it with the cmdline check so an unreaped zombie (Linux:
    the parent has not called wait) does not stall the full timeout.
    Windows dispatches to _pid_alive_windows -- signal 0 does not exist
    there and os.kill would terminate the probed process."""
    import os
    if os.name == "nt":
        return _pid_alive_windows(pid)
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _terminate_predecessor(pidfile: Optional[Path] = None,
                           markers: tuple = APP_ENTRY_MARKERS,
                           wait: float = 5.0) -> bool:
    """Single-instance takeover: if the pidfile names a live process whose
    command line contains our entry point, terminate it (SIGTERM, up to
    `wait` seconds, then SIGKILL) so the relaunch owns the port outright.
    The stale pidfile is removed either way. Never raises; returns True
    when a predecessor was actually signalled."""
    import os
    import signal
    import time
    pidfile = pidfile if pidfile is not None else APP_PID_FILE
    signalled = False
    try:
        if not pidfile.is_file():
            return False
        pid = int(pidfile.read_text().strip())
        if pid != os.getpid():
            cmd = _pid_cmdline(pid)
            if cmd and any(mk in cmd for mk in markers):
                try:
                    os.kill(pid, signal.SIGTERM)
                    signalled = True
                    t0 = time.time()
                    while (time.time() - t0 < wait and _pid_alive(pid)
                           and _pid_cmdline(pid)):
                        time.sleep(0.1)
                    if _pid_alive(pid) and _pid_cmdline(pid):
                        # SIGKILL does not exist on Windows; there the
                        # SIGTERM above was already TerminateProcess (hard),
                        # so re-sending it is the same escalation
                        os.kill(pid, getattr(signal, "SIGKILL",
                                             signal.SIGTERM))
                except (ProcessLookupError, PermissionError):
                    pass
    except Exception:
        pass
    try:
        pidfile.unlink(missing_ok=True)
    except Exception:
        pass
    return signalled


def _write_pidfile(pidfile: Optional[Path] = None):
    """Record this process for the next launch's takeover check, and remove
    the record at clean exit (atexit). Returns the cleanup function so the
    logic is unit-testable; the cleanup only removes a pidfile this process
    still owns. Never raises."""
    import atexit
    import os
    pidfile = pidfile if pidfile is not None else APP_PID_FILE
    me = str(os.getpid())

    def _cleanup():
        try:
            if pidfile.is_file() and pidfile.read_text().strip() == me:
                pidfile.unlink()
        except Exception:
            pass

    try:
        pidfile.parent.mkdir(parents=True, exist_ok=True)
        pidfile.write_text(me)
        atexit.register(_cleanup)
    except Exception:
        pass
    return _cleanup


_MAX_PORT = 65535


def _port_candidates(preferred: int, tries: int) -> range:
    """The ports a fallback search may probe, CLAMPED at 65535.

    Clamping rather than catching: a TCP port above 65535 does not exist,
    so a probe up there is not a busy port to skip past, it is a nonsense
    request. socket.bind refuses it with OverflowError ("port must be
    0-65535"), which is a ValueError and NOT an OSError, so it sails
    straight through the `except OSError` that both searches use to mean
    "try the next port". A caller who seeds `preferred` from an OS
    ephemeral port (macOS hands those out in 49152-65535, and the launch
    tests do exactly that) then gets a crash instead of a fallback
    whenever the kernel picks something above 65525. Ending the walk at
    the real ceiling keeps the search honest: it probes every port that
    can exist, and if they are all busy the caller's all-busy branch runs
    and uvicorn reports the conflict loudly, which is the documented
    behaviour for that case anyway.

    An out-of-range `preferred` yields an EMPTY range for the same reason:
    there is nothing legal to probe, so the search declines rather than
    inventing a port, and the all-busy branch hands the bad value to
    uvicorn to complain about. Note that a negative `preferred` is not
    slid up to 0, because 0 means "any ephemeral port" to the kernel and
    silently serving on a random port would hide the caller's mistake."""
    if not 0 <= preferred <= _MAX_PORT:
        return range(0)
    return range(preferred, min(preferred + max(1, tries), _MAX_PORT + 1))


def _pick_port(preferred: int = 8710, tries: int = 10) -> int:
    """The first bindable port in preferred..preferred+tries-1. Probing
    binds with SO_REUSEADDR, exactly as uvicorn will: a TIME_WAIT ghost
    passes, a live listener fails. When every probe fails the preferred
    port is returned so uvicorn reports the real conflict loudly. The
    search is clamped at 65535, see _port_candidates for why."""
    import socket
    for port in _port_candidates(preferred, tries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
    return preferred


def _bind_app_socket(preferred: int = 8710, tries: int = 10):
    """(listening socket, port) for the window path: the first bindable
    port in preferred..preferred+tries-1, bound and LISTENING before the
    window ever opens, then handed to uvicorn (Server.run(sockets=...)).

    Holding the socket -- instead of probing, closing, and letting uvicorn
    rebind -- closes both launch races at the root: the port cannot be
    lost between probe and bind (the zombie-of-the-first-attempt case),
    and WKWebView's first connection can never be REFUSED, because the OS
    queues it in this socket's backlog until the server thread finishes
    importing and starts accepting. The connection-refused cache was the
    original dead-first-window failure; with the backlog it is structurally
    impossible while this process lives.

    (None, preferred) when every port is busy, so uvicorn binds for itself
    and reports the real conflict loudly. The search is clamped at 65535,
    see _port_candidates for why that matters here."""
    import socket
    for port in _port_candidates(preferred, tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
            s.listen(128)
            # the KERNEL's port, so a preferred of 0 (tests) reports the
            # ephemeral port actually bound rather than the request
            return s, s.getsockname()[1]
        except OSError:
            s.close()
            continue
    return None, preferred


def _server_answering(url: str, timeout: float = 1.0) -> bool:
    """True when the console server behind `url` answers HTTP at all (any
    status: an error page is still an answering server). The watchdog's
    reload decision hangs on this: reloading helps only when the server is
    up but the window shows a dead page."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/versions",
                                    timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def _window_watchdog(window, url: str, wait: float = 4.0, retries: int = 3,
                     fail_page: str = _SERVER_FAIL_PAGE,
                     probe=None) -> str:
    """Run on a small thread after webview.start's callback fires: wait for
    the window's loaded event; when the page never arrived, decide WHY
    before touching anything. A reload helps in exactly one case: the
    server answers HTTP but the window shows a dead page (WKWebView cached
    a refused connection from a dying predecessor). When the server is not
    answering at all, load_url would only cache ANOTHER refused page and
    cancel whatever navigation is in flight -- the reload storm that turned
    a slow cold start into a dead first window (diagnosed 2026-08-22) --
    so the watchdog then just keeps waiting out its budget. Only when every
    window of the budget passes without a load is the inline failure page
    shown; nothing is surfaced before that.

    `probe` answers "is the server answering HTTP?" and defaults to a real
    1-second request against the light /api/versions endpoint (injectable
    for tests).

    Verified against the installed pywebview 6.2.1 source: events.loaded is
    a webview.event.Event whose += appends a handler invoked from set(), and
    set() fires only after a successful navigation (cocoa
    webView_didFinishNavigation_ -> inject_pywebview -> events.loaded.set),
    so a refused connection leaves it unset; load_url is @_shown_call, clears
    events.loaded first, and dispatches to the Cocoa main run loop via
    AppHelper.callAfter, so calling it from this thread is safe.

    Returns 'loaded', 'recovered', or 'failed' (for tests)."""
    import threading
    if probe is None:
        probe = lambda: _server_answering(url)   # noqa: E731
    loaded = threading.Event()

    def _mark():
        _trace("watchdog: loaded event fired")
        loaded.set()

    try:
        window.events.loaded += _mark
        if window.events.loaded.is_set():   # fired before we attached
            loaded.set()
    except Exception:
        return "failed"
    _trace(f"watchdog: attached, waiting {wait}s for loaded")
    if loaded.wait(wait):
        _trace("watchdog: loaded within first wait")
        return "loaded"
    for attempt in range(max(1, retries)):
        if probe():
            # server up, page dead: the one case a reload fixes
            loaded.clear()
            _trace(f"watchdog: server answers but page dead, "
                   f"reload attempt {attempt + 1}")
            try:
                window.load_url(url)
            except Exception:
                pass
        else:
            _trace(f"watchdog: server not answering, waiting on "
                   f"(attempt {attempt + 1})")
        if loaded.wait(wait):
            _trace("watchdog: recovered within budget")
            return "recovered"
    _trace("watchdog: FAILED, showing failure page")
    try:
        window.load_html(fail_page)
    except Exception:
        pass
    return "failed"


@app.command("app")
def app_serve(port: int = 8710):
    """Launch the operations console. Prefers a native desktop window
    (pywebview) and falls back to the browser without it."""
    _trace("app: command entered")
    try:
        import webview  # noqa: F401
        return app_window(port=port)
    except ImportError:
        pass
    import socket
    import threading
    import time
    import webbrowser

    import uvicorn

    # take over from a dying predecessor, then bind a port that is really
    # free (the same guards the native window path applies)
    _terminate_predecessor()
    _write_pidfile()
    port = _pick_port(port)
    url = f"http://localhost:{port}"

    def _wait_ready(timeout=30.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                with socket.create_connection(("127.0.0.1", port), 0.5):
                    return True
            except OSError:
                time.sleep(0.3)
        return False

    def _open():
        if _wait_ready():
            webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()
    uvicorn.run("app.ui.server:app", port=port, host="127.0.0.1")


@app.command("window")
def app_window(port: int = 8710):
    """The console in its own native window (no browser). Needs pywebview:
    .venv/bin/pip install pywebview"""
    import threading

    import uvicorn
    try:
        import webview
    except ImportError:
        print("pywebview not installed: .venv/bin/pip install pywebview")
        raise SystemExit(1)
    # pywebview refuses downloads unless this is set (verified against the
    # installed pywebview 6.2.1: webview.settings['ALLOW_DOWNLOADS'] defaults
    # to False in webview/__init__.py; platforms/cocoa.py honors it both for
    # anchors carrying the download attribute, which become a WKDownload with
    # a save panel, and for attachment responses WKWebView cannot display).
    # Without it the "Download season report" link is a dead end in the
    # native window.
    webview.settings['ALLOW_DOWNLOADS'] = True
    _trace("window: webview imported, settings applied")
    # single instance: a dying predecessor could otherwise keep the port,
    # leaving this window bound to nothing (the random dead window on
    # reopen). Take its place explicitly, then BIND AND HOLD a port that
    # is really free.
    signalled = _terminate_predecessor()
    _trace(f"window: predecessor takeover done (signalled={signalled})")
    _write_pidfile()
    sock, port = _bind_app_socket(port)
    url = f"http://localhost:{port}"
    _trace(f"window: port {port} bound and listening "
           f"(held={sock is not None}), starting server thread")

    def _serve():
        config = uvicorn.Config("app.ui.server:app", port=port,
                                host="127.0.0.1", log_level="warning")
        uvicorn.Server(config).run(sockets=[sock] if sock else None)

    threading.Thread(target=_serve, daemon=True).start()
    # The window opens IMMEDIATELY: the socket above is already listening,
    # so WKWebView's first request queues in its backlog until the server
    # thread finishes importing and starts accepting -- it can never be
    # refused (the refused-page cache was the original dead-first-window
    # bug), and the old wait-for-the-server loop that held the window
    # closed for the whole server import is gone.
    _trace("window: creating window (server import in flight)")
    window = webview.create_window("FluBNF", url,
                                   width=1120, height=800,
                                   min_size=(760, 520))
    def _activate():
        # Launched from a .command script the process is not a bundled app,
        # so macOS may leave the window deactivated (clicks ignored until
        # the user switches away and back). The start callback runs on a
        # SECONDARY thread; Cocoa activation must happen on the main run
        # loop or it works only intermittently -- hence callAfter.
        # Load watchdog: if the page never arrives (server import crashed,
        # or activation raced the first navigation), recover it rather
        # than sit dead -- see _window_watchdog for the reload rule.
        _trace("window: start callback fired (window shown)")
        threading.Thread(target=_window_watchdog, args=(window, url),
                         daemon=True).start()
        try:
            # pyobjc ships with pywebview
            from AppKit import NSApplication, NSImage
            from PyObjCTools import AppHelper

            # Runtime dock icon: launched through a plain interpreter the
            # process inherits the generic Python icon, so hand Cocoa the
            # brand icon explicitly. NSImage cannot load the SVG mark;
            # a 512px PNG from the brand kit lives next to it.
            icon_png = (Path(__file__).resolve().parents[1]
                        / "app" / "ui" / "static" / "brand"
                        / "pybnf_icon_512.png")

            def _front():
                app = NSApplication.sharedApplication()
                app.activateIgnoringOtherApps_(True)
                try:
                    if icon_png.is_file():
                        img = NSImage.alloc().initWithContentsOfFile_(
                            str(icon_png))
                        if img:
                            app.setApplicationIconImage_(img)
                except Exception:
                    pass
            AppHelper.callAfter(_front)
            import time as _t
            _t.sleep(1.0)          # once more after the window settles
            AppHelper.callAfter(_front)
        except Exception:
            pass
    _trace("window: entering webview.start (main loop)")
    webview.start(_activate)


@app.command("retro")
def retro_cmd(season: str, locations: str = "all", width: int = 4,
              replicates: int = 3, root: str = ""):
    """Run a season-as-competition retrospective (resumable)."""
    import pandas as pd
    from pathlib import Path as _P
    from app.core import retro
    from flubnf.settings import LOCATIONS
    locs = pd.read_csv(LOCATIONS, dtype=str)
    names = (list(locs.location_name[locs.location.str.len() == 2]
                  [locs.abbreviation != "US"])
             if locations == "all" else
             [x.strip() for x in locations.split(",")])
    r = _P(root) if root else _P("app/state/retro") / season
    done = retro.run_season(r, season, names, replicates=replicates,
                            width=width,
                            progress=lambda a: print(f"  {a} done", flush=True))
    print(f"{season}: {len(done)} weeks complete -> {r}")


# ---------------------------------------------------------------------------
# site — build the public static site from the lab's own state
#
# A sub-app rather than a flat command, because the site has a lifecycle
# (build now; check, and later publish/preview) and "flubnf site build"
# keeps that room without crowding the top-level command list.
# ---------------------------------------------------------------------------
site_app = typer.Typer(
    add_completion=False, no_args_is_help=True,
    help="Build the public static site from the lab's retrospectives.")
app.add_typer(site_app, name="site")


@site_app.command("build")
def site_build_cmd(
    out: Optional[Path] = typer.Option(
        None, "--out", help="Output directory (default: the repo's site/)."),
    season: str = typer.Option(
        "", "--season",
        help="Pin the home outlook to this season instead of the newest "
             "forecast. Deliberate override; recorded in the payload."),
    asof: str = typer.Option(
        "", "--asof",
        help="Pin the home outlook to this forecast week (YYYY-MM-DD). "
             "Requires the week to exist in the chosen season."),
    check: bool = typer.Option(
        False, "--check",
        help="Exit non-zero if any computed score disagrees with the "
             "figure the console publishes for the same season."),
):
    """Read the app's state and write the static site.

    Everything on the page is computed here from the stored forecasts: the
    outlook map from the newest full-country forecast, the season table from
    whichever retrospective seasons exist on disk, and Methods from the
    console's own templates. Nothing is copied from a note.
    """
    from app.core import site_build as sb
    pin = (season, asof) if (season or asof) else None
    try:
        res = sb.build(out_dir=out, pin=pin)
    except sb.BuildError as e:
        console.print(f"[red]site build: {e}[/red]")
        raise typer.Exit(2)

    src = res["outlook"]
    console.print(f"[bold]site[/bold] -> {res['out']}")
    console.print(f"  page      {res['page_bytes']:>9,} bytes")
    console.print(f"  payload   {res['payload_bytes']:>9,} bytes"
                  "   (site.json, review this diff)")
    console.print(f"  plotly    {res['plotly_bytes']:>9,} bytes"
                  "   (cached sibling, not inlined)")
    console.print(f"  outlook   {src['label']}")
    console.print(f"  locations {res['locations']}")
    console.print(f"  seasons   {', '.join(res['seasons']) or 'none'}")
    if res["pooled"] is not None:
        console.print(f"  pooled    ensemble relWIS {res['pooled']:.4f}")
    console.print(f"  built in  {res['elapsed_s']:.1f}s")

    if res["mismatches"]:
        console.print("[red]scores disagree with the console:[/red]")
        for m in res["mismatches"]:
            console.print(f"  {m['what']}: computed {m['computed']:.4f}, "
                          f"console states {m['app']:.4f}")
        if check:
            raise typer.Exit(1)
    else:
        console.print("[green]  scores match the console's published "
                      "figures[/green]")
