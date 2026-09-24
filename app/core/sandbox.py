"""SANDBOX: user models run through the PF engine outside production (server
/sandbox routes).

The sandbox: the particle filter on a model of your own, outside the
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
and the production templates are never read from here. The examples and
a template for a new pathogen ship with FluBNF (flubnf/sandbox_examples;
each one's data simulated from the model itself) and can be copied in
under any name,
new_model writes a runnable skeleton of the three files to edit, and
copy_model duplicates a model; model.json records where each came from.
from_shipped starts a model from the Oracle SIHRS filter exactly as the
console's particle filter builds it for one jurisdiction and week, with
creation digests so an edited copy never passes for it. check() reads a
model without the engine (and sets the model at its written values,
expected_counts, beside the data); prepare() runs the production
preflight first; fit_health reads a finished run in plain words.
data.exp can be filled from the hub archive, from a stored custom
dataset (app/core/datasets.py), always in calendar weeks, or with counts
simulated from the model (simulate_data). Runs can be
compared (diff_runs) and downloaded (model_zip, run_zip), and a run of an
unedited Oracle SIHRS start can take the production Oracle step inside
its own folder (oracle_step: sandbox, never a submission).
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
               "pf_binom_neff_cap", "initialization", "pf_bounds",
               "pf_start_time", "pf_sampling_interval")
#: Conf keys only the run settings and the workroot decide; a priors.conf
#: line naming one would duplicate a key, so it is refused.
RESERVED_KEYS = ("fit_type", "model", "output_dir", "bng_command",
                 "pf_particles", "pf_seed", "population_size",
                 "max_iterations")
#: Keys an older priors.conf may carry that no engine reads any more: the
#: check names them, a run drops them (the filter always fits the weekly
#: increment, what pf_observable_mode = integrated used to ask for).
RETIRED_KEYS = ("pf_observable_mode",)
DRY_RUN_PARTICLES = 200
FULL_FIT_PARTICLES = 10_000
#: A run's status while its fit may still be live; with no live fit behind
#: it (an app restart) it reads as INTERRUPTED, as the Storage panel does.
LIVE_STATUSES = ("prepared", "running")
INTERRUPTED = "interrupted"
#: run folder names: prepare's <UTC stamp>_<model>[_<n>]
RUN_ID_RE = re.compile(r"^\d{8}-\d{6}_[A-Za-z0-9][A-Za-z0-9_-]{0,70}$")


class SandboxError(ValueError):
    """A model or a request the sandbox refuses, with the reason in words."""


def check_name(name: str) -> str:
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise SandboxError(
            f"{name!r} is not a model name: letters, digits, _ and -, up "
            "to 64 characters, starting with a letter or digit")
    return name


def _first_comment(path: Path) -> str:
    """The model's note: the first sentence of its leading comment, which
    may run over several comment lines (at most 280 characters)."""
    words = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s.startswith("#"):
                if s or words:
                    break
                continue
            text = s.strip("# ").strip()
            if not text:
                if words:
                    break
                continue
            words.append(text)
            if re.search(r"[.:!?]$", text) or re.search(r"[.!?]\s", text):
                break
    except OSError:
        pass
    note = " ".join(words)
    m = re.match(r"(.+?[.!?])(\s|$)", note)
    note = m.group(1) if m else note
    return note if len(note) <= 280 else note[:277].rstrip() + "..."


def list_models() -> list:
    """Every model folder: which of the three files it has, the note (its
    first comment line), where it came from, and when it last changed."""
    out = []
    if not MODELS.is_dir():
        return out
    for d in sorted(p for p in MODELS.iterdir() if p.is_dir()):
        present = [f for f in REQUIRED if (d / f).is_file()]
        mtime = max((int((d / f).stat().st_mtime) for f in present), default=0)
        out.append({"name": d.name, "present": present,
                    "modified_h": (time.strftime("%Y-%m-%d %H:%M",
                                                 time.localtime(mtime))
                                   if mtime else ""),
                    "missing": [f for f in REQUIRED if f not in present],
                    "complete": len(present) == len(REQUIRED),
                    "note": _first_comment(d / "model.bngl"),
                    "origin": model_origin(d.name),
                    "modified": max((int((d / f).stat().st_mtime)
                                     for f in present), default=0)})
    return out


def origin_label(origin: str) -> str:
    """model.json's origin in words for the gallery."""
    if origin in (SHIPPED, SHIPPED_DATASET):
        return "the Oracle SIHRS start"
    kind, _, what = str(origin or "").partition(":")
    return {"skeleton": "skeleton", "example": f"example {what}",
            "copy": f"copy of {what}"}.get(kind, "")


def model_origin(name: str) -> str:
    """A model's origin in words; a shipped start says where and when, and
    says 'modified' once any of its three files changed since creation."""
    st = shipped_state(name)
    if not st["shipped"]:
        return origin_label(st["info"].get("origin", ""))
    i = st["info"]
    where = f"{i.get('location', '')}, {i.get('forecast_date', '')}"
    if st["intact"]:
        return f"the Oracle SIHRS start ({where})"
    return f"the Oracle SIHRS start ({where}), modified"


def list_examples() -> list:
    if not EXAMPLES.is_dir():
        return []
    return sorted(p.name for p in EXAMPLES.iterdir()
                  if p.is_dir() and all((p / f).is_file() for f in REQUIRED))


def example_note(name: str) -> str:
    """A shipped example's note: the first sentence of its model.bngl."""
    return _first_comment(EXAMPLES / check_name(name) / "model.bngl")


def _write_info(name: str, info: dict) -> None:
    (MODELS / check_name(name) / MODEL_FILE).write_text(
        json.dumps(info, indent=1) + "\n", encoding="utf-8", newline="\n")


def _new_folder(name: str) -> Path:
    dst = MODELS / check_name(name)
    if dst.exists():
        raise SandboxError(f"a sandbox model named {name!r} already exists")
    return dst


def _stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def add_example(name: str, as_name: str | None = None) -> Path:
    """Copy a shipped example into the sandbox, under its own name or
    as_name. An existing model of that name is left alone."""
    check_name(name)
    src = EXAMPLES / name
    if not all((src / f).is_file() for f in REQUIRED):
        raise SandboxError(f"no shipped example named {name!r}")
    target = as_name or name
    dst = _new_folder(target)
    dst.mkdir(parents=True)
    for f in REQUIRED:
        shutil.copy2(src / f, dst / f)
    _write_info(target, {"origin": f"example:{name}", "created_utc": _stamp()})
    return dst


def copy_model(src: str, dst: str) -> Path:
    """A copy of a sandbox model under a new name: its three files and its
    data sidecar. The copy's origin names the model it came from (never
    the original's origin, which it no longer is)."""
    s = model_dir(src)
    d = _new_folder(dst)
    d.mkdir(parents=True)
    for f in REQUIRED + (SOURCE_FILE,):
        if (s / f).is_file():
            shutil.copy2(s / f, d / f)
    info = {k: v for k, v in read_info(src).items()
            if k in ("season_start",)}
    _write_info(dst, {**info, "origin": f"copy:{src}", "created_utc": _stamp()})
    return d


def _live_model(live) -> str:
    """The model of the live run id, or ''."""
    if not live:
        return ""
    try:
        return json.loads((RUNS / str(live) / "meta.json").read_text())["model"]
    except Exception:
        return ""


def delete_model(name: str, live=None) -> int:
    """Delete a model with its runs and its diagram folder; the number of
    runs deleted. Refused while one of its runs is the live fit."""
    d = MODELS / check_name(name)
    if not d.is_dir():
        raise SandboxError(f"no sandbox model named {name!r}")
    if _live_model(live) == name:
        raise SandboxError(f"a run of {name} is fitting; stop it first")
    runs = list_runs(model=name)
    for r in runs:
        shutil.rmtree(RUNS / r["run_id"], ignore_errors=True)
    shutil.rmtree(SANDBOX / "contactmap" / name, ignore_errors=True)
    shutil.rmtree(d)
    return len(runs)


def delete_run(run_id: str, live=None) -> str:
    """Delete one run folder (never the live fit); its model's name."""
    d = run_dir(run_id)
    if live and run_id == live:
        raise SandboxError(f"sandbox run {run_id} is fitting; stop it first")
    try:
        model = json.loads((d / "meta.json").read_text()).get("model", "")
    except Exception:
        model = ""
    shutil.rmtree(d)
    return model


