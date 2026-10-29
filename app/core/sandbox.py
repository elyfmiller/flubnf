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
lookups; the diagram cache; the time a fit takes (the estimate, scaled
by this computer's last finished fit, and a live fit's words); the moved
names.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

# numpy loads with the console as it did before the split (the topic
# modules use it; app/tests/golden/ui_routes.json snapshots the imports)
import numpy as np  # noqa: F401

from flubnf.settings import BNG, bng_env
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
            # the copy changed now: the gallery's "changed" is its creation
            # time, not the original's last edit (copy2 keeps that mtime)
            (d / f).touch()
    info = {k: v for k, v in read_info(src).items()
            if k in ("season_start",)}
    _write_info(dst, {**info, "origin": f"copy:{src}", "created_utc": _stamp()})
    return d


def _live_model(live) -> str:
    """The model of the live run id, or ''."""
    return str(run_meta(live).get("model") or "")


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
    text = with_population(bngl, pop)
    if text is None:
        raise SandboxError(NO_N_LINE)
    (d / "model.bngl").write_text(text, encoding="utf-8", newline="\n")


#: set_population's refusal for a model without an N line
NO_N_LINE = "the parameters block has no line named N to set"


def with_population(bngl: str, pop: int) -> str | None:
    """The model text with its parameters-block line named N set to pop,
    or None when it has no such line (fill_data asks before writing)."""
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
    return "".join(out) if done else None


def _sentence_end(text: str) -> int | None:
    """The index of the first sentence's closing mark: a '.', '!' or '?'
    followed by a space and a capital, never inside parentheses or a
    quoted path, and never an initial ('C:\\Users\\J. Smith'), so a path
    in the message is not cut."""
    depth, quoted = 0, False
    for i, ch in enumerate(text):
        if ch == "(" and not quoted:
            depth += 1
        elif ch == ")" and not quoted:
            depth = max(0, depth - 1)
        elif ch == "'":
            # a quote mark, not an apostrophe inside a word (engine's)
            inner = (0 < i < len(text) - 1 and text[i - 1].isalnum()
                     and text[i + 1].isalnum())
            if not inner:
                quoted = not quoted
        elif ch in ".!?" and not depth and not quoted:
            if not re.match(r"\s+[A-Z(]", text[i + 1:]):
                continue
            if i >= 1 and text[i - 1].isupper() and (
                    i == 1 or text[i - 2] in " \\/"):
                continue                           # an initial
            return i
    return None


def split_reason(text: str, cap: int = 200) -> tuple:
    """(notice, tip) for a refusal shown as a one-line notice with its
    "?": the first line, the rest the tip. A first line that is one long
    paragraph (the engine and Perl refusals, whose remedy comes last)
    gives its first sentence as the notice and the rest to the tip, so
    the remedy is never cut off."""
    first, _, rest = str(text).strip().partition("\n")
    first, rest = first.strip(), rest.strip()
    if len(first) > cap:
        end = _sentence_end(first)
        if end is not None and end < 2 * cap:
            head, more = first[:end + 1], first[end + 1:]
        else:
            cut = first.rfind(" ", 0, cap)
            cut = cut if cut > 0 else cap
            head, more = first[:cut] + " ...", first[cut:]
        first, rest = head, (more.strip() + ("\n" + rest if rest else ""))
    return first, rest.strip()[:1500]


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
    # the template fits a single season: more than a year of data would
    # hand it two (production starts on August 1 of the forecast's season)
    if (dt.date.fromisoformat(fd) - dt.date.fromisoformat(ss)).days > 366:
        raise SandboxError(f"the season start {ss} is more than a year "
                           f"before the forecast date {fd}; the Oracle "
                           f"SIHRS fits one season (production starts "
                           f"{default_season_start(fd)})")
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


def _engine_retry(_platform: str | None = None) -> str:
    """How to finish an engine install that stopped part way, as a
    sentence: the launcher retries on every open, and on Windows the
    FluBNF.bat window says why it stopped."""
    from app.core import engine_build as _eb
    plat = _platform or sys.platform
    if plat == "win32":
        return ("To finish it, open FluBNF.bat again: it tries again, and "
                "if it stops again, the lines above 'Engine setup did not "
                "finish' in that window give the cause.")
    return (f"To finish it, {_eb.setup_step(plat)}: it tries again, and "
            "says what failed if it stops again.")


