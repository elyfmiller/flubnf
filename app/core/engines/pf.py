"""The PF-SIHRS engine: conf generation + execution of PyBNF `fit_type=pf`.

Two-venv dispatch (constitutional rule 8): materialization and scoring run in
the analysis venv (py3.12, this process); the filter itself runs in the
pybnf/bngsim venv (py3.10) via runner scripts written to the workroot --
FILES, never stdin, because macOS spawn kills stdin-launched pools
(rule 4, measured 2026-08-17). The prepared cells are dealt across several
such runners, the way the retrospective path has always done it; see the
sharding block above execute().
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from flubnf.settings import PY_ENGINE as PY310, PYBNF as PYBNF_PF
TEMPLATE = REPO / "flubnf/templates/SIHRS_pop_min.bngl"   # H stays: verdict 2026-08-17
DEFAULTS_BLOCK = ("begin parameters\nReff__FREE 1.20\neps1__FREE 0.15\n"
                  "phi1__FREE 22.0\nmult__FREE 0.05\nr__FREE 8.0\n")
# Two-strain candidate (spec.extra["variant"] == "2strain"): A/B circuits +
# the NREVSS typed-positives binomial channel. Same trim as min.
TEMPLATE_2S = REPO / "flubnf/templates/SIHRS_pop_2strain_min.bngl"
# National-growth candidate (spec.extra["variant"] == "natg"): production `min`
# plus exp(iota*(g_nat^-s - g_s)) on beta(t), iota FROZEN a priori. Same 5
# fitted parameters, same defaults, same vars -- the arm adds no dimension, so
# DEFAULTS_BLOCK and VARS_1S are reused verbatim. See flubnf/natgrowth.py.
TEMPLATE_NATG = REPO / "flubnf/templates/SIHRS_pop_natg.bngl"
DEFAULTS_2S = ("begin parameters\nReffA__FREE 1.20\nReffB__FREE 0.95\n"
               "eps1__FREE 0.15\nphi1A__FREE 22.0\nphi1B__FREE 30.0\n"
               "mult__FREE 0.05\nr__FREE 8.0\n")
VARS_1S = """uniform_var = Reff__FREE 0.6 2.5
uniform_var = eps1__FREE 0.0 1.0
uniform_var = phi1__FREE 0.0 52.0
loguniform_var = mult__FREE 0.002 1.0
loguniform_var = r__FREE 0.1 40.0
"""
VARS_2S = """loguniform_var = ReffA__FREE 0.6 2.5
loguniform_var = ReffB__FREE 0.3 2.5
uniform_var = eps1__FREE 0.0 1.0
uniform_var = phi1A__FREE 0.0 52.0
uniform_var = phi1B__FREE 0.0 52.0
loguniform_var = mult__FREE 0.002 1.0
loguniform_var = r__FREE 0.1 40.0
"""

#: One shard's runner: the same idea as the retrospective path's
#: (app/core/retro.py::_RETRO_RUNNER), and for the same reason an entry-point
#: FILE rather than stdin (rule 4). Two properties the plural case needs:
#: it checks the halt flag BETWEEN cells, so a stop dispatches nothing more,
#: and it rewrites its status after EVERY cell, so a shard that dies still
#: reports what it finished instead of losing the whole shard.
_RUNNER = '''"""Auto-generated PF runner. Executes one shard's cells sequentially."""
import json, os, shutil, sys
import time as _t
sys.path.insert(0, {pybnf_path!r})
from pathlib import Path
cells = json.load(open({cells_json!r}))
out = {out_json!r}
halt = Path({halt_path!r})
results = {{}}
_t0 = _t.time()


def _publish(done):
    """Status and progress, written beside-then-replaced so a reader never
    sees half a file."""
    for path, payload in ((out, results),
                          (out + ".prog", {{"done": done, "total": len(cells),
                                            "t0": _t0, "now": _t.time()}})):
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(payload, fh)
        os.replace(tmp, path)


_publish(0)
for _i, c in enumerate(cells, 1):
    if halt.exists():
        break                     # stopped: this shard dispatches nothing more
    d = Path(c["dir"])
    shutil.rmtree(d / "out", ignore_errors=True)
    (d / "out" / "Results").mkdir(parents=True)
    cwd = os.getcwd(); os.chdir(d)
    try:
        from pybnf.parse import load_config
        from pybnf.pf import ParticleFilter
        ParticleFilter(load_config(str(d / "pf.conf"))).run(None)
        results[c["key"]] = "ok"
    except Exception as e:
        results[c["key"]] = f"FAIL: {{e}}"[:200]
    finally:
        os.chdir(cwd)
    _publish(_i)