def storage() -> dict:
    """The sandbox folder's size for the Storage panel (read-only)."""
    total, files = 0, 0
    if SANDBOX.is_dir():
        for p in SANDBOX.rglob("*"):
            try:
                if p.is_file() and not p.is_symlink():
                    total += p.stat().st_size
                    files += 1
            except OSError:
                continue
    n_runs = (sum(1 for p in RUNS.iterdir() if p.is_dir())
              if RUNS.is_dir() else 0)
    return {"bytes": total, "files": files, "models": len(list_models()),
            "runs": n_runs}


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
    Tobs; the engine starts the model one week before the first row, at
    pf_start_time = -1, so row t is the increment from t-1 to t, which is
    model time t to t+1 from the seed; the engine's data reader takes one
    header line and no other comment), and the priors that name its free
    parameters."""
    import math
    k, scale, n = 0.5, 0.5, 100000
    rows = []
    for t in range(SKELETON_WEEKS):
        rows.append(f"{t} {scale * n * (math.exp(-k * t) - math.exp(-k * (t + 1))):.0f}")
    data = "# time T_weekly\n" + "\n".join(rows) + "\n"
    return {"model.bngl": SKELETON_BNGL.format(name=name, t_end=SKELETON_WEEKS),
            "data.exp": data, "priors.conf": SKELETON_PRIORS}


def new_model(name: str) -> Path:
    """Write the skeleton as a new sandbox model. An existing model of
    that name is left alone."""
    _new_folder(name)
    d = save_model(name, skeleton(name))
    _write_info(name, {"origin": "skeleton", "created_utc": _stamp()})
    return d


# ------------------------------------------------------ the shipped start
# The Oracle SIHRS filter as the console's particle filter materializes it
# for one jurisdiction and forecast date (app/core/engines/pf.py prepare):
# the same resolve_state, template, parameter defaults, priors, suffix and
# seed rule, composed here without the engine. model.json records where it
# came from and the creation digests of the three files, so an edited or
# copied model never passes for the shipped one.

SHIPPED = "shipped:sihrs"
SHIPPED_DATASET = "shipped:sihrs-dataset"
SHIPPED_ORIGINS = (SHIPPED, SHIPPED_DATASET)
SEED_RULE = "runs.derive_seed(location, forecast_date, 0), as the console's replicate 0"


def digests(files: dict) -> dict:
    """The three files' digests (newlines and outer whitespace ignored)."""
    return {f: _digest(str(files.get(f, ""))) for f in REQUIRED}


def from_shipped(name: str, location: str, forecast_date: str, *,
                 season_start: str = "", dataset: str | None = None) -> Path:
    """A new model: the production Oracle SIHRS filter cell for one
    jurisdiction as of forecast_date (the hub vintage of that date), or
    for one group of a stored dataset that has a population. N, rhomult
    and i0 are resolved together from the data (sihrs_fit.resolve_state);
    data.exp keeps the calendar week offsets from season_start. Refused in
    words, leaving nothing behind, when the vintage, location or data are
    missing."""
    import datetime as dt
    import tempfile
    from flubnf.sihrs_fit import materialize_model, resolve_state, write_exp
    from app.core.runs import RunSpec, derive_seed, default_season_start
    check_name(name)
    if (MODELS / name).exists():
        raise SandboxError(f"a sandbox model named {name!r} already exists")
    loc = str(location or "").strip()
    if not loc:
        raise SandboxError("choose a location for the Oracle SIHRS start")
    fd = _iso_date(forecast_date, "the forecast date").isoformat()
    ss = (_iso_date(season_start, "the season start").isoformat()
          if str(season_start or "").strip() else default_season_start(fd))
    if ss >= fd:
        raise SandboxError(f"the season start {ss} is not before the "
                           f"forecast date {fd}")
    extra, ref = {}, None
    if dataset:
        from app.core import datasets
        try:
            ds = datasets.get(dataset)
        except datasets.DatasetError as e:
            raise SandboxError(str(e)) from None
        if not ds.pf_eligible:
            raise SandboxError(
                f"dataset {ds.name!r} holds {'rates' if ds.kind == 'rate' else 'counts'}"
                f"{'' if ds.has_population else ' with no population'}: the "
                "Oracle SIHRS filter needs counts and a population")
        if loc not in ds.groups:
            raise SandboxError(f"dataset {ds.name!r} has no group {loc!r}")
        try:
            truth = ds.truth_path(fd)
        except FileNotFoundError as e:
            raise SandboxError(str(e)) from None
        loc_csv, tag, ref = ds.locations_csv, pf_engine.dataset_tag(loc), ds.ref()
        extra["dataset"] = ref
        origin, source_asof = SHIPPED_DATASET, "dataset"
    else:
        from app.core import data as data_mod
        try:
            truth = data_mod.vintage_path(fd)
        except FileNotFoundError as e:
            raise SandboxError(f"no hub vintage for {fd} here ({e}); pick one "
                               "of the archived dates") from None
        loc_csv, tag = data_mod.LOCATIONS, pf_engine._hub_tag(loc)
        origin, source_asof = SHIPPED, fd
    try:
        s = resolve_state(loc, truth_csv=truth, locations_csv=loc_csv,
                          season_start=ss, as_of=fd)
    except KeyError:
        raise SandboxError(f"unknown location {loc!r}: the locations table "
                           "does not name it") from None
    except (ValueError, OSError) as e:
        raise SandboxError(str(e)) from None
    sfx = f"{tag}_flu"                           # production's suffix
    spec = RunSpec(engine="pf", forecast_date=fd, locations=[loc],
                   season_start=ss, extra=extra)
    with tempfile.TemporaryDirectory() as tmp:
        m = materialize_model(s, pf_engine.TEMPLATE, Path(tmp) / "m.bngl", sfx)
        cell_bngl = m.read_text().replace("begin parameters\n",
                                          pf_engine.DEFAULTS_BLOCK, 1)
        exp = write_exp(s, Path(tmp) / "data.exp").read_text()
    where = f"dataset {ref['name']}, group {loc}" if ref else loc
    files = {
        "model.bngl": (f"# The Oracle SIHRS filter for {where} as of {fd}.\n"
                       "# The production template with this week's data, as "
                       "the console's filter\n# writes it (season from "
                       f"{ss}; suffix {sfx}).\n" + cell_bngl),
        "data.exp": exp,
        "priors.conf": ("# The production priors of the Oracle SIHRS filter "
                        "(app/core/engines/pf.py).\n"
                        + pf_engine.priors_for(spec)
                        + "pf_cumulative_observable = Hobs\n")}
    seed = derive_seed(loc, pf_engine.seed_date_for(spec), 0)
    # each row's week: the one Saturday in its week after season_start
    ss_d = _iso_date(ss, "the season start")
    dates = [_first_saturday((ss_d + dt.timedelta(days=7 * int(t))).isoformat())
             for t in s.times]
    d = save_model(name, files)
    info = {"origin": origin, "created_utc": _stamp(), "location": loc,
            "forecast_date": fd, "season_start": ss, "suffix": sfx,
            "seed": int(seed), "seed_rule": SEED_RULE,
            "population": int(s.population), "digests": digests(files)}
    if ref:
        info["dataset"] = ref
    _write_info(name, info)
    times = [int(t) for t in s.times]
    src = {"location": loc, "start": dates[0], "end": dates[-1],
           "asof": source_asof, "rows": len(times),
           "dropped": int(times[-1] - times[0] + 1 - len(times)),
           "origin": ss, "dates": dates, "population": int(s.population),
           "written_utc": _stamp(), "digest": _digest(files["data.exp"])}
    if ref:
        src.update(dataset=ref, kind="count")
    (d / SOURCE_FILE).write_text(json.dumps(src, indent=1) + "\n",
                                 encoding="utf-8", newline="\n")
    return d


