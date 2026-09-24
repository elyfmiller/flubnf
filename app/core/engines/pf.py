"""SHIPPED: the PF-SIHRS engine; writes pf.conf and runs PyBNF `fit_type=pf`.

Two-venv dispatch (rule 8): materialization and scoring run here, in the
analysis venv; the filter runs in the pybnf/bngsim venv (Python 3.11/3.12,
the engine's numpy ceiling) via runner script FILES in the workroot, never
stdin (macOS spawn kills stdin-launched pools, rule 4). The prepared cells
are sharded across several runners, as the retrospective path does.

Sections: constants | runner | preflight | research knobs | prepare |
execution | collect.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

# --- constants: templates, defaults, fitted-variable boxes ------------------

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from app.core import horizons as hz
from flubnf.settings import PY_ENGINE as PY310, PYBNF as PYBNF_PF
TEMPLATE = REPO / "flubnf/templates/SIHRS_pop_min.bngl"   # H stays: verdict 2026-08-17
DEFAULTS_BLOCK = ("begin parameters\nReff__FREE 1.20\neps1__FREE 0.15\n"
                  "phi1__FREE 22.0\nmult__FREE 0.05\nr__FREE 8.0\n")
# RESEARCH spec.extra["variant"] == "2strain": A/B circuits + the NREVSS
# typed-positives binomial channel.
TEMPLATE_2S = REPO / "flubnf/templates/SIHRS_pop_2strain_min.bngl"
# RESEARCH spec.extra["variant"] == "natg": `min` plus exp(iota*(g_nat^-s - g_s))
# on beta(t), iota frozen a priori; no new dimension, so DEFAULTS_BLOCK and
# VARS_1S are reused verbatim. See flubnf/natgrowth.py.
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

# --- runner -----------------------------------------------------------------

#: One shard's runner (cf. retro.py::_RETRO_RUNNER), a FILE not stdin (rule 4).
#: It checks the halt flag BETWEEN cells and rewrites its status after EVERY
#: cell, so a shard that dies still reports what it finished.
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


# --- preflight: conf-safe paths, Perl, engine checks -------------------------
# PyBNF's conf grammar stops bng_command/output_dir at whitespace, so a path
# with a space (e.g. a Windows username) cannot be written at all: use the
# Windows 8.3 short form, or refuse legibly at prepare().

def _short_path_win(path: str, _api=None):
    """The 8.3 short form of an EXISTING path via GetShortPathNameW (first
    call sizes the buffer), or None on any failure. `_api` is injectable so
    this is testable off Windows."""
    try:
        import ctypes
        if _api is None:
            _api = ctypes.windll.kernel32.GetShortPathNameW   # type: ignore[attr-defined]
        n = _api(path, None, 0)
        if not n:
            return None
        buf = ctypes.create_unicode_buffer(int(n))
        # ret >= n means the path changed between calls: buffer undefined
        ret = _api(path, buf, int(n))
        if not (0 < ret < int(n)):
            return None
        return buf.value or None
    except Exception:
        return None


def conf_safe_path(p, _platform: str | None = None) -> str:
    """`p` as pf.conf may carry it: unchanged when space-free, else the
    Windows 8.3 short form, else a RuntimeError (instead of a ParseException
    inside the engine venv mid-run). `_platform` is injectable for tests."""
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


def perl_missing_message() -> str:
    """Operator message for a machine with no Perl on PATH: BNG2.pl runs once
    per cell at prepare, and without Perl Windows only says '[WinError 2]'."""
    if sys.platform == 'win32':
        how = ("install Strawberry Perl (https://strawberryperl.com, or let "
               "FluBNF.bat offer it during engine install) and start the "
               "console again so the new PATH is seen")
    else:
        how = ("perl ships with macOS and every Linux distribution; add its "
               "directory to PATH or reinstall it")
    return ("Perl was not found on PATH. BioNetGen's BNG2.pl is a Perl "
            "program that generates each cell's reaction network at run "
            f"preparation, so no fit can start without it: {how}.")


def perl_available() -> bool:
    return shutil.which("perl") is not None


#: The file that provides fit_type = pf (stock PyBNF from PyPI lacks it).
PF_MODULE = "pybnf/pf.py"

#: The remedy, shared by the console message and the doctor's hint.
ENGINE_FIX = ("Put the engine archive in Downloads and run "
              "./setup_engine.sh, or point FLUBNF_PYBNF at the unpacked "
              "engine.")


def engine_missing_message() -> str:
    """Operator message for a fork path without pybnf/pf.py. The runner would
    silently import the engine venv's stock PyBNF (no filter) and every cell
    would fail late with an opaque config error. The remedy comes before the
    reason because the ledger's error field keeps only a prefix."""
    p = Path(PYBNF_PF)
    if not p.is_dir():
        found = ("there is no such directory" if not p.exists()
                 else "that path is a file, not a directory")
    elif not os.access(p, os.R_OK | os.X_OK):
        found = "the directory cannot be read"
    else:
        found = f"the directory is there but holds no {PF_MODULE}"
    return (f"The PyBNF fork at {p} does not provide fit_type = pf: "
            f"{found}. {ENGINE_FIX} Without {PF_MODULE} the fit runner "
            "imports the stock PyBNF in the engine venv instead, which has "
            "no particle filter, so every fit fails.")