def engine_python_missing_message(_platform: str | None = None) -> str:
    """The engine is unpacked and its Python is not where FluBNF looks:
    every fit would fail late on the missing interpreter. The install
    stopped before the Python environment was made, so the remedy is the
    retry, not the engine file again. Asked only with the engine unpacked
    (machine_problems): without it, installing the engine file is what
    makes this Python, and the engine's own message says how."""
    return (f"The engine's Python is missing ({pf_engine.PY310} does not "
            "exist), so no fit can start. The engine is unpacked at "
            f"{pf_engine.PYBNF_PF}, but its Python environment was never "
            f"made. {_engine_retry(_platform)} Or point FLUBNF_PY_ENGINE at "
            "the engine's Python.")


def engine_import_message(said: str, _platform: str | None = None,
                          _vc_missing: bool | None = None) -> str:
    """The engine's Python is there and cannot load the engine (doctor's
    ENGINE_PROBE exited nonzero): a pip install that stopped part way, or
    on Windows a missing Visual C++ runtime, which bngsim and
    libroadrunner load (msvcp140.dll). `said` is the probe's last stderr
    line. `_platform` and `_vc_missing` are injectable for tests."""
    plat = _platform or sys.platform
    head = (f"The engine's Python cannot load the engine ({said}), so no fit "
            "can start")
    if plat == "win32" and (_vc_missing if _vc_missing is not None
                            else _vc_runtime_missing()):
        return (f"{head}: this computer lacks the Microsoft Visual C++ "
                "runtime (msvcp140.dll is not in Windows\\System32), which "
                "the engine's simulator needs. Install the Visual C++ "
                "Redistributable for x64 from "
                "https://aka.ms/vs/17/release/vc_redist.x64.exe, then open "
                "FluBNF.bat again.")
    return (f"{head}. The engine is on disk and its Python is "
            f"{pf_engine.PY310}, but that Python's install did not finish. "
            f"{_engine_retry(plat)}")


def _vc_runtime_missing() -> bool:
    """Windows without the Visual C++ runtime's msvcp140.dll in System32
    (a new or freshly reset PC); False elsewhere and on any doubt."""
    if not sys.platform.startswith("win"):
        return False
    root = os.environ.get("SystemRoot") or os.environ.get("windir")
    if not root:
        return False
    return not (Path(root) / "System32" / "msvcp140.dll").is_file()


def perl_folder_message(p) -> str:
    """A folder name Windows Perl cannot read (pf.perl_path): letters
    outside the ANSI code page and no 8.3 short name, so BNG2.pl is never
    opened. C:\\Users\\Public is open to every account without an
    administrator, and its name is plain."""
    return ("Perl cannot read the name of the folder FluBNF is in. The path "
            f"{p} holds letters outside the character set Windows hands to "
            "Perl, and has no short (8.3) name to use instead, so BNG2.pl "
            f"cannot start. Close FluBNF, move {REPO} to "
            "C:\\Users\\Public\\FluBNF\\flubnf and open FluBNF.bat there.")


# --- what this computer lacks: the checks a run makes before anything
# The pieces a fit needs, checked in the order a student puts them right:
# the engine folder, then with it there the engine's Python and that Python
# loading the engine, a Perl that runs BNG2.pl, BNG2.pl itself, and BNG2.pl
# starting under that Perl. Every one that fails is collected: the page's notice names
# the first, and its "?" lists the rest, so a student with neither the
# engine nor Perl learns both at once. pf.conf names no folder (prepare),
# so the folder FluBNF is in matters only to Perl.

#: the two answers below that start a process, cached for the life of the
#: console: subprocess.run bound at import, so a test faking BNG2.pl's
#: runs (sandbox_root) never answers for them too
_probe_run = subprocess.run
#: the engine-import probe: key -> {"done": Event, "said": str}
_ENGINE_PROBES: dict = {}
#: BNG2.pl's self-test: key -> what it said ('' when it started)
_BNG_SELFTESTS: dict = {}
_PROBE_LOCK = threading.Lock()
#: seconds the engine-import probe may take before it counts as unknown (a
#: first start under a virus scan can be slow); a page waits for it
#: ENGINE_PROBE_PAGE_WAIT_S and says nothing until it is done, a run up to
#: ENGINE_PROBE_RUN_WAIT_S
ENGINE_PROBE_TIMEOUT_S = 120
ENGINE_PROBE_PAGE_WAIT_S = 3.0
ENGINE_PROBE_RUN_WAIT_S = 60.0
#: seconds `perl BNG2.pl -v` may take (about 0.3 s when it works)
BNG_SELFTEST_TIMEOUT_S = 60