def shipped_state(name: str, files: dict | None = None) -> dict:
    """Whether a model is an Oracle SIHRS start and still as created:
    {"shipped", "intact", "changed": [files edited since], "info"}. A
    model without creation digests is never intact."""
    info = read_info(name)
    out = {"shipped": info.get("origin") in SHIPPED_ORIGINS, "intact": False,
           "changed": [], "info": info}
    if not out["shipped"]:
        return out
    dig = info.get("digests")
    if not isinstance(dig, dict):
        out["changed"] = list(REQUIRED)
        return out
    try:
        files = files or read_model(name)
    except SandboxError:
        out["changed"] = list(REQUIRED)
        return out
    now = digests(files)
    out["changed"] = [f for f in REQUIRED if dig.get(f) != now[f]]
    out["intact"] = not out["changed"]
    return out


def sihrs_shaped(bngl: str) -> bool:
    """A model whose initial state is derived from N and the data (the
    Oracle SIHRS filter's i0), where N cannot be changed on its own."""
    params = set(bngl_parameters(bngl))
    return "N" in params and "i0" in params


def set_population(name: str, population: int) -> None:
    """Rewrite the parameters-block line named N to a population. Refused
    for a model without such a line, and for an SIHRS-shaped model, whose
    i0 and ascertainment are derived from N and the data together: start
    that from the Oracle SIHRS filter instead."""
    d = model_dir(name)
    bngl = (d / "model.bngl").read_text(encoding="utf-8", errors="replace")
    if sihrs_shaped(bngl):
        raise SandboxError(
            "N not changed: this model derives i0 from N and the data, so N "
            "alone would rescale every count. Start from the Oracle SIHRS "
            "filter for the location instead.")
    pop = int(population)
    if pop <= 0:
        raise SandboxError(f"population {population!r} is not positive")
    out, inside, done = [], False, 0
    for line in bngl.splitlines(keepends=True):
        low = " ".join(line.split("#", 1)[0].lower().split())
        if low == "begin parameters":
            inside = True
        elif low == "end parameters":
            inside = False
        elif inside and not done:
            m = re.match(r"^(\s*(?:\d+\s+)?N)(\s*=?\s*)(\S+)(.*)$", line,
                         flags=re.S)
            if m:
                line = f"{m.group(1)}{m.group(2)}{pop}{m.group(4)}"
                done = 1
        out.append(line)
    if not done:
        raise SandboxError("the parameters block has no line named N to set")
    (d / "model.bngl").write_text("".join(out), encoding="utf-8", newline="\n")


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


#: A sidecar the engine never reads: where the model came from ("origin")
#: and, for a seasonal model, its "season_start" (week_origin).
MODEL_FILE = "model.json"


def read_info(name: str) -> dict:
    """The model's model.json, or {} (none, unreadable, not an object)."""
    try:
        info = json.loads((MODELS / check_name(name) / MODEL_FILE)
                          .read_text(encoding="utf-8"))
        return info if isinstance(info, dict) else {}
    except Exception:
        return {}


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
    """(prior lines, engine key overrides) from priors.conf. A line naming
    a key the run settings write (RESERVED_KEYS) is refused in words."""
    priors, keys = [], {}
    for line in priors_text.splitlines():
        s = line.split("#", 1)[0].strip()
        if not s:
            continue
        if "=" in s:
            k, v = (x.strip() for x in s.split("=", 1))
            if k in ENGINE_KEYS or k in RETIRED_KEYS:
                keys[k] = v
                continue
            if k in RESERVED_KEYS:
                raise SandboxError(
                    f"priors.conf sets {k}, which the sandbox writes from "
                    "the run settings; remove that line")
        priors.append(s)
    if not any(p.split("=", 1)[0].strip().endswith("_var") for p in priors):
        raise SandboxError("priors.conf declares no free parameter "
                           "(no uniform_var, loguniform_var, normal_var or "
                           "lognormal_var line)")
    return priors, keys


def _strip_comments(text: str) -> list:
    return [l.split("#", 1)[0].strip() for l in text.splitlines()]


def _block(bngl: str, name: str) -> list:
    """The non-empty, comment-free lines of one `begin <name>` block."""
    out, inside = [], False
    for s in _strip_comments(bngl):
        low = " ".join(s.lower().split())
        if low == f"begin {name}":
            inside = True
        elif low == f"end {name}":
            inside = False
        elif inside and s:
            out.append(s)
    return out


def bngl_parameters(bngl: str) -> list:
    """The names the parameters block defines ('k 0.5', 'k = 0.5' and an
    index before the name all read)."""
    names = []
    for s in _block(bngl, "parameters"):
        toks = s.replace("=", " ").split()
        if toks and toks[0].isdigit():
            toks = toks[1:]
        if toks:
            names.append(toks[0])
    return names


def bngl_parameter_values(bngl: str) -> dict:
    """{name: its value as written} for each parameters-block line (the
    first token after the name: a number or an expression)."""
    out = {}
    for s in _block(bngl, "parameters"):
        toks = s.replace("=", " ").split()
        if toks and toks[0].isdigit():
            toks = toks[1:]
        if len(toks) >= 2:
            out.setdefault(toks[0], toks[1])
    return out


def _number(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def bngl_outputs(bngl: str) -> list:
    """The observable and function names: what pf_cumulative_observable
    may name."""
    names = []
    for s in _block(bngl, "observables"):
        toks = s.split()
        if toks and toks[0].isdigit():
            toks = toks[1:]
        if len(toks) >= 2:
            names.append(toks[1])
    for s in _block(bngl, "functions"):
        toks = s.split()
        if toks and toks[0].isdigit():
            toks = toks[1:]
        if toks:
            names.append(re.split(r"[(=\s]", toks[0])[0])
    return [n for n in names if n]


#: prior lines whose two numbers are a range (the others are mu, sigma)
RANGE_PRIORS = ("uniform_var", "loguniform_var")
SPREAD_PRIORS = ("normal_var", "lognormal_var")


def _check_prior(line: str, params: set, problems: list) -> str:
    """One *_var line; its parameter name ('' when unreadable)."""
    kind, _, rest = (x.strip() for x in line.partition("="))
    toks = rest.split()
    if len(toks) < 3:
        problems.append(f"'{line}' needs a parameter name and two numbers")
        return ""
    name = toks[0]
    try:
        a, b = float(toks[1]), float(toks[2])
    except ValueError:
        problems.append(f"'{line}': {toks[1]} and {toks[2]} must be numbers")
        return name
    if name not in params:
        problems.append(f"{kind} names {name}, which the parameters block "
                        "does not define")
    if kind in RANGE_PRIORS and a >= b:
        problems.append(f"{kind} {name}: the low end {toks[1]} is not below "
                        f"the high end {toks[2]}")
    if kind == "loguniform_var" and a <= 0:
        problems.append(f"loguniform_var {name}: the low end must be above 0")
    if kind in SPREAD_PRIORS and b <= 0:
        problems.append(f"{kind} {name}: the spread {toks[2]} must be above 0")
    return name


def check(files: dict, *, work: Path | None = None) -> dict:
    """What can be known about a model without the engine: fatal problems
    (a run would fail), warnings (it may run but likely not as meant) and
    facts. Network generation runs through BNG2.pl in `work` (a scratch
    folder, never the diagram's) with the model's actions replaced by
    generate_network; without Perl or BNG2.pl it reads 'not checked'.
    Never a precondition of a run: the run makes its own checks."""
    from app.core import contactmap
    problems, warnings = [], []
    facts = {"suffix": "", "free": [], "priors": [], "rows": 0,
             "columns": [], "cumulative": "", "species": None,
             "reactions": None, "network": "not checked", "at_start": ""}
    bngl = str(files.get("model.bngl", ""))
    try:
        facts["suffix"] = simulate_suffix(bngl)
    except SandboxError as e:
        problems.append(str(e))
    code = "\n".join(_strip_comments(bngl))
    if "generate_network(" not in code:
        problems.append("the actions never call generate_network(...): the "
                        "run generates the network with the model's own "
                        "actions")
    params = bngl_parameters(bngl)
    facts["free"] = [p for p in params if p.endswith("__FREE")]
    outputs = bngl_outputs(bngl)
    times = None
    try:
        exp = read_exp(str(files.get("data.exp", "")))
        facts["rows"], facts["columns"] = len(exp["rows"]), exp["columns"]
        times = [r[0] for r in exp["rows"]]
        if any(b <= a for a, b in zip(times, times[1:])):
            problems.append("data.exp: time must increase from row to row")
    except SandboxError as e:
        problems.append(str(e))
    except ValueError as e:
        problems.append(f"data.exp holds a value that is not a number ({e})")
    priors, keys = [], {}
    try:
        priors, keys = split_priors(str(files.get("priors.conf", "")))
    except SandboxError as e:
        problems.append(str(e))
    named = set()
    for line in priors:
        k = line.split("=", 1)[0].strip()
        if k.endswith("_var"):
            named.add(_check_prior(line, set(params), problems))
    facts["priors"] = sorted(n for n in named if n)
    for p in facts["free"]:
        if p not in named:
            warnings.append(f"{p} ends in __FREE but has no prior line")
    warnings += _prior_start_warnings(bngl, priors)
    cum = keys.get("pf_cumulative_observable", "")
    facts["cumulative"] = cum
    if not cum:
        warnings.append("no pf_cumulative_observable line: the filter reads "
                        "the observation column itself, not a weekly "
                        "increment")
    elif cum not in outputs:
        problems.append(f"pf_cumulative_observable names {cum}, which is "
                        "neither an observable nor a function of the model")
    if "pf_observable_mode" in keys:
        warnings.append("pf_observable_mode is retired: the filter always "
                        "fits the weekly increment, and runs drop this line, "
                        "so it can be deleted")
    if pf_engine.engine_available():
        for line in priors:
            k = line.split("=", 1)[0].strip()
            if k.startswith("pf_") and not pf_engine.engine_accepts_pf_key(k):
                warnings.append(f"{k} is not a setting the installed engine "
                                "knows (check the spelling), so a run would "
                                "stop on it")
    if (times is not None and len(times) == 1
            and "pf_sampling_interval" not in keys
            and not pf_engine.sampling_interval_line()):
        warnings.append("one data row: this engine needs two or more "
                        "(it does not accept pf_sampling_interval)")
    if not pf_engine.perl_available() or not Path(BNG).is_file():
        facts["network"] = "not checked (no Perl or BNG2.pl here)"
    else:
        import tempfile
        if work:
            Path(work).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(work) if work else None) as tmp:
            try:
                net = contactmap.parse_net(
                    contactmap.network_from_bngl(bngl, Path(tmp)))
                facts["species"] = len(net["species"])
                facts["reactions"] = len(net["reactions"])
                facts["network"] = "generates"
            except (contactmap.ContactMapError, OSError,
                    subprocess.SubprocessError) as e:
                facts["network"] = "fails"
                problems.append(str(e).strip())
        # the model at its written values beside the data: a scale that
        # is off tenfold is the commonest reason a first fit collapses
        if facts["network"] == "generates" and cum in outputs and times:
            try:
                ex = expected_counts(files, times=times, work=work)
                observed = [r[1] for r in read_exp(str(files["data.exp"]))["rows"]]
                fact, warn = _scale_note(ex["expected"], observed)
                facts["at_start"] = fact
                if warn:
                    warnings.append(warn)
            except (SandboxError, ValueError, KeyError):
                pass                       # nothing to compare: no warning
    return {"ok": not problems, "problems": problems, "warnings": warnings,
            "facts": facts}


