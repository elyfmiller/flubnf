"""The sandbox: the particle filter on a model of your own, outside the
production path.

A model lives in sandbox/models/<name>/ as three files: model.bngl (any
BNGL model whose simulate action names a suffix), data.exp (the counts
to fit, one time column and one observation column), and priors.conf
(one *_var line per free parameter, plus any pf_* keys the model needs,
such as pf_cumulative_observable naming the scaled accumulator whose
increment is the expected count). A run copies the model into its own
workroot under sandbox/runs/, generates the network with BNG2.pl, writes
the engine configuration, runs the engine exactly as a console run does
(the same runner, the same engine venv), and reads the outputs back.

The sandbox never touches the runs ledger, the retrospectives or the
seal: its workroots are its own, the folder is not under version control,
and the production templates are never read from here. Four examples ship
with FluBNF (flubnf/sandbox_examples) and can be copied in to start from,
and new_model writes a runnable skeleton of the three files to edit.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

from flubnf.settings import BNG
from app.core.engines.pf import REPO
from app.core.engines import pf as pf_engine

SANDBOX = REPO / "sandbox"
MODELS = SANDBOX / "models"
RUNS = SANDBOX / "runs"
EXAMPLES = REPO / "flubnf" / "sandbox_examples"
REQUIRED = ("model.bngl", "data.exp", "priors.conf")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
#: The conf keys the sandbox itself writes; a priors.conf line naming one
#: of them overrides the form's value instead of duplicating the key.
ENGINE_KEYS = ("objfunc", "pf_cumulative_observable",
               "pf_forecast_intervals", "pf_jitter", "pf_resample_threshold",
               "pf_binom_neff_cap", "initialization")
DRY_RUN_PARTICLES = 200


class SandboxError(ValueError):
    """A model or a request the sandbox refuses, with the reason in words."""


def check_name(name: str) -> str:
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise SandboxError(
            f"{name!r} is not a model name: letters, digits, _ and -, up "
            "to 64 characters, starting with a letter or digit")
    return name


def _first_comment(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if s.startswith("#") and s.strip("# ").strip():
                return s.strip("# ").strip()
            if s and not s.startswith("#"):
                break
    except OSError:
        pass
    return ""


def list_models() -> list:
    """Every model folder, with which of the three files it has."""
    out = []
    if not MODELS.is_dir():
        return out
    for d in sorted(p for p in MODELS.iterdir() if p.is_dir()):
        present = [f for f in REQUIRED if (d / f).is_file()]
        out.append({"name": d.name, "present": present,
                    "missing": [f for f in REQUIRED if f not in present],
                    "complete": len(present) == len(REQUIRED),
                    "note": _first_comment(d / "model.bngl"),
                    "modified": max((int((d / f).stat().st_mtime)
                                     for f in present), default=0)})
    return out


def list_examples() -> list:
    if not EXAMPLES.is_dir():
        return []
    return sorted(p.name for p in EXAMPLES.iterdir()
                  if p.is_dir() and all((p / f).is_file() for f in REQUIRED))


def add_example(name: str) -> Path:
    """Copy a shipped example into the sandbox as a model of the same
    name. An existing model of that name is left alone."""
    check_name(name)
    src = EXAMPLES / name
    if not all((src / f).is_file() for f in REQUIRED):
        raise SandboxError(f"no shipped example named {name!r}")
    dst = MODELS / name
    if dst.exists():
        raise SandboxError(f"a sandbox model named {name!r} already exists")
    dst.mkdir(parents=True)
    for f in REQUIRED:
        shutil.copy2(src / f, dst / f)
    return dst


#: The skeleton new_model writes: a one-step conversion with a tally,
#: every BNGL block the engine needs, the simulate action with its suffix,
#: and one fitted rate, one reporting scale and one dispersion, so the
#: skeleton itself generates and fits before a line of it is changed.
SKELETON_BNGL = """\
# {name}: one line describing the model (it is shown in the model list).
# Every block below is one the engine reads; keep the block names and the
# simulate action, change the rest. Time is in weeks. The observed count
# is the weekly increment of the function priors.conf names as
# pf_cumulative_observable.
begin model
begin parameters
# a fitted parameter ends in __FREE and has a *_var line in priors.conf
k__FREE      0.5        # the rate of the one event; fitted
scale__FREE  0.5        # fraction of events that are counted; fitted
r__FREE      10.0       # negative-binomial dispersion of the counts; fitted
N            100000     # how many can undergo the event; fixed
end parameters

