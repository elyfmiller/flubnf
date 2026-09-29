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
under any name; model.json records where each model came from.

This module is the facade: the folders and settings the console and the
tests patch (SANDBOX, MODELS, RUNS, BNG, TRAJ_ZIP_MAX, the hub lookups
locations and vintages), the model folders, the shipped Oracle SIHRS
start and the run entry points (prepare, run, stop). The rest is split by
topic; every name still imports from app.core.sandbox (see _MOVED at the
end: the topic module loads on first use, so the console's startup
imports are unchanged):

  sandbox_bngl.py     the three files as text: parsing, priors, the
                      engine settings a run writes, the skeleton
  sandbox_check.py    check() without the engine; the model at its
                      written values (expected_counts, synthetic_exp)
  sandbox_results.py  a run read back: results, fit_health, summary_rows
  sandbox_data.py     data.exp from the hub archive, a stored dataset or
                      an upload; the data.source.json sidecar
  sandbox_export.py   diff_runs, model_zip, run_zip; the Oracle step

Sections: paths and settings; refusals and small helpers; model folders;
the shipped start; runs (prepare, run, stop, run_dir, list_runs); the hub
lookups; the diagram cache; the moved names.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

# numpy loads with the console as it did before the split (the topic
# modules use it; app/tests/golden/ui_routes.json snapshots the imports)
import numpy as np  # noqa: F401

from flubnf.settings import BNG
from app.core.engines.pf import REPO
from app.core.engines import pf as pf_engine

SANDBOX = REPO / "sandbox"
MODELS = SANDBOX / "models"
RUNS = SANDBOX / "runs"
EXAMPLES = REPO / "flubnf" / "sandbox_examples"
REQUIRED = ("model.bngl", "data.exp", "priors.conf")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
#: A sidecar the engine never reads: where the model came from ("origin")
#: and, for a seasonal model, its "season_start" (week_origin).
MODEL_FILE = "model.json"
#: The other sidecar: where data.exp's rows came from (sandbox_data.py).
SOURCE_FILE = "data.source.json"
#: data.exp's header when the model has none to keep
DEFAULT_HEADER = "# time H_weekly"
DRY_RUN_PARTICLES = 200
FULL_FIT_PARTICLES = 10_000
#: A run's status while its fit may still be live; with no live fit behind
#: it (an app restart) it reads as INTERRUPTED, as the Storage panel does.
LIVE_STATUSES = ("prepared", "running")
INTERRUPTED = "interrupted"
#: run folder names: prepare's <UTC stamp>_<model>[_<n>]
RUN_ID_RE = re.compile(r"^\d{8}-\d{6}_[A-Za-z0-9][A-Za-z0-9_-]{0,70}$")
#: the raw trajectory rides in a run's zip only up to this size (run_zip)
TRAJ_ZIP_MAX = 2 * 1024 * 1024
#: The largest CSV the sandbox's upload accepts (the dataset store's own
#: limit is larger; a sandbox fit needs one series, not a hub).
UPLOAD_MAX_BYTES = 20 * 1024 * 1024
#: model.json origins of a model started from the Oracle SIHRS filter
#: (from_shipped): the hub's vintage, or a stored dataset's group
SHIPPED = "shipped:sihrs"
SHIPPED_DATASET = "shipped:sihrs-dataset"
SHIPPED_ORIGINS = (SHIPPED, SHIPPED_DATASET)
SEED_RULE = "runs.derive_seed(location, forecast_date, 0), as the console's replicate 0"


# ------------------------------------------- refusals and small helpers


class SandboxError(ValueError):
    """A model or a request the sandbox refuses, with the reason in words."""


def check_name(name: str) -> str:
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise SandboxError(
            f"{name!r} is not a model name: letters, digits, _ and -, up "
            "to 64 characters, starting with a letter or digit")
    return name


def _stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _fmt(v: float) -> str:
    v = float(v)
    return str(int(v)) if v.is_integer() else repr(v)


def _digest(text: str) -> str:
    return hashlib.sha1(text.replace("\r\n", "\n").strip()
                        .encode("utf-8")).hexdigest()


def digests(files: dict) -> dict:
    """The three files' digests (newlines and outer whitespace ignored)."""
    return {f: _digest(str(files.get(f, ""))) for f in REQUIRED}


def _iso_date(s: str, what: str):
    try:
        return dt.date.fromisoformat(str(s).strip())
    except (TypeError, ValueError):
        raise SandboxError(f"{what} must be a date written YYYY-MM-DD, "
                           f"not {s!r}") from None