# ------------------------------------------- the model at its written values
# BNG2.pl's own ODE run of the model as written (no engine, no fit): what
# the counts would be if every parameter were the value model.bngl writes.
# Check compares it with data.exp, and "Simulate data" writes counts drawn
# from it, so a student can see whether a fit recovers values they know.

#: rows simulate_data writes when data.exp has no readable time column
SIMULATE_WEEKS = 20
#: the noise simulate_data draws when the model has no r__FREE
DISPERSION_PARAM = "r__FREE"


def expected_counts(files: dict, times: list | None = None,
                    work: Path | None = None) -> dict:
    """The weekly counts the model gives at its written values, read as
    the engine reads them: the increment of pf_cumulative_observable over
    each data row's week, the model starting at pf_start_time (-1 unless
    priors.conf sets it). times defaults to data.exp's time column.
    {"times", "expected", "column"}; SandboxError in words otherwise
    (BNG2.pl's own words when it cannot simulate)."""
    import tempfile
    from app.core import contactmap
    bngl = str(files.get("model.bngl", ""))
    _, keys = split_priors(str(files.get("priors.conf", "")))
    cum = keys.get("pf_cumulative_observable", "")
    if not cum:
        raise SandboxError("priors.conf names no pf_cumulative_observable, "
                           "so there is no count to simulate")
    if times is None:
        try:
            times = [r[0] for r in read_exp(str(files.get("data.exp", "")))["rows"]]
        except (SandboxError, ValueError):
            times = list(range(SIMULATE_WEEKS))
    t0 = _number(keys.get("pf_start_time", "-1"))
    times = [float(t) for t in times]
    if (t0 is None or not float(t0).is_integer()
            or any(not t.is_integer() for t in times)):
        raise SandboxError("simulating needs whole-number times (weeks) in "
                           "data.exp and pf_start_time")
    if not times or min(times) <= t0:
        raise SandboxError(f"every data row must come after the start time "
                           f"{t0:g}")
    t_end = int(max(times) - t0)
    if work:
        Path(work).mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=str(work) if work else None) as tmp:
            traj = contactmap.trajectory_from_bngl(bngl, Path(tmp), t_end)
    except (contactmap.ContactMapError, OSError,
            subprocess.SubprocessError) as e:
        raise SandboxError(str(e).strip()) from None
    col = traj.get(cum)
    if not col or len(col) < t_end + 1:
        raise SandboxError(f"the simulation printed no column {cum}: is it "
                           "an observable or a function of the model?")
    expected = [col[int(t - t0)] - col[int(t - t0) - 1] for t in times]
    return {"times": times, "expected": expected, "column": cum}


def synthetic_exp(files: dict, *, seed: int = 1, times: list | None = None,
                  work: Path | None = None) -> tuple:
    """(data.exp text, facts): counts drawn around expected_counts, with
    negative-binomial noise at the model's written r__FREE (Poisson when
    it has none), one row per time, under data.exp's own header line."""
    ex = expected_counts(files, times=times, work=work)
    r = _number(bngl_parameter_values(str(files.get("model.bngl", "")))
                .get(DISPERSION_PARAM))
    r = r if r and r > 0 else None
    rng = np.random.default_rng(int(seed))
    counts = []
    for mu in ex["expected"]:
        mu = max(float(mu), 0.0)
        if mu == 0:
            counts.append(0)
        elif r:
            counts.append(int(rng.negative_binomial(r, r / (r + mu))))
        else:
            counts.append(int(rng.poisson(mu)))
    header = DEFAULT_HEADER
    for line in str(files.get("data.exp", "")).splitlines():
        if line.strip():
            if line.lstrip().startswith("#"):
                header = line.rstrip()
            break
    text = header + "\n" + "\n".join(
        f"{_fmt(t)} {c}" for t, c in zip(ex["times"], counts)) + "\n"
    return text, {"rows": len(counts), "r": r, "seed": int(seed),
                  "column": ex["column"]}


def simulate_data(name: str, *, seed: int = 1) -> dict:
    """Rewrite a model's data.exp with counts simulated from the model at
    its written values (synthetic_exp), keeping its time rows; the data
    sidecar goes, since the rows are no longer the archive's."""
    files = read_model(name)
    text, facts = synthetic_exp(files, seed=seed, work=SANDBOX / "check")
    d = model_dir(name)
    (d / "data.exp").write_text(text, encoding="utf-8", newline="\n")
    (d / SOURCE_FILE).unlink(missing_ok=True)
    return facts


def _scale_note(expected: list, observed: list) -> tuple:
    """(fact, warning or '') comparing the model at its written values
    with the data: their ranges, and a warning when their totals differ
    tenfold or more (N, the starting state or the scale is off)."""
    obs = [float(v) for v in observed if float(v) >= 0]
    exp_ = [max(float(v), 0.0) for v in expected]
    if not obs or not exp_:
        return "", ""
    f = lambda v: f"{v:,.0f}" if abs(v) >= 10 else f"{v:.2g}"
    fact = (f"at its written values the model gives {f(min(exp_))} to "
            f"{f(max(exp_))} a week; data.exp holds {f(min(obs))} to "
            f"{f(max(obs))}")
    so, se = sum(obs), sum(exp_)
    if so <= 0 or se <= 0:
        return fact, ""
    ratio = se / so
    if ratio >= 10 or ratio <= 0.1:
        how = (f"{ratio:,.0f} times" if ratio >= 10
               else f"1/{1 / ratio:,.0f} of")
        return fact, (f"at the values written in model.bngl the model's "
                      f"counts total {how} the data's: check N, the "
                      "starting state and the reporting scale, or the fit "
                      "starts far from the data")
    return fact, ""