def _stamp_of(*paths) -> tuple:
    """The modification times of `paths` (None for one that is not
    there): a cache key that changes when an install touches them."""
    out = []
    for p in paths:
        try:
            out.append(Path(p).stat().st_mtime_ns)
        except OSError:
            out.append(None)
    return tuple(out)


def _engine_probe_key() -> tuple:
    """The engine's Python and folder as they are now: the interpreter,
    the venv's pyvenv.cfg and site-packages (a pip install adds folders
    there), and the fork's pf.py (a replaced archive). The environment's
    root is the interpreter's grandparent in a venv (bin/, Scripts\\) and
    its parent in a Windows conda environment (python.exe at the top)."""
    py = Path(pf_engine.PY310)
    sites = []
    for root in (py.parent.parent, py.parent):
        sites += [root / "Lib" / "site-packages"] + sorted(
            root.glob("lib/python3*/site-packages"))
    return (str(py), str(pf_engine.PYBNF_PF),
            _stamp_of(py, py.parent.parent / "pyvenv.cfg", *sites,
                      Path(pf_engine.PYBNF_PF) / pf_engine.PF_MODULE))


def _last_line(text: str) -> str:
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    return lines[-1][:300] if lines else ""


def _engine_probe(key: tuple, slot: dict) -> None:
    """Run doctor's ENGINE_PROBE (the launchers' own gate: import bngsim,
    then the fork's ParticleFilter) in the engine's Python. A finished
    nonzero exit records its last stderr line; a timeout records nothing
    and leaves the cache, so the next look asks again."""
    from flubnf.doctor import ENGINE_PROBE
    said = ""
    try:
        r = _probe_run([key[0], "-c", ENGINE_PROBE.format(pybnf=key[1])],
                       capture_output=True, text=True, errors="replace",
                       timeout=ENGINE_PROBE_TIMEOUT_S)
        if r.returncode != 0:
            said = (_last_line(r.stderr) or _last_line(r.stdout)
                    or f"it exited with status {r.returncode}")
    except subprocess.TimeoutExpired:
        with _PROBE_LOCK:
            _ENGINE_PROBES.pop(key, None)
    except (OSError, ValueError) as e:      # it could not be started at all
        said = str(e)[:300]
    finally:
        slot["said"] = said
        slot["done"].set()


def engine_import_problem(wait: float = ENGINE_PROBE_PAGE_WAIT_S) -> str:
    """Why the engine's Python cannot load the engine, or ''.

    The probe runs once per state of the engine venv (_engine_probe_key)
    for the life of the console, on its own thread; this waits up to
    `wait` seconds for it. Only a finished probe that failed refuses: one
    still running, or one that timed out, says nothing, and the run's own
    import then decides."""
    key = _engine_probe_key()
    with _PROBE_LOCK:
        slot = _ENGINE_PROBES.get(key)
        if slot is None:
            slot = {"done": threading.Event(), "said": ""}
            _ENGINE_PROBES[key] = slot
            threading.Thread(target=_engine_probe, args=(key, slot),
                             daemon=True, name="flubnf-engine-probe").start()
    if not slot["done"].wait(max(0.0, float(wait))):
        return ""
    return engine_import_message(slot["said"]) if slot["said"] else ""


def bng_selftest() -> str:
    """What `perl BNG2.pl -v` said when it did not print BioNetGen's banner,
    or '' when it did: the whole of BNG2.pl's start (Perl, its modules
    under BNGPATH, a path Perl can open) in about 0.3 s, with the perl,
    path and environment every BNG2.pl run here uses. Cached per perl,
    BNG2.pl (and its modification time) and the environment variables
    BNG2.pl reads; a timeout is not remembered and says nothing."""
    perl = pf_engine.resolve_perl() or "perl"
    env = bng_env(BNG)
    seen = env if env is not None else os.environ
    key = (perl, str(BNG), _stamp_of(BNG)) + tuple(
        seen.get(k, "") for k in ("BNGPATH", "BioNetGenRoot", "PERL5LIB",
                                  "PERL5OPT"))
    with _PROBE_LOCK:
        if key in _BNG_SELFTESTS:
            return _BNG_SELFTESTS[key]
    try:
        r = _probe_run([perl, pf_engine.perl_path(BNG) or str(BNG), "-v"],
                       capture_output=True, timeout=BNG_SELFTEST_TIMEOUT_S,
                       **pf_engine.bng_run_kwargs(env))
        said = ("" if r.returncode == 0 and pf_engine.bng_started(r.stdout)
                else pf_engine.bng_failure_text(r))
    except subprocess.TimeoutExpired:
        return ""
    except (OSError, ValueError) as e:
        said = str(e)
    with _PROBE_LOCK:
        _BNG_SELFTESTS[key] = said
    return said