def _first_saturday(day: str) -> str:
    d = dt.date.fromisoformat(day)
    return (d + dt.timedelta(days=(5 - d.weekday()) % 7)).isoformat()


# ---------------------------------------------------------- model folders


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
                    "modified": mtime})
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
        return json.loads((RUNS / str(live) / "meta.json")
                          .read_text(encoding="utf-8"))["model"]
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
        model = json.loads((d / "meta.json").read_text(encoding="utf-8")
                           ).get("model", "")
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


def new_model(name: str) -> Path:
    """Write the skeleton as a new sandbox model. An existing model of
    that name is left alone."""
    from app.core.sandbox_bngl import skeleton
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


def set_population(name: str, population: int) -> None:
    """Rewrite the parameters-block line named N to a population. Refused
    for a model without such a line, and for an SIHRS-shaped model, whose
    i0 and ascertainment are derived from N and the data together: start
    that from the Oracle SIHRS filter instead."""
    from app.core.sandbox_bngl import sihrs_shaped
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
            # N itself, not N_y or No: the name ends at a space or '='
            m = re.match(r"^(\s*(?:\d+\s+)?N)(?=[\s=])(\s*=?\s*)(\S+)(.*)$",
                         line, flags=re.S)
            if m:
                line = f"{m.group(1)}{m.group(2)}{pop}{m.group(4)}"
                done = 1
        out.append(line)
    if not done:
        raise SandboxError("the parameters block has no line named N to set")
    (d / "model.bngl").write_text("".join(out), encoding="utf-8", newline="\n")


def simulate_data(name: str, *, seed: int = 1) -> dict:
    """Rewrite a model's data.exp with counts simulated from the model at
    its written values (synthetic_exp), keeping its time rows; the data
    sidecar goes, since the rows are no longer the archive's."""
    from app.core.sandbox_check import synthetic_exp
    files = read_model(name)
    text, facts = synthetic_exp(files, seed=seed, work=SANDBOX / "check")
    d = model_dir(name)
    (d / "data.exp").write_text(text, encoding="utf-8", newline="\n")
    (d / SOURCE_FILE).unlink(missing_ok=True)
    return facts



# ------------------------------------------------------ the shipped start
# The Oracle SIHRS filter as the console's particle filter materializes it
# for one jurisdiction and forecast date (app/core/engines/pf.py prepare):
# the same resolve_state, template, parameter defaults, priors, suffix and
# seed rule, composed here without the engine. model.json records where it
# came from and the creation digests of the three files, so an edited or
# copied model never passes for the shipped one.


def from_shipped(name: str, location: str, forecast_date: str, *,
                 season_start: str = "", dataset: str | None = None) -> Path:
    """A new model: the production Oracle SIHRS filter cell for one
    jurisdiction as of forecast_date (the hub vintage of that date), or
    for one group of a stored dataset that has a population. N, rhomult
    and i0 are resolved together from the data (sihrs_fit.resolve_state);
    data.exp keeps the calendar week offsets from season_start. Refused in
    words, leaving nothing behind, when the vintage, location or data are
    missing."""
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
        cell_bngl = m.read_text(encoding="utf-8").replace("begin parameters\n",
                                          pf_engine.DEFAULTS_BLOCK, 1)
        exp = write_exp(s, Path(tmp) / "data.exp").read_text(encoding="utf-8")
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


# ------------------------------------------------------------------ runs
# prepare writes a workroot with one cell; run executes it on the engine
# (the console's runner and venv); the routes call both.