def _prior_start_warnings(bngl: str, priors: list) -> list:
    """A fitted parameter whose written value lies outside its range
    prior: harmless to the filter (it draws from the prior) but a sign
    the two files disagree."""
    vals = bngl_parameter_values(bngl)
    out = []
    for line in priors:
        kind, _, rest = (x.strip() for x in line.partition("="))
        toks = rest.split()
        if kind not in RANGE_PRIORS or len(toks) < 3:
            continue
        v, lo, hi = _number(vals.get(toks[0])), _number(toks[1]), _number(toks[2])
        if None in (v, lo, hi) or lo >= hi:
            continue
        if not lo <= v <= hi:
            out.append(f"{toks[0]} is written as {vals[toks[0]]} "
                       f"in model.bngl but its prior runs {toks[1]} to "
                       f"{toks[2]}: the fit only looks inside the prior")
    return out


def preflight() -> None:
    """The production preflight (app/core/engines/pf.py prepare), in the
    same words: Perl for BNG2.pl, the fork's filter, a current parser."""
    if not pf_engine.perl_available():
        raise SandboxError(pf_engine.perl_missing_message())
    if not pf_engine.engine_available():
        raise SandboxError(pf_engine.engine_missing_message())
    if not pf_engine.engine_current():
        raise SandboxError(pf_engine.engine_stale_message())


def unit_spacing(times: list) -> bool:
    """Whole-number times one unit apart at their closest (weekly rows,
    gaps allowed), or a single row: the data pf_sampling_interval = 1
    describes."""
    if len(times) < 2:
        return True
    if any(float(t) != int(t) for t in times):
        return False
    return min(b - a for a, b in zip(times, times[1:])) == 1


def engine_settings(priors_text: str, *, particles: int = DRY_RUN_PARTICLES,
                    jitter: float = 0.15, forecast_weeks: int = 4,
                    seed: int = 0, times: list | None = None) -> list:
    """The engine keys a run writes besides the paths and the priors, as
    [(key, value, source)], source one of 'run settings', 'priors.conf',
    'default' (the production convention) or 'engine' (what the installed
    engine accepts). prepare writes exactly these and the workbench shows
    them. A malformed priors.conf raises SandboxError."""
    _, keys = split_priors(priors_text)
    for k in RETIRED_KEYS:                    # named by check, never written
        keys.pop(k, None)
    rows = [("fit_type", "pf", "default")]

    def pick(key, default, src="default"):
        rows.append((key, keys.pop(key), "priors.conf") if key in keys
                    else (key, default, src))
    pick("objfunc", "neg_bin_dynamic")
    rows.append(("pf_particles", str(max(50, min(int(particles), 100_000))),
                 "run settings"))
    pick("pf_jitter", f"{float(jitter):g}", "run settings")
    # the production conventions, see app/core/engines/pf.py
    pick("pf_bounds", "reflect")
    pick("pf_start_time", "-1")
    pick("pf_forecast_intervals", str(max(0, min(int(forecast_weeks), 12))),
         "run settings")
    rows += [("population_size", "1", "default"),
             ("max_iterations", "1", "default")]
    pick("initialization", "rand")
    rows.append(("pf_seed", str(int(seed)), "run settings"))
    if "pf_cumulative_observable" in keys:
        rows.append(("pf_cumulative_observable",
                     keys.pop("pf_cumulative_observable"), "priors.conf"))
    if "pf_sampling_interval" in keys:
        rows.append(("pf_sampling_interval", keys.pop("pf_sampling_interval"),
                     "priors.conf"))
    else:
        # production writes it whenever the engine accepts it; here only
        # for weekly data too, so a model in other time units is unchanged
        si = pf_engine.sampling_interval_line().strip()
        if si and (times is None or unit_spacing(times)):
            k, v = (x.strip() for x in si.split("=", 1))
            rows.append((k, v, "engine"))
    rows += [(k, v, "priors.conf") for k, v in keys.items()]
    return rows


def _netgen(cell: Path) -> None:
    try:
        r = subprocess.run(["perl", BNG, "m.bngl"], capture_output=True,
                           text=True, cwd=str(cell), timeout=300)
    except FileNotFoundError:
        # perl vanished since the preflight, or which() disagreed
        raise SandboxError(pf_engine.perl_missing_message()) from None
    if not (cell / "m.net").is_file():
        raise SandboxError("BNG2.pl could not generate the network:\n"
                           + (r.stdout or "")[-600:] + (r.stderr or "")[-300:])


def prepare(name: str, *, particles: int = DRY_RUN_PARTICLES,
            jitter: float = 0.15, forecast_weeks: int = 4, seed: int = 0,
            runs_root: Path | None = None) -> Path:
    """A workroot with one prepared cell, ready for pf_engine.execute.

    The production preflight runs first. The network is generated here,
    by BNG2.pl, so a model that does not generate is refused before the
    engine is asked for anything, with BNG2.pl's own words. Run settings
    the engine would refuse late (a jitter outside 0 to 1, a negative
    seed) are refused here, before anything is written.
    """
    if not 0 < float(jitter) < 1:
        raise SandboxError(f"jitter {float(jitter):g} is not between 0 and 1 "
                           "(0.15 is the production setting)")
    if int(seed) < 0:
        raise SandboxError(f"seed {int(seed)} is negative: use 0 or more")
    preflight()
    files = read_model(name)
    sfx = simulate_suffix(files["model.bngl"])
    exp = read_exp(files["data.exp"])
    times = [row[0] for row in exp["rows"]]
    settings = engine_settings(files["priors.conf"], particles=particles,
                               jitter=jitter, forecast_weeks=forecast_weeks,
                               seed=seed, times=times)
    priors, _ = split_priors(files["priors.conf"])
    val = {k: v for k, v, _ in settings}
    particles = int(val["pf_particles"])
    forecast_weeks = int(val["pf_forecast_intervals"])
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
    _netgen(cell)
    c = pf_engine.conf_safe_path(cell)
    conf = [f"bng_command = {pf_engine.conf_safe_path(BNG)}",
            f"model = {c}/m.bngl : {c}/{sfx}.exp",
            f"output_dir = {c}/out"]
    conf += [f"{k} = {v}" for k, v, _ in settings]
    (cell / "pf.conf").write_text("\n".join(conf) + "\n" + "\n".join(priors)
                                  + "\n", encoding="utf-8", newline="\n")
    # the run's own copy of priors.conf (the engine never reads it): what
    # the run's diff and download show as the third file
    (cell / "priors.conf").write_text(files["priors.conf"].replace("\r\n", "\n"),
                                      encoding="utf-8", newline="\n")
    obs_col = exp["columns"][1]
    observed = [row[1] for row in exp["rows"]]
    shipped = shipped_state(name, files)
    info = shipped["info"]
    # a shipped start's cell names its jurisdiction, as production's does,
    # so collect() and the Oracle step key it by location
    location = (str(info.get("location")) if shipped["shipped"]
                and info.get("location") else name)
    cells = [{"key": f"{name}_r0", "dir": str(cell), "location": location,
              "replicate": 0, "seed": int(seed), "n_obs": len(observed),
              "particles": particles, "last_observed": float(observed[-1]),
              "weeks_dropped": 0, "last_week_offset": int(times[-1]),
              "sandbox": True}]
    (workroot / "cells.json").write_text(json.dumps(cells))
    meta = {"model": name,
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "particles": particles, "jitter": float(val["pf_jitter"]),
            "cumulative": val.get("pf_cumulative_observable", ""),
            "forecast_weeks": forecast_weeks,
            "seed": int(seed), "suffix": sfx, "obs_col": obs_col,
            "time": times, "observed": observed, "n_obs": len(observed),
            "digests": digests(files),
            "origin": str(info.get("origin", "")),
            "status": "prepared"}
    if shipped["shipped"]:
        meta["shipped"] = {k: info.get(k) for k in
                           ("location", "forecast_date", "season_start",
                            "seed", "dataset")}
        meta["shipped"]["intact"] = shipped["intact"]
        meta["shipped"]["changed"] = shipped["changed"]
    src = read_data_source(name)
    if src:
        meta["source"] = src
        if len(src.get("dates") or []) == len(times):
            meta["dates"] = src["dates"]         # the plot's calendar axis
    (workroot / "meta.json").write_text(json.dumps(meta))
    return workroot


