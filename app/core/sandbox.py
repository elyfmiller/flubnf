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
               "pf_binom_neff_cap", "initialization", "pf_bounds",
               "pf_start_time", "pf_sampling_interval")
#: Conf keys only the run settings and the workroot decide; a priors.conf
#: line naming one would duplicate a key, so it is refused.
RESERVED_KEYS = ("fit_type", "model", "output_dir", "bng_command",
                 "pf_particles", "pf_seed", "population_size",
                 "max_iterations")
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
                    "origin": origin_label(read_info(d.name).get("origin", "")),
                    "modified": max((int((d / f).stat().st_mtime)
                                     for f in present), default=0)})
    return out


def origin_label(origin: str) -> str:
    """model.json's origin in words for the gallery."""
    kind, _, what = str(origin or "").partition(":")
    return {"skeleton": "skeleton", "example": f"example {what}",
            "copy": f"copy of {what}"}.get(kind, "")


def list_examples() -> list:
    if not EXAMPLES.is_dir():
        return []
    return sorted(p.name for p in EXAMPLES.iterdir()
                  if p.is_dir() and all((p / f).is_file() for f in REQUIRED))


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
    _new_folder(name)
    d = save_model(name, skeleton(name))
    _write_info(name, {"origin": "skeleton", "created_utc": _stamp()})
    return d


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
            if k in ENGINE_KEYS:
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
             "reactions": None, "network": "not checked"}
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
    cum = keys.get("pf_cumulative_observable", "")
    facts["cumulative"] = cum
    if not cum:
        warnings.append("no pf_cumulative_observable line: the filter reads "
                        "the observation column itself, not a weekly "
                        "increment")
    elif cum not in outputs:
        problems.append(f"pf_cumulative_observable names {cum}, which is "
                        "neither an observable nor a function of the model")
    if pf_engine.engine_available():
        for line in priors:
            k = line.split("=", 1)[0].strip()
            if k.startswith("pf_") and not pf_engine.engine_accepts_pf_key(k):
                warnings.append(f"the installed engine does not accept {k}")
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
    return {"ok": not problems, "problems": problems, "warnings": warnings,
            "facts": facts}


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
    keys.pop("pf_observable_mode", None)      # a retired key: ignored
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
    engine is asked for anything, with BNG2.pl's own words.
    """
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
    obs_col = exp["columns"][1]
    observed = [row[1] for row in exp["rows"]]
    cells = [{"key": f"{name}_r0", "dir": str(cell), "location": name,
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
            "digests": {f: _digest(files[f]) for f in REQUIRED},
            "status": "prepared"}
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
              asof: str | None = None) -> dict:
    """Rewrite a model's data.exp from the archive: the file's own header
    line if it has one (else '# time H_weekly'), then one 't value' row
    per reported week, t the whole weeks since week_origin, so a missing
    week is a gap in t. Writes the sidecar data.source.json beside it
    (with the origin and each row's date) and returns its contents.
    Refuses an unknown location, a range with no reported week, and
    start after end."""
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
            "asof": str(asof) if asof else "settled",
            "rows": len(s["values"]), "dropped": int(s["dropped"]),
            "origin": origin, "dates": list(s["dates"]),
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