def preflight() -> None:
    """The production preflight (app/core/engines/pf.py prepare), in the
    same words: Perl for BNG2.pl, the fork's filter, a current parser."""
    if not pf_engine.perl_available():
        raise SandboxError(pf_engine.perl_missing_message())
    if not pf_engine.engine_available():
        raise SandboxError(pf_engine.engine_missing_message())
    if not pf_engine.engine_current():
        raise SandboxError(pf_engine.engine_stale_message())


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
    from app.core.sandbox_bngl import (engine_settings, read_exp, simulate_suffix,
                                       split_priors)
    from app.core.sandbox_data import read_data_source
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
    # a priors.conf line overrides the form's jitter and forecast weeks:
    # the same refusals, in words and before anything is written
    try:
        eff_jitter = float(val["pf_jitter"])
    except ValueError:
        raise SandboxError(f"priors.conf sets pf_jitter = {val['pf_jitter']}, "
                           "which is not a number") from None
    if not 0 < eff_jitter < 1:
        raise SandboxError(f"priors.conf sets pf_jitter = {val['pf_jitter']}, "
                           "which is not between 0 and 1 (0.15 is the "
                           "production setting)")
    try:
        forecast_weeks = int(val["pf_forecast_intervals"])
    except ValueError:
        raise SandboxError("priors.conf sets pf_forecast_intervals = "
                           f"{val['pf_forecast_intervals']}, which is not a "
                           "whole number of weeks") from None
    if forecast_weeks < 0:
        raise SandboxError(f"priors.conf sets pf_forecast_intervals = "
                           f"{forecast_weeks}, which is negative")
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
    (workroot / "cells.json").write_text(json.dumps(cells), encoding="utf-8")
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
    (workroot / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return workroot


def _write_meta(workroot: Path, meta: dict) -> None:
    tmp = Path(workroot) / "meta.json.tmp"
    tmp.write_text(json.dumps(meta), encoding="utf-8")
    tmp.replace(Path(workroot) / "meta.json")


def run(workroot: Path, width: int = 1) -> dict:
    """Execute the prepared cell in the engine venv; the workroot's
    meta.json records the outcome either way: ok, failed, or stopped
    (stop() wrote the STOP flag execute polls)."""
    workroot = Path(workroot)
    meta = json.loads((workroot / "meta.json").read_text(encoding="utf-8"))
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
    meta = json.loads((Path(workroot) / "meta.json").read_text(encoding="utf-8"))
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
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        if model is not None and meta.get("model") != model:
            continue
        meta["run_id"] = d.name
        meta["status"] = shown_status(meta, d.name, live)
        out.append(meta)
    return out


# ------------------------------------------------------- the hub lookups
# Imported inside the functions so this module imports without a hub.


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



# --------------------------------------------------------- the diagram cache
# The contact map and network routes keep their parsed JSON beside the
# drawing, keyed by the model text and the BNG2.pl path, so reloading the
# workbench does not rerun BNG2.pl until the model (or BNG) changes. A
# failure is never cached: the next request tries again.

def _view_file(name: str, kind: str) -> Path:
    return SANDBOX / "contactmap" / check_name(name) / f"{kind}.json"


#: bumped when the views' reading of a model changes (2: rule_flow reads
#: cBNGL compartment prefixes), so a drawing cached before is redrawn
VIEW_VERSION = 2


def _view_key(bngl: str) -> str:
    return _digest(str(bngl) + "\n" + str(BNG) + f"\nviews {VIEW_VERSION}")


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


# ---------------------------------------------------------- the moved names
# Each name still imports from here; its topic module loads on first use
# (never at import, so the console's startup imports are unchanged) and
# the name is then bound here like any other.

_MOVED = {
    "sandbox_bngl": (
        "ENGINE_KEYS", "RESERVED_KEYS", "RETIRED_KEYS", "SKELETON_BNGL",
        "SKELETON_PRIORS", "SKELETON_WEEKS", "skeleton", "simulate_suffix",
        "read_exp", "split_priors", "_strip_comments", "_block",
        "bngl_parameters", "bngl_parameter_values", "_number", "bngl_outputs",
        "RANGE_PRIORS", "SPREAD_PRIORS", "_check_prior",
        "_prior_start_warnings", "sihrs_shaped", "unit_spacing",
        "engine_settings"),
    "sandbox_check": (
        "check", "SIMULATE_WEEKS", "DISPERSION_PARAM", "expected_counts",
        "synthetic_exp", "_scale_note"),
    "sandbox_results": (
        "results", "HEALTH_COLLAPSED", "HEALTH_THIN", "HEALTH_COVER",
        "fit_health", "summary_rows"),
    "sandbox_data": (
        "DEFAULT_WEEKS", "default_range", "_check_range", "_window",
        "series_for", "dataset_choices", "UploadRefused", "display_name",
        "ingest_upload", "dataset_series", "week_origin", "calendar_offsets",
        "fill_data", "hub_population", "read_data_source"),
    "sandbox_export": (
        "RUN_SETTINGS", "_run_meta", "run_files", "diff_runs", "_zip",
        "model_zip", "_relative_conf", "run_zip", "ORACLE_FILE", "ORACLE_DIR",
        "ORACLE_LEVELS", "oracle_default_w", "oracle_gate", "_levels",
        "oracle_step", "read_oracle"),
}
_HOME = {name: mod for mod, names in _MOVED.items() for name in names}


def __getattr__(name: str):
    mod = _HOME.get(name)
    if mod is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib
    value = getattr(importlib.import_module(f"app.core.{mod}"), name)
    globals()[name] = value
    return value


def __dir__() -> list:
    return sorted(set(globals()) | set(_HOME))