def _write_meta(workroot: Path, meta: dict) -> None:
    tmp = Path(workroot) / "meta.json.tmp"
    tmp.write_text(json.dumps(meta))
    tmp.replace(Path(workroot) / "meta.json")


def run(workroot: Path, width: int = 1) -> dict:
    """Execute the prepared cell in the engine venv; the workroot's
    meta.json records the outcome either way: ok, failed, or stopped
    (stop() wrote the STOP flag execute polls)."""
    workroot = Path(workroot)
    meta = json.loads((workroot / "meta.json").read_text())
    meta["status"] = "running"
    _write_meta(workroot, meta)
    t0 = time.monotonic()
    try:
        status = pf_engine.execute(workroot, width=width)
        key = next(iter(status)) if status else None
        meta["status"] = "ok" if key and status[key] == "ok" else "failed"
        meta["engine_status"] = status
    except pf_engine.RunStopped:
        meta["status"] = "stopped"
    except Exception as e:                       # the reason reaches the page
        meta["status"] = "failed"
        meta["error"] = str(e)[:2000]
    meta["seconds"] = round(time.monotonic() - t0, 1)
    meta["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_meta(workroot, meta)
    return meta


def stop(workroot: Path) -> None:
    """Ask a live fit to stop: execute() polls <workroot>/STOP."""
    (Path(workroot) / "STOP").touch()


def mark(workroot: Path, status: str) -> None:
    """Record a status on a run that never reached the engine."""
    meta = json.loads((Path(workroot) / "meta.json").read_text())
    meta["status"] = status
    _write_meta(workroot, meta)


_RAW = object()


def shown_status(meta: dict, run_id: str, live=_RAW) -> str:
    """The status a page shows. A prepared or running run that is not the
    live fit (live: the server's running run id, or None) was cut off by
    an app restart and reads as interrupted. One rule for the page, the
    run list and the poll, so they never disagree."""
    st = str(meta.get("status", ""))
    if live is not _RAW and st in LIVE_STATUSES and run_id != live:
        return INTERRUPTED
    return st


def run_dir(run_id: str, runs_root: Path | None = None) -> Path:
    """The folder of an existing run, refusing anything that is not a run
    id or resolves outside the runs folder (a Windows 'C:x' too)."""
    root = Path(runs_root or RUNS)
    if not isinstance(run_id, str) or not RUN_ID_RE.match(run_id):
        raise SandboxError(f"{run_id!r} is not a sandbox run")
    d = root / run_id
    try:
        inside = d.resolve().parent == root.resolve()
    except OSError:
        inside = False
    if not inside or not (d / "meta.json").is_file():
        raise SandboxError(f"no sandbox run {run_id!r}")
    return d


def list_runs(runs_root: Path | None = None, *, model: str | None = None,
              live=_RAW) -> list:
    """Every run, newest first; one model's only with model=. With live=
    (the live run id or None) statuses read as shown_status says."""
    root = runs_root or RUNS
    out = []
    if not root.is_dir():
        return out
    for d in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        try:
            meta = json.loads((d / "meta.json").read_text())
        except Exception:
            continue
        if model is not None and meta.get("model") != model:
            continue
        meta["run_id"] = d.name
        meta["status"] = shown_status(meta, d.name, live)
        out.append(meta)
    return out


def results(workroot: Path, live=_RAW) -> dict:
    """What the engine wrote, read back: the outcome, a parameter table
    (5th, 50th and 95th percentiles of the posterior sample), the ESS
    record, and the trajectory summarised per week (10th, 50th, 90th
    percentiles over particles) with the observed counts beside it. With
    live=, the status reads as shown_status says."""
    workroot = Path(workroot)
    meta = json.loads((workroot / "meta.json").read_text())
    meta["status"] = shown_status(meta, workroot.name, live)
    out = {"meta": meta, "run_id": workroot.name, "params": [], "ess": [],
           "traj": None, "stderr": ""}
    cell = workroot / f"{meta['model']}_r0"
    runs = cell / "out" / "Results" / "PF" / "Runs"
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
    ef = cell / "out" / "Results" / "PF" / "ess_0.txt"
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
    out["health"] = fit_health(out)
    return out


#: fit_health's thresholds, as fractions of the particles: under COLLAPSED
#: the cloud is a handful of copies (the engine's own collapse warning is
#: ESS under 2%), under THIN it is thinning out
HEALTH_COLLAPSED = 0.02
HEALTH_THIN = 0.10
#: fewer of the observed rows inside the 10 to 90% band: the band misses
HEALTH_COVER = 0.5


def fit_health(res: dict) -> dict | None:
    """The run's outcome in plain words for the Results card, read from
    what the engine wrote: "level" (good, rough, collapsed), a "title", a
    "says" sentence, the week "at" it went wrong, whether the band "misses"
    most of the data, and "tries": what to do next, most useful first.
    None for a run that left no parameter sample and no ESS record."""
    meta = res.get("meta") or {}
    ess, params = res.get("ess") or [], res.get("params") or []
    if not ess and not params:
        return None
    n = int(meta.get("particles") or 0) or int(res.get("sample") or 0) or 1
    sample = int(res.get("sample") or 0)
    distinct = int(res.get("distinct") or 0)
    ess_min = min((e["ess"] for e in ess), default=None)
    thin_at = next((e["t"] for e in ess
                    if e["ess"] < HEALTH_THIN * n
                    or e["distinct"] < HEALTH_THIN * n), None)
    gone_at = next((e["t"] for e in ess
                    if e["ess"] < HEALTH_COLLAPSED * n
                    or e["distinct"] < HEALTH_COLLAPSED * n
                    or e.get("degenerate")), None)
    flat = bool(params) and all(p["p5"] == p["p95"] for p in params)
    few = bool(sample) and distinct <= max(2, HEALTH_COLLAPSED * sample)
    first_t = ess[0]["t"] if ess else None
    # the band against the data: observed rows inside the 10 to 90% band
    misses, inside, counted = False, 0, 0
    tr = res.get("traj") or {}
    obs = meta.get("observed") or []
    if tr.get("q10") and obs:
        for i, y in enumerate(obs[:len(tr["q10"])]):
            if y is None or float(y) < 0:
                continue
            counted += 1
            inside += tr["q10"][i] <= float(y) <= tr["q90"][i]
        misses = counted >= 3 and inside < HEALTH_COVER * counted
    fmt_t = lambda t: f"{t:g}"
    h = {"level": "good", "at": None, "misses": misses, "tries": [],
         "ess_min": ess_min, "particles": n, "inside": inside,
         "counted": counted}
    if flat or few or gone_at is not None:
        # the first sign: thinning comes before (or with) the collapse
        at = min((t for t in (thin_at, gone_at) if t is not None), default=None)
        h.update(level="collapsed", at=at, title="The fit collapsed",
                 says=("Nearly every particle ended as a copy of the same "
                       "one or few parameter sets"
                       + (f", from t = {fmt_t(at)} on" if at is not None else "")
                       + ", so the table shows one value where a range "
                       "should be and the band is not a real estimate."))
    elif thin_at is not None:
        h.update(level="rough", at=thin_at, title="The fit is rough",
                 says=(f"The particles thinned out at t = {fmt_t(thin_at)} "
                       f"(lowest ESS {ess_min:,.0f} of {n:,}), so the ranges "
                       "are likely too narrow."))
    else:
        h.update(title="The fit looks healthy",
                 says=("The particles stayed varied at every week"
                       + (f" (lowest ESS {ess_min:,.0f} of {n:,})"
                          if ess_min is not None else "") + "."))
    if misses:
        h["says"] += (f" Only {inside} of the {counted} data points sit "
                      "inside the 10 to 90% band.")
    tries = h["tries"]
    if n < FULL_FIT_PARTICLES and h["level"] != "good":
        tries.append(f"Run the full fit with {FULL_FIT_PARTICLES:,} "
                     f"particles: {n:,} cover a prior too thinly.")
    if h["level"] == "collapsed" and h["at"] is not None and h["at"] == first_t:
        tries.append("It went wrong at the first data row: Check compares "
                     "the model at its written values with the data. N, "
                     "the starting state and the reporting scale set the "
                     "first weeks' counts; the model starts one week "
                     "before the first row.")
    if h["level"] != "good" or misses:
        tries.append("Narrow a prior that is much wider than the values "
                     "you find plausible: particles drawn where the data "
                     "rule them out are wasted.")
    if misses:
        tries.append("A band that misses the data is the model, not the "
                     "filter: check the rates, the fixed values and which "
                     "output pf_cumulative_observable names.")
    if h["level"] != "good":
        tries.append("Raise Jitter to 0.2 or 0.3 so a thinning cloud "
                     "spreads out again.")
    return h


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


def _window(got: dict, start: str, end: str) -> dict:
    """{"dates", "values", "dropped"} of a {date: value} map within a
    range; dropped counts the range's Saturdays with no value."""
    import datetime as dt
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


#: The largest CSV the sandbox's upload accepts (the dataset store's own
#: limit is larger; a sandbox fit needs one series, not a hub).
UPLOAD_MAX_BYTES = 20 * 1024 * 1024


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
    import csv
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


def _fmt(v: float) -> str:
    v = float(v)
    return str(int(v)) if v.is_integer() else repr(v)


def _digest(text: str) -> str:
    import hashlib
    return hashlib.sha1(text.replace("\r\n", "\n").strip()
                        .encode("utf-8")).hexdigest()


def _first_saturday(day: str) -> str:
    import datetime as dt
    d = dt.date.fromisoformat(day)
    return (d + dt.timedelta(days=(5 - d.weekday()) % 7)).isoformat()


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
    import datetime as dt
    o = dt.date.fromisoformat(origin)
    out = []
    for d in dates:
        days = (dt.date.fromisoformat(d) - o).days
        if days < 0:
            raise SandboxError(f"week {d} is before t = 0 ({origin})")
        out.append(int(round(days / 7)))
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
        known = {l["name"] for l in locations()}
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


# --------------------------------------------------------- the diagram cache
# The contact map and network routes keep their parsed JSON beside the
# drawing, keyed by the model text and the BNG2.pl path, so reloading the
# workbench does not rerun BNG2.pl until the model (or BNG) changes. A
# failure is never cached: the next request tries again.

def _view_file(name: str, kind: str) -> Path:
    return SANDBOX / "contactmap" / check_name(name) / f"{kind}.json"


def _view_key(bngl: str) -> str:
    return _digest(str(bngl) + "\n" + str(BNG))


def cached_view(name: str, kind: str, bngl: str) -> dict | None:
    try:
        d = json.loads(_view_file(name, kind).read_text(encoding="utf-8"))
        return d["payload"] if d.get("key") == _view_key(bngl) else None
    except Exception:
        return None


def store_view(name: str, kind: str, bngl: str, payload: dict) -> None:
    try:
        f = _view_file(name, kind)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"key": _view_key(bngl), "payload": payload}),
                     encoding="utf-8")
    except OSError:
        pass