begin molecule types
A()
B()
Tally()
end molecule types

begin seed species
A()     N
B()     0
Tally() 0
end seed species

begin observables
Molecules A      A()
Molecules B      B()
Molecules T_Cum  Tally()     # events to date: the tally the data are read from
end observables

begin functions
Tobs() = scale__FREE*T_Cum   # the tally at the reporting scale
end functions

begin reaction rules
# one event per conversion; Tally() counts it without consuming anyone
A() -> B() + Tally()   k__FREE
end reaction rules
end model

begin actions
generate_network({{overwrite=>1}})
simulate({{suffix=>"sim",method=>"ode",t_start=>0,t_end=>{t_end},n_steps=>{t_end},print_functions=>1}})
end actions
"""

SKELETON_PRIORS = """\
# One *_var line per fitted parameter, named as in model.bngl. The pf_
# lines tell the filter which model output the counts are read from.
uniform_var = k__FREE 0.05 2.0
loguniform_var = scale__FREE 0.05 1.0
loguniform_var = r__FREE 0.1 40.0
pf_cumulative_observable = Tobs
"""

SKELETON_WEEKS = 12


def skeleton(name: str) -> dict:
    """The three files of a new model: the skeleton BNGL, placeholder
    counts simulated from it at its starting values (weekly increments of
    Tobs, the first row the first week's; the engine's data reader takes
    one header line and no other comment), and the priors that name its
    free parameters."""
    import math
    k, scale, n = 0.5, 0.5, 100000
    rows = []
    for t in range(SKELETON_WEEKS):
        a, b = max(t - 1, 0), max(t, 1)
        rows.append(f"{t} {scale * n * (math.exp(-k * a) - math.exp(-k * b)):.0f}")
    data = "# time T_weekly\n" + "\n".join(rows) + "\n"
    return {"model.bngl": SKELETON_BNGL.format(name=name, t_end=SKELETON_WEEKS),
            "data.exp": data, "priors.conf": SKELETON_PRIORS}


def new_model(name: str) -> Path:
    """Write the skeleton as a new sandbox model. An existing model of
    that name is left alone."""
    check_name(name)
    dst = MODELS / name
    if dst.exists():
        raise SandboxError(f"a sandbox model named {name!r} already exists")
    return save_model(name, skeleton(name))


def model_dir(name: str) -> Path:
    d = MODELS / check_name(name)
    missing = [f for f in REQUIRED if not (d / f).is_file()]
    if missing:
        raise SandboxError(f"model {name!r} is missing {', '.join(missing)}")
    return d


def read_model(name: str) -> dict:
    d = model_dir(name)
    return {f: (d / f).read_text(encoding="utf-8", errors="replace")
            for f in REQUIRED}


def save_model(name: str, files: dict) -> Path:
    """Write the three files of a model (creating the folder), keeping
    every byte as given, newlines pinned to \\n for the engine."""
    d = MODELS / check_name(name)
    d.mkdir(parents=True, exist_ok=True)
    for f in REQUIRED:
        if f in files:
            (d / f).write_text(str(files[f]).replace("\r\n", "\n"),
                               encoding="utf-8", newline="\n")
    return d


def simulate_suffix(bngl_text: str) -> str:
    m = re.search(r'suffix\s*=>\s*"([^"]+)"', bngl_text)
    if not m:
        raise SandboxError("the model's simulate action must name a suffix "
                           '(suffix=>"..."): the engine matches the data '
                           "file to the model by it")
    return m.group(1)


def read_exp(exp_text: str) -> dict:
    """The data file's columns and rows; a negative value is a missing
    week, as the production data writer records it."""
    lines = [l for l in exp_text.splitlines() if l.strip()]
    if not lines or not lines[0].lstrip().startswith("#"):
        raise SandboxError("data.exp must start with a header line such as "
                           "'# time H_weekly'")
    cols = lines[0].lstrip("#").split()
    rows = []
    for l in lines[1:]:
        if l.lstrip().startswith("#"):
            continue
        parts = l.split()
        if len(parts) != len(cols):
            raise SandboxError(f"data.exp row {l!r} has {len(parts)} values "
                               f"for {len(cols)} columns")
        rows.append([float(x) for x in parts])
    if len(cols) < 2 or not rows:
        raise SandboxError("data.exp needs a time column, one observation "
                           "column and at least one row")
    return {"columns": cols, "rows": rows}


def split_priors(priors_text: str) -> tuple:
    """(prior lines, engine key overrides) from priors.conf."""
    priors, keys = [], {}
    for line in priors_text.splitlines():
        s = line.split("#", 1)[0].strip()
        if not s:
            continue
        if "=" in s:
            k, v = (x.strip() for x in s.split("=", 1))
            if k in ENGINE_KEYS:
                keys[k] = v
                continue
        priors.append(s)
    if not any(p.split("=", 1)[0].strip().endswith("_var") for p in priors):
        raise SandboxError("priors.conf declares no free parameter "
                           "(no uniform_var, loguniform_var, normal_var or "
                           "lognormal_var line)")
    return priors, keys


def prepare(name: str, *, particles: int = DRY_RUN_PARTICLES,
            jitter: float = 0.15,
            cumulative: str = "", forecast_weeks: int = 4, seed: int = 0,
            runs_root: Path | None = None) -> Path:
    """A workroot with one prepared cell, ready for pf_engine.execute.

    The network is generated here, by BNG2.pl, so a model that does not
    generate is refused before the engine is asked for anything, with
    BNG2.pl's own words.
    """
    d = model_dir(name)
    files = read_model(name)
    sfx = simulate_suffix(files["model.bngl"])
    exp = read_exp(files["data.exp"])
    priors, keys = split_priors(files["priors.conf"])
    particles = max(50, min(int(particles), 100_000))
    forecast_weeks = max(0, min(int(forecast_weeks), 12))
    keys.pop("pf_observable_mode", None)      # a retired key: ignored
    cumulative = keys.pop("pf_cumulative_observable", cumulative) or ""
    objfunc = keys.pop("objfunc", "neg_bin_dynamic")
    jitter = float(keys.pop("pf_jitter", jitter))
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    workroot = (runs_root or RUNS) / f"{stamp}_{name}"
    n = 1
    while workroot.exists():
        n += 1
        workroot = (runs_root or RUNS) / f"{stamp}_{name}_{n}"
    cell = workroot / f"{name}_r0"
    cell.mkdir(parents=True)
    pf_engine.conf_safe_path(workroot)
    (cell / "m.bngl").write_text(files["model.bngl"].replace("\r\n", "\n"),
                                 encoding="utf-8", newline="\n")
    (cell / f"{sfx}.exp").write_text(files["data.exp"].replace("\r\n", "\n"),
                                     encoding="utf-8", newline="\n")
    r = subprocess.run(["perl", BNG, "m.bngl"], capture_output=True,
                       text=True, cwd=str(cell), timeout=300)
    if not (cell / "m.net").is_file():
        raise SandboxError("BNG2.pl could not generate the network:\n"
                           + (r.stdout or "")[-600:] + (r.stderr or "")[-300:])
    c = pf_engine.conf_safe_path(cell)
    conf = [f"bng_command = {pf_engine.conf_safe_path(BNG)}",
            f"model = {c}/m.bngl : {c}/{sfx}.exp",
            f"output_dir = {c}/out",
            "fit_type = pf",
            f"objfunc = {objfunc}",
            f"pf_particles = {particles}",
            f"pf_jitter = {jitter:g}",
            f"pf_forecast_intervals = {forecast_weeks}",
            "population_size = 1",
            "max_iterations = 1",
            f"initialization = {keys.pop('initialization', 'rand')}",
            f"seed = {int(seed)}"]
    if cumulative:
        conf.append(f"pf_cumulative_observable = {cumulative}")
    conf += [f"{k} = {v}" for k, v in keys.items()]
    (cell / "pf.conf").write_text("\n".join(conf) + "\n" + "\n".join(priors)
                                  + "\n", encoding="utf-8", newline="\n")
    obs_col = exp["columns"][1]
    observed = [row[1] for row in exp["rows"]]
    cells = [{"key": f"{name}_r0", "dir": str(cell), "location": name,
              "replicate": 0, "seed": int(seed), "n_obs": len(observed),
              "particles": particles, "last_observed": float(observed[-1]),
              "weeks_dropped": 0, "last_week_offset": len(observed) - 1,
              "sandbox": True}]
    (workroot / "cells.json").write_text(json.dumps(cells))
    meta = {"model": name, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "particles": particles, "jitter": jitter,
            "cumulative": cumulative, "forecast_weeks": forecast_weeks,
            "seed": int(seed), "suffix": sfx, "obs_col": obs_col,
            "time": [row[0] for row in exp["rows"]], "observed": observed,
            "status": "prepared"}
    (workroot / "meta.json").write_text(json.dumps(meta))
    return workroot


def run(workroot: Path, width: int = 1) -> dict:
    """Execute the prepared cell in the engine venv; the workroot's
    meta.json records the outcome either way."""
    workroot = Path(workroot)
    meta = json.loads((workroot / "meta.json").read_text())
    meta["status"] = "running"
    (workroot / "meta.json").write_text(json.dumps(meta))
    t0 = time.monotonic()
    try:
        status = pf_engine.execute(workroot, width=width)
        key = next(iter(status)) if status else None
        meta["status"] = "ok" if key and status[key] == "ok" else "failed"
        meta["engine_status"] = status
    except Exception as e:                       # the reason reaches the page
        meta["status"] = "failed"
        meta["error"] = str(e)[:2000]
    meta["seconds"] = round(time.monotonic() - t0, 1)
    meta["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (workroot / "meta.json").write_text(json.dumps(meta))
    return meta


def list_runs(runs_root: Path | None = None) -> list:
    root = runs_root or RUNS
    out = []
    if not root.is_dir():
        return out
    for d in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        try:
            meta = json.loads((d / "meta.json").read_text())
        except Exception:
            continue
        meta["run_id"] = d.name
        out.append(meta)
    return out


def results(workroot: Path) -> dict:
    """What the engine wrote, read back: the outcome, a parameter table
    (5th, 50th and 95th percentiles of the posterior sample), the ESS
    record, and the trajectory summarised per week (10th, 50th, 90th
    percentiles over particles) with the observed counts beside it."""
    workroot = Path(workroot)
    meta = json.loads((workroot / "meta.json").read_text())
    out = {"meta": meta, "run_id": workroot.name, "params": [], "ess": [],
           "traj": None, "stderr": ""}
    cell = workroot / f"{meta['model']}_r0"
    runs = cell / "out" / "Results" / "A_MCMC" / "Runs"
    pf = next(runs.glob("params_*.txt"), None) if runs.is_dir() else None
    if pf is not None:
        try:
            names = pf.read_text().splitlines()[0].split("\t")
            arr = np.loadtxt(pf, skiprows=1, ndmin=2)
            for j, nme in enumerate(names):
                q = np.percentile(arr[:, j], [5, 50, 95])
                out["params"].append({"name": nme, "p5": float(q[0]),
                                      "p50": float(q[1]), "p95": float(q[2])})
            out["distinct"] = int(np.unique(arr, axis=0).shape[0])
            out["sample"] = int(arr.shape[0])
        except Exception as e:
            out["stderr"] += f"params unreadable: {e}\n"
    ef = cell / "out" / "ess_0.txt"
    if ef.is_file():
        try:
            e = np.loadtxt(ef, ndmin=2, comments="#")
            out["ess"] = [{"t": float(r[0]), "ess": float(r[1]),
                           "distinct": int(r[3]), "degenerate": int(r[4])}
                          for r in e]
        except Exception as exc:
            out["stderr"] += f"ess unreadable: {exc}\n"
    tf = next(runs.glob("*traj_noise*"), None) if runs.is_dir() else None
    if tf is not None:
        try:
            tr = np.loadtxt(tf, ndmin=2)
            n = int(meta["n_obs"]) if "n_obs" in meta else len(meta["observed"])
            q = np.nanpercentile(tr, [10, 50, 90], axis=0)
            out["traj"] = {"n_obs": n, "columns": int(tr.shape[1]),
                           "q10": q[0].tolist(), "q50": q[1].tolist(),
                           "q90": q[2].tolist()}
        except Exception as exc:
            out["stderr"] += f"trajectory unreadable: {exc}\n"
    for err in sorted(workroot.glob("pf_runner_*.err")):
        try:
            txt = err.read_text(errors="replace").strip()
        except OSError:
            continue
        if txt:
            out["stderr"] += txt[-1500:]
    return out


# ------------------------------------------------------------- the archive
# A model's data.exp filled from the hub archive: one location's weekly
# admissions over a date range, settled or as one vintage knew it. The
# hub modules are imported inside the functions so this module imports
# on a machine without a hub. The sidecar data.source.json records where
# the rows came from; the engine never reads it.

SOURCE_FILE = "data.source.json"
DEFAULT_HEADER = "# time H_weekly"
DEFAULT_WEEKS = 20


def locations() -> list:
    """Every location the hub's locations table names, US first then
    alphabetical, as [{"name", "fips"}]. Empty when there is no hub."""
    try:
        import pandas as pd
        from app.core import data as data_mod
        locs = pd.read_csv(data_mod.LOCATIONS, dtype=str)
        rows = [{"name": str(n), "fips": str(f).zfill(2)}
                for n, f in zip(locs.location_name, locs.location)
                if isinstance(n, str) and n.strip()]
    except Exception:
        return []
    rows.sort(key=lambda r: r["name"])
    return ([r for r in rows if r["name"].upper() == "US"]
            + [r for r in rows if r["name"].upper() != "US"])


def vintages() -> list:
    """The archive's vintage dates, newest first; empty when there is no
    hub. Never raises: the page renders either way."""
    try:
        from app.core import data as data_mod
        return list(reversed(data_mod.vintages()))
    except Exception:
        return []


def default_range(vintage_dates: list, weeks: int = DEFAULT_WEEKS) -> dict:
    """The date inputs' starting values: the last `weeks` weeks ending on
    the newest vintage's date (a vintage archived on Saturday D carries
    the week ending D). Empty strings when no vintage is known."""
    import datetime as dt
    newest = vintage_dates[0] if vintage_dates else ""
    try:
        end = dt.date.fromisoformat(str(newest))
    except (TypeError, ValueError):
        return {"start": "", "end": ""}
    start = end - dt.timedelta(days=7 * (max(int(weeks), 1) - 1))
    return {"start": start.isoformat(), "end": end.isoformat()}


def _iso_date(s: str, what: str):
    import datetime as dt
    try:
        return dt.date.fromisoformat(str(s).strip())
    except (TypeError, ValueError):
        raise SandboxError(f"{what} must be a date written YYYY-MM-DD, "
                           f"not {s!r}") from None


def _check_range(start: str, end: str) -> tuple:
    a, b = _iso_date(start, "start"), _iso_date(end, "end")
    if a > b:
        raise SandboxError(f"start {a.isoformat()} is after end {b.isoformat()}")
    return a.isoformat(), b.isoformat()


def series_for(location_name: str, start: str, end: str,
               asof: str | None = None) -> dict:
    """The weekly admissions of one location between two dates: the
    settled truth when asof is None, else what the vintage archived on
    asof held. {"dates": [...], "values": [...], "dropped": n}, where
    dropped counts the Saturdays in the range with no reported value.
    Missing weeks are dropped, never imputed."""
    import datetime as dt
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
    dates = sorted(d for d in got if start <= d <= end)
    d = dt.date.fromisoformat(start)
    while d.weekday() != 5:                      # forward to a Saturday
        d += dt.timedelta(days=1)
    dropped = 0
    last = dt.date.fromisoformat(end)
    while d <= last:
        if d.isoformat() not in got:
            dropped += 1
        d += dt.timedelta(days=7)
    return {"dates": dates, "values": [float(got[d]) for d in dates],
            "dropped": dropped}


def _fmt(v: float) -> str:
    v = float(v)
    return str(int(v)) if v.is_integer() else repr(v)


def _digest(text: str) -> str:
    import hashlib
    return hashlib.sha1(text.replace("\r\n", "\n").strip()
                        .encode("utf-8")).hexdigest()


def fill_data(name: str, location_name: str, start: str, end: str,
              asof: str | None = None) -> dict:
    """Rewrite a model's data.exp from the archive: the file's own header
    line if it has one (else '# time H_weekly'), then one 't value' row
    per reported week, t counting 0, 1, 2 ... in date order. Writes the
    sidecar data.source.json beside it and returns its contents. Refuses
    an unknown location, a range with no reported week, and start after
    end."""
    d = model_dir(name)
    start, end = _check_range(start, end)
    known = {l["name"] for l in locations()}
    if str(location_name) not in known:
        raise SandboxError(f"unknown location {location_name!r}: the hub's "
                           "locations table does not name it")
    s = series_for(location_name, start, end, asof)
    if not s["values"]:
        raise SandboxError(f"no reported week for {location_name} between "
                           f"{start} and {end}"
                           + (f" in the vintage of {asof}" if asof else ""))
    header = DEFAULT_HEADER
    exp = d / "data.exp"
    if exp.is_file():
        for line in exp.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                if line.lstrip().startswith("#"):
                    header = line.rstrip()
                break
    text = header + "\n" + "\n".join(
        f"{t} {_fmt(v)}" for t, v in enumerate(s["values"])) + "\n"
    exp.write_text(text, encoding="utf-8", newline="\n")
    info = {"location": str(location_name), "start": start, "end": end,
            "asof": str(asof) if asof else "settled",
            "rows": len(s["values"]), "dropped": int(s["dropped"]),
            "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "digest": _digest(text)}
    (d / SOURCE_FILE).write_text(json.dumps(info, indent=1) + "\n",
                                 encoding="utf-8", newline="\n")
    return info


def read_data_source(name: str) -> dict | None:
    """The sidecar of a model, or None: none written, unreadable, or
    data.exp edited since (its digest no longer matches), so the page
    never says the file holds archive rows it no longer holds."""
    try:
        d = MODELS / check_name(name)
        info = json.loads((d / SOURCE_FILE).read_text(encoding="utf-8"))
        if not isinstance(info, dict):
            return None
        cur = (d / "data.exp").read_text(encoding="utf-8", errors="replace")
        if info.get("digest") and info["digest"] != _digest(cur):
            return None
        return info
    except Exception:
        return None