def engine_available() -> bool:
    """Whether the fork path holds PF_MODULE (the directory merely existing
    proves nothing: half-unpacked archive, wrong FLUBNF_PYBNF, ...)."""
    return (Path(PYBNF_PF) / PF_MODULE).is_file()


#: Keys this console writes that older engines' parsers refuse (an unknown
#: key fails every cell late). The engine's parser source is the contract.
CONF_KEYS_REQUIRED = ("pf_particles", "pf_forecast_intervals", "pf_start_time",
                      "pf_bounds", "pf_seed")
PARSE_MODULE = "pybnf/parse.py"


def engine_accepts(key: str) -> bool:
    """Whether the fork's parser lists a configuration key."""
    try:
        text = (Path(PYBNF_PF) / PARSE_MODULE).read_text(encoding="utf-8")
    except OSError:
        return False
    return ("'%s'" % key) in text


def engine_missing_keys() -> tuple:
    """The keys this console writes that the fork does not accept."""
    return tuple(k for k in CONF_KEYS_REQUIRED if not engine_accepts(k))


def engine_current() -> bool:
    """Whether the fork accepts every key this console writes."""
    return not engine_missing_keys()


#: The engine's per-algorithm key sets (Configuration.check_unused_params):
#: what the filter READS, where the parser's lists say what it accepts.
CONFIG_MODULE = "pybnf/config.py"

#: `pf_sampling_interval = 1` lets an engine fit a ONE-ROW .exp (a season's
#: first week). Engines before a827e2f8 refuse the key, so it is written only
#: when the installed source accepts it; the cell records whether it was.
SAMPLING_INTERVAL_KEY = "pf_sampling_interval"


def engine_accepts_pf_key(key: str) -> bool:
    """Whether the fork both parses `key` (pybnf/parse.py) and lists it among
    the pf keys (pybnf/config.py); engine_accepts asks the grammar alone."""
    if not engine_accepts(key):
        return False
    try:
        text = (Path(PYBNF_PF) / CONFIG_MODULE).read_text(encoding="utf-8")
    except OSError:
        return False
    return ("'%s'" % key) in text


def sampling_interval_line() -> str:
    """The conf line `pf_sampling_interval = 1`, or nothing, by the
    installed engine's own source."""
    return (f"{SAMPLING_INTERVAL_KEY} = 1\n"
            if engine_accepts_pf_key(SAMPLING_INTERVAL_KEY) else "")


def engine_stale_message() -> str:
    """Operator message for an engine older than the console, named once at
    prepare instead of once per cell."""
    p = Path(PYBNF_PF)
    missing = ", ".join(engine_missing_keys())
    stamp = ""
    try:
        v = (p / "VERSION").read_text().strip().splitlines()[0]
        stamp = f" Its version stamp is '{v}'."
    except (OSError, IndexError):
        pass
    return (f"The PyBNF fork at {p} is older than this console: its parser "
            f"does not accept {missing}, which every fit configuration the "
            f"console writes carries, so every fit would fail.{stamp} Save "
            "the current engine archive (pybnf-pf-<sha>.tar.gz) in "
            "Downloads and open the app again, or run ./setup_engine.sh: "
            "a newer archive replaces the older copy.")


#: Prepare-stage failures keyed by location tag (no _r suffix, so never a
#: cell key). execute() and retro.run_week fold them in, so a state the
#: vintage cannot resolve costs that state, not the run.
PREPARE_FAILURES_NAME = "pf_prepare_failures.json"


def read_prepare_failures(workroot: Path) -> dict:
    """The prepare-stage failures for a workroot; {} if absent/unreadable."""
    try:
        d = json.loads((Path(workroot) / PREPARE_FAILURES_NAME).read_text())
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


# --- research knobs (spec.extra; none set on the shipped path) ---------------
# variant (2strain|natg), iota, fit_i0, anchor_asof, reporting, neff_cap,
# pf_keys, prior_ranges, initialization, seed_anchor, seed_salt,
# continue_states, save_states. All are read by prepare() or the helpers below.

#: A cell's saved/continued particle cloud; outside out/, which runners clear.
CLOUD_NAME = "cloud.npz"
#: collect() records here a cell asked to save a cloud that had none.
STATE_MISSING_NAME = "pf_state_missing.json"


def continuation_for(spec, cell_dir: Path, key: str) -> dict | None:
    """The cell's cloud paths under the swarm-carry keys; None when neither
    is set (an ordinary pf.conf is unchanged).

      continue_states  dir of <key>.npz clouds. Present: pf_continue = 1;
                       absent: fresh start, recorded as continued_from None
                       in cells.json (never a silent fallback).
      save_states      dir collect() copies the ending cloud into.

    The engine overwrites its one pf_state_file, so the source cloud is
    copied into the cell first and the ledger's copy is never touched.
    """
    ex = spec.extra or {}
    if not ex.get("continue_states") and not ex.get("save_states"):
        return None
    state = Path(cell_dir) / CLOUD_NAME
    src = None
    if ex.get("continue_states"):
        cand = Path(ex["continue_states"]) / f"{key}.npz"
        if cand.is_file():
            shutil.copy2(cand, state)
            src = str(cand)
    dest = (str(Path(ex["save_states"]) / f"{key}.npz")
            if ex.get("save_states") else None)
    return {"state_file": str(state), "continued_from": src,
            "save_state_to": dest}