def eta_seconds(n_obs: int, particles: int) -> float:
    """The engine's own cost model (pf.cell_seconds), calibrated on the
    production cell: approximate for any other model."""
    return pf_engine.cell_seconds({"n_obs": int(n_obs),
                                   "particles": int(particles)})


# ------------------------------------------------ compare, export, clean up
# A run's three files are its own copies in the cell folder (m.bngl, the
# <suffix>.exp and priors.conf; runs made before priors.conf was copied
# fall back to pf.conf's prior lines). Downloads are built in memory and
# carry no absolute path: pf.conf's paths are rewritten relative to the
# cell, as the zip lays it out.

#: the raw trajectory rides in a run's zip only up to this size
TRAJ_ZIP_MAX = 2 * 1024 * 1024
#: settings a comparison lists when they differ
RUN_SETTINGS = ("particles", "jitter", "forecast_weeks", "seed", "cumulative",
                "suffix", "obs_col", "n_obs")


def _run_meta(run_id: str) -> tuple:
    d = run_dir(run_id)
    return d, json.loads((d / "meta.json").read_text())


def run_files(run_id: str) -> dict:
    """The three files as the run used them: {"model.bngl", "data.exp",
    "priors.conf"} (a missing one reads '')."""
    d, meta = _run_meta(run_id)
    cell = d / f"{meta['model']}_r0"

    def read(p: Path) -> str:
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    priors = read(cell / "priors.conf")
    if not priors:
        conf = read(cell / "pf.conf").splitlines()
        priors = "".join(l + "\n" for l in conf
                         if l.split("=", 1)[0].strip().endswith("_var"))
    return {"model.bngl": read(cell / "m.bngl"),
            "data.exp": read(cell / f"{meta.get('suffix', '')}.exp"),
            "priors.conf": priors}


def diff_runs(a: str, b: str, max_lines: int = 400) -> dict:
    """What changed from run a to run b: a unified diff of each of the
    three files (empty when identical) and the run settings that differ,
    as {"files": [{"name", "diff", "same"}], "settings": [{"key", "a",
    "b"}], "data_source": {"a", "b"} when the data came from elsewhere}."""
    import difflib
    fa, fb = run_files(a), run_files(b)
    _, ma = _run_meta(a)
    _, mb = _run_meta(b)
    files = []
    for f in REQUIRED:
        lines = list(difflib.unified_diff(
            fa[f].splitlines(), fb[f].splitlines(), fromfile=f"{a}/{f}",
            tofile=f"{b}/{f}", n=2, lineterm=""))
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"... {len(lines) - max_lines} more lines"]
        files.append({"name": f, "diff": "\n".join(lines),
                      "same": fa[f] == fb[f]})
    settings = [{"key": k, "a": ma.get(k), "b": mb.get(k)} for k in RUN_SETTINGS
                if ma.get(k) != mb.get(k)]
    out = {"a": a, "b": b, "files": files, "settings": settings}

    def src(m):
        s = m.get("source") or {}
        return {k: s.get(k) for k in ("location", "asof", "start", "end")} if s else {}
    if src(ma) != src(mb):
        out["data_source"] = {"a": src(ma), "b": src(mb)}
    return out


def _zip(entries: list) -> bytes:
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, data in entries:
            info = zipfile.ZipInfo(arc, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data if isinstance(data, bytes)
                       else str(data).encode("utf-8"))
    return buf.getvalue()


def model_zip(name: str) -> bytes:
    """The model folder as a zip: its three files and the model.json and
    data.source.json sidecars, under <name>/."""
    d = model_dir(name)
    return _zip([(f"{name}/{f}", (d / f).read_bytes())
                 for f in REQUIRED + (MODEL_FILE, SOURCE_FILE)
                 if (d / f).is_file()])


def _relative_conf(text: str, cell: Path) -> str:
    """pf.conf with the cell's and BNG2.pl's absolute paths removed."""
    out = []
    for line in text.splitlines():
        if line.split("=", 1)[0].strip() == "bng_command":
            line = "bng_command = BNG2.pl"
        else:
            for p in sorted({pf_engine.conf_safe_path(cell), str(cell)},
                            key=len, reverse=True):
                line = line.replace(p + "/", "").replace(p, ".")
        out.append(line)
    return "\n".join(out) + "\n"