def bng_problem() -> str:
    """Why BNG2.pl cannot run here, or '': it is not there, or it does not
    start (bng_selftest). The self-test needs a perl and a path Perl can
    read; the preflight names those first."""
    if not Path(BNG).is_file():
        return pf_engine.bng_missing_message(BNG)
    if not pf_engine.perl_available() or pf_engine.perl_path(BNG) is None:
        return ""
    said = bng_selftest()
    return pf_engine.bng_broken_message(said) if said else ""


def machine_problems(wait: float = ENGINE_PROBE_PAGE_WAIT_S) -> list:
    """Every reason this computer cannot fit yet, in the order a student
    fixes them (see the section's head); [] when it can. `wait` is how
    long to wait for the engine-import probe."""
    out = []
    engine = pf_engine.engine_available()
    if not engine:
        out.append(pf_engine.engine_missing_message())
    elif not pf_engine.engine_current():
        out.append(pf_engine.engine_stale_message())
    # the engine's Python only once the engine is unpacked: installing the
    # engine file is what makes it, so without one it is not another thing
    # to fix
    if engine:
        if not Path(pf_engine.PY310).exists():
            out.append(engine_python_missing_message())
        else:
            said = engine_import_problem(wait)
            if said:
                out.append(said)
    if not pf_engine.perl_available():
        out.append(pf_engine.perl_missing_message())
    try:
        RUNS.mkdir(parents=True, exist_ok=True)  # a short form needs it to exist
    except OSError as e:
        out.append(f"The sandbox folder cannot be written: {e}")
    for p in (RUNS, BNG):
        if pf_engine.perl_path(p) is None:
            out.append(perl_folder_message(p))
            break
    said = bng_problem()
    if said:
        out.append(said)
    return out


def _joined(problems: list) -> str:
    """The problems as one refusal: the first as it is (split_reason makes
    its first sentence the notice), the rest after it, numbered, so the
    tip lists them."""
    if not problems:
        return ""
    if len(problems) == 1:
        return problems[0]
    rest = " ".join(f"({i}) {p}" for i, p in enumerate(problems[1:], 2))
    n = len(problems) - 1
    return (problems[0] + "\n" + f"{n} more thing{'s' if n > 1 else ''} "
            f"to fix after that: {rest}")


def preflight() -> None:
    """Every check machine_problems makes, refused before a run folder is
    made, the reasons in the page's words. A run waits longer than a page
    for the engine-import probe."""
    problems = machine_problems(wait=ENGINE_PROBE_RUN_WAIT_S)
    if problems:
        raise SandboxError(_joined(problems))


def machine_problem() -> str:
    """Why this computer cannot fit yet, or '': the page says it before a
    run is tried, and Check beside the model's own problems. The first
    reason is the notice (split_reason); the rest are its tip."""
    return _joined(machine_problems())


#: seconds BNG2.pl may take on the model's actions at run preparation
NETGEN_TIMEOUT_S = 300


def _netgen(cell: Path) -> None:
    """BNG2.pl on the cell's model, with the resolved perl, BNG2.pl's path
    as Perl can read it, and BioNetGen's environment (settings.bng_env:
    a stale BNGPATH from an earlier install never decides). A failure
    before BioNetGen's banner is the computer's (pf.bng_started), said as
    the preflight says it; after it, the model's, in BNG2.pl's words."""
    try:
        r = subprocess.run(
            [pf_engine.resolve_perl() or "perl",
             pf_engine.perl_path(BNG) or str(BNG), "m.bngl"],
            capture_output=True, cwd=str(cell), timeout=NETGEN_TIMEOUT_S,
            **pf_engine.bng_run_kwargs(bng_env(BNG)))
    except FileNotFoundError:
        # perl vanished since the preflight, or which() disagreed
        raise SandboxError(pf_engine.perl_missing_message()) from None
    except subprocess.TimeoutExpired:
        raise SandboxError(
            f"BNG2.pl did not finish the model's actions in "
            f"{NETGEN_TIMEOUT_S} s. A run carries out the whole actions "
            "block once to generate the network: shorten a long simulate "
            "action (t_end, n_steps) or remove extra actions.") from None
    if not (cell / "m.net").is_file():
        said = pf_engine.bng_failure_text(r)
        if not pf_engine.bng_started(r.stdout):
            raise SandboxError(pf_engine.bng_broken_message(said))
        raise SandboxError("BNG2.pl could not generate the network:\n"
                           + said)