def seed_date_for(spec) -> str:
    """The date the cell seed is keyed on. forecast_date (the sealed default)
    makes every as-of week its own draw. season_start (swarm-carry research)
    shares draws across a season's weeks under the engine's per-week streams
    (PyBNF-pf f09eeb9b), so a continued run is bit-identical to the refit."""
    anchor = str((spec.extra or {}).get("seed_anchor", "forecast_date"))
    # seed_salt: extra draws for a seed-spread measurement, folded into the
    # date key (recorded in cells.json via seed_date).
    salt = str((spec.extra or {}).get("seed_salt", "") or "")
    if anchor == "forecast_date":
        return spec.forecast_date + (f"#{salt}" if salt else "")
    if anchor == "season_start":
        return spec.season_start + (f"#{salt}" if salt else "")
    raise ValueError("seed_anchor must be forecast_date or season_start, "
                     f"not {anchor!r}")


#: Engine keys spec.extra["pf_keys"] may set, with the engine's own ranges;
#: anything else is refused so a typo cannot become an ignored conf line.
PF_KEYS_ALLOWED = {"pf_shrink": lambda v: float(v) in (0.0, 1.0),
                   "pf_forecast_jitter": lambda v: 0.0 <= float(v) < 1.0,
                   "pf_resample_threshold": lambda v: 0.0 < float(v) <= 1.0}


def pf_key_lines(spec) -> str:
    """Validated conf lines from spec.extra["pf_keys"]; empty normally."""
    keys = (spec.extra or {}).get("pf_keys") or {}
    out = []
    for k, v in keys.items():
        if k not in PF_KEYS_ALLOWED:
            raise ValueError(f"pf_keys: {k!r} is not a key the console may set "
                             f"(allowed: {', '.join(sorted(PF_KEYS_ALLOWED))})")
        if not PF_KEYS_ALLOWED[k](v):
            raise ValueError(f"pf_keys: {k} = {v!r} is out of the engine's range")
        out.append(f"{k} = {float(v):g}")
    return ("\n".join(out) + "\n") if out else ""


def priors_for(spec, two_strain: bool = False) -> str:
    """The prior block, with any ranges spec.extra["prior_ranges"] widens or
    narrows: {"r__FREE": [0.1, 200]} rewrites that parameter's line and
    keeps its distribution type. A name not in the block is refused."""
    block = VARS_2S if two_strain else VARS_1S
    ranges = (spec.extra or {}).get("prior_ranges") or {}
    if not ranges:
        return block
    lines = block.splitlines()
    for name, (lo, hi) in ranges.items():
        hit = [i for i, l in enumerate(lines) if l.split("=")[-1].split()[0] == name]
        if len(hit) != 1:
            raise ValueError(f"prior_ranges: {name!r} is not a fitted parameter "
                             "of this template")
        kind = lines[hit[0]].split("=")[0].strip()
        if not (0 <= float(lo) < float(hi)) or (kind == "loguniform_var" and float(lo) <= 0):
            raise ValueError(f"prior_ranges: {name} [{lo}, {hi}] is not a valid "
                             f"{kind} range")
        lines[hit[0]] = f"{kind} = {name} {float(lo):g} {float(hi):g}"
    return "\n".join(lines) + "\n"


def initialization_for(spec) -> str:
    """The engine's initialization key: rand (every recorded number) unless
    spec.extra names lh (PyBNF's own default, Latin hypercube)."""
    init = str((spec.extra or {}).get("initialization", "rand") or "rand")
    if init not in ("rand", "lh"):
        raise ValueError(f"initialization must be rand or lh, not {init!r}")
    return init


# --- prepare ------------------------------------------------------------------

#: spec.extra keys refused on a custom dataset: each reads hub-only data
#: (national growth, NREVSS typing, FluSight completeness, a hub vintage)
DATASET_REFUSED = ("variant", "reporting", "anchor_asof")


def _hub_tag(loc: str) -> str:
    """A hub location's cell-directory and BNGL-suffix stem (unchanged)."""
    return loc.replace(' ', '_')


def dataset_tag(loc: str) -> str:
    """A dataset group's stem: letters, digits and '_' only (a national
    group may be spelled 'US (national)'). Group names are unique after
    casefold and space-to-underscore (datasets._norm_name), so stems are."""
    return re.sub(r"[^A-Za-z0-9_]", "_", loc)


