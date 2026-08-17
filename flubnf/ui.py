"""Streamlit UI for FluBNF — Mode-based workflow.

Two modes:
  * **Real-time Forecasting** — the production weekly job; what you run
    every Tuesday during the live FluSight competition.
  * **Retrospective** — backtest a past season, score head-to-head
    against the team's actual hub submissions.

Plus shared **Diagnostics** and **Settings** tabs.

Run with: streamlit run flubnf/ui.py
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from flubnf import (auto, bngl_files, compare as cmp_mod, conf_files,
                    exp_files, fetch, flusight, weekly_job as wjmod)
from flubnf import backtest as bt
from flubnf.config import FluBNFConfig
from flubnf.constants import JURISDICTIONS
from flubnf.paths import WorkspacePaths
from flubnf.session import load_session
from flubnf.state import WorkspaceState


# ===========================================================================
# Page + theming
# ===========================================================================
st.set_page_config(
    page_title="FluBNF Forecasting",
    layout="wide",
    page_icon=":microscope:",
    initial_sidebar_state="expanded",
)


# Inline CSS — a light "MicroHub-inspired" treatment so the app doesn't
# feel like raw Streamlit defaults. Banner color matches LANL navy.
st.markdown(
    """
    <style>
      .flubnf-banner {
        background: linear-gradient(135deg, #002454 0%, #00488a 100%);
        color: #ffffff;
        padding: 28px 32px;
        border-radius: 8px;
        margin-bottom: 18px;
        box-shadow: 0 10px 30px rgba(7, 26, 63, 0.18);
      }
      .flubnf-banner h1 {
        margin: 0 0 6px 0;
        font-size: 30px;
        font-weight: 700;
        letter-spacing: 0.02em;
        color: #ffffff;
      }
      .flubnf-banner p {
        margin: 0;
        font-size: 15px;
        color: #d6e2f3;
        line-height: 1.55;
      }
      .flubnf-mode-pill {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        background: rgba(255,255,255,0.18);
        color: #ffffff;
        margin-bottom: 10px;
      }
      .flubnf-feature-card {
        background: #ffffff;
        border: 1px solid #d7dde4;
        border-radius: 6px;
        padding: 16px 18px;
        box-shadow: 0 4px 14px rgba(7, 26, 63, 0.06);
        height: 100%;
      }
      .flubnf-feature-card h4 {
        margin: 0 0 6px 0;
        color: #16355f;
        font-weight: 700;
      }
      .flubnf-feature-card p { margin: 0; color: #475569; font-size: 14px; }
      .flubnf-stat-pill {
        display: inline-block; padding: 4px 12px; margin: 3px;
        border-radius: 6px; background: #eef3f9; color: #16355f;
        font-size: 13px; font-weight: 600;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# ===========================================================================
# Cached objects
# ===========================================================================
@st.cache_resource
def _get_config() -> FluBNFConfig:
    return FluBNFConfig.load()


def _get_paths(workspace_name: str) -> WorkspacePaths:
    cfg = _get_config()
    return WorkspacePaths(root=cfg.workspace(workspace_name)).ensure()


def _get_state(paths: WorkspacePaths, workspace_name: str, year: int) -> WorkspaceState:
    return WorkspaceState.load_or_create(
        paths.state_file, workspace=workspace_name, season_year=year,
    )


def _dir_signature(path: Path) -> tuple:
    """Stable cache key for a directory: (name, mtime, file count)."""
    try:
        if not path.exists():
            return (str(path), 0.0, 0)
        st_path = path.stat()
        n_files = sum(1 for _ in path.rglob("*")) if path.is_dir() else 1
        return (str(path), st_path.st_mtime, n_files)
    except Exception:
        return (str(path), 0.0, 0)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_season_report(workspace_root_str: str, signature: tuple):
    """Wrap `season_report.build_season_report` with a 60s TTL cache
    keyed on the workspace dir's signature (mtime + file count).

    The signature ensures the cache invalidates when sessions /
    submissions / calibration files change."""
    from flubnf.season_report import build_season_report
    return build_season_report(WorkspacePaths(root=Path(workspace_root_str)))


@st.cache_data(ttl=300, show_spinner=False)
def _cached_csv(csv_path_str: str, signature: tuple) -> pd.DataFrame:
    """Cache CSV reads keyed on path + mtime. CSVs are pure data files —
    safe to cache aggressively."""
    return pd.read_csv(csv_path_str)


# ===========================================================================
# Sidebar — shared across all tabs
# ===========================================================================
cfg = _get_config()
st.sidebar.title(":microscope: FluBNF")
st.sidebar.caption("Automated FluSight forecasting")

existing_workspaces = sorted(
    [p.name for p in cfg.workspace_root.glob("*") if p.is_dir()]
) if cfg.workspace_root.exists() else []
default_workspace = f"season_{cfg.season.year}"
workspace_options = list(dict.fromkeys([default_workspace, *existing_workspaces]))

st.sidebar.divider()
st.sidebar.subheader("Workspace")
workspace_name = st.sidebar.selectbox(
    "Active workspace", workspace_options, index=0,
    help="Per-season working directory. Real-time forecasts and "
         "retrospective backtests can live in different workspaces.",
)
paths = _get_paths(workspace_name)
state = _get_state(paths, workspace_name, cfg.season.year)
st.sidebar.markdown(f"`{paths.root}`")
st.sidebar.markdown(
    f"**season**: {cfg.season.year}<br>"
    f"**last fetch**: {state.last_data_as_of or '—'}",
    unsafe_allow_html=True,
)

# Inventory counts in the sidebar.
n_bngl = len(list(paths.bngl_dir.glob("*.bngl")))
n_conf = len(list(paths.conf_dir.glob("*.conf")))
n_exp = len(list(paths.exp_dir.glob("*_flu.exp")))
n_sub = len(list((paths.root / "submissions").glob("*.csv"))) \
    if (paths.root / "submissions").exists() else 0
st.sidebar.metric("bngl / conf / exp", f"{n_bngl}/{n_conf}/{n_exp}")
st.sidebar.metric("submissions written", n_sub)


# ===========================================================================
# Mode tabs
# ===========================================================================
TAB_HOME = "🏠 Home"
TAB_REALTIME = "📡 Real-time"
TAB_RETROSPECTIVE = "🕰 Retrospective"
TAB_HUB = "📊 Submission Hub"
TAB_SEASON = "📈 Season Report"
TAB_DIAGNOSTICS = "🔬 Diagnostics"
TAB_SETTINGS = "⚙️ Settings"

(tab_home, tab_realtime, tab_retro, tab_hub, tab_season,
 tab_diag, tab_settings) = st.tabs([
    TAB_HOME, TAB_REALTIME, TAB_RETROSPECTIVE, TAB_HUB,
    TAB_SEASON, TAB_DIAGNOSTICS, TAB_SETTINGS,
])


# ===========================================================================
# HOME TAB
# ===========================================================================
with tab_home:
    st.markdown(
        '<div class="flubnf-banner">'
        '<div class="flubnf-mode-pill">FluSight automation</div>'
        '<h1>FluBNF Forecasting</h1>'
        '<p>An automated weekly workflow producing FluSight-format flu '
        'forecasts using PyBNF-fit SIR models, with adaptive bounds, '
        'piecewise-beta evolution, posterior anchoring, and diagnostic-driven '
        'reactive controls. Beats the manual LANL team pipeline on '
        '2025-26 Alabama by <strong>-30% WIS</strong>.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            '<div class="flubnf-feature-card">'
            '<h4>📡 Real-time mode</h4>'
            '<p>One-click weekly workflow: fetch latest CDC data, fit all 52 '
            'jurisdictions, generate quantile forecasts, write the FluSight '
            'submission CSV. Use this every Tuesday during the live '
            'competition.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            '<div class="flubnf-feature-card">'
            '<h4>🕰 Retrospective mode</h4>'
            '<p>Walk-forward backtest a past season week-by-week. Compare '
            'WIS head-to-head against the team\'s actual hub submissions. '
            'Use this to validate algorithmic changes and discover fringe '
            'cases.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            '<div class="flubnf-feature-card">'
            '<h4>🔬 Diagnostics</h4>'
            '<p>Per-state convergence diagnostics from the most recent '
            'AMCMC fit, outbreak phase classification, session history '
            'showing how bounds and piecewise complexity evolved across '
            'weeks.</p>'
            '</div>',
            unsafe_allow_html=True,
        )

    st.divider()
    st.subheader("Workspace at a glance")
    pills = [
        f'<span class="flubnf-stat-pill">workspace: {workspace_name}</span>',
        f'<span class="flubnf-stat-pill">season: {cfg.season.year}</span>',
        f'<span class="flubnf-stat-pill">{n_bngl} bngl / {n_conf} conf / {n_exp} exp</span>',
        f'<span class="flubnf-stat-pill">{n_sub} submission(s) written</span>',
    ]
    if state.last_data_as_of:
        pills.append(f'<span class="flubnf-stat-pill">last fetch: {state.last_data_as_of}</span>')
    st.markdown(" ".join(pills), unsafe_allow_html=True)

    if state.stages:
        st.subheader("Recent activity")
        recent_df = pd.DataFrame([
            {"timestamp": s.ts, "stage": s.name, "status": s.status,
             "details": ", ".join(f"{k}={v}" for k, v in s.details.items())[:80]}
            for s in state.stages[-10:][::-1]
        ])
        st.dataframe(recent_df, use_container_width=True, hide_index=True, height=260)
    else:
        st.info("No activity in this workspace yet. Open the **Real-time** "
                "or **Retrospective** tab to begin.")


# ===========================================================================
# REAL-TIME TAB
# ===========================================================================
with tab_realtime:
    st.markdown('<div class="flubnf-mode-pill" style="background:#0b6b3a;color:white;">LIVE COMPETITION</div>',
                unsafe_allow_html=True)
    st.subheader("Run today's FluSight submission")
    st.caption(
        "Fetches the latest CDC weekly hospitalization data, applies "
        "the per-state adaptive analysis, runs PyBNF AMCMC per state, "
        "and writes a FluSight-format submission CSV."
    )

    left, right = st.columns([1, 2])
    with left:
        with st.container(border=True):
            _today = date.today()
            _delta = (5 - _today.weekday()) % 7 or 7
            default_ref = (_today + timedelta(days=_delta)).isoformat()
            ref_date_str = st.text_input(
                "Reference Saturday",
                value=default_ref,
                key="rt_ref_date",
                help="The Saturday of the week being forecast. Defaults to "
                     "the upcoming Saturday.",
            )

            state_filter = st.text_input(
                "States to fit",
                value="all",
                key="rt_state_filter",
                help="Comma-separated state names, or 'all' for every "
                     "jurisdiction.",
            )

            method = st.selectbox(
                "Fit method", ["am", "de"], index=0,
                key="rt_method",
                help="AMCMC ('am') gives proper posterior quantiles "
                     "(recommended). DE ('de') is faster but less calibrated.",
            )
            cols = st.columns(2)
            with cols[0]:
                max_iter = st.number_input(
                    "max_iter", min_value=100, max_value=50000,
                    value=800 if method == "am" else 200, step=100,
                    key="rt_max_iter",
                )
                burn_in = st.number_input(
                    "burn_in (AMCMC)", min_value=0, max_value=10000,
                    value=150, step=50,
                    key="rt_burn_in",
                )
            with cols[1]:
                popsize = st.number_input(
                    "popsize / chains", min_value=1, max_value=20,
                    value=1 if method == "am" else 15, step=1,
                    key="rt_popsize",
                )
                adaptive_iter = st.number_input(
                    "adaptive (AMCMC)", min_value=0, max_value=10000,
                    value=150, step=50,
                    key="rt_adaptive_iter",
                )
            parallel = st.slider(
                "Parallel state fits", 1, 8, 1,
                key="rt_parallel",
                help="Number of states to fit concurrently. Use 4-8 on "
                     "Mac Studio, 1-2 on laptop.",
            )

            run_now = st.button(
                "▶ Run weekly job", type="primary", use_container_width=True,
                key="rt_run_now",
            )

    with right:
        progress_box = st.empty()
        result_box = st.empty()
        if run_now:
            states_list = (list(JURISDICTIONS) if state_filter.strip() == "all"
                           else [s.strip() for s in state_filter.split(",") if s.strip()])
            try:
                ref_date = date.fromisoformat(ref_date_str)
            except ValueError:
                st.error(f"Bad reference date: {ref_date_str!r}")
                ref_date = None
            if ref_date is not None:
                updates: list[tuple[str, str]] = []

                def _cb(s: str, status: str):
                    updates.append((s, status))
                    df = pd.DataFrame(updates, columns=["state", "status"])
                    progress_box.dataframe(
                        df.tail(20), hide_index=True,
                        use_container_width=True,
                    )

                with st.spinner(f"Running {len(states_list)} state(s)..."):
                    res = wjmod.run_weekly_job(
                        cfg, paths,
                        reference_date=ref_date, states=states_list,
                        method=method, popsize=int(popsize),
                        max_iter=int(max_iter), burn_in=int(burn_in),
                        adaptive=int(adaptive_iter),
                        parallel=parallel, on_progress=_cb,
                    )
                state.record(
                    "weekly-job", n_ok=res.n_ok, n_states=len(res.states),
                    submission=str(res.submission_csv) if res.submission_csv else None,
                )
                state.save(paths.state_file)
                with result_box.container():
                    if res.n_ok == len(res.states):
                        st.success(
                            f"Done — all {res.n_ok}/{len(res.states)} states succeeded."
                        )
                    elif res.n_ok == 0:
                        st.error(
                            f"All fits failed ({len(res.states)} states). "
                            f"Check the Diagnostics tab or PyBNF logs."
                        )
                    else:
                        st.warning(
                            f"Partial success — {res.n_ok}/{len(res.states)} "
                            f"states succeeded. Failed states are still "
                            f"included in the submission only if their previous "
                            f"week's fit is reusable; otherwise they're missing."
                        )
                    # Show per-state result breakdown.
                    if res.states:
                        breakdown = pd.DataFrame([
                            {"state": s.state, "status": s.status,
                             "K": s.n_steps,
                             "best_obj": (f"{s.best_obj:.1f}"
                                          if s.best_obj is not None else "—"),
                             "fringe": ", ".join(s.fringe_cases) or "—",
                             "notes": s.notes or "—"}
                            for s in res.states
                        ])
                        # Highlight failed rows.
                        st.dataframe(
                            breakdown, use_container_width=True,
                            hide_index=True, height=320,
                        )
                    if res.submission_csv:
                        st.markdown(f"**Submission written to:** `{res.submission_csv}`")
                        with open(res.submission_csv, "rb") as f:
                            st.download_button(
                                "⬇ Download submission CSV",
                                data=f.read(),
                                file_name=res.submission_csv.name,
                                mime="text/csv",
                                key="rt_dl_just_run",
                            )
        else:
            # Show the latest existing submission if any.
            subs = sorted((paths.root / "submissions").glob("*.csv")) \
                if (paths.root / "submissions").exists() else []
            if subs:
                latest = subs[-1]
                with st.container(border=True):
                    st.markdown(f"**Latest submission:** `{latest.name}`")
                    # Preview: pick a state and show its forecast fan.
                    preview_state = st.selectbox(
                        "Preview state forecast", JURISDICTIONS,
                        index=0, key="rt_preview_state_sel",
                    )
                    try:
                        from .constants import load_locations
                        from .ui_plots import build_quantile_fan
                        sub_df = pd.read_csv(latest, dtype={"location": str})
                        sub_df["location"] = sub_df["location"].str.zfill(2)
                        locs = load_locations(cfg.locations_csv)
                        fips = locs[preview_state].fips
                        sub_state = sub_df[
                            (sub_df["location"] == fips) &
                            (sub_df["output_type"] == "quantile")
                        ].copy()
                        sub_state["output_type_id"] = sub_state["output_type_id"].astype(float)
                        qd_per_h: dict = {}
                        for fs_h, group in sub_state.groupby("horizon"):
                            qd_per_h[int(fs_h) + 1] = dict(zip(
                                group["output_type_id"], group["value"]))
                        ref_dt = pd.to_datetime(
                            sub_df["reference_date"].iloc[0]).date()
                        obs_path = paths.exp_file(preview_state)
                        if obs_path.exists() and qd_per_h:
                            obs = pd.read_csv(obs_path, sep="\t")["H_weekly"].to_numpy(dtype=float)
                            chart = build_quantile_fan(
                                obs, qd_per_h, sorted(qd_per_h.keys()),
                                reference_date=ref_dt,
                                state_name=preview_state,
                            )
                            st.altair_chart(chart, use_container_width=True)
                    except Exception as e:
                        st.caption(f"(fan chart unavailable: {e})")
                    st.dataframe(pd.read_csv(latest).head(30),
                                 use_container_width=True, height=200)
                    st.download_button(
                        "⬇ Download latest submission",
                        data=latest.read_bytes(),
                        file_name=latest.name,
                        mime="text/csv",
                        key="rt_dl_latest",
                    )
            else:
                st.info(
                    "No submissions in this workspace yet. Configure "
                    "settings on the left and click **Run weekly job**."
                )


# ===========================================================================
# RETROSPECTIVE TAB
# ===========================================================================
with tab_retro:
    st.markdown('<div class="flubnf-mode-pill" style="background:#5b3a99;color:white;">PAST-SEASON BACKTEST</div>',
                unsafe_allow_html=True)
    st.subheader("Walk-forward backtest against held-out actuals")
    st.caption(
        "Pick a season + state set + week range. The harness refits "
        "week-by-week using only data available at that point, then scores "
        "each forecast's WIS against what actually happened. If team "
        "submission scores are loaded, you also get a head-to-head "
        "comparison."
    )

    left, right = st.columns([1, 2])
    with left:
        with st.container(border=True):
            retro_states = st.text_input(
                "States",
                value="Alabama",
                key="retro_states",
                help="Comma-separated. Multi-state runs are slower.",
            )
            cols = st.columns(2)
            with cols[0]:
                start_week = st.number_input(
                    "Start week", min_value=0, max_value=50, value=18, step=1,
                    key="retro_start_week",
                )
            with cols[1]:
                end_week = st.number_input(
                    "End week", min_value=0, max_value=52, value=40, step=1,
                    key="retro_end_week",
                )

            retro_method = st.selectbox(
                "Engine", ["amcmc", "pybnf", "inproc"], index=0,
                key="retro_method",
                help="amcmc = real PyBNF AMCMC (best quantiles). "
                     "pybnf = real PyBNF DE (faster). "
                     "inproc = in-Python scipy DE (fastest, no calibration).",
            )
            cols = st.columns(2)
            with cols[0]:
                retro_max_iter = st.number_input(
                    "max_iter", min_value=100, max_value=50000,
                    value=800 if retro_method == "amcmc" else 200, step=100,
                    key="retro_max_iter",
                )
            with cols[1]:
                retro_popsize = st.number_input(
                    "popsize", min_value=1, max_value=20,
                    value=10, step=1,
                    key="retro_popsize",
                )

            retro_mode = st.selectbox(
                "Mode", ["adaptive", "static", "both"], index=0,
                key="retro_mode",
                help="adaptive = with auto bounds-expansion + step-add. "
                     "static = no automation (control). "
                     "both = run each separately for comparison.",
            )

            run_retro = st.button(
                "▶ Run retrospective backtest",
                type="primary", use_container_width=True,
                key="retro_run_btn",
            )
            st.caption(
                f"Estimated wall-time: ~{(end_week - start_week + 1) * len(retro_states.split(',')) * (100 if retro_method == 'amcmc' else 20)} sec"
            )

    with right:
        retro_progress = st.empty()
        retro_result = st.empty()

        if run_retro:
            try:
                states_list = [s.strip() for s in retro_states.split(",") if s.strip()]
                # Use CDC CSV from data cache.
                csvs = sorted(cfg.data_cache.glob("*.csv")) if cfg.data_cache.exists() else []
                if not csvs:
                    st.error("No CDC CSV cached. Use Settings → Fetch first.")
                else:
                    csv_path = csvs[-1]
                    df_raw = pd.read_csv(csv_path)
                    geo_col, date_col, val_col = bt._resolve_columns_quick(df_raw, cfg)
                    all_records = []
                    from flubnf.constants import STATE_TO_ABBREV
                    import pymmwr as pm

                    def _obs_for(abbrev):
                        sub = df_raw[df_raw[geo_col] == abbrev].copy()
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

                    modes_list = [True] if retro_mode == "adaptive" else [False] if retro_mode == "static" else [True, False]
                    for s in states_list:
                        abbrev = STATE_TO_ABBREV.get(s)
                        if abbrev is None:
                            continue
                        observed = _obs_for(abbrev)
                        retro_progress.info(f"running {s} ({len(observed)} weeks observed)...")
                        for adaptive_flag in modes_list:
                            recs = bt.walk_forward(
                                s, observed,
                                start_week=int(start_week),
                                end_week=int(end_week),
                                horizons=(1, 2, 3, 4),
                                adaptive=adaptive_flag,
                                popsize=int(retro_popsize),
                                max_iter=int(retro_max_iter),
                                engine=retro_method,
                                workspace_paths=paths if retro_method in {"pybnf", "amcmc"} else None,
                                config=cfg if retro_method in {"pybnf", "amcmc"} else None,
                                quantile_horizons=True,
                            )
                            all_records.extend(recs)
                    df_out = bt.records_to_dataframe(all_records)
                    out_csv = paths.root / f"retrospective_{date.today().isoformat()}.csv"
                    df_out.to_csv(out_csv, index=False)
                    state.record("retrospective", n_states=len(states_list),
                                 n_weeks=end_week - start_week + 1,
                                 mode=retro_mode, out=str(out_csv))
                    state.save(paths.state_file)
                    with retro_result.container():
                        st.success(f"Done — {len(df_out)} (state, week, mode) cells.")
                        summary = df_out.groupby(["state", "adaptive"]).agg(
                            mean_mae=("mae", "mean"),
                            mean_wis=("wis_mean", "mean"),
                            final_K=("n_steps", "last"),
                            n_weeks=("week", "count"),
                        ).reset_index().round(2)
                        st.dataframe(summary, use_container_width=True, hide_index=True)
                        st.markdown(f"**Records CSV:** `{out_csv}`")
                        st.download_button(
                            "⬇ Download records",
                            data=out_csv.read_bytes(),
                            file_name=out_csv.name,
                            mime="text/csv",
                            key="retro_dl_records",
                        )
            except Exception as e:
                st.error(f"Backtest failed: {e}")

        # Team comparison panel
        st.divider()
        with st.container(border=True):
            st.markdown("**Compare against team baseline**")
            team_path = paths.root.parent.parent / "backtest_results" / "flusight_team_scored.csv"
            backtests = sorted((paths.root.parent.parent / "backtest_results").glob("*.csv")) \
                if (paths.root.parent.parent / "backtest_results").exists() else []
            ours_path = st.selectbox(
                "Backtest CSV", [p.name for p in backtests] or ["(none — run a backtest first)"],
                key="retro_team_cmp_csv",
            )
            cmp_state = st.selectbox(
                "State to compare", JURISDICTIONS, index=0,
                key="retro_team_cmp_state",
            )
            if st.button("Compare to team", use_container_width=True,
                         key="retro_team_cmp_btn") and backtests:
                ours = paths.root.parent.parent / "backtest_results" / ours_path
                if not team_path.exists():
                    st.error("No team-scored CSV. Run `flubnf score-team` from the CLI first.")
                else:
                    try:
                        cmp_df = cmp_mod.align_backtest_with_team(ours, team_path, cmp_state, cfg)
                        if cmp_df.empty:
                            st.warning(f"No overlap between backtest and team data for {cmp_state}.")
                        else:
                            summary = cmp_mod.summarize_alignment(cmp_df).round(2)
                            st.dataframe(summary, use_container_width=True, hide_index=True)
                            delta = cmp_df["our_wis_adapt"] - cmp_df["team_wis"]
                            wins = (delta < 0).sum()
                            pct = (cmp_df["our_wis_adapt"].mean() / cmp_df["team_wis"].mean() - 1) * 100
                            if pct < 0:
                                st.success(
                                    f"**We win by {-pct:.1f}%** — mean WIS "
                                    f"{cmp_df['our_wis_adapt'].mean():.1f} vs team "
                                    f"{cmp_df['team_wis'].mean():.1f} "
                                    f"({wins}/{len(cmp_df)} head-to-head cells)."
                                )
                            else:
                                st.warning(
                                    f"We lose by {pct:.1f}% — mean WIS "
                                    f"{cmp_df['our_wis_adapt'].mean():.1f} vs team "
                                    f"{cmp_df['team_wis'].mean():.1f} "
                                    f"({wins}/{len(cmp_df)} head-to-head cells)."
                                )
                            st.dataframe(cmp_df, use_container_width=True, height=300)
                    except Exception as e:
                        st.error(f"compare failed: {e}")


# ===========================================================================
# SUBMISSION HUB TAB
# ===========================================================================
with tab_hub:
    st.subheader("Submission Hub — view, diff, and review past submissions")
    st.caption(
        "Every weekly job writes a FluSight-format CSV into the workspace's "
        "submissions/ directory. This tab lets you inspect any of those, "
        "diff two side-by-side, or download bundles."
    )

    submissions_dir = paths.root / "submissions"
    submissions_dir.mkdir(parents=True, exist_ok=True)
    sub_files = sorted(submissions_dir.glob("*.csv"))

    if not sub_files:
        st.info(
            f"No submission CSVs in this workspace yet. Run a weekly job "
            f"or copy CSVs into `{submissions_dir}`."
        )
    else:
        from .constants import load_locations, STATE_TO_ABBREV
        from .ui_plots import build_submission_diff_chart, build_quantile_fan

        # Inventory
        with st.container(border=True):
            st.markdown(f"**{len(sub_files)} submission(s) in this workspace**")
            inv_rows = []
            for p in sub_files:
                df_p = pd.read_csv(p, dtype={"location": str})
                if "location" in df_p.columns:
                    locations = df_p["location"].nunique()
                else:
                    locations = 0
                if "reference_date" in df_p.columns and not df_p.empty:
                    rd = df_p["reference_date"].iloc[0]
                else:
                    rd = "—"
                inv_rows.append({
                    "file": p.name,
                    "reference_date": rd,
                    "locations": locations,
                    "rows": len(df_p),
                    "size_kb": p.stat().st_size // 1024,
                })
            st.dataframe(pd.DataFrame(inv_rows), use_container_width=True,
                         hide_index=True)

        # Single-submission viewer with quantile fan plot per state.
        with st.container(border=True):
            st.markdown("**View one submission**")
            cols = st.columns([2, 2, 1])
            with cols[0]:
                view_file = st.selectbox(
                    "Submission CSV", [p.name for p in sub_files],
                    index=len(sub_files) - 1, key="hub_view_file",
                )
            with cols[1]:
                view_state = st.selectbox(
                    "State", JURISDICTIONS, index=0, key="hub_view_state",
                )
            with cols[2]:
                st.markdown("&nbsp;", unsafe_allow_html=True)
                show_data = st.checkbox("show table", value=False,
                                         key="hub_view_show_data")

            sub_path = submissions_dir / view_file
            sub_df = pd.read_csv(sub_path, dtype={"location": str})
            sub_df["location"] = sub_df["location"].str.zfill(2)
            try:
                locs = load_locations(cfg.locations_csv)
                fips = locs[view_state].fips
            except Exception:
                fips = None
            sub_state = sub_df[sub_df["location"] == fips] if fips else pd.DataFrame()
            if sub_state.empty:
                st.warning(f"No rows for {view_state} (FIPS {fips}) in {view_file}.")
            else:
                # Build quantile dict per horizon and observed series.
                quant_state = sub_state[sub_state["output_type"] == "quantile"].copy()
                quant_state["output_type_id"] = quant_state["output_type_id"].astype(float)
                qd_per_h: dict = {}
                bt_horizons = []
                for fs_h, group in quant_state.groupby("horizon"):
                    bt_h = int(fs_h) + 1  # FluSight h=0 == backtest h=1
                    qd_per_h[bt_h] = dict(zip(group["output_type_id"],
                                              group["value"]))
                    bt_horizons.append(bt_h)
                bt_horizons = sorted(set(bt_horizons))

                # Observed series for the state, anchored at this submission's date.
                obs_path = paths.exp_file(view_state)
                if obs_path.exists():
                    obs = pd.read_csv(obs_path, sep="\t")["H_weekly"].to_numpy(dtype=float)
                else:
                    obs = np.array([], dtype=float)

                if "reference_date" in sub_df.columns:
                    rd_str = sub_df["reference_date"].iloc[0]
                    try:
                        ref_dt = pd.to_datetime(rd_str).date()
                    except Exception:
                        ref_dt = None
                else:
                    ref_dt = None

                if len(obs) > 0:
                    chart = build_quantile_fan(
                        obs, qd_per_h, bt_horizons,
                        reference_date=ref_dt, state_name=view_state,
                    )
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.info(
                        "Forecast loaded but no observed .exp file to plot history."
                    )

                if show_data:
                    st.dataframe(sub_state, use_container_width=True, height=300)

                st.download_button(
                    "⬇ Download this submission",
                    data=sub_path.read_bytes(),
                    file_name=sub_path.name,
                    mime="text/csv",
                    key="hub_dl_view",
                )

        # Diff two submissions side-by-side.
        if len(sub_files) >= 2:
            with st.container(border=True):
                st.markdown("**Diff two submissions** (typically week-over-week)")
                cols = st.columns(3)
                with cols[0]:
                    file_a = st.selectbox(
                        "A", [p.name for p in sub_files],
                        index=max(0, len(sub_files) - 2),
                        key="hub_diff_a",
                    )
                with cols[1]:
                    file_b = st.selectbox(
                        "B", [p.name for p in sub_files],
                        index=len(sub_files) - 1,
                        key="hub_diff_b",
                    )
                with cols[2]:
                    diff_state = st.selectbox(
                        "State", JURISDICTIONS, index=0, key="hub_diff_state",
                    )
                try:
                    locs = load_locations(cfg.locations_csv)
                    diff_fips = locs[diff_state].fips
                except Exception:
                    diff_fips = None
                if diff_fips:
                    sub_a = pd.read_csv(submissions_dir / file_a,
                                        dtype={"location": str})
                    sub_b = pd.read_csv(submissions_dir / file_b,
                                        dtype={"location": str})
                    sub_a["location"] = sub_a["location"].str.zfill(2)
                    sub_b["location"] = sub_b["location"].str.zfill(2)
                    chart = build_submission_diff_chart(
                        sub_a, sub_b, location=diff_fips,
                        label_a=file_a.split("-LosAlamos")[0],
                        label_b=file_b.split("-LosAlamos")[0],
                    )
                    if chart is not None:
                        st.altair_chart(chart, use_container_width=True)
                    else:
                        st.info("No overlap for this state between the two submissions.")

                    # Numerical diff at median.
                    def _medians(sub, fips):
                        s = sub[(sub.location == fips) &
                                (sub.output_type == "quantile") &
                                (sub.output_type_id.astype(float) == 0.5)].copy()
                        s = s[["horizon", "target_end_date", "value"]].sort_values("horizon")
                        return s
                    m_a = _medians(sub_a, diff_fips).rename(columns={"value": "median_a"})
                    m_b = _medians(sub_b, diff_fips).rename(columns={"value": "median_b"})
                    if not m_a.empty and not m_b.empty:
                        m = m_a.merge(m_b, on="horizon", suffixes=("_a", "_b"))
                        m["abs_delta"] = m["median_b"] - m["median_a"]
                        m["pct_delta"] = (m["median_b"] / m["median_a"] - 1) * 100
                        m = m[["horizon", "median_a", "median_b",
                               "abs_delta", "pct_delta"]].round(2)
                        st.markdown("**Median forecast diff (B − A)**")
                        st.dataframe(m, use_container_width=True,
                                     hide_index=True)


# ===========================================================================
# SEASON REPORT TAB
# ===========================================================================
with tab_season:
    st.subheader("Season-progress dashboard")
    st.caption(
        "Aggregate view of how the season has evolved in this workspace: "
        "piecewise complexity, calibration drift, and forecast trend."
    )
    try:
        import altair as alt
        report = _cached_season_report(
            str(paths.root), _dir_signature(paths.root),
        )

        # --- K trend across the season ---
        with st.container(border=True):
            st.markdown("**Piecewise K growth across the season**")
            if report.aggregate_k_trend.empty:
                st.info(
                    "No session history yet. Run weekly jobs or "
                    "retrospective backtests with `adaptive` mode to "
                    "populate this."
                )
            else:
                k_df = report.aggregate_k_trend.copy()
                k_df["reference_date"] = pd.to_datetime(k_df["reference_date"])
                ch_mean = alt.Chart(k_df).mark_line(
                    color="#16355f", strokeWidth=2.5,
                ).encode(
                    x=alt.X("reference_date:T", title=None),
                    y=alt.Y("mean_K:Q", title="K (mean across states)",
                            scale=alt.Scale(zero=False)),
                    tooltip=["reference_date:T", "mean_K:Q", "max_K:Q",
                            "n_states_with_K_gt_1:Q"],
                )
                ch_max = alt.Chart(k_df).mark_line(
                    color="#0b6b3a", strokeWidth=1.5, strokeDash=[6, 4],
                ).encode(
                    x=alt.X("reference_date:T"),
                    y=alt.Y("max_K:Q"),
                )
                st.altair_chart(
                    alt.layer(ch_mean, ch_max).resolve_scale(y="shared")
                       .properties(height=260),
                    use_container_width=True,
                )
                st.dataframe(k_df.tail(12), use_container_width=True,
                             hide_index=True, height=200)

        # --- Calibration drift ---
        with st.container(border=True):
            st.markdown("**Calibration drift per horizon**")
            if report.aggregate_calibration.empty:
                st.info(
                    "No calibration records yet. After a few weeks of "
                    "submissions get realized, this panel populates."
                )
            else:
                ac = report.aggregate_calibration.copy()
                # Tidy long-form for plotting.
                tidy = ac.melt(
                    id_vars=["horizon", "n_states"],
                    value_vars=["mean_coverage_50", "mean_coverage_80",
                                "mean_coverage_95"],
                    var_name="pi_level", value_name="coverage",
                )
                # Map names to nominal levels for comparison.
                level_map = {"mean_coverage_50": 0.5, "mean_coverage_80": 0.8,
                             "mean_coverage_95": 0.95}
                tidy["nominal"] = tidy["pi_level"].map(level_map)
                chart = alt.Chart(tidy).mark_line(point=True).encode(
                    x=alt.X("horizon:O", title="forecast horizon"),
                    y=alt.Y("coverage:Q", title="empirical coverage",
                            scale=alt.Scale(domain=[0, 1])),
                    color=alt.Color("pi_level:N", title="PI level"),
                    tooltip=["pi_level:N", "horizon:O", "coverage:Q",
                            "nominal:Q"],
                ).properties(height=240)
                # Reference line at each PI's nominal value.
                ref_df = pd.DataFrame([
                    {"horizon": h, "nominal": n, "pi_level": k}
                    for h in tidy["horizon"].unique()
                    for k, n in level_map.items()
                ])
                ref_layer = alt.Chart(ref_df).mark_rule(
                    strokeDash=[2, 2], color="#999",
                ).encode(
                    x="horizon:O", y="nominal:Q",
                )
                st.altair_chart(
                    alt.layer(chart, ref_layer).properties(height=260),
                    use_container_width=True,
                )
                st.dataframe(ac, use_container_width=True, hide_index=True)

        # --- Forecast medians across the season for a chosen state ---
        with st.container(border=True):
            st.markdown("**Forecast median trend (per state)**")
            if report.submissions.empty:
                st.info(
                    "No submissions in this workspace yet to plot the trend."
                )
            else:
                from flubnf.constants import load_locations
                try:
                    locs = load_locations(cfg.locations_csv)
                except Exception:
                    locs = None
                state_choice_sr = st.selectbox(
                    "State", JURISDICTIONS, index=0,
                    key="season_state_choice",
                )
                fips = (locs[state_choice_sr].fips if locs and
                        state_choice_sr in locs else None)
                sub_state = report.submissions[
                    report.submissions["location"] == fips
                ].copy()
                if sub_state.empty:
                    st.info(f"No submissions for {state_choice_sr}.")
                else:
                    sub_state["target_end_date"] = pd.to_datetime(
                        sub_state["target_end_date"]
                    )
                    ch = alt.Chart(sub_state).mark_line(point=True).encode(
                        x=alt.X("target_end_date:T", title="forecast week"),
                        y=alt.Y("median:Q", title="median forecast"),
                        color=alt.Color(
                            "horizon:O", title="horizon (weeks ahead)",
                        ),
                        tooltip=["reference_date:N", "target_end_date:T",
                                 "horizon:O", "median:Q"],
                    ).properties(height=260)
                    st.altair_chart(ch, use_container_width=True)

    except Exception as e:
        st.error(f"Season report failed to build: {e}")

    # --- WIS leaderboard vs team baseline ---
    with st.container(border=True):
        st.markdown("**WIS leaderboard vs team baseline**")
        st.caption(
            "How our submissions in this workspace stack up against the "
            "team's actual hub submissions, per state and per horizon. "
            "Run `flubnf score-team` first to populate the team baseline."
        )
        team_csv_dir = paths.root.parent.parent / "backtest_results"
        team_csv = team_csv_dir / "flusight_team_scored.csv"
        csvs_data = sorted(cfg.data_cache.glob("*.csv")) \
            if cfg.data_cache.exists() else []
        if not (paths.root / "submissions").exists() or \
                not list((paths.root / "submissions").glob("*.csv")):
            st.info(
                "No submissions in this workspace yet. Run weekly jobs "
                "to populate."
            )
        elif not team_csv.exists():
            st.info(
                f"Team baseline not found at `{team_csv}`. Run "
                "`flubnf score-team` from the CLI to score the FluSight hub "
                "submissions."
            )
        elif not csvs_data:
            st.info("No CDC observed CSV cached; can't score our own forecasts.")
        else:
            try:
                from flubnf.leaderboard import score_our_submissions, leaderboard
                obs_csv = csvs_data[-1]
                ours = score_our_submissions(
                    paths.root / "submissions", obs_csv, cfg,
                )
                if ours.empty:
                    st.info(
                        "Couldn't score our submissions — observed CSV "
                        "may not yet have data for forecast target dates."
                    )
                else:
                    lb = leaderboard(ours, team_csv)
                    merged = lb["merged"]
                    if merged.empty:
                        st.info(
                            "No overlapping (date, state, horizon) cells "
                            "between our submissions and team baseline."
                        )
                    else:
                        won = int(merged["we_win"].sum())
                        total = len(merged)
                        delta = float(merged["delta_wis"].mean())
                        if delta < 0:
                            st.success(
                                f"**We're winning** by {-delta:.1f} WIS on "
                                f"average ({won}/{total} cells = "
                                f"{won/total:.0%})"
                            )
                        else:
                            st.warning(
                                f"Team is winning by {delta:.1f} WIS on "
                                f"average ({won}/{total} cells = "
                                f"{won/total:.0%} for us)"
                            )
                        st.markdown("**Per-state**")
                        st.dataframe(
                            lb["by_state"].round(2),
                            use_container_width=True, hide_index=True,
                            height=300,
                        )
                        st.markdown("**Per-horizon**")
                        st.dataframe(
                            lb["by_horizon"].round(2),
                            use_container_width=True, hide_index=True,
                        )
                        st.markdown("**Per-week trend**")
                        import altair as alt
                        wk = lb["by_week"].copy()
                        wk["reference_date"] = pd.to_datetime(wk["reference_date"])
                        long_df = wk.melt(
                            id_vars="reference_date",
                            value_vars=["our_mean_wis", "team_mean_wis"],
                            var_name="who", value_name="mean_wis",
                        )
                        ch = alt.Chart(long_df).mark_line(point=True).encode(
                            x=alt.X("reference_date:T"),
                            y=alt.Y("mean_wis:Q", title="mean WIS",
                                    scale=alt.Scale(zero=False)),
                            color=alt.Color("who:N", title=""),
                            tooltip=["reference_date:T", "who:N",
                                     "mean_wis:Q"],
                        ).properties(height=240)
                        st.altair_chart(ch, use_container_width=True)
            except Exception as e:
                st.error(f"leaderboard failed: {e}")

    # --- Per-state error decomposition (sharpness / calibration / bias) ---
    with st.container(border=True):
        st.markdown("**Error decomposition — sharpness, calibration, bias**")
        st.caption(
            "WIS broken into its three sources: how wide our intervals are "
            "(sharpness), how often the actual lands inside them (coverage "
            "of the 50/80/95% PIs), and whether we systematically over- or "
            "under-forecast (bias). Helps target what to tune."
        )
        if not (paths.root / "submissions").exists() or \
                not list((paths.root / "submissions").glob("*.csv")):
            st.info("No submissions to decompose yet.")
        elif not csvs_data:
            st.info("No CDC observed CSV cached; can't score for decomposition.")
        else:
            try:
                from flubnf.error_decomp import (aggregate_by_state,
                                                 aggregate_by_state_horizon,
                                                 decompose_submissions)
                decomp = decompose_submissions(
                    paths.root / "submissions", csvs_data[-1], cfg,
                )
                if decomp.empty:
                    st.info(
                        "Couldn't decompose — observed CSV may lack data "
                        "for the forecast target dates."
                    )
                else:
                    by_state = aggregate_by_state(decomp)
                    st.markdown("**Per-state summary** (sorted by mean WIS, worst first)")
                    st.dataframe(
                        by_state.round(3),
                        use_container_width=True, hide_index=True,
                        height=300,
                        column_config={
                            "calibration_score": st.column_config.ProgressColumn(
                                "calibration", format="%.2f",
                                min_value=0.0, max_value=1.0,
                            ),
                            "coverage_50": st.column_config.NumberColumn(
                                "cov50 (target 0.50)", format="%.2f",
                            ),
                            "coverage_95": st.column_config.NumberColumn(
                                "cov95 (target 0.95)", format="%.2f",
                            ),
                        },
                    )
                    by_sh = aggregate_by_state_horizon(decomp)
                    if not by_sh.empty:
                        st.markdown("**Per-(state, horizon) sharpness heatmap**")
                        import altair as alt
                        heat = alt.Chart(by_sh).mark_rect().encode(
                            x=alt.X("horizon:O"),
                            y=alt.Y("state:N", sort="-x"),
                            color=alt.Color(
                                "mean_sharpness:Q",
                                scale=alt.Scale(scheme="orangered"),
                            ),
                            tooltip=["state", "horizon", "mean_sharpness",
                                     "mean_bias", "mean_wis"],
                        ).properties(height=420)
                        st.altair_chart(heat, use_container_width=True)
            except Exception as e:
                st.error(f"error decomposition failed: {e}")


# ===========================================================================
# DIAGNOSTICS TAB
# ===========================================================================
with tab_diag:
    st.subheader("Per-state diagnostics")
    st.caption(
        "Inspect AMCMC convergence, outbreak phase, session history, and "
        "raw input/output files for a state in the active workspace."
    )

    diag_state = st.selectbox(
        "State", JURISDICTIONS, index=0, key="diag_state",
    )

    # Session ledger
    with st.container(border=True):
        st.markdown(f"**Session ledger — {diag_state}**")
        sess = load_session(paths.root, diag_state)
        if sess is None:
            st.info("No session ledger yet (the state has not been fit in this workspace).")
        else:
            cols = st.columns(3)
            cols[0].metric("Piecewise K", sess.n_steps)
            cols[1].metric("Last reference date", sess.last_reference_date or "—")
            cols[2].metric("History entries", len(sess.history))
            st.markdown("**Current bounds**")
            bounds_df = pd.DataFrame([
                {"param": fp.name, "low": fp.low, "high": fp.high,
                 "width": fp.high - fp.low}
                for fp in sess.bounds
            ])
            st.dataframe(bounds_df, use_container_width=True, hide_index=True,
                         height=240)
            if sess.history:
                st.markdown("**History (most recent 10)**")
                hist_df = pd.DataFrame(sess.history[-10:][::-1])
                st.dataframe(hist_df, use_container_width=True,
                             hide_index=True, height=240)

    # Fringe-case ledger
    with st.container(border=True):
        st.markdown(f"**Fringe cases — {diag_state}**")
        st.caption(
            "Codified failure modes the system has learned to watch for. "
            "Each case shows whether it's currently fired for this state, "
            "and what the recommended automated response is."
        )
        try:
            from flubnf.fringe_cases import evaluate_all
            exp_path = paths.exp_file(diag_state)
            obs_arr = (
                pd.read_csv(exp_path, sep="\t")["H_weekly"].to_numpy(dtype=float)
                if exp_path.exists() else np.array([], dtype=float)
            )
            sess_for_fringe = load_session(paths.root, diag_state)
            matches = evaluate_all(obs_arr, sess_for_fringe)
            rows = []
            for m in matches:
                rows.append({
                    "case": m.case_name,
                    "fired": "🔴 yes" if m.triggered else "—",
                    "detail": m.detail,
                    "recommendations": ", ".join(m.recommended_actions) or "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True,
                         hide_index=True, height=240)
        except Exception as e:
            st.info(f"Could not evaluate fringe cases: {e}")

    # Outbreak phase
    with st.container(border=True):
        st.markdown(f"**Outbreak phase — {diag_state}**")
        try:
            from flubnf.phase import detect_phase
        except Exception:
            detect_phase = None
        exp_path = paths.exp_file(diag_state)
        if exp_path.exists() and detect_phase is not None:
            obs = pd.read_csv(exp_path, sep="\t")["H_weekly"].to_numpy(dtype=float)
            if len(obs) > 0:
                pa = detect_phase(obs)
                color = {
                    "rising": "#0b6b3a", "near_peak": "#b35900",
                    "falling": "#5b3a99", "trough": "#b35900",
                    "pre_outbreak": "#475569", "unknown": "#475569",
                }.get(pa.phase.value, "#475569")
                st.markdown(
                    f'<span class="flubnf-stat-pill" style="background:{color};color:white;">'
                    f"{pa.phase.value.upper()}</span>",
                    unsafe_allow_html=True,
                )
                cols = st.columns(3)
                cols[0].metric("recent slope (weekly Δ)", f"{pa.recent_slope:.1f}")
                cols[1].metric("curvature (Δ²)", f"{pa.recent_curvature:.1f}")
                cols[2].metric("median recent", f"{pa.median_recent:.0f}")
                # Plot observed
                obs_df = pd.DataFrame({"week": range(len(obs)), "H_weekly": obs})
                st.line_chart(obs_df.set_index("week"))
        else:
            st.info(".exp file missing for this state. Run a backtest or "
                    "weekly job first.")

    # AMCMC diagnostics if available
    with st.container(border=True):
        st.markdown(f"**AMCMC chain diagnostics — {diag_state}**")
        try:
            from flubnf.diagnostics import (compute_diagnostics,
                                             react_to_diagnostics)
        except Exception:
            compute_diagnostics = None
        sess = load_session(paths.root, diag_state) if sess is None else sess
        if compute_diagnostics is not None:
            try:
                rep = compute_diagnostics(
                    paths.results_for(diag_state), diag_state,
                    bounds=(sess.bounds if sess else None),
                )
            except Exception as e:
                rep = None
                st.info(f"No diagnostics available: {e}")
            if rep is not None:
                cols = st.columns(4)
                cols[0].metric("samples post-burn", rep.n_samples)
                cols[1].metric("acceptance proxy", f"{rep.acceptance_proxy:.0%}")
                cols[2].metric("ESS proxy", f"{rep.ess_proxy:.0f}")
                cols[3].metric("score range", f"{rep.score_range:.1f}")
                if rep.warnings:
                    st.warning("Diagnostic warnings:\n- " + "\n- ".join(rep.warnings))
                else:
                    st.success("Chain diagnostics are clean.")
                if rep.param_stats:
                    stat_df = pd.DataFrame([
                        {"param": p.name, "median": p.median,
                         "p5": p.p05, "p95": p.p95, "iqr": p.iqr,
                         "% near low": p.frac_near_low * 100,
                         "% near high": p.frac_near_high * 100}
                        for p in rep.param_stats
                    ]).round(3)
                    st.dataframe(stat_df, use_container_width=True, hide_index=True)
                actions = react_to_diagnostics(rep)
                action_rows = [
                    {"kind": a.kind, "param": a.param or "—", "factor": a.factor,
                     "detail": a.detail}
                    for a in actions
                ]
                if action_rows:
                    st.markdown("**Reactive actions queued for next fit**")
                    st.dataframe(pd.DataFrame(action_rows),
                                 use_container_width=True, hide_index=True)
        else:
            st.info("diagnostics module not importable")

    # AMCMC posterior + chain trace plots.
    with st.container(border=True):
        st.markdown(f"**Posterior + chain traces — {diag_state}**")
        st.caption(
            "One trace + posterior-density plot per parameter from the "
            "most recent AMCMC chain. Use to spot stuck or poorly-mixed "
            "parameters by eye."
        )
        try:
            from flubnf.results import read_amcmc_chain
            from flubnf.ui_plots import (build_chain_trace_chart,
                                          build_posterior_density_chart)
            chain = read_amcmc_chain(paths.results_for(diag_state), diag_state)
        except Exception as e:
            chain = None
            st.info(f"no AMCMC chain available: {e}")
        if chain is not None and not chain.empty:
            free_cols = [c for c in chain.columns if c.endswith("__FREE")]
            cols = st.columns(2)
            for idx, p_name in enumerate(free_cols):
                target = cols[idx % 2]
                with target:
                    trace = build_chain_trace_chart(chain, param=p_name)
                    if trace is not None:
                        st.altair_chart(trace, use_container_width=True)
                    density = build_posterior_density_chart(chain, param=p_name)
                    if density is not None:
                        st.altair_chart(density, use_container_width=True)
        else:
            st.info(
                "No AMCMC chain yet. Run an AMCMC fit "
                "(Real-time or Retrospective with engine=amcmc)."
            )

    # Per-state forecast accuracy across the season.
    with st.container(border=True):
        st.markdown(f"**Forecast medians vs realized actuals — {diag_state}**")
        st.caption(
            "Every past submission's median forecast for this state, "
            "compared against the realized observation when it landed. "
            "Quick eyeball of which horizons we tend to over/under-predict."
        )
        try:
            from flubnf.leaderboard import score_our_submissions
            from flubnf.ui_plots import build_forecast_accuracy_chart
            csvs_data = sorted(cfg.data_cache.glob("*.csv")) \
                if cfg.data_cache.exists() else []
            if not csvs_data:
                st.info("No CDC CSV cached.")
            elif not (paths.root / "submissions").exists() or \
                    not list((paths.root / "submissions").glob("*.csv")):
                st.info("No submissions in this workspace yet.")
            else:
                ours = score_our_submissions(
                    paths.root / "submissions", csvs_data[-1], cfg,
                )
                ours_state = ours[ours["state"] == diag_state]
                if ours_state.empty:
                    st.info(
                        f"No realized actuals yet for {diag_state}'s past "
                        f"forecasts."
                    )
                else:
                    chart = build_forecast_accuracy_chart(
                        ours_state[["reference_date", "horizon", "our_median",
                                     "our_wis", "actual"]],
                        state=diag_state,
                    )
                    if chart is not None:
                        st.altair_chart(chart, use_container_width=True)
                    # Tabular WIS summary per horizon.
                    by_h = ours_state.groupby("horizon").agg(
                        n=("our_wis", "count"),
                        mean_wis=("our_wis", "mean"),
                        median_wis=("our_wis", "median"),
                    ).reset_index().round(2)
                    st.markdown("**WIS summary (this state)**")
                    st.dataframe(by_h, use_container_width=True,
                                 hide_index=True)
        except Exception as e:
            st.info(f"Could not build accuracy plot: {e}")

    # Forecast fan from the latest AMCMC traj_noise file in this workspace.
    with st.container(border=True):
        st.markdown(f"**Latest forecast fan — {diag_state}**")
        try:
            from .amcmc import read_traj_noise, quantile_forecast_from_amcmc
            from .ui_plots import build_quantile_fan
        except Exception:
            read_traj_noise = None
        traj = read_traj_noise(paths.results_for(diag_state), diag_state) \
            if read_traj_noise else None
        exp_path = paths.exp_file(diag_state)
        if traj is not None and exp_path.exists():
            obs = pd.read_csv(exp_path, sep="\t")["H_weekly"].to_numpy(dtype=float)
            n_obs = len(obs)
            if traj.shape[1] >= n_obs + 4:
                qf = quantile_forecast_from_amcmc(
                    traj, n_observed=n_obs, horizons=[1, 2, 3, 4],
                    observed=obs, anchor=True,
                )
                qd = qf.to_dict()
                chart = build_quantile_fan(
                    obs, qd, horizons=[1, 2, 3, 4],
                    state_name=diag_state,
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info(
                    f"traj_noise has {traj.shape[1]} weeks but needs at "
                    f"least {n_obs + 4} (n_obs={n_obs}). Re-fit with "
                    f"forecast_horizon=4 to enable the fan plot."
                )
        else:
            st.info(
                "No AMCMC traj_noise file for this state yet. Run an AMCMC "
                "fit (Real-time tab or Retrospective tab with engine=amcmc)."
            )

    # Backtest CSV comparison — drop in two backtest CSVs to see where one
    # mode helps vs the other (e.g. v6 adaptive_blend vs v5 anchored-only).
    with st.container(border=True):
        st.markdown(f"**Compare two backtests — {diag_state}**")
        backtest_dir = paths.root.parent.parent / "backtest_results"
        bt_csvs = sorted(backtest_dir.glob("*.csv")) if backtest_dir.exists() else []
        if len(bt_csvs) < 2:
            st.caption(
                f"Need at least 2 backtest CSVs in `{backtest_dir}` "
                f"(found {len(bt_csvs)}). Run two `flubnf backtest` "
                f"invocations with different settings to use this panel."
            )
        else:
            cols = st.columns(2)
            with cols[0]:
                cmp_a = st.selectbox("A", [p.name for p in bt_csvs],
                                     index=max(0, len(bt_csvs) - 2),
                                     key="diag_cmp_a")
                label_a = st.text_input("label A", value="A",
                                        key="diag_cmp_la")
            with cols[1]:
                cmp_b = st.selectbox("B", [p.name for p in bt_csvs],
                                     index=len(bt_csvs) - 1,
                                     key="diag_cmp_b")
                label_b = st.text_input("label B", value="B",
                                        key="diag_cmp_lb")
            if st.button("Compare", key="diag_cmp_btn"):
                df_a = pd.read_csv(backtest_dir / cmp_a)
                df_b = pd.read_csv(backtest_dir / cmp_b)
                df_a = df_a[df_a["state"] == diag_state]
                df_b = df_b[df_b["state"] == diag_state]
                if df_a.empty or df_b.empty:
                    st.warning(f"No rows for {diag_state} in one of the CSVs.")
                else:
                    merged = df_a.merge(df_b, on=["state", "week", "adaptive"],
                                        suffixes=(f"_{label_a}", f"_{label_b}"))
                    delta = merged[f"wis_mean_{label_b}"] - merged[f"wis_mean_{label_a}"]
                    cols2 = st.columns(3)
                    cols2[0].metric(f"{label_a} mean WIS", f"{merged[f'wis_mean_{label_a}'].mean():.1f}")
                    cols2[1].metric(f"{label_b} mean WIS", f"{merged[f'wis_mean_{label_b}'].mean():.1f}")
                    cols2[2].metric(f"{label_b} − {label_a}", f"{delta.mean():+.1f}",
                                    delta_color="inverse")
                    show_df = merged[["week", "adaptive",
                                       f"wis_mean_{label_a}",
                                       f"wis_mean_{label_b}",
                                       f"n_steps_{label_a}",
                                       f"n_steps_{label_b}"]].round(1)
                    show_df.columns = ["week", "adaptive",
                                        f"WIS {label_a}", f"WIS {label_b}",
                                        f"K {label_a}", f"K {label_b}"]
                    st.dataframe(show_df, use_container_width=True,
                                 hide_index=True, height=300)

    # Raw files
    with st.container(border=True):
        st.markdown(f"**Files — {diag_state}**")
        file_tabs = st.tabs([".exp", ".conf", ".bngl"])
        with file_tabs[0]:
            p = paths.exp_file(diag_state)
            if p.exists():
                df = pd.read_csv(p, sep="\t")
                if not df.empty:
                    st.line_chart(df.set_index("#time"))
                st.dataframe(df, use_container_width=True, height=200)
            else:
                st.info("not generated yet")
        with file_tabs[1]:
            p = paths.conf_file(diag_state)
            st.code(p.read_text() if p.exists() else "(missing)", language="ini")
        with file_tabs[2]:
            p = paths.bngl_file(diag_state)
            st.code(p.read_text() if p.exists() else "(missing)", language="text")


# ===========================================================================
# SETTINGS TAB
# ===========================================================================
with tab_settings:
    st.subheader("Settings & manual controls")
    st.caption(
        "Per-stage controls for when something needs intervention outside "
        "the one-click workflow. Most users won't need this tab."
    )

    with st.expander("Active config", expanded=False):
        cfg_dict = cfg.model_dump()
        st.json(cfg_dict, expanded=False)

    with st.expander("Initialize / refresh per-state .bngl + .conf"):
        c1, c2 = st.columns([1, 2])
        with c1:
            force_init = st.checkbox("re-materialize", value=False, key="force_init")
            if st.button("init", key="btn_init"):
                with st.spinner("materializing template files..."):
                    bngl_files.materialize_all(JURISDICTIONS, paths, cfg, force=force_init)
                    conf_files.materialize_all(JURISDICTIONS, paths, cfg, force=force_init)
                st.success(f"initialized {len(JURISDICTIONS)} jurisdictions.")
        with c2:
            st.metric("bngl files", n_bngl)
            st.metric("conf files", n_conf)

    with st.expander("Fetch CDC data"):
        c1, c2 = st.columns([1, 2])
        with c1:
            force_fetch = st.checkbox("force redownload", value=False, key="force_fetch")
            source = st.selectbox("source", ["socrata", "flusight"], index=0,
                                  key="settings_fetch_source")
            if st.button("fetch", key="btn_fetch"):
                with st.spinner(f"fetching from {source}..."):
                    try:
                        result = fetch.fetch_cdc_data(cfg, force=force_fetch, prefer=source)
                        state.last_data_as_of = result.as_of.isoformat()
                        state.save(paths.state_file)
                        st.success(f"{result.source}: {result.rows} rows, as_of={result.as_of}")
                    except Exception as e:
                        st.error(f"fetch failed: {e}")
        with c2:
            csvs = sorted(cfg.data_cache.glob("*.csv")) if cfg.data_cache.exists() else []
            if csvs:
                st.write("Cached CSVs:")
                for c in csvs[-5:]:
                    st.code(c.name)

    with st.expander("Score team submissions (for retrospective comparison)"):
        team_dir = cfg.data_cache.parent / "flusight"
        target_csv = cfg.data_cache.parent / "flusight_target" / "target-hospital-admissions.csv"
        st.markdown(f"**Submissions dir**: `{team_dir}`")
        st.markdown(f"**Target CSV**: `{target_csv}`")
        out_dir = paths.root.parent.parent / "backtest_results"
        out_csv = st.text_input(
            "Output CSV path",
            value=str(out_dir / "flusight_team_scored.csv"),
            key="settings_score_team_out",
        )
        if st.button("Score team submissions", key="settings_score_team_btn"):
            with st.spinner("scoring..."):
                paths_in = sorted(team_dir.glob("*.csv")) if team_dir.exists() else []
                if not paths_in:
                    st.error(f"No submissions in {team_dir}")
                elif not target_csv.exists():
                    st.error(f"Target CSV missing: {target_csv}")
                else:
                    df = flusight.score_all_submissions(paths_in, target_csv)
                    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
                    df.to_csv(out_csv, index=False)
                    st.success(f"Scored {len(df)} rows → `{out_csv}`")

    with st.expander("Per-state tuning overrides"):
        st.caption(
            "Edit hyperparameters that override defaults for a single "
            "state. Persisted in the state's session.json — survives "
            "across weekly jobs. Use this when a Mac Studio sweep or "
            "manual experimentation finds a per-state optimum."
        )
        try:
            from flubnf.session import save_session, StateSession
            tune_state = st.selectbox(
                "State", JURISDICTIONS, index=0, key="settings_tune_state",
            )
            sess = load_session(paths.root, tune_state)
            if sess is None:
                sess = StateSession(state=tune_state)
            cols = st.columns(2)
            current_blend = float(sess.get_tuning("slope_blend", 0.0))
            current_lookback = int(sess.get_tuning("anchor_lookback", 3))
            current_phase_aware = bool(sess.get_tuning("phase_aware", True))
            current_max_K = int(sess.get_tuning("max_K", 0))   # 0 = use default
            with cols[0]:
                new_blend = st.number_input(
                    "slope_blend",
                    min_value=-1.0, max_value=1.0, step=0.05,
                    value=current_blend, key="settings_tune_blend",
                    help="0 = trust model. -1 = adaptive auto-tune. "
                         "0.1-0.5 = pull toward observed momentum.",
                )
                new_lookback = st.number_input(
                    "anchor_lookback",
                    min_value=1, max_value=10, step=1,
                    value=current_lookback, key="settings_tune_lookback",
                    help="Weeks of recent observations used to compute "
                         "the anchor ratio.",
                )
            with cols[1]:
                new_phase_aware = st.checkbox(
                    "phase_aware (suppress blend in NEAR_PEAK/TROUGH)",
                    value=current_phase_aware,
                    key="settings_tune_phase",
                )
                new_max_K = st.number_input(
                    "max_K (0 = use jurisdiction default)",
                    min_value=0, max_value=12, step=1,
                    value=current_max_K, key="settings_tune_max_K",
                )
            if st.button("Save tuning", key="settings_tune_save",
                          type="primary"):
                sess.tuning["slope_blend"] = float(new_blend)
                sess.tuning["anchor_lookback"] = int(new_lookback)
                sess.tuning["phase_aware"] = bool(new_phase_aware)
                if int(new_max_K) > 0:
                    sess.tuning["max_K"] = int(new_max_K)
                elif "max_K" in sess.tuning:
                    del sess.tuning["max_K"]
                save_session(paths.root, sess)
                st.success(
                    f"saved tuning for {tune_state}: "
                    f"slope_blend={new_blend} lookback={new_lookback} "
                    f"phase_aware={new_phase_aware} "
                    f"max_K={'(default)' if new_max_K == 0 else new_max_K}"
                )
        except Exception as e:
            st.error(f"tuning editor failed: {e}")

    with st.expander("Calibration tracker (PI coverage rolling window)"):
        st.caption(
            "Empirical prediction-interval coverage per (state, horizon) "
            "over a rolling window of past forecast→actual pairs. Used "
            "to adaptively widen / narrow future quantile intervals when "
            "the model is systematically over- or under-confident."
        )
        try:
            from flubnf.calibration import CalibrationTracker
            cal_path = paths.root / "calibration.json"
            tracker = CalibrationTracker.load(cal_path)
        except Exception as e:
            tracker = None
            st.info(f"calibration tracker not loadable: {e}")
        if tracker is not None and tracker.history:
            rows = []
            for (st_name, h), recs in tracker.history.items():
                cov = tracker.empirical_coverage(st_name, h)
                factor = tracker.rescale_factor(st_name, h)
                rows.append({
                    "state": st_name,
                    "horizon": h,
                    "n_records": len(recs),
                    "50% coverage": f"{cov.get(0.5, float('nan')):.0%}"
                                    if not np.isnan(cov.get(0.5, float('nan'))) else "—",
                    "80% coverage": f"{cov.get(0.8, float('nan')):.0%}"
                                    if not np.isnan(cov.get(0.8, float('nan'))) else "—",
                    "95% coverage": f"{cov.get(0.95, float('nan')):.0%}"
                                    if not np.isnan(cov.get(0.95, float('nan'))) else "—",
                    "rescale factor": f"{factor:.2f}",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True,
                         hide_index=True, height=320)
        else:
            st.info(
                f"No calibration history yet at `{paths.root / 'calibration.json'}`. "
                "Run a few weekly jobs + the actuals will start accumulating "
                "automatically."
            )

    with st.expander("Historical priors (season-over-season learning)"):
        st.caption(
            "Per-state best-fit parameter summaries from prior seasons. "
            "Used as informed priors for next year — when this state's "
            "outbreak typically starts, what beta/gamma values fit."
        )
        try:
            from flubnf.historical_priors import (load_history,
                                                   history_path)
            hp_dir = paths.root.parent.parent / "data" / "historical_priors"
        except Exception as e:
            hp_dir = None
            st.info(f"historical_priors not importable: {e}")
        if hp_dir is not None:
            hp_files = sorted(hp_dir.glob("*.json")) if hp_dir.exists() else []
            if not hp_files:
                st.info(
                    f"No historical priors yet. After a season completes, "
                    f"call `flubnf.historical_priors.record_season(...)` "
                    f"per state to populate `{hp_dir}`."
                )
            else:
                rows = []
                for p in hp_files:
                    state_name = p.stem
                    hist = load_history(hp_dir, state_name)
                    if hist:
                        rows.append({
                            "state": state_name,
                            "seasons": ", ".join(
                                str(s.season_year) for s in hist.seasons
                            ),
                            "n_seasons": len(hist.seasons),
                        })
                st.dataframe(pd.DataFrame(rows), use_container_width=True,
                             hide_index=True)

    with st.expander("Workspace history"):
        if state.stages:
            df = pd.DataFrame([
                {"timestamp": s.ts, "stage": s.name, "status": s.status,
                 "details": ", ".join(f"{k}={v}" for k, v in s.details.items())}
                for s in state.stages
            ])
            st.dataframe(df, use_container_width=True, height=320)
        else:
            st.info("No activity in this workspace yet.")