def prepare(name: str, *, particles: int = DRY_RUN_PARTICLES,
            jitter: float = 0.15, forecast_weeks: int = 4, seed: int = 0,
            runs_root: Path | None = None) -> Path:
    """A workroot with one prepared cell, ready for pf_engine.execute.

    The preflight runs first (machine_problems: every check, in the
    page's words). The network is generated here, by BNG2.pl, so a model
    that does not generate is refused before the engine is asked for
    anything, with BNG2.pl's own words. Run settings
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
    try:
        (cell / "m.bngl").write_text(files["model.bngl"].replace("\r\n", "\n"),
                                     encoding="utf-8", newline="\n")
        (cell / f"{sfx}.exp").write_text(files["data.exp"].replace("\r\n", "\n"),
                                         encoding="utf-8", newline="\n")
        _netgen(cell)
    except Exception as e:
        # a run that never reached the engine leaves no folder behind
        shutil.rmtree(workroot, ignore_errors=True)
        if isinstance(e, RuntimeError) and not isinstance(e, SandboxError):
            raise SandboxError(str(e)) from None
        raise
    # No folder in pf.conf: the runner works inside the cell (os.chdir),
    # and the engine finds BNG2.pl under the BNGPATH run() gives it
    # (bng_env). The engine's conf grammar reads ASCII only and splits the
    # model line at the first '.con', '.exp' or '.xml', so a profile
    # folder named José or m.contreras failed every fit when its path was
    # written here. The bare names carry no './': the engine splits a
    # file's prefix on '/' only.
    conf = [f"model = m.bngl : {sfx}.exp",
            "output_dir = out"]
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
    # retried: on Windows the page's poll reading meta.json, or a virus
    # scanner, refuses the replace for a moment
    pf_engine.replace_file(tmp, Path(workroot) / "meta.json")


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
        # BioNetGen's environment on every platform: the engine runs
        # BNG2.pl itself, and a stale BNGPATH would decide it
        status = pf_engine.execute(workroot, width=width, env=bng_env(BNG))
        key = next(iter(status)) if status else None
        meta["status"] = "ok" if key and status[key] == "ok" else "failed"
        meta["engine_status"] = status
        if meta["status"] == "failed":
            # the engine's own words (its runner records "FAIL: <reason>"),
            # where the page shows a failed run's reason
            said = [str(v) for v in (status or {}).values() if v != "ok"]
            meta["error"] = _with_load_remedy(
                "\n".join(said)[:2000] if said else
                "the engine reported no outcome for the run")
    except pf_engine.RunStopped:
        meta["status"] = "stopped"
    except Exception as e:                       # the reason reaches the page
        meta["status"] = "failed"
        meta["error"] = _with_load_remedy(str(e)[:2000])
    meta["seconds"] = round(time.monotonic() - t0, 1)
    meta["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_meta(workroot, meta)
    return meta


#: what a runner says when the engine's Python cannot load the engine
#: (the venv launcher's "No Python at" when its base Python was removed)
_LOAD_FAILURES = ("No module named", "DLL load failed", "ImportError",
                  "No Python at")


def _with_load_remedy(error: str) -> str:
    """A failed run's error, with the engine-install remedy after it when
    the runner died loading the engine: the import probe had not finished
    when the run started, or the venv changed since."""
    if not any(s in error for s in _LOAD_FAILURES):
        return error
    hit = next(ln for ln in error.splitlines()
               if any(s in ln for s in _LOAD_FAILURES))
    said = hit.strip().removeprefix("FAIL: ")[:300]
    return error + "\n\n" + engine_import_message(said)


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


# --------------------------------------------------- the time a fit takes
# The cost model was fitted on the production machine; student laptops ran
# about 3 times its prediction (2.9 to 3.3 in the walkthroughs), and the
# ratio held for the next fit on the same laptop. So an estimate is the
# cost model times this computer's own ratio, taken from its last finished
# fit; before one has finished, a span of it that covers the machines timed.

#: the estimate's span before a fit has finished here, as multiples of
#: the cost model: the production machine at 1, the slowest computers
#: timed so far under 4
ETA_FIRST_SPAN = (1.0, 4.0)
#: a live fit past this multiple of its estimate (the span's top, before a
#: fit has finished here) reads as slow
ETA_SLOW = 1.5
#: and never before this many seconds: a fit's first seconds are the engine
#: starting, which the cost model leaves out, so a quick check (a second by
#: the model) is not called slow for them. It changes nothing for a fit
#: estimated at 20 s or more.
ETA_SLOW_FLOOR_S = 30.0


def _run_ratio(meta: dict) -> float | None:
    """A finished run's seconds over what the cost model predicts for its
    own rows and particles, or None for a run that cannot say."""
    if meta.get("status") != "ok":
        return None
    try:
        seconds = float(meta["seconds"])
        n_obs = int(meta.get("n_obs") or len(meta.get("observed") or []))
        predicted = eta_seconds(n_obs, int(meta["particles"]))
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 < seconds < float("inf")) or predicted <= 0:
        return None
    return seconds / predicted


def eta_ratio(runs: list | None = None) -> float | None:
    """This computer's speed against the cost model: the ratio of its
    newest finished full fit, else of its newest finished run of any size
    (a quick check's seconds are mostly the engine starting, so it scales
    a full fit high); None before any run has finished here. `runs` is
    list_runs()'s list, newest first, for a caller that has it already."""
    newest = None
    for r in (list_runs() if runs is None else runs):
        x = _run_ratio(r)
        if x is None:
            continue
        if int(r["particles"]) >= FULL_FIT_PARTICLES:
            return x
        if newest is None:
            newest = x
    return newest