def prepare(spec, workroot: Path) -> list:
    """Materialize model+net+exp+conf for every (location, replicate) cell.

    Failures are contained PER LOCATION (e.g. resolve_state refusing an
    all-NaN tail during a reporting pause) and recorded in
    pf_prepare_failures.json in execute()'s FAIL-string shape. A run where
    every location fails still raises; a single-location run re-raises its
    one error verbatim."""
    from flubnf.sihrs_fit import materialize_model, resolve_state, write_exp
    from flubnf.settings import BNG
    from app.core.data import LOCATIONS, vintage_path
    from app.core.runs import derive_seed

    # Run-level preflight, once, before any location. The workroot is
    # resolved (the engine subprocess has another cwd) and created first
    # because the Windows 8.3 lookup needs an existing path.
    workroot = Path(workroot).resolve()
    workroot.mkdir(parents=True, exist_ok=True)
    conf_safe_path(workroot)
    bng_conf = conf_safe_path(BNG)
    if not perl_available():
        raise RuntimeError(perl_missing_message())
    # Here, not only in the console, so retro, the CLI and research runs
    # are covered too.
    if not engine_available():
        raise RuntimeError(engine_missing_message())
    if not engine_current():
        raise RuntimeError(engine_stale_message())
    # read once: the line goes into every cell's conf or into none
    si_line = sampling_interval_line()

    # the data source: the hub's vintage and locations table, or a custom
    # dataset's (extra["dataset"]); the hub branch is today's expression
    from app.core import datasets as _ds
    ds = _ds.from_spec(spec)
    if ds is None:
        vintage = vintage_path(spec.forecast_date)
        loc_csv = LOCATIONS
        tag_of = _hub_tag
    else:
        bad = [k for k in DATASET_REFUSED
               if (spec.extra or {}).get(k)]
        if bad:
            raise ValueError(
                f"{', '.join(bad)}: these read FluSight, NREVSS or hub "
                f"completeness data and cannot run on the custom dataset "
                f"{ds.name!r}; the plain SIHRS filter can")
        vintage = ds.truth_path(spec.forecast_date)
        loc_csv = ds.locations_csv
        tag_of = dataset_tag
    variant = (spec.extra or {}).get("variant")
    # fit_i0 = [lo, hi]: fit i0 (loguniform) instead of deriving it.
    fit_i0 = (spec.extra or {}).get("fit_i0")
    if fit_i0 is not None:
        fit_i0 = (float(fit_i0[0]), float(fit_i0[1]))
        if not (0 < fit_i0[0] < fit_i0[1] < 1):
            raise ValueError(f"fit_i0 must be [lo, hi] with 0 < lo < hi < 1, "
                             f"not {fit_i0}")
    two_strain = variant == "2strain"
    natg = variant == "natg"
    if natg:
        from flubnf.natgrowth import IOTA_FROZEN, growth_gap_series, natg_tokens
        # The frozen value travels in spec.extra (the ledger's record); never
        # derived or fitted here.
        iota = float((spec.extra or {}).get("iota", IOTA_FROZEN))
    if two_strain:
        from datetime import date as _d, timedelta as _td

        import pandas as _pd

        from flubnf import nrevss
        # NREVSS week D publishes the following Friday, after the FluSight
        # deadline, so honest as-of uses typed data through D-7.
        nrevss_asof = (_d.fromisoformat(spec.forecast_date)
                       - _td(days=7)).isoformat()

    def _one_location(loc: str) -> list:
        """Every prepared cell for one location; the caller contains raises."""
        s = resolve_state(loc, truth_csv=vintage, locations_csv=loc_csv,
                          season_start=spec.season_start,
                          as_of=spec.forecast_date)
        # i0/rhomult derive from the season-to-date count, so they drift
        # weekly even with no revision; spec.extra["anchor_asof"] pins them
        # to one as-of week's vintage (needed when a cloud is carried).
        anchor = (spec.extra or {}).get("anchor_asof")
        if anchor:
            sa = resolve_state(loc, truth_csv=vintage_path(anchor),
                               locations_csv=loc_csv,
                               season_start=spec.season_start, as_of=anchor)
            s.i0, s.rhomult = sa.i0, sa.rhomult   # a fresh object per call
        # Optional nowcast rule (RunSpec.drop_same_day, off by default): trim
        # the same-day row on top of weeks_to_drop; weeks_dropped and
        # pf_forecast_intervals keep horizon labels as-of-relative.
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
            # Labels shift by k_total: valid only on a calendar-consecutive
            # tail (a NaN reporting gap breaks it), so refuse otherwise.
            if _off - int(s.times[-1]) != k_total:
                raise ValueError(
                    f"{loc}: after trimming {k_total} week(s) the fit "
                    f"origin sits {_off - int(s.times[-1])} weeks before "
                    f"{spec.forecast_date}, not {k_total}: the series tail "
                    "is not calendar-consecutive (a reporting gap), so "
                    "horizon labels cannot be kept as-of-relative. "
                    "Refusing rather than mislabelling.")
            # Re-derive rhomult/i0 from the trimmed series (resolve_state
            # used the untrimmed one) unless anchor_asof pins them.
            if not (spec.extra or {}).get("anchor_asof"):
                from flubnf.sihrs_priors import (initial_infected_fraction
                                                 as _iif, pin_rho_mult as _prm)
                import numpy as _np0
                _obs = _np0.asarray(s.observed, dtype=float)
                s.rhomult = _prm(float(_obs.sum()) / s.population, s.attack_rate)
                s.i0 = _iif(max(float(_obs[0]), 1.0), s.population,
                            s.rhomult, s.gamma)
        # RESEARCH reporting model, spec.extra["reporting"]["mode"]: edge rows
        # are corrected by app.core.completeness' per-lag factors. anchor:
        # only rhomult/i0 see the corrected rows; lik: also
        # pf_mean_scale_column in the likelihood; both: the analogue divides
        # its anchor too. The forecast is never scaled. Single-strain only.
        rep = (spec.extra or {}).get("reporting")
        rep_rec = None
        if rep:
            import numpy as _np
            from app.core import completeness as _comp
            from flubnf.sihrs_priors import (initial_infected_fraction,
                                             pin_rho_mult)
            mode = str(rep.get("mode") or "")
            if mode not in ("anchor", "lik", "both"):
                raise ValueError("reporting mode must be anchor, lik or both, "
                                 f"not {mode!r}")
            if two_strain or natg:
                raise ValueError("the reporting model is defined for the "
                                 "single-strain route only")
            if anchor:
                raise ValueError("reporting and anchor_asof cannot be "
                                 "combined: both set the anchor")
            fac = _comp.factors_cached(spec.forecast_date, spec.season_start)
            from datetime import date as _date3
            _asof_off = (_date3.fromisoformat(spec.forecast_date)
                         - _date3.fromisoformat(spec.season_start)).days // 7
            scales = _comp.row_scales(s.times, _asof_off, fac)
            corrected = (_np.asarray(s.observed, dtype=float)
                         / _np.asarray(scales, dtype=float))
            s.rhomult = pin_rho_mult(float(corrected.sum()) / s.population,
                                     s.attack_rate)
            s.i0 = initial_infected_fraction(max(float(corrected[0]), 1.0),
                                             s.population, s.rhomult, s.gamma)
            rep_rec = {"mode": mode,
                       "factors": {str(k): float(v) for k, v in fac["factors"].items()},
                       "pairs": {str(k): int(v) for k, v in fac["pairs"].items()},
                       "row_scales": [float(x) for x in scales]}
        gg = None
        if natg:
            # Same vintage as the likelihood; truncated to the filter's last
            # week so "hold the last gap" starts where the forecast does.
            gg = growth_gap_series(
                loc, truth_csv=vintage, locations_csv=loc_csv,
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
            tag = f"{tag_of(loc)}_r{rep}"
            d = workroot / tag
            d.mkdir(parents=True)
            sfx = f"{tag_of(loc)}_flu"
            if two_strain:
                tmpl, tok = TEMPLATE_2S, {"{{A0SHARE}}": f"{a0:.4f}"}
            elif natg:
                tmpl, tok = TEMPLATE_NATG, natg_tokens(gg, iota)
            else:
                tmpl, tok = TEMPLATE, None
            m = materialize_model(s, tmpl, d / "m.bngl", sfx, extra_tokens=tok)
            # newline="\n" on the write below: it is the last write of the
            # model, and Windows text mode would hand BNG2.pl a CRLF file.
            # (Universal-newline read_text needs no such care.)
            txt = m.read_text().replace("begin parameters\n",
                                        DEFAULTS_2S if two_strain
                                        else DEFAULTS_BLOCK, 1)
            if fit_i0:
                # i0 becomes a sixth fitted parameter (per-particle initial
                # state), defaulting to this week's data-derived value. The
                # derived anchor is 20-700x too large early in a season.
                txt = txt.replace("begin parameters\n",
                                  f"begin parameters\ni0__FREE {s.i0:.8e}\n", 1)
                txt, n_sub = re.subn(r"(?m)^i0\s+\S+", "i0      i0__FREE", txt)
                if n_sub != 1:
                    raise RuntimeError(f"{loc}: expected one i0 line in the "
                                       f"model, found {n_sub}")
            m.write_text(txt, newline="\n")
            if two_strain:
                lines = ["# time H_weekly A_share_bin A_share_n"]
                for t_off, v in zip(s.times, s.observed):
                    a_k, n_k = typed_by_t.get(int(t_off), (-1, -1))
                    lines.append(f"{int(t_off)} {v:.6f} {a_k} {n_k}")
                # newline pinned: PyBNF splits the .exp line-wise.
                (d / f"{sfx}.exp").write_text("\n".join(lines) + "\n",
                                              newline="\n")
            elif rep_rec and rep_rec["mode"] in ("lik", "both"):
                lines = [f"# time H_weekly {_comp.COLUMN}"]
                for t_off, v, c in zip(s.times, s.observed, rep_rec["row_scales"]):
                    lines.append(f"{int(t_off)} {v:.6f} {c:.6f}")
                (d / f"{sfx}.exp").write_text("\n".join(lines) + "\n",
                                              newline="\n")
            else:
                write_exp(s, d / f"{sfx}.exp")
            try:
                r = subprocess.run(["perl", BNG, "m.bngl"], capture_output=True,
                                   text=True, cwd=str(d), timeout=300)
            except FileNotFoundError:
                # perl vanished since preflight, or which() disagreed
                raise RuntimeError(perl_missing_message())
            if not (d / "m.net").is_file():
                raise RuntimeError(f"netgen failed for {loc}: {r.stdout[-300:]}")
            seed = derive_seed(loc, seed_date_for(spec), rep)
            cont = continuation_for(spec, d, tag)
            # conf: newline="\n" (line-based reader); every path via
            # conf_safe_path.
            d_conf = conf_safe_path(d)
            # Pinned to the records' conventions, not engine defaults:
            # pf_bounds = reflect (engine default: logit-scale moves, a
            # pre-registered comparison not yet run) and pf_start_time = -1
            # (initial state one week before the .exp's t = 0 row).
            (d / "pf.conf").write_text(f"""bng_command = {bng_conf}
model = {d_conf}/m.bngl : {d_conf}/{sfx}.exp
output_dir = {d_conf}/out
fit_type = pf
objfunc = neg_bin_dynamic
pf_particles = {spec.particles}
pf_jitter = {spec.jitter}
pf_bounds = reflect
pf_start_time = -1
pf_cumulative_observable = Hobs
pf_forecast_intervals = {4 + k_total}
population_size = 1
max_iterations = 1
pf_seed = {seed}
initialization = {initialization_for(spec)}
{si_line}{pf_key_lines(spec)}{priors_for(spec, two_strain)}"""
+ (f"loguniform_var = i0__FREE {fit_i0[0]:g} {fit_i0[1]:g}\n" if fit_i0 else "")
+ (f"pf_binom_neff_cap = {(spec.extra or {}).get('neff_cap', 300)}\n"
   if two_strain else "")
+ (f"pf_mean_scale_column = {_comp.COLUMN}\n"
   if rep_rec and rep_rec["mode"] in ("lik", "both") else "")
# initialization is always written: PyBNF's default is lh (honoured since
# PyBNF-pf f09eeb9b), but every recorded number used rand.
+ (f"pf_state_file = {conf_safe_path(cont['state_file'])}\n"
   f"pf_continue = {1 if cont['continued_from'] else 0}\n"
   if cont else ""), newline="\n")
            loc_cells.append({
                "key": tag, "dir": str(d), "location": loc,
                "replicate": rep, "seed": seed,
                # collect() shifts forecast columns by this (incl. the
                # same-day trim) so horizon labels stay as-of-relative.
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
                "seed_date": seed_date_for(spec),
                "initialization": initialization_for(spec),
                # 1 if the conf carries the line, else None
                SAMPLING_INTERVAL_KEY: (1 if si_line else None),
                "pf_keys": dict((spec.extra or {}).get("pf_keys") or {}),
                "prior_ranges": {k: list(v) for k, v in
                                 ((spec.extra or {}).get("prior_ranges") or {}).items()},
                "anchor_asof": anchor or spec.forecast_date,
                "i0": float(s.i0),
                "fit_i0": list(fit_i0) if fit_i0 else None,
                "reporting": rep_rec,
                **(cont or {"state_file": None, "continued_from": None,
                            "save_state_to": None}),
                # read back by the cost model to size the time budget
                "particles": int(spec.particles),
                "last_observed": float(s.observed[-1])})
        return loc_cells

    cells, failures, errors = [], {}, []
    for loc in spec.locations:
        try:
            cells.extend(_one_location(loc))
        except Exception as e:
            failures[tag_of(loc)] = f"FAIL: prepare: {e}"[:200]
            errors.append(e)
    (workroot / PREPARE_FAILURES_NAME).write_text(json.dumps(failures))
    (workroot / "cells.json").write_text(json.dumps(cells))
    if failures and not cells:
        if len(errors) == 1:
            # a single location's error is clearer verbatim
            raise errors[0]
        raise RuntimeError(
            f"prepare failed for all {len(failures)} location(s) "
            f"(first: {next(iter(failures.values()))})")
    return cells


# --- execution: sharded runners, time budget, stop/reap ----------------------
# Cells (location x replicate, each with its own model, conf and seed) are
# independent, so they are dealt across runner subprocesses as
# retro._run_round does: wall clock changes, no number does.

class RunStopped(Exception):
    pass


#: Cores left for the console and OS (fits are also nice-d, app/core/proc.py).
SHARD_CORES_RESERVED = 2

#: Upper bound: the measured speed-up is flat past this; each runner costs memory.
SHARD_WIDTH_CAP = 16


def default_shard_width(cpus: int | None = None) -> int:
    """Runners for this machine: cores minus SHARD_CORES_RESERVED, clamped to
    [2, SHARD_WIDTH_CAP]. Measured near-linear to ~8 runners, flat by 16; a
    fixed width would idle a workstation or oversubscribe a laptop."""
    n = cpus if cpus is not None else (os.cpu_count() or 4)
    return max(2, min(SHARD_WIDTH_CAP, n - SHARD_CORES_RESERVED))


#: Resolved once at import; retro.py's default width is this too.
DEFAULT_SHARD_WIDTH = default_shard_width()

#: Per-machine override (never scientific); =1 runs a single process.
WIDTH_ENV = "FLUBNF_PF_WIDTH"


def resolve_width(width) -> int:
    """A requested shard width; 0, None or garbage means DEFAULT_SHARD_WIDTH.
    Used by the CLI; execute() resolves its own via shard_width()."""
    try:
        w = int(width)
    except (TypeError, ValueError):
        w = 0
    return w if w > 0 else DEFAULT_SHARD_WIDTH

#: Seconds per cell, fitted on 680 shard-weeks of the sealed record (R^2 0.988):
#:     seconds = 1.194 + 0.6365 * (n_obs + 4)      (+4 = the forecast weeks)
#: at 10,000 particles; linear in particles. Prediction only.
COST_INTERCEPT_S = 1.194
COST_PER_WEEK_S = 0.6365
COST_FORECAST_WEEKS = 4
COST_REFERENCE_PARTICLES = 10_000

#: Budget = this multiple of the predicted SLOWEST shard: covers a box up to
#: 3x slower (or shared with the browser/server/replay). Dead runners end the
#: poll at once, so the budget only governs a run still alive.
TIMEOUT_SAFETY = 3.0

#: Floor under the budget: the old fixed hour, so a budget is never shorter
#: than before. The multiple assumes the width's concurrency is real; on an
#: oversubscribed box it is not (full grid at n_obs 23: 2922 s serial vs
#: 2206 s = 3x slowest shard), and tiny grids need slack for cold starts.
#: Cost: a hung run lives up to an hour; STOP works at any time.
TIMEOUT_FLOOR_S = 3600.0

#: How often the supervisor looks at its runners and at the STOP flag.
POLL_S = 1.0

#: Cancel signals; SIGKILL is POSIX-only (Windows: both mean terminate).
_SIGTERM = signal.SIGTERM
_SIGKILL = getattr(signal, "SIGKILL", signal.SIGTERM)

_sleep = time.sleep          # indirection so tests can drive the poll loop

#: subprocess.CREATE_NEW_PROCESS_GROUP by value (the name is Windows-only).
_CREATE_NEW_PROCESS_GROUP = 0x00000200

#: Launched-runner registry ({pid: {pgid, runner}}), beside app.pid. A
#: takeover kills the server without the supervisors' finally blocks, so the
#: next launch sweeps orphaned runners from here (flubnf/cli.py::
#: _sweep_runner_groups reads this format and must agree with it).
RUNNER_PIDS_FILE = REPO / "app" / "state" / "pf_runners.json"


def runner_popen_kwargs(base: dict | None = None,
                        _os_name: str | None = None) -> dict:
    """`base` plus the keywords that put a runner in its own process group
    (session on POSIX): the address a takeover sweep can still signal once
    the supervisor died. The live cancel path uses _signal_tree instead.
    `_os_name` is injectable for tests."""
    kw = dict(base or {})
    if (_os_name or os.name) == "posix":
        kw["start_new_session"] = True
    else:
        kw["creationflags"] = (int(kw.get("creationflags", 0))
                               | _CREATE_NEW_PROCESS_GROUP)
    return kw


def record_runner_pids(procs, path: Path | None = None) -> None:
    """Add runners to the takeover registry: pid, pgid (== pid on POSIX,
    None on Windows) and the runner script, which the sweep matches against
    the live command line so a recycled pid is never signalled. Merged with
    concurrent runs' entries. Never fatal."""
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
    """Drop finished runners from the registry (their pids may be recycled);
    other runs' entries stay. Never fatal."""
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
    """Predicted seconds for one cell (no particle count: the reference 10,000)."""
    n_obs = int(cell.get("n_obs") or 0)
    particles = float(cell.get("particles") or COST_REFERENCE_PARTICLES)
    return ((COST_INTERCEPT_S + COST_PER_WEEK_S * (n_obs + COST_FORECAST_WEEKS))
            * max(particles, 1.0) / COST_REFERENCE_PARTICLES)


def expected_seconds(shards: list) -> float:
    """Predicted wall clock: the slowest shard (shards run concurrently)."""
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
    """Every process below `pid`, deepest last; [] where the tree cannot be
    read (non-POSIX, ps failure)."""
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
    """Signal a runner AND its engine processes (PyBNF's pool would
    otherwise keep its cores).

    The tree is READ before signalling (a dead runner's children are
    reparented and unidentifiable) and the runner goes first, so a pool it
    was growing cannot outlive the sweep. `ps` rather than the runner's
    session: Windows has no killpg and a pool member may change group.
    Terminal Ctrl-C no longer reaches runners (own session): _stop_all reaps
    them, or the next launch's takeover sweep.
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
    """Stop every live runner with its engine processes and WAIT for each;
    no exception may skip this."""
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
    """The over-budget message: progress, and which term of budget_seconds
    bound (the floor usually does; "60 min = 3 x 12 min" would be false)."""
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
    # counts and budget lead: the ledger keeps only 300 chars of an error
    return (f"PF fitting exceeded its time budget: {done} of {n_cells} cells "
            f"finished. Budget was {how}. On a slower machine widen the "
            f"sharding ({WIDTH_ENV}); otherwise suspect the engine venv.")


def execute(workroot: Path, timeout: float | None = None,
            width: int | None = None) -> dict:
    """Run the prepared cells sharded across low-priority runner
    subprocesses; return (and write to pf_status.json) the merged
    {cell key: "ok" | "FAIL: ..."}.

    <workroot>/STOP halts runners between cells; every runner is reaped
    before RunStopped is raised. A cell no shard reported becomes a FAIL
    quoting that shard's stderr; no status at all raises with the stderr.
    `timeout` defaults to budget_seconds(); `width` to shard_width() (env
    override, else DEFAULT_SHARD_WIDTH).
    """
    workroot = Path(workroot)
    out_json = workroot / "pf_status.json"
    cells = json.loads((workroot / "cells.json").read_text())
    # prepare-stage failures belong to this run's status (-> pf_failures)
    prep_failures = read_prepare_failures(workroot)
    if not cells:
        # nothing to fit is not a failure; prepare's refusals still surface
        out_json.write_text(json.dumps(prep_failures))
        return dict(prep_failures)
    shards = shard_cells(cells, width)
    sized = not timeout
    budget = budget_seconds(shards) if sized else float(timeout)
    stop = workroot / "STOP"            # the user's flag AND the runners' halt

    # Fits yield to the interactive server; `nice` execs the interpreter, so
    # each Popen is still the real runner. See app/core/proc.py.
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
            # stderr to a FILE: an undrained pipe would fill and hang the runner
            fh = open(ef, "w")
            handles.append(fh)
            # own session/process group: see runner_popen_kwargs
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
        # STOP landed before the first poll or after the last runner exited:
        # still a stop, never a status that reads like a finished grid
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


# --- collect ------------------------------------------------------------------

def _cell_statuses(workroot: Path) -> dict:
    """Per-cell fit statuses: pf_status.json (forecast path) over cells_done/
    markers (retro.py's CELL_DONE_DIRNAME, mirrored: retro imports this
    module, not the reverse). {} when neither exists (read every cell)."""
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
    """Record an assembly-time failure in pf_status.json. Never fatal."""
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


def _save_cloud(workroot: Path, c: dict) -> None:
    """Copy the cell's ending cloud to save_state_to (it outlives the prune).
    A missing cloud is recorded in STATE_MISSING_NAME; the cell is still
    pooled, only the carry is lost."""
    src = Path(c.get("state_file") or "")
    dest = Path(c["save_state_to"])
    if src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return
    rec = Path(workroot) / STATE_MISSING_NAME
    try:
        cur = json.loads(rec.read_text()) if rec.is_file() else {}
    except Exception:
        cur = {}
    cur[c["key"]] = f"no cloud file at {src}"
    rec.write_text(json.dumps(cur, sort_keys=True))


def collect(workroot: Path) -> dict:
    """Forecast samples per location: replicate-pooled, anchored at origin.

    Only cells whose status is ok (or unrecorded) are read. A torn
    trajectory (empty, one row, ragged) is recorded as a failure and
    skipped, so one dead cell cannot cost the others their samples."""
    import numpy as np
    cells = json.loads((workroot / "cells.json").read_text())
    status = _cell_statuses(workroot)
    by_loc: dict = {}
    for c in cells:
        st = status.get(c["key"])
        if st is not None and st != "ok":
            continue              # a recorded failure has nothing to pool
        runs = Path(c["dir"]) / "out" / "Results" / "PF" / "Runs"
        tr_files = sorted(runs.glob("*traj_noise*"))
        if not tr_files:
            continue
        try:
            tr = np.genfromtxt(tr_files[0])
        except Exception as e:
            _record_collect_failure(
                workroot, c["key"],
                f"FAIL: trajectory {tr_files[0].name} unreadable ({e}); "
                "the cell is excluded from assembly")
            continue
        if tr.ndim < 2:
            # empty -> shape (0,), one row -> 1-D; a real one is particles x weeks
            _record_collect_failure(
                workroot, c["key"],
                f"FAIL: trajectory {tr_files[0].name} is torn "
                f"({'empty' if tr.size == 0 else 'a single row'}); "
                "the cell is excluded from assembly")
            continue
        if c.get("save_state_to"):
            _save_cloud(workroot, c)
        n = c["n_obs"]
        origin = tr[:, n - 1]
        med = float(np.median(origin[np.isfinite(origin)]))
        scale = c["last_observed"] / med if med > 0 else 1.0
        # Horizons are AS-OF-relative: with k trimmed weeks the conf asked for
        # pf_forecast_intervals = 4 + k, so horizon h is column n-1+k+h and
        # the as-of week is n-1+k. The anchor pair (last_observed, med) is
        # still the fit origin's.
        k = int(c.get("weeks_dropped", 0) or 0)
        need = n + k + 4
        if tr.shape[1] < need:
            # a recorded trim the engine did not extend the forecast for
            raise RuntimeError(
                f"{c['key']}: trajectory has {tr.shape[1]} columns, "
                f"{need} needed for weeks_dropped={k}; the engine did not "
                "extend the forecast for the recorded trim -- rerun the "
                "forecast on a current engine")
        # Canonical keys (app.core.horizons): anchor under hz.ORIGIN, physical
        # week h under hub label h-1 (an anchor keyed "0" would shift every
        # submitted row a week early).
        d = by_loc.setdefault(c["location"],
                              {hz.ORIGIN: [], **{h: [] for h in hz.HORIZONS}})
        d[hz.ORIGIN].extend((tr[:, n - 1 + k] * scale).tolist())
        for h in (1, 2, 3, 4):
            d[str(h - 1)].extend((tr[:, n - 1 + k + h] * scale).tolist())
    return by_loc