'''


# --------------------------------------------------------------------------
# conf-safe paths
#
# PyBNF reads pf.conf with a pyparsing grammar whose bng_command and
# output_dir rules stop at whitespace (only the model line rides on
# pp.Regex), so a path containing a space cannot be expressed in the file
# at all: "C:\\Users\\John Smith\\..." raises ParseException "Expected end
# of text, found Smith" from deep inside the engine venv. On Windows the
# default workroot lives under C:\\Users\\<name>\\AppData\\..., so any
# student with a space in the username would fail every fit. The 8.3 short
# form of the same path is space-free wherever the volume keeps short
# names; where it does not (8.3 creation disabled), and on POSIX always,
# the only honest move is a legible refusal at prepare() time naming the
# path and the remedy.
# --------------------------------------------------------------------------

def _short_path_win(path: str, _api=None):
    """The 8.3 short form of an EXISTING path via kernel32
    GetShortPathNameW (the wide API; a first call with no buffer reports
    the size the second call needs), or None when the API is unavailable
    or either call fails. `_api` is injectable so the sizing dance is
    testable off Windows."""
    try:
        import ctypes
        if _api is None:
            _api = ctypes.windll.kernel32.GetShortPathNameW   # type: ignore[attr-defined]
        n = _api(path, None, 0)
        if not n:
            return None
        buf = ctypes.create_unicode_buffer(int(n))
        # per the API contract a return >= the buffer size means the path
        # changed between the two calls and the buffer contents are
        # undefined, so only 0 < ret < n is a completed copy
        ret = _api(path, buf, int(n))
        if not (0 < ret < int(n)):
            return None
        return buf.value or None
    except Exception:
        return None


def conf_safe_path(p, _platform: str | None = None) -> str:
    """`p` as pf.conf may carry it: unchanged when space-free, the 8.3
    short form on Windows when the path contains a space, and otherwise a
    legible refusal, because the grammar limit is platform-independent and
    the alternative is a ParseException from inside the engine venv
    mid-run. `_platform` is injectable for tests."""
    s = str(p)
    if " " not in s:
        return s
    if (_platform or sys.platform) == "win32":
        short = _short_path_win(s)
        if short and " " not in short:
            return short
    raise RuntimeError(
        f"PF configuration cannot express a path containing a space: {s!r}. "
        "PyBNF's conf grammar splits on whitespace, and no space-free (8.3) "
        "short form of this path is available. Move the FluBNF folder (and "
        "its workroot) to a path without spaces and rerun.")


#: Prepare-stage failures, keyed by location tag (no _r suffix, so a key
#: can never collide with a cell's). execute() folds the file into the
#: merged pf_status.json and the retrospective run_week folds it into the
#: week's failure record, so a state the vintage cannot resolve costs
#: that state, not the run.
PREPARE_FAILURES_NAME = "pf_prepare_failures.json"


def read_prepare_failures(workroot: Path) -> dict:
    """The prepare-stage failures recorded for a workroot; {} when the
    file is absent (an older workroot, or a stubbed prepare) or
    unreadable."""
    try:
        d = json.loads((Path(workroot) / PREPARE_FAILURES_NAME).read_text())
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def prepare(spec, workroot: Path) -> list:
    """Materialize model+net+exp+conf for every (location, replicate) cell.

    Failures are contained PER LOCATION: resolve_state refuses an empty
    window or an all-NaN tail (the documented MA/MN/WV reporting-pause
    pattern, present in 55 of 87 vintages), and one such state must cost
    itself, not the other 52 jurisdictions. Each contained failure is
    recorded in pf_prepare_failures.json under the location's tag, in the
    same FAIL-string shape execute() records fit failures, so it reaches
    pf_failures downstream. A run where every location fails still raises;
    a single-location run re-raises its one error verbatim."""
    from flubnf.sihrs_fit import materialize_model, resolve_state, write_exp
    from flubnf.settings import BNG
    from app.core.data import LOCATIONS, vintage_path
    from app.core.runs import derive_seed

    # The space guard runs first, before any location is touched: the
    # grammar limit is the same for every cell, and failing here names the
    # offending path instead of raising a ParseException from the engine
    # venv mid-run. The workroot is created up front so the Windows 8.3
    # lookup, which needs an existing path, can resolve it.
    workroot = Path(workroot)
    workroot.mkdir(parents=True, exist_ok=True)
    conf_safe_path(workroot)
    bng_conf = conf_safe_path(BNG)

    vintage = vintage_path(spec.forecast_date)
    variant = (spec.extra or {}).get("variant")
    two_strain = variant == "2strain"
    natg = variant == "natg"
    if natg:
        from flubnf.natgrowth import IOTA_FROZEN, growth_gap_series, natg_tokens
        # The ledger's copy of the spec is the record of record, so the frozen
        # value travels in spec.extra. Absent, it falls back to the constant --
        # it is never derived here and never fitted.
        iota = float((spec.extra or {}).get("iota", IOTA_FROZEN))
    if two_strain:
        from datetime import date as _d, timedelta as _td

        import pandas as _pd

        from flubnf import nrevss
        # NREVSS release cadence: week ending Saturday D publishes the
        # following Friday, i.e. AFTER the FluSight deadline for reference
        # date D. Honest as-of uses typed data through D-7.
        nrevss_asof = (_d.fromisoformat(spec.forecast_date)
                       - _td(days=7)).isoformat()

    def _one_location(loc: str) -> list:
        """Every prepared cell for one location; raises are the caller's
        to contain. A closure so the season context above (vintage,
        variant switches, the frozen iota) needs no plumbing."""
        s = resolve_state(loc, truth_csv=vintage, locations_csv=LOCATIONS,
                          season_start=spec.season_start,
                          as_of=spec.forecast_date)
        # The nowcast rule (drop_same_day, OFF by default since the
        # 2026-08-27 v1.1 measurement: dropping the same-day row cost
        # 2023-24 +0.24 pooled relWIS because that row carries the turn
        # signal; see RunSpec.drop_same_day). When enabled it trims the
        # vintage's same-day row per state, on top of any user-requested
        # weeks_to_drop; the weeks_dropped/pf_forecast_weeks machinery
        # keeps every horizon label as-of-relative either way.
        auto_drop = 0
        if getattr(spec, "drop_same_day", False) and len(s.times):
            from datetime import date as _date
            asof_off = (_date.fromisoformat(spec.forecast_date)
                        - _date.fromisoformat(spec.season_start)).days // 7
            if int(s.times[-1]) == int(asof_off):
                auto_drop = 1
        k_total = int(spec.weeks_to_drop or 0) + auto_drop
        if k_total:
            from datetime import date as _date2
            _off = (_date2.fromisoformat(spec.forecast_date)
                    - _date2.fromisoformat(spec.season_start)).days // 7
            if len(s.observed) <= k_total:
                raise ValueError(
                    f"{loc}: trimming {k_total} week(s) "
                    f"(weeks_to_drop={int(spec.weeks_to_drop or 0)}, "
                    f"same-day {auto_drop}) leaves no observations at "
                    f"{spec.forecast_date}; lower weeks_to_drop or pick a "
                    "later forecast date")
            s.observed = s.observed[:-k_total]
            s.times = s.times[:-k_total]
            s.n_obs = len(s.observed)
            # the horizon-label arithmetic (as-of-relative shift by
            # k_total) is only valid when the fit origin lands exactly
            # k_total calendar weeks before the as-of date. A NaN gap at
            # the series tail (the documented NHSN-pause pattern) breaks
            # that; refuse loudly rather than mislabel every horizon
            # (review finding).
            if _off - int(s.times[-1]) != k_total:
                raise ValueError(
                    f"{loc}: after trimming {k_total} week(s) the fit "
                    f"origin sits {_off - int(s.times[-1])} weeks before "
                    f"{spec.forecast_date}, not {k_total}: the series tail "
                    "is not calendar-consecutive (a reporting gap), so "
                    "horizon labels cannot be kept as-of-relative. "
                    "Refusing rather than mislabelling.")
        gg = None
        if natg:
            # Vintage-true on BOTH sides: the same file the state's own
            # likelihood reads. Truncated to the filter's real last week so the
            # "hold the last gap over h=1..4" branch begins exactly where the
            # forecast does, even when weeks_to_drop trimmed the tail.
            gg = growth_gap_series(
                loc, truth_csv=vintage, locations_csv=LOCATIONS,
                season_start=spec.season_start, as_of=spec.forecast_date
            ).truncate(int(s.last_week_offset))
        typed_by_t, a0 = {}, 0.85
        if two_strain:
            try:
                ser = nrevss.a_share_series(loc, spec.season_start, nrevss_asof)
                for row in ser.itertuples():
                    t_off = int((_pd.Timestamp(row.date)
                                 - _pd.Timestamp(spec.season_start)).days // 7)
                    typed_by_t[t_off] = (int(row.total_a),
                                         int(row.total_a) + int(row.total_b))
                a0 = nrevss.a0_share(loc, spec.season_start, nrevss_asof)
            except Exception:
                typed_by_t, a0 = {}, 0.85   # typed feed down: channel 2 just
                                            # has no rows; the fit still runs
        loc_cells = []
        for rep in range(spec.replicates):
            tag = f"{loc.replace(' ', '_')}_r{rep}"
            d = workroot / tag
            d.mkdir(parents=True)
            sfx = f"{loc.replace(' ', '_')}_flu"
            if two_strain:
                tmpl, tok = TEMPLATE_2S, {"{{A0SHARE}}": f"{a0:.4f}"}
            elif natg:
                tmpl, tok = TEMPLATE_NATG, natg_tokens(gg, iota)
            else:
                tmpl, tok = TEMPLATE, None
            m = materialize_model(s, tmpl, d / "m.bngl", sfx, extra_tokens=tok)
            # newline pinned, for the same reason materialize_model pins it:
            # this rewrite is the LAST hand on the model file, and a plain
            # write_text takes newline=None, which on Windows translates
            # every \n to \r\n on the way to disk. That silently undid the
            # pinning one line above and handed BNG2.pl and bngsim a CRLF
            # model. The Windows CI job caught it as a byte-identity
            # failure (test_natgrowth: b'...end actions\r\n' against
            # b'...end actions\n'); the engine bytes were the real casualty.
            # read_text needs no such care: universal-newline READ is
            # platform independent, so the \n in "begin parameters\n" below
            # matches whatever is on disk.
            m.write_text(m.read_text().replace("begin parameters\n",
                                               DEFAULTS_2S if two_strain
                                               else DEFAULTS_BLOCK, 1),
                         newline="\n")
            if two_strain:
                lines = ["# time H_weekly A_share_bin A_share_n"]
                for t_off, v in zip(s.times, s.observed):
                    a_k, n_k = typed_by_t.get(int(t_off), (-1, -1))
                    lines.append(f"{int(t_off)} {v:.6f} {a_k} {n_k}")
                # newline pinned: PyBNF splits the .exp line-wise, so a
                # trailing \r would ride along on the last column of every
                # row. Same treatment as the model file above.
                (d / f"{sfx}.exp").write_text("\n".join(lines) + "\n",
                                              newline="\n")
            else:
                write_exp(s, d / f"{sfx}.exp")
            r = subprocess.run(["perl", BNG, "m.bngl"], capture_output=True,
                               text=True, cwd=str(d), timeout=300)
            if not (d / "m.net").is_file():
                raise RuntimeError(f"netgen failed for {loc}: {r.stdout[-300:]}")
            seed = derive_seed(loc, spec.forecast_date, rep)
            # newline pinned: PyBNF's conf reader is line-based, so on
            # Windows every value would arrive with a trailing \r attached.
            # Every path goes through conf_safe_path: the bng_command and
            # output_dir grammar rules stop at whitespace, so a spaced
            # path here is a ParseException inside the engine venv.
            d_conf = conf_safe_path(d)
            (d / "pf.conf").write_text(f"""bng_command = {bng_conf}
model = {d_conf}/m.bngl : {d_conf}/{sfx}.exp
output_dir = {d_conf}/out
fit_type = pf
objfunc = neg_bin_dynamic
num_particles = {spec.particles}
pf_jitter = {spec.jitter}
pf_observable_mode = {spec.observable_mode}
pf_forecast_weeks = {4 + k_total}
population_size = 1
max_iterations = 1
seed = {seed}
{VARS_2S if two_strain else VARS_1S}"""
+ (f"pf_binom_neff_cap = {(spec.extra or {}).get('neff_cap', 300)}\n"
   if two_strain else ""), newline="\n")
            loc_cells.append({
                "key": tag, "dir": str(d), "location": loc,
                "replicate": rep, "seed": seed,
                # collect() shifts its forecast columns by this,
                # so horizon labels stay AS-OF-relative when the
                # newest weeks were trimmed (audit: with drop > 0
                # every horizon rode one week off its label).
                # Includes the nowcast rule's same-day trim.
                "weeks_dropped": k_total,
                "variant": ("2strain" if two_strain
                            else "natg" if natg else "1strain"),
                "a0": a0 if two_strain else None,
                "typed_weeks": len(typed_by_t) if two_strain else None,
                "iota": iota if natg else None,
                "natg_last_gap": gg.last_gap if natg else None,
                "natg_active_weeks": gg.n_active if natg else None,
                "natg_clipped_weeks": gg.n_clipped if natg else None,
                "n_obs": int(s.n_obs),
                "last_week_offset": int(s.last_week_offset),
                # the two quantities the cost model reads back at
                # execution time to size the run's time budget
                "particles": int(spec.particles),
                "last_observed": float(s.observed[-1])})
        return loc_cells

    cells, failures, errors = [], {}, []
    for loc in spec.locations:
        try:
            cells.extend(_one_location(loc))
        except Exception as e:
            failures[loc.replace(" ", "_")] = f"FAIL: prepare: {e}"[:200]
            errors.append(e)
    (workroot / PREPARE_FAILURES_NAME).write_text(json.dumps(failures))
    (workroot / "cells.json").write_text(json.dumps(cells))
    if failures and not cells:
        if len(errors) == 1:
            # a single-location run has nothing to continue with, and its
            # one error is more legible verbatim than wrapped
            raise errors[0]
        raise RuntimeError(
            f"prepare failed for all {len(failures)} location(s) "
            f"(first: {next(iter(failures.values()))})")
    return cells


class RunStopped(Exception):
    pass


# --------------------------------------------------------------------------
# parallel execution of a prepared grid
#
# The retrospective path has sharded since it was written (retro.py's
# _run_round: a stride partition of the week's cells, one runner subprocess
# per shard, all polled together). The forecast path did not, and because the
# entire sealed record was produced through the retrospective path, the
# sequential forecast path was never exercised at full grid. It cannot
# finish one: 53 jurisdictions x 3 replicates is 159 cells, and at the
# season's most expensive as-of (48 observed weeks) the measured cost of a
# cell is 34.3 s, so one process needs 91 minutes against a fixed 60-minute
# timeout. This is the same sharding, so that the two paths are one idea:
# cells are independent (one location by one replicate, its own model, conf
# and seed), so partitioning them changes no number, only the wall clock.
# --------------------------------------------------------------------------

#: Cores to leave for the console and the operating system. The fits are
#: also nice-d (app/core/proc.py), but a reserve keeps the machine usable
#: even when the scheduler is generous to the runners.
SHARD_CORES_RESERVED = 2

#: Upper bound. Past roughly this many runners the measured curve is flat,
#: and every extra process still costs memory and a startup.
SHARD_WIDTH_CAP = 16


def default_shard_width(cpus: int | None = None) -> int:
    """Runner subprocesses to deal the prepared cells across.

    Sized to the MACHINE rather than fixed, measured 2026-08-28 on a
    12-core M2 Max over a 24-cell grid: 1 runner 384s, 2 runners 200s,
    4 runners 103s, 8 runners 56s, 16 runners 53s. The old fixed default
    of 4 therefore left most of a workstation idle -- about 2x on this
    box, confirmed on a 48-cell grid (4 runners 206s, 16 runners 100s) --
    while the same fixed 4 would oversubscribe a 2-core laptop. Scaling
    with the core count is right on both, which is why this is a function
    of the machine and not a different constant.

    Sharding partitions independent cells (each carries its own model,
    config and seed), so this changes wall clock and no number.
    """
    n = cpus if cpus is not None else (os.cpu_count() or 4)
    return max(2, min(SHARD_WIDTH_CAP, n - SHARD_CORES_RESERVED))


#: Resolved once at import. retro.py takes its own default from this, so a
#: forecast and a replay of the same grid cannot drift apart in cost.
DEFAULT_SHARD_WIDTH = default_shard_width()

#: Per-machine override, never a scientific one: FLUBNF_PF_WIDTH=8 on a
#: wider box, =1 to reproduce the old single-process behaviour.
WIDTH_ENV = "FLUBNF_PF_WIDTH"

#: Measured seconds for one cell, fitted on 680 shard-weeks of the sealed
#: record (R^2 = 0.988):
#:
#:     seconds = 1.194 + 0.6365 * (n_obs + 4)
#:
#: The (n_obs + 4) is the filter's real length: the observed weeks plus the
#: four forecast weeks every pf.conf asks for. Cost is linear in the particle
#: count and the record was measured at 10,000, so a heavier run scales in
#: proportion. Prediction only: nothing here reaches a published number.
COST_INTERCEPT_S = 1.194
COST_PER_WEEK_S = 0.6365
COST_FORECAST_WEEKS = 4
COST_REFERENCE_PARTICLES = 10_000

#: The budget is this multiple of the predicted duration of the SLOWEST
#: shard. Three, and the reason is what the cost model cannot see: it
#: describes the throughput of one machine, and the machine running now may
#: be slower, or sharing its cores with the browser, the server, and a
#: retrospective replay. 3x covers a box three times slower than the one that
#: produced the sealed record while still failing a genuinely hung run in a
#: small multiple of its own estimate. The fixed 3600 s was too SHORT: it
#: killed the legitimate 91-minute full grid. It was never too long, because
#: a run whose runners have died does not wait out its budget -- they exit,
#: the poll loop below ends on the same tick, and the "produced no status"
#: error is raised at once. The budget only ever governs a run still alive.
TIMEOUT_SAFETY = 3.0

#: Floor under the budget, and the guarantee that this change only ever
#: EXTENDS the old behaviour.
#:
#: The multiple alone is not that guarantee. It is taken over the slowest
#: SHARD, so it silently assumes the machine really delivers the concurrency
#: the width asks for. Where it does not -- few free cores, thermal
#: throttling, a retrospective replay at width 4 on the same box (/api/busy
#: warns but permits) -- each runner's per-cell time inflates by the
#: oversubscription factor, and at width 4 a fully serialised machine needs
#: 4x the slowest shard against a 3x budget. Sizing on the shard would then
#: KILL runs the old fixed hour completed: the mid-January full grid this
#: change exists to protect is 159 cells at n_obs 23, 2922 s of honest
#: sequential work, and 3 x the slowest shard is only 2206 s.
#:
#: So the floor is the hour itself. The budget is by construction never
#: shorter than the constant it replaces and only ever longer, which is the
#: single property that makes this change safe to ship into a live season;
#: the multiple takes over above the crossover, where it is the old constant
#: that was too short. It also covers the small-grid case it was first
#: written for: three replicates at one location predict under two minutes,
#: which a cold interpreter, a cold network file and a busy disk can eat on
#: their own, and the multiple has nothing to work with at that size.
#:
#: The cost of a floor this high is bounded and small: a genuinely HUNG run
#: is declared dead after an hour rather than fifteen minutes, and the user
#: can press STOP at any point. Killing a legitimate weekly submission is
#: not comparably cheap.
TIMEOUT_FLOOR_S = 3600.0

#: How often the supervisor looks at its runners and at the STOP flag.
POLL_S = 1.0

#: The two signals a cancel uses. SIGKILL is POSIX-only; on Windows both
#: names resolve to the terminate path in _signal_tree, which is what that
#: platform did before.
_SIGTERM = signal.SIGTERM
_SIGKILL = getattr(signal, "SIGKILL", signal.SIGTERM)

_sleep = time.sleep          # indirection so tests can drive the poll loop

#: subprocess.CREATE_NEW_PROCESS_GROUP, spelled as its value because the
#: constant exists only in Windows builds of Python and this module must
#: import everywhere.
_CREATE_NEW_PROCESS_GROUP = 0x00000200

#: Where launched runners are recorded so a console takeover can sweep the
#: fits a dead predecessor left behind. The runners are plain Popen
#: children supervised from daemon threads: a takeover or window close
#: kills the server without running any supervisor's finally block, the
#: runners keep fitting, and a heartbeat-stale resume would then fit the
#: same cells concurrently. The relaunch path (flubnf/cli.py::
#: _sweep_runner_groups, which mirrors this path and must agree with it)
#: reads and clears the file. It lives beside app.pid: same lifecycle,
#: same owner.
RUNNER_PIDS_FILE = REPO / "app" / "state" / "pf_runners.json"


def runner_popen_kwargs(base: dict | None = None,
                        _os_name: str | None = None) -> dict:
    """`base` plus the keywords that put a runner in its own process group
    (its own session on POSIX). The group is the one address a console
    takeover can still signal after the supervising thread died with the
    server, and on POSIX killpg reaches the engine pool the runner spawned
    even though the parent link is gone. The supervisor's own cancel path
    does not lean on the group (_signal_tree sweeps the tree read from
    `ps`); the group exists for the runner that has no supervisor left.
    `_os_name` is injectable so both branches are testable anywhere."""
    kw = dict(base or {})
    if (_os_name or os.name) == "posix":
        kw["start_new_session"] = True
    else:
        kw["creationflags"] = (int(kw.get("creationflags", 0))
                               | _CREATE_NEW_PROCESS_GROUP)
    return kw


def record_runner_pids(procs, path: Path | None = None) -> None:
    """Add the launched runners to the takeover registry: pid, group id
    (POSIX sessions make pgid == pid; Windows taskkill /T needs only the
    pid), and the runner script, which the sweep checks against the live
    command line so a recycled pid is never signalled. Merged into any
    entries already present, because concurrent runs (a forecast beside a
    replay) each record their own runners. Never fatal: the registry is a
    courtesy to the NEXT launch, and no fit may die because it could not
    be written."""
    try:
        path = Path(path) if path else RUNNER_PIDS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            reg = json.loads(path.read_text())
        except Exception:
            reg = {}
        if not isinstance(reg, dict):
            reg = {}
        for p in procs:
            pid = getattr(p, "pid", None)
            if not pid:
                continue
            runner = ""
            try:
                args = (p.args if isinstance(p.args, (list, tuple))
                        else [p.args])
                runner = next((str(a) for a in args
                               if str(a).endswith(".py")), "")
            except Exception:
                pass
            reg[str(pid)] = {"pgid": pid if os.name == "posix" else None,
                             "runner": runner}
        tmp = path.parent / (path.name + ".tmp")
        tmp.write_text(json.dumps(reg))
        os.replace(tmp, path)
    except Exception:
        pass


def unrecord_runner_pids(procs, path: Path | None = None) -> None:
    """Drop finished runners from the takeover registry: the supervisor's
    own finally already stopped them, and a later sweep must not chase
    their recycled pids. Entries recorded by other live runs are left in
    place. Never fatal."""
    try:
        path = Path(path) if path else RUNNER_PIDS_FILE
        reg = json.loads(path.read_text())
        if not isinstance(reg, dict):
            return
        for p in procs:
            reg.pop(str(getattr(p, "pid", "")), None)
        tmp = path.parent / (path.name + ".tmp")
        tmp.write_text(json.dumps(reg))
        os.replace(tmp, path)
    except Exception:
        pass


def shard_width(width: int | None = None) -> int:
    """The parallel width to use: the caller's, else the environment's, else
    the default. Never below 1."""
    if width is None:
        raw = (os.environ.get(WIDTH_ENV) or "").strip()
        try:
            width = int(raw) if raw else DEFAULT_SHARD_WIDTH
        except ValueError:
            width = DEFAULT_SHARD_WIDTH
    return max(1, int(width))


def shard_cells(cells: list, width: int | None = None) -> list:
    """Deal the cells across runners exactly as retro.py does: a stride
    partition, empty shards dropped."""
    w = shard_width(width)
    return [cells[i::w] for i in range(w) if cells[i::w]]


def cell_seconds(cell: dict) -> float:
    """Predicted seconds for one prepared cell. Cells written before the
    cost model existed carry no particle count and are read at the
    reference 10,000."""
    n_obs = int(cell.get("n_obs") or 0)
    particles = float(cell.get("particles") or COST_REFERENCE_PARTICLES)
    return ((COST_INTERCEPT_S + COST_PER_WEEK_S * (n_obs + COST_FORECAST_WEEKS))
            * max(particles, 1.0) / COST_REFERENCE_PARTICLES)


def expected_seconds(shards: list) -> float:
    """Predicted wall clock for the whole run: the slowest shard, since the
    shards run concurrently and the run ends with the last of them."""
    return max((sum(cell_seconds(c) for c in s) for s in shards), default=0.0)


def budget_seconds(shards: list) -> float:
    """The time budget for a sharded run: TIMEOUT_SAFETY times the
    prediction, never below the floor."""
    return max(TIMEOUT_FLOOR_S, TIMEOUT_SAFETY * expected_seconds(shards))


def _stderr_tail(err_files: list, n: int = 400) -> str:
    """The tail of the first runner stderr that has anything to say."""
    for p in err_files:
        try:
            txt = Path(p).read_text(errors="replace").strip()
        except Exception:
            continue
        if txt:
            return txt[-n:]
    return ""


def _finished(status_files: list) -> int:
    """Cells reported finished so far, across every shard."""
    n = 0
    for p in status_files:
        try:
            d = json.loads(Path(p).read_text())
        except Exception:
            continue
        if isinstance(d, dict):
            n += len(d)
    return n


def _descendants(pid: int) -> list:
    """Every process below `pid`, deepest last. [] on any platform or
    failure where the tree cannot be read, which leaves the caller doing
    exactly what it did before."""
    if os.name != "posix":
        return []
    try:
        r = subprocess.run(["ps", "-Ao", "pid=,ppid="], capture_output=True,
                           text=True, timeout=10)
    except Exception:
        return []
    kids: dict = {}
    for line in r.stdout.splitlines():
        try:
            child, parent = (int(x) for x in line.split())
        except ValueError:
            continue                      # a header or a torn line: skip it
        kids.setdefault(parent, []).append(child)
    out, frontier = [], [pid]
    while frontier:                       # breadth-first, parents before kids
        nxt = []
        for q in frontier:
            for child in kids.get(q, ()):
                if child not in out and child != pid:
                    out.append(child)
                    nxt.append(child)
        frontier = nxt
    return out


def _signal_tree(p, sig) -> None:
    """Signal a runner AND the engine processes it spawned.

    Signalling the runner alone is not enough: PyBNF's filter runs a pool, so
    the runner is a parent, and terminating it leaves its workers alive and
    holding cores. Measured 2026-08-26 against the pre-sharding code as well,
    so this is an old defect -- but one the sharding multiplies by the width,
    because a cancel now abandons the pool of every shard rather than of one
    process. A cancel that leaves engine processes chewing CPU is worse than
    no cancel.

    Order matters twice. The tree is READ before anything is signalled,
    because once the runner dies its children are reparented to init and the
    link that identifies them as ours is gone. The runner is then signalled
    before its descendants, so a pool it was about to grow cannot outlive the
    sweep.

    The tree is still read from `ps` even though each runner now leads its
    own session (the console takeover sweep in flubnf/cli.py is what the
    session exists for): Windows has no killpg, and a pool member that
    moved itself to a new group would escape a group signal, so the cancel
    path keeps the explicit sweep. The session does mean the terminal's
    Ctrl-C no longer reaches the runners through the console's process
    group; what reaps them is this supervisor's finally block (_stop_all)
    while it lives, and the next launch's takeover sweep when it does not.
    """
    kids = _descendants(p.pid)
    try:
        p.kill() if sig == _SIGKILL else p.terminate()
    except Exception:
        pass
    for child in kids:
        try:
            os.kill(child, sig)
        except Exception:
            pass                          # already gone, or not ours to signal


def _stop_all(procs: list) -> None:
    """Stop every runner still alive, with its engine processes, and WAIT
    for each one. This is the one step no exception may skip."""
    for p in procs:
        try:
            if p.poll() is None:
                _signal_tree(p, _SIGTERM)
        except Exception:
            pass
    for p in procs:
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            try:
                _signal_tree(p, _SIGKILL)
                p.wait(5)
            except Exception:
                pass
        except Exception:
            pass


def _over_budget(status_files: list, n_cells: int, shards: list,
                 budget: float, sized: bool) -> str:
    """What a run that ran out of time should say: how far it got, out of
    how many, and where its budget came from.

    Which of the two terms in budget_seconds actually bound is named, not
    assumed. Since the floor is the old fixed hour it binds for most grids,
    and a message reading "60 min = 3 x the 12 min predicted" would be
    arithmetic the reader can see is false."""
    done = _finished(status_files)
    predicted = expected_seconds(shards)
    model = (f"the {predicted / 60:.0f} min the cost model "
             f"({COST_INTERCEPT_S} + {COST_PER_WEEK_S} * (n_obs + "
             f"{COST_FORECAST_WEEKS}) s per cell) predicts for the slowest "
             f"of {len(shards)} shard(s)")
    if not sized:
        how = f"{budget / 60:.0f} min, set by the caller"
    elif TIMEOUT_SAFETY * predicted < TIMEOUT_FLOOR_S:   # the floor bound
        how = (f"{budget / 60:.0f} min, the floor, which already exceeds "
               f"{TIMEOUT_SAFETY:g} x {model}")
    else:
        how = f"{budget / 60:.0f} min = {TIMEOUT_SAFETY:g} x {model}"
    # the counts and the budget lead, because a ledger row keeps only the
    # first 300 characters of an error
    return (f"PF fitting exceeded its time budget: {done} of {n_cells} cells "
            f"finished. Budget was {how}. On a slower machine widen the "
            f"sharding ({WIDTH_ENV}); otherwise suspect the engine venv.")


def execute(workroot: Path, timeout: float | None = None,
            width: int | None = None) -> dict:
    """Run every prepared cell in the engine venv, sharded across parallel
    runners, and return the merged {cell key: "ok" | "FAIL: ..."} status.

    Three properties of the single-runner version are kept, each of which
    needed something once the runners became plural:

      * Cancellation. <workroot>/STOP is both the supervisor's flag and the
        runners' own: every runner checks it between cells and dispatches
        nothing more, and the supervisor terminates all of them and waits
        for each before raising RunStopped, so none is left behind.
      * The status file. Each shard rewrites its own after every cell. This
        merges them into pf_status.json, and records any cell no shard ever
        reported as a failure naming that shard and its stderr, so a shard
        that died is visible in the result rather than averaged away. When
        no shard produced a status at all, the specific error is raised as
        before, quoting the runner stderr.
      * Reduced priority. Every runner is wrapped in low_priority_cmd and
        low_priority_popen_kwargs, on every platform.

    `timeout` defaults to a budget sized to the work (budget_seconds); an
    explicit value overrides it. `width` defaults to DEFAULT_SHARD_WIDTH,
    which is also the retrospective path's default.
    """
    workroot = Path(workroot)
    out_json = workroot / "pf_status.json"
    cells = json.loads((workroot / "cells.json").read_text())
    # prepare-stage failures (a state the vintage could not resolve) are
    # part of this run's status: folding them here is what carries them
    # into pf_failures downstream
    prep_failures = read_prepare_failures(workroot)
    if not cells:
        # nothing to fit is not a failure; prepare's own refusals, if any,
        # still surface in the record
        out_json.write_text(json.dumps(prep_failures))
        return dict(prep_failures)
    shards = shard_cells(cells, width)
    sized = not timeout
    budget = budget_seconds(shards) if sized else float(timeout)
    stop = workroot / "STOP"            # the user's flag AND the runners' halt

    # reduced scheduling priority: the fits yield to the interactive server
    # so the application stays usable during a multi-hour run. `nice` execs
    # the interpreter, so each Popen still refers to the real runner process
    # and the stop handling below is unchanged. See app/core/proc.py.
    from app.core.proc import low_priority_cmd, low_priority_popen_kwargs
    procs, status_files, err_files, handles = [], [], [], []
    try:
        for i, shard in enumerate(shards):
            sj = workroot / f"pf_cells_{i}.json"
            sj.write_text(json.dumps(shard))
            sf = workroot / f"pf_status_{i}.json"
            ef = workroot / f"pf_runner_{i}.err"
            runner = workroot / f"pf_runner_{i}.py"
            runner.write_text(_RUNNER.format(pybnf_path=str(PYBNF_PF),
                                             cells_json=str(sj),
                                             out_json=str(sf),
                                             halt_path=str(stop)))
            # stderr to a FILE, not a pipe: with several runners and nobody
            # draining them, a chatty one would fill its pipe buffer and
            # block forever, which is the very hang the budget exists for.
            fh = open(ef, "w")
            handles.append(fh)
            # Each runner leads its own session (its own process group on
            # Windows): the supervisor is a daemon thread of the server, so
            # a takeover or window close kills it without running this
            # function's finally, and the group id is then the only address
            # the relaunch can still signal (the takeover sweep in
            # flubnf/cli.py). This supervisor's own cancel path does not
            # depend on the group: _signal_tree sweeps the tree from `ps`.
            procs.append(subprocess.Popen(
                low_priority_cmd([str(PY310), str(runner)]),
                stdout=subprocess.DEVNULL, stderr=fh,
                **runner_popen_kwargs(low_priority_popen_kwargs())))
            status_files.append(sf)
            err_files.append(ef)
        record_runner_pids(procs)
        t0 = time.time()
        while any(p.poll() is None for p in procs):
            if stop.exists():
                raise RunStopped("stopped by user")
            if time.time() - t0 > budget:
                raise RuntimeError(_over_budget(status_files, len(cells),
                                                shards, budget, sized))
            _sleep(POLL_S)
    finally:
        _stop_all(procs)                # no orphans, on any exit path
        unrecord_runner_pids(procs)     # stopped: nothing left to sweep
        for fh in handles:
            try:
                fh.close()
            except Exception:
                pass
    if stop.exists():
        # the flag can also land before the first poll, or between the last
        # runner exiting and this line. Either way the run was stopped, and
        # it must not return a status that reads like a finished grid.
        raise RunStopped("stopped by user")
    if not any(sf.is_file() for sf in status_files):
        raise RuntimeError(f"PF runner produced no status: "
                           f"{_stderr_tail(err_files)}")
    merged = dict(prep_failures)
    for i, shard in enumerate(shards):
        try:
            part = json.loads(status_files[i].read_text())
        except Exception:
            part = {}
        if not isinstance(part, dict):
            part = {}
        merged.update(part)
        for c in shard:
            if c["key"] not in part:
                merged[c["key"]] = (
                    f"FAIL: shard {i} reported no result for this cell "
                    f"({_stderr_tail([err_files[i]], 120) or 'no stderr'})"
                )[:200]
    out_json.write_text(json.dumps(merged))
    return merged


def _cell_statuses(workroot: Path) -> dict:
    """Per-cell fit statuses, whichever path recorded them: the forecast
    supervisor's merged pf_status.json, overlaid on the retrospective
    runner's per-cell markers in cells_done/ (retro.py's CELL_DONE_DIRNAME,
    mirrored here because retro imports this module, never the reverse).
    {} for an older workroot with neither, which leaves collect() reading
    every cell exactly as it always did."""
    workroot = Path(workroot)
    out: dict = {}
    done = workroot / "cells_done"
    if done.is_dir():
        for p in done.glob("*.json"):
            try:
                out[p.stem] = str(json.loads(p.read_text()).get("status", ""))
            except Exception:
                out[p.stem] = "unreadable marker"
    try:
        merged = json.loads((workroot / "pf_status.json").read_text())
        if isinstance(merged, dict):
            out.update({k: str(v) for k, v in merged.items()})
    except Exception:
        pass
    return out


def _record_collect_failure(workroot: Path, key: str, msg: str) -> None:
    """Fold one assembly-time failure into the merged status file, so a
    torn cell is a recorded failure with a reason rather than a silent
    absence. Never fatal: the healthy cells' samples matter more than the
    record of the torn one."""
    try:
        out = Path(workroot) / "pf_status.json"
        try:
            merged = json.loads(out.read_text())
        except Exception:
            merged = {}
        if not isinstance(merged, dict):
            merged = {}
        merged[key] = msg[:200]
        tmp = out.parent / (out.name + ".tmp")
        tmp.write_text(json.dumps(merged))
        os.replace(tmp, out)
    except Exception:
        pass


def collect(workroot: Path) -> dict:
    """Forecast samples per location: replicate-pooled, anchored at origin.

    Only cells whose recorded status is ok (or unrecorded, for an older
    workroot) are read. A failed fit can leave a torn trajectory behind --
    an empty file, or a single flushed row -- and parsing it used to kill
    the WHOLE assembly with an IndexError, so one dead cell cost the other
    158 their samples. A torn file under an ok status is downgraded to a
    recorded failure and skipped for the same reason."""
    import numpy as np
    cells = json.loads((workroot / "cells.json").read_text())
    status = _cell_statuses(workroot)
    by_loc: dict = {}
    for c in cells:
        st = status.get(c["key"])
        if st is not None and st != "ok":
            continue              # a recorded failure has nothing to pool
        runs = Path(c["dir"]) / "out" / "Results" / "A_MCMC" / "Runs"
        tr_files = sorted(runs.glob("*traj_noise*"))
        if not tr_files:
            continue
        try:
            tr = np.genfromtxt(tr_files[0])
        except Exception as e:
            # a row torn mid-write leaves a ragged file genfromtxt refuses
            _record_collect_failure(
                workroot, c["key"],
                f"FAIL: trajectory {tr_files[0].name} unreadable ({e}); "
                "the cell is excluded from assembly")
            continue
        if tr.ndim < 2:
            # an empty or single-row file: a fit torn mid-write. The real
            # trajectory is a matrix (particles by weeks), so anything
            # 1-D is unreadable, and np.genfromtxt gives shape (0,) for
            # an empty file and a 1-D vector for one row.
            _record_collect_failure(
                workroot, c["key"],
                f"FAIL: trajectory {tr_files[0].name} is torn "
                f"({'empty' if tr.size == 0 else 'a single row'}); "
                "the cell is excluded from assembly")
            continue
        n = c["n_obs"]
        origin = tr[:, n - 1]
        med = float(np.median(origin[np.isfinite(origin)]))
        scale = c["last_observed"] / med if med > 0 else 1.0
        # Horizons are AS-OF-relative, always. When weeks_to_drop trimmed
        # k rows, the fit origin sits k weeks before the as-of date and the
        # conf extended pf_forecast_weeks by k, so the as-of-relative
        # horizon h lives at column (n-1) + k + h. Before this shift every
        # consumer (quantile_rows, retro scoring, the fan) read the
        # origin-relative columns and labelled them one week late per
        # dropped week (audit finding). "0" is the as-of week itself: the
        # model's nowcast of the trimmed weeks when k > 0, the anchored
        # origin when k = 0, so the fan connects to the same calendar spot
        # either way. The anchor pair is unchanged: last_observed is the
        # trimmed series' final value, med the fit origin's median.
        k = int(c.get("weeks_dropped", 0) or 0)
        need = n + k + 4
        if tr.shape[1] < need:
            # reachable only when a cell RECORDS a trim but its trajectory
            # was not extended -- an engine build that ignored
            # pf_forecast_weeks, or a workroot mixing fix generations. (A
            # genuinely pre-fix workroot has no weeks_dropped key at all
            # and reads k=0 here, exactly as it always did.)
            raise RuntimeError(
                f"{c['key']}: trajectory has {tr.shape[1]} columns, "
                f"{need} needed for weeks_dropped={k}; the engine did not "
                "extend the forecast for the recorded trim -- rerun the "
                "forecast on a current engine")
        d = by_loc.setdefault(c["location"], {str(h): [] for h in range(5)})
        d["0"].extend((tr[:, n - 1 + k] * scale).tolist())
        for h in (1, 2, 3, 4):
            d[str(h)].extend((tr[:, n - 1 + k + h] * scale).tolist())
    return by_loc