def eta_span(n_obs: int, particles: int, ratio: float | None) -> tuple:
    """(low, high) seconds a fit of this size takes here: the cost model
    times this computer's ratio, the two equal; with no ratio yet,
    ETA_FIRST_SPAN of it."""
    base = eta_seconds(n_obs, particles)
    lo, hi = (ratio, ratio) if ratio else ETA_FIRST_SPAN
    return round(base * lo, 1), round(base * hi, 1)


def clock(seconds: float) -> str:
    """A time as the sandbox writes it: m:ss, h:mm:ss from an hour."""
    s = max(0, int(seconds))
    h, m = divmod(s // 60, 60)
    return f"{h}:{m:02d}:{s % 60:02d}" if h else f"{m}:{s % 60:02d}"


def eta_words(low: float, high: float) -> str:
    """'about 0:51', or 'about 0:40 to 2:00' while the two ends differ;
    '' for no estimate. Rounded as sandbox.js rounds (half up)."""
    if not low > 0:
        return ""
    lo, hi = (clock(max(1, int(x + 0.5))) for x in (low, high))
    return f"about {lo}" if lo == hi else f"about {lo} to {hi}"


def slow_after(high: float) -> float:
    """Seconds after which a live fit reads as slow: ETA_SLOW times its
    estimate's top, never before ETA_SLOW_FLOOR_S."""
    return round(max(ETA_SLOW * high, ETA_SLOW_FLOOR_S), 1)


def fitting_line(elapsed: float, low: float, high: float) -> str:
    """The live fit's one line, as sandbox.js rewrites it every second:
    '0:27 so far · about 0:51 in all', and once slow (slow_after), the
    line that says stopping is safe."""
    if low > 0 and elapsed > slow_after(high):
        return "Taking longer than usual. Stopping is safe."
    eta = eta_words(low, high)
    return f"{clock(elapsed)} so far" + (f" · {eta} in all" if eta else "")


def run_meta(run_id) -> dict:
    """A run's meta.json, or {} (no id, no such run, unreadable)."""
    if not run_id:
        return {}
    try:
        meta = json.loads((run_dir(str(run_id)) / "meta.json")
                          .read_text(encoding="utf-8"))
        return meta if isinstance(meta, dict) else {}
    except Exception:
        return {}


def run_elapsed(meta: dict, now: float | None = None) -> float:
    """Seconds since the run started (its started_utc), 0 when unknown."""
    try:
        t0 = dt.datetime.strptime(str(meta["started_utc"]),
                                  "%Y-%m-%dT%H:%M:%SZ")
    except (KeyError, ValueError):
        return 0.0
    t0 = t0.replace(tzinfo=dt.timezone.utc).timestamp()
    return max(0.0, (time.time() if now is None else now) - t0)


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
        "results", "HEALTH_COLLAPSED", "HEALTH_THIN", "TRIES_SHOWN",
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