def summary_rows(res: dict) -> list:
    """One row per trajectory column: [column, t, date, q10, q50, q90,
    observed]; forecast columns step past the last row by the closest
    spacing of the observed times (as the page plots them)."""
    import datetime as dt
    meta, traj = res["meta"], res.get("traj") or {}
    times = list(meta.get("time") or [])
    obs = list(meta.get("observed") or [])
    dates = list(meta.get("dates") or [])
    ncol = int(traj.get("columns") or 0)
    gaps = [b - a for a, b in zip(times, times[1:]) if b > a]
    step = min(gaps) if gaps else 1
    rows = []
    for i in range(ncol):
        t = times[i] if i < len(times) else (
            (times[-1] if times else 0) + step * (i - len(times) + 1))
        day = ""
        if dates and len(dates) == len(times) and times:
            day = (dt.date.fromisoformat(dates[0])
                   + dt.timedelta(days=round(7 * (t - times[0])))).isoformat()
        rows.append([i, _fmt(t), day] + [f"{float(traj[q][i]):.6g}"
                                         for q in ("q10", "q50", "q90")]
                    + [_fmt(obs[i]) if i < len(obs) else ""])
    return rows


def run_zip(run_id: str) -> bytes:
    """A run as a zip under <run_id>/: meta.json, pf.conf (paths made
    relative), the three files, the engine's parameter sample and ESS
    record, summary.csv (the 10/50/90% trajectory per week beside the
    observed count), the Oracle step's summary when one was made, and the
    raw trajectory only when it is small (TRAJ_ZIP_MAX)."""
    import csv
    import io
    d, meta = _run_meta(run_id)
    cell = d / f"{meta['model']}_r0"
    files = run_files(run_id)
    entries = [(f"{run_id}/meta.json", (d / "meta.json").read_bytes())]
    if (cell / "pf.conf").is_file():
        entries.append((f"{run_id}/pf.conf", _relative_conf(
            (cell / "pf.conf").read_text(encoding="utf-8", errors="replace"),
            cell)))
    entries += [(f"{run_id}/m.bngl", files["model.bngl"]),
                (f"{run_id}/{meta.get('suffix') or 'data'}.exp", files["data.exp"]),
                (f"{run_id}/priors.conf", files["priors.conf"])]
    pf_out = cell / "out" / "Results" / "PF"
    runs = pf_out / "Runs"
    for p in sorted(runs.glob("params_*.txt")) if runs.is_dir() else []:
        entries.append((f"{run_id}/{p.name}", p.read_bytes()))
    if (pf_out / "ess_0.txt").is_file():
        entries.append((f"{run_id}/ess_0.txt", (pf_out / "ess_0.txt").read_bytes()))
    res = results(d)
    if res.get("traj"):
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["column", "t", "date", "q10", "q50", "q90",
                    meta.get("obs_col") or "observed"])
        w.writerows(summary_rows(res))
        entries.append((f"{run_id}/summary.csv", buf.getvalue()))
    for p in sorted(runs.glob("*traj_noise*")) if runs.is_dir() else []:
        if p.stat().st_size <= TRAJ_ZIP_MAX:
            entries.append((f"{run_id}/{p.name}", p.read_bytes()))
    if (d / ORACLE_FILE).is_file():
        entries.append((f"{run_id}/{ORACLE_FILE}", (d / ORACLE_FILE).read_bytes()))
    return _zip(entries)


# ------------------------------------------- the Oracle step (sandbox only)
# On a finished run of an unedited Oracle SIHRS start (hub origin, four
# forecast weeks), the production Oracle step (app/core/oracle.apply_week
# on pf_engine.collect's samples) is applied inside the run folder and its
# quantiles shown beside the plain filter's. It writes only under the run
# folder: never the ledger, the site, the archive or model-output.

ORACLE_FILE = "oracle_step.json"
ORACLE_DIR = "oracle"
#: the quantile levels the page shows (of the 23 FluSight levels)
ORACLE_LEVELS = (0.025, 0.25, 0.5, 0.75, 0.975)


def oracle_default_w() -> float:
    """The production blend weight (flubnf.oracle.W_PRODUCTION)."""
    from flubnf import oracle as OR
    return float(OR.W_PRODUCTION)


def oracle_gate(run_id: str) -> dict:
    """Whether the Oracle step may run on this run: {"ok", "reason"}.
    It may when the run finished, has four forecast weeks, is of a model
    started from the hub's Oracle SIHRS filter, and neither the run's
    files nor the model's differ from the creation digests."""
    try:
        _, meta = _run_meta(run_id)
    except SandboxError as e:
        return {"ok": False, "reason": str(e)}
    name = str(meta.get("model", ""))
    info = read_info(name) if NAME_RE.match(name) else {}
    origin = meta.get("origin") or info.get("origin")
    if SHIPPED_DATASET in (origin, info.get("origin")):
        return {"ok": False, "reason": "The Oracle step reads the hub's vintage "
                "and donor bank; this model starts from a dataset."}
    if origin != SHIPPED or info.get("origin") != SHIPPED:
        return {"ok": False, "reason": "Only runs of a model started from the "
                "Oracle SIHRS filter can take the Oracle step."}
    if meta.get("status") != "ok":
        return {"ok": False, "reason": "The run has not finished cleanly."}
    if int(meta.get("forecast_weeks", 0) or 0) != 4:
        return {"ok": False, "reason": "The Oracle step needs a run with 4 "
                "forecast weeks, as production makes."}
    dig = info.get("digests") or {}
    ran = meta.get("digests") or {}
    edited = [f for f in REQUIRED if ran.get(f) != dig.get(f)]
    if edited:
        return {"ok": False, "reason": "This run's " + ", ".join(edited)
                + (" differs" if len(edited) == 1 else " differ")
                + " from the Oracle SIHRS start as created."}
    st = shipped_state(name)
    if not st["intact"]:
        return {"ok": False, "reason": "The model was edited after it was "
                "created (" + ", ".join(st["changed"]) + "), so it is no "
                "longer the Oracle SIHRS start."}
    if not (info.get("location") and info.get("forecast_date")):
        return {"ok": False, "reason": "model.json does not record the "
                "location and forecast date."}
    return {"ok": True, "reason": ""}


def _levels(xs) -> list | None:
    v = np.asarray(xs, float)
    v = v[np.isfinite(v)]
    if not v.size:
        return None
    return [float(q) for q in np.quantile(v, ORACLE_LEVELS)]


def oracle_step(run_id: str, w: float | None = None) -> dict:
    """Apply the production Oracle step to one run's forecast samples;
    the summary is written to <run>/oracle_step.json (apply_week's own
    oracle.json and donor bank go to <run>/oracle/). Refused in words
    when oracle_gate refuses or w is outside 0..1."""
    from app.core import horizons as hz
    from app.core import oracle as oracle_mod
    gate = oracle_gate(run_id)
    if not gate["ok"]:
        raise SandboxError(gate["reason"])
    w = oracle_default_w() if w is None else float(w)
    if not (0.0 <= w <= 1.0):
        raise SandboxError(f"the blend weight w must be between 0 and 1, "
                           f"not {w:g}")
    d, meta = _run_meta(run_id)
    info = read_info(meta["model"])
    loc, fd = str(info["location"]), str(info["forecast_date"])
    samples = pf_engine.collect(d)
    if loc not in samples:
        raise SandboxError(f"the fit left no forecast samples for {loc}")
    samples = {loc: samples[loc]}
    member, prov = oracle_mod.apply_week(samples, fd, d / ORACLE_DIR, w=w)
    table = {r["canonical"]: r["target_end_date"]
             for r in prov["quantiles"]["horizons"]["table"]}
    ent = prov["locations"].get(loc, {})
    rows = [{"horizon": h, "target_end_date": table.get(h, ""),
             "filter": _levels(samples[loc][h]),
             "oracle": _levels(member[loc][h])} for h in hz.HORIZONS]
    out = {"run_id": run_id, "location": loc, "forecast_date": fd,
           "w": w, "w_production": oracle_default_w(),
           "levels": list(ORACLE_LEVELS), "rows": rows,
           "state": ent.get("state", ""), "active": ent.get("active"),
           "reason": ent.get("reason", ""), "bank": prov["bank"]["label"],
           "reference_date": prov["quantiles"]["horizons"]["reference_date"],
           "label": "sandbox, not a submission", "utc": _stamp()}
    tmp = d / (ORACLE_FILE + ".tmp")
    tmp.write_text(json.dumps(out, indent=1))
    tmp.replace(d / ORACLE_FILE)
    return out


def read_oracle(run_id: str) -> dict | None:
    """The run's Oracle step summary, or None."""
    try:
        return json.loads((run_dir(run_id) / ORACLE_FILE).read_text())
    except Exception:
        return None
