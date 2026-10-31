"""SHIPPED behind FLUBNF_ENGINE=public: the public engine, lanl/PyBNF's
job_type = lwf (the Liu–West filter), from the venv engine-requirements.txt
pins.

pf.prepare() writes every cell as it always has (model, data, network check,
pf.conf). When the runners start, translate_cell() derives the public
engine's three files from those, in the cell's lwf/ folder:

  model   the cell's m.bngl without its actions block (lwf integrates the
          model itself and refuses the block's simulate action)
  data    one row per week, the production row at time t moved to t + 1
          (the private engine starts the state at t = -1, lwf at 0; the
          model's counter species keeps the seasonal phase), a week the
          console dropped written as nan, the column named after the
          cumulative observable
  conf    an edition-2 conf with job_type = lwf and the pf.conf settings
          under their lwf names; random_seed = pf_seed mod 2^32

That translation reproduced the private engine's forecast draws exactly on
144 of 144 SIHRS cells when fed its random inputs, and its own streams score
the same (WIS ratio 1.0013; FluBNF-local/research/lwf-production-equivalence,
in-house and retrospective). A pf.conf key with no lwf counterpart (the
research knobs: two-strain, the reporting model's likelihood column, carried
clouds, pf_shrink, pf_forecast_jitter) is refused for that cell, never
dropped.

The runners (RUNNER for the forecast, RETRO_RUNNER for replays) start one
PyBNF process per cell in the public venv's Python, with nothing on
PYTHONPATH, and keep its output in lwf/run.log; a cell is ok when PyBNF
exits 0 and wrote forecasts.txt. A degenerate update is a failed cell, as on
the private engine. cell_blocks() reads Results/LWF: the fit origin is the
last column of predicted_counts.txt and the horizons are the columns of
forecasts.txt; pf.collect() anchors them as it anchors the private engine's.

The console keeps its pf.* knob and ledger names (decided 2026-10-15); only
the conf written here says lwf.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

#: the public engine's PyBNF: lanl/PyBNF's merge of the Liu–West filter
PUBLIC_ENGINE_COMMIT = "8410f794e3fa4817572fd07fceb043ddec39d77b"
PUBLIC_ENGINE_REPO = "lanl/PyBNF"
LOCK_NAME = "engine-requirements.txt"

LWF_DIR = "lwf"
CONF_NAME = "lwf.conf"
MODEL_NAME = "m.bngl"
LOG_NAME = "run.log"
#: the run's output folder, inside lwf/; the runner clears it before a fit
OUT_DIR = "out"
#: the tables, under the cell's folder
RESULTS = (LWF_DIR, OUT_DIR, "Results", "LWF")

#: the likelihood's dispersion, the one parameter name the SIHRS conf and
#: the Sandbox reserve for it
DISPERSION = "r__FREE"
#: the private engine's resample threshold, written explicitly
RESAMPLE_THRESHOLD = 0.5


# --- the switch and the venv ------------------------------------------------

def public() -> bool:
    """Whether FLUBNF_ENGINE asks for the public engine (read each call)."""
    from flubnf.settings import engine_public
    return engine_public()


def python() -> Path:
    """The public engine venv's Python (FLUBNF_PY_ENGINE_PUBLIC first)."""
    from flubnf.settings import py_engine_public
    return py_engine_public()


def lock_path() -> Path:
    env = os.environ.get("FLUBNF_ENGINE_LOCK", "").strip()
    return Path(env) if env else REPO / LOCK_NAME


def runner_cmd(runner) -> list:
    """The command that starts a public runner script: the public venv's
    Python, -I so neither PYTHONPATH nor the runner's folder can shadow the
    installed pybnf."""
    return [str(python()), "-I", "-W", "ignore::SyntaxWarning", str(runner)]


def _setup_step(platform: str | None = None) -> str:
    plat = platform or sys.platform
    if plat == "win32":
        return ("open FluBNF.bat again with FLUBNF_ENGINE=public (setup.ps1 "
                "-Engine public records that)")
    return ("run ./setup_engine.sh --public in the FluBNF folder "
            "(SetupEngine.command on a Mac runs the same script)")


def engine_available() -> bool:
    """Whether the public venv's Python is there (cheap: no import)."""
    try:
        return python().is_file()
    except OSError:
        return False


def engine_missing_message(platform: str | None = None) -> str:
    return (f"The public engine is not installed: there is no Python at "
            f"{python()}. To install it, {_setup_step(platform)}. To use "
            "the private engine instead, set FLUBNF_ENGINE=private, or leave "
            "it unset.")


#: (key, result) of the last lock check; the check imports bngsim and the
#: filter in another process, about a second, so it is not repeated while
#: neither the venv's Python, its lock stamp nor the lock changed
_CHECK: dict = {}
CHECK_TTL_S = 300.0
CHECK_TIMEOUT_S = 120.0


def _file_key(p: Path) -> tuple:
    try:
        st = p.stat()
        return (str(p), st.st_mtime_ns, st.st_size)
    except OSError:
        return (str(p), None, None)


def _venv_root(py: Path) -> Path:
    # bin/python (POSIX) and Scripts\\python.exe (Windows) alike
    return py.parent.parent


def lock_check(force: bool = False) -> tuple[bool, str]:
    """(ok, line): does the public venv hold what engine-requirements.txt
    names? scripts/engine_lock.py check, run in the public venv's Python:
    the filter and bngsim import, bngsim is the lock's version, and pip's
    record of pybnf (direct_url.json) names the lock's wheel and hash. The
    line is engine_lock's own, in words someone can act on."""
    py = python()
    lock = lock_path()
    key = (_file_key(py), _file_key(lock),
           _file_key(_venv_root(py) / "flubnf-lock.sha256"))
    hit = _CHECK.get("key") == key and time.time() - _CHECK.get("at", 0) < CHECK_TTL_S
    if hit and not force:
        return _CHECK["result"]
    if not py.is_file():
        res = (False, f"there is no Python at {py}")
    else:
        try:
            r = subprocess.run(
                [str(py), "-I", "-W", "ignore::SyntaxWarning",
                 str(REPO / "scripts" / "engine_lock.py"), "check", str(lock)],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=CHECK_TIMEOUT_S, check=False,
                stdin=subprocess.DEVNULL, env=_clean_env(),
                **_no_window())
            said = (r.stdout + "\n" + r.stderr).strip()
            line = next((ln.strip(" !+") for ln in said.splitlines()
                         if ln.strip()), "") or f"exit code {r.returncode}"
            res = (r.returncode == 0, line)
        except subprocess.TimeoutExpired:
            res = (False, f"the check did not finish within {CHECK_TIMEOUT_S:g} s")
        except OSError as e:
            res = (False, f"{type(e).__name__}: {e}")
    _CHECK.update(key=key, at=time.time(), result=res)
    return res


def engine_current() -> bool:
    return lock_check()[0]


#: lock checks running for a page: key -> {"done": Event, "result"}
_PENDING: dict = {}


def lock_check_soon(wait: float) -> tuple[bool, str] | None:
    """lock_check for a page: the answer when it is ready within `wait`
    seconds, None while it is still running (the page says nothing yet,
    and a run's own preflight waits for it)."""
    import threading
    py = python()
    key = (str(py), _file_key(py), _file_key(lock_path()))
    slot = _PENDING.get(key)
    if slot is None:
        slot = {"done": threading.Event(), "result": None}
        _PENDING[key] = slot

        def _go():
            try:
                slot["result"] = lock_check()
            finally:
                slot["done"].set()
        threading.Thread(target=_go, daemon=True,
                         name="flubnf-public-lock-check").start()
    if not slot["done"].wait(max(0.0, float(wait))):
        return None
    _PENDING.pop(key, None)        # the next look asks lock_check (cached)
    return slot["result"]


def engine_stale_message(platform: str | None = None) -> str:
    line = lock_check()[1]
    return (f"The public engine at {python()} does not match "
            f"{LOCK_NAME}: {line}. To bring it up to the lock, "
            f"{_setup_step(platform)}.")


def _no_window() -> dict:
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def _clean_env(env: dict | None = None) -> dict:
    """The environment a public process gets: nothing on PYTHONPATH (the
    venv's pybnf, not a checkout), one BLAS thread per process (the runners
    already run one cell per core; the equivalence was measured so)."""
    e = dict(os.environ if env is None else env)
    e.pop("PYTHONPATH", None)
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
              "VECLIB_MAXIMUM_THREADS"):
        e.setdefault(k, "1")
    return e


def runner_env(env: dict | None) -> dict:
    """The public runners' environment, from what pf.runner_popen_kwargs
    would give (None: this process's)."""
    return _clean_env(env)


# --- provenance ---------------------------------------------------------------

_PROBE = r"""
import json, importlib.metadata as md
out = {}
try:
    d = md.distribution("pybnf")
    out["pybnf_version"] = d.version
    raw = d.read_text("direct_url.json") or ""
    info = json.loads(raw) if raw else {}
    out["url"] = info.get("url", "")
    out["commit"] = (info.get("vcs_info") or {}).get("commit_id", "")
    arch = info.get("archive_info") or {}
    out["wheel_sha256"] = ((arch.get("hashes") or {}).get("sha256")
                           or str(arch.get("hash", "")).partition("sha256=")[2])
except Exception as e:
    out["error"] = "pybnf: %s: %s" % (type(e).__name__, e)
try:
    import bngsim
    out["bngsim"] = getattr(bngsim, "__version__", "")
    try:
        from bngsim import _build_provenance
        out["bngsim_build"] = str(_build_provenance.summary().get("commit", ""))
    except Exception:
        out["bngsim_build"] = ""
except Exception as e:
    out.setdefault("error", "bngsim: %s: %s" % (type(e).__name__, e))
print(json.dumps(out))
"""

_BUILD: dict = {}


def _lock_wheel() -> tuple[str, str]:
    """(url, sha256) of the lock's PyBNF wheel; ("", "") without one."""
    try:
        sys.path.insert(0, str(REPO / "scripts"))
        import engine_lock  # stdlib only
        lines = engine_lock.read_lock(lock_path())
        return engine_lock.wheel(lines, lock_path())
    except Exception:
        return "", ""
    finally:
        try:
            sys.path.remove(str(REPO / "scripts"))
        except ValueError:
            pass


def public_build() -> dict:
    """The public engine's build in engine_build's shape: {branch
    ("lanl/PyBNF"), commit (8 characters), dirty, source ("wheel", "git",
    "unknown"), path}, plus the full commit, the wheel's sha256 and whether
    it is the lock's, and bngsim's version and build commit. Read from pip's
    record in the venv (PEP 610), never from pybnf.__version__, which reads
    1.8.1 on every build. Never raises; cached while the venv is unchanged."""
    py = python()
    key = (_file_key(py), _file_key(_venv_root(py) / "flubnf-lock.sha256"),
           _file_key(lock_path()))
    if _BUILD.get("key") == key and time.time() - _BUILD.get("at", 0) < CHECK_TTL_S:
        return dict(_BUILD["build"])
    out = {"branch": "", "commit": "", "dirty": False, "source": "unknown",
           "path": str(py), "engine": "public"}
    info: dict = {}
    if not py.is_file():
        info = {"error": f"there is no Python at {py}"}
    else:
        try:
            r = subprocess.run([str(py), "-I", "-c", _PROBE],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               timeout=CHECK_TIMEOUT_S, env=_clean_env(),
                               check=False,
                               stdin=subprocess.DEVNULL, **_no_window())
            info = json.loads((r.stdout or "").strip().splitlines()[-1])
        except Exception as e:  # noqa: BLE001
            info = {"error": f"{type(e).__name__}: {e}"}
    if info.get("error"):
        out["error"] = info["error"]
    url, sha = _lock_wheel()
    if info.get("commit"):
        out.update(branch=PUBLIC_ENGINE_REPO, source="git",
                   full_commit=info["commit"], commit=info["commit"][:8])
    elif info.get("url"):
        # the wheel is known by its bytes: the lock's hash names the lock's
        # build (its release tag names the commit), wherever pip fetched it
        here = str(info.get("wheel_sha256", "")).lower()
        same = bool(sha) and here == sha
        m = re.search(r"pybnf-([0-9a-f]{40})/", url if same else info["url"])
        full = m.group(1) if m else ""
        out.update(branch=PUBLIC_ENGINE_REPO, source="wheel",
                   full_commit=full, commit=full[:8], wheel_sha256=here,
                   lock_wheel=same)
    if info.get("bngsim"):
        out["bngsim"] = info["bngsim"]
        out["bngsim_build"] = info.get("bngsim_build", "")
    _BUILD.update(key=key, at=time.time(), build=out)
    return dict(out)


def is_pinned(build: dict | None) -> bool:
    """The public engine at its pinned commit: from the lock's wheel, or a
    git install of the same commit (the equivalence venv)."""
    b = build or {}
    full = str(b.get("full_commit") or "")
    if full != PUBLIC_ENGINE_COMMIT:
        return False
    return b.get("source") == "git" or bool(b.get("lock_wheel"))


# --- translation --------------------------------------------------------------

class Untranslatable(ValueError):
    """A cell the public engine cannot run as the private engine would."""


#: the prior lines both engines read (PyBNF's own grammar), passed through
PRIOR_KEYS = ("uniform_var", "loguniform_var", "normal_var", "lognormal_var")
#: pf.conf keys taken over under another name, or used to write the conf
_MAPPED = {"pf_particles": "lwf_particles", "pf_jitter": "lwf_jitter",
           "pf_bounds": "lwf_bounds",
           "pf_forecast_intervals": "lwf_forecast_intervals",
           "pf_resample_threshold": "lwf_resample_threshold",
           "initialization": "initialization"}
#: pf.conf keys the translation reads or that hold for every lwf conf
_READ = {"bng_command", "model", "output_dir", "fit_type", "objfunc",
         "pf_start_time", "pf_cumulative_observable", "population_size",
         "max_iterations", "pf_seed", "pf_sampling_interval", *PRIOR_KEYS}
#: the value each of those must hold; anything else is refused
_REQUIRED = {"fit_type": "pf", "objfunc": "neg_bin_dynamic",
             "pf_start_time": "-1", "population_size": "1",
             "max_iterations": "1", "pf_sampling_interval": "1"}
#: research keys with no counterpart in lwf, and why
_NO_COUNTERPART = {
    "pf_shrink": "the kernel's shrinkage switch",
    "pf_forecast_jitter": "a jitter applied during the forecast",
    "pf_binom_neff_cap": "the two-strain typed-positives channel",
    "pf_mean_scale_column": "the reporting model's likelihood column",
    "pf_state_file": "a carried particle cloud",
    "pf_continue": "a carried particle cloud",
}


def parse_conf(text: str) -> list[tuple[str, str]]:
    """pf.conf as (key, value) pairs, in order; comments and blanks out."""
    out = []
    for ln in text.splitlines():
        ln = ln.split("#", 1)[0].strip()
        if not ln:
            continue
        key, sep, val = ln.partition("=")
        if not sep:
            raise Untranslatable(f"pf.conf line {ln!r} is not key = value")
        out.append((key.strip(), val.strip()))
    return out


#: what str.splitlines ends a line at and BNG2.pl (Perl, by \n) does not:
#: PyBNF reads the model through splitlines and writes what it read back
#: out for BNG2.pl, so a comment could end at one for PyBNF and leave the
#: rest of its line a statement (the library's LINE_BREAK_NOT_ALLOWED set,
#: plus a lone \r)
_BREAKS = re.compile("[\x0b\x0c\x1c\x1d\x1e\x85  ]|\r(?!\n)")
_BLOCK = re.compile(r"^\s*(begin|end)\s+([A-Za-z_]+(?:\s+[A-Za-z_]+)?)\b",
                    re.IGNORECASE)


def strip_actions(model: str) -> str:
    """The model without its actions: lwf integrates the model itself and
    refuses a simulate action. Removed: a begin/end actions block (any
    case, a comment after either line) and every statement outside the
    blocks (BNG2.pl's actions may also stand bare after the model, one
    statement running over several lines until its parentheses close).
    Blocks, comments and blank lines are kept as written."""
    out, stack, skipping, depth = [], [], False, 0
    for ln in model.splitlines(keepends=True):
        code = ln.split("#", 1)[0]
        if skipping:                       # inside a bare multi-line action
            depth += code.count("(") - code.count(")")
            skipping = depth > 0
            continue
        m = _BLOCK.match(code)
        if m:
            kind, name = m.group(1).lower(), " ".join(m.group(2).lower().split())
            if kind == "begin":
                stack.append(name)
                if name != "actions":
                    out.append(ln)
            else:
                if stack and stack[-1] == name:
                    stack.pop()
                if name != "actions":
                    out.append(ln)
            continue
        if "actions" in stack:
            continue
        if stack and stack != ["model"]:
            out.append(ln)                 # inside a block: the model itself
            continue
        if not code.strip():
            out.append(ln)                 # blank or comment
            continue
        if stack == ["model"]:
            out.append(ln)                 # e.g. setOption inside begin model
            continue
        # a statement outside every block: an action
        depth = code.count("(") - code.count(")")
        skipping = depth > 0
    return "".join(out)


def lwf_rows(exp_text: str) -> tuple[list[str], dict]:
    """The data rows lwf reads, from the private .exp (header, then
    "<week> <count>"): week t becomes time t + 1, every week from 0 to the
    last present. A week with no row, or a negative count (the Sandbox's
    mark for a missing week, which the private engine leaves unscored), is
    written as nan. The rows must be one unit apart where present: lwf
    scores each count over one step from the row before, so data in other
    units is refused rather than refit week by week. Returns the value
    strings in order and a record of the gaps."""
    rows = []
    for ln in exp_text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split()
        if len(parts) != 2:
            raise Untranslatable(
                f"the data row {s!r} has {len(parts)} columns; the public "
                "engine reads one count per week")
        rows.append((parts[0], parts[1]))
    if not rows:
        raise Untranslatable("the data file has no rows")
    weeks = {}
    for t_raw, v in rows:
        try:
            t = float(t_raw)
            val = float(v)
        except ValueError:
            raise Untranslatable(f"the data row {t_raw} {v} is not two "
                                 "numbers") from None
        if not (t == t and t >= 0 and t == int(t)):
            raise Untranslatable(f"the data week {t_raw} is not a whole "
                                 "number of 0 or more")
        if int(t) in weeks:
            raise Untranslatable(f"the data week {int(t)} appears twice")
        weeks[int(t)] = val
    order = list(weeks)
    if order != sorted(order):
        raise Untranslatable("the data weeks are not in order")
    if len(order) > 1:
        step = min(b - a for a, b in zip(order, order[1:]))
        if step != 1:
            raise Untranslatable(
                f"the data rows are {step} time units apart; the public "
                "engine scores each count over one unit, so it runs data "
                "with one row per unit of time (a missing one may be left "
                "out)")
    last = order[-1]
    missing = [t for t in order if not (weeks[t] >= 0)]
    vals = [("%.6f" % weeks[t]) if t in weeks and weeks[t] >= 0 else "nan"
            for t in range(last + 1)]
    gaps = [t for t in range(last + 1) if t not in weeks]
    return vals, {"gaps": gaps, "missing": missing, "first_row": order[0],
                  "n_rows": len(order), "last_week": last}


def _model_and_data(conf: list[tuple[str, str]]) -> tuple[Path, Path]:
    """The model line's two files, split at its " : " (a Windows path holds
    a drive letter's colon with no space around it)."""
    vals = [v for k, v in conf if k == "model"]
    if len(vals) != 1:
        raise Untranslatable(f"pf.conf names {len(vals)} model lines, not one")
    parts = re.split(r"\s+:\s+", vals[0].strip(), maxsplit=1)
    if len(parts) != 2 or not all(p.strip() for p in parts):
        raise Untranslatable(f"pf.conf's model line {vals[0]!r} does not "
                             "pair one model with one data file")
    return Path(parts[0].strip()), Path(parts[1].strip())


def _read_conf(path: Path) -> str:
    """pf.conf as written: prepare leaves it in the locale's encoding (PyBNF
    opens it so), the Sandbox in UTF-8."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text()


def translate_cell(cell: dict) -> Path:
    """Write the cell's lwf/ folder (model, data, lwf.conf) from what
    pf.prepare wrote, and return the conf. Raises Untranslatable with the
    reason when a setting has no lwf counterpart."""
    d = Path(cell["dir"]).resolve()
    conf = parse_conf(_read_conf(d / "pf.conf"))
    keys = [k for k, _ in conf]
    for k in keys:
        if k in _NO_COUNTERPART:
            raise Untranslatable(
                f"{k} ({_NO_COUNTERPART[k]}) has no counterpart in the "
                "public engine; run this on the private engine "
                "(FLUBNF_ENGINE=private)")
        if k not in _MAPPED and k not in _READ:
            raise Untranslatable(f"pf.conf's key {k} has no counterpart in "
                                 "the public engine")
    one = {}
    for k, v in conf:
        if k in PRIOR_KEYS:
            continue
        if k in one:
            raise Untranslatable(f"pf.conf sets {k} twice")
        one[k] = v
    for k, want in _REQUIRED.items():
        if one.get(k, want) != want:
            raise Untranslatable(f"pf.conf sets {k} = {one[k]}; the "
                                 f"translation is defined for {k} = {want}")
    obs = one.get("pf_cumulative_observable", "")
    if not obs:
        raise Untranslatable(
            "the public engine scores each row's count as the increase of a "
            "cumulative observable over the interval; name one with "
            "pf_cumulative_observable")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", obs):
        raise Untranslatable(f"pf_cumulative_observable = {obs} is not an "
                             "observable name")
    priors = [f"{k} = {v}" for k, v in conf if k in PRIOR_KEYS]
    if not any(v.split()[0] == DISPERSION for k, v in conf
               if k in PRIOR_KEYS and v.split()):
        raise Untranslatable(f"the priors hold no {DISPERSION}, the "
                             "likelihood's dispersion")
    try:
        seed = int(one["pf_seed"]) % (1 << 32)
    except (KeyError, ValueError):
        raise Untranslatable("pf.conf holds no whole-number pf_seed") from None
    model_src, data_src = _model_and_data(conf)
    # relative names (the Sandbox writes them) are the cell's own files
    model_src = model_src if model_src.is_absolute() else d / model_src
    data_src = data_src if data_src.is_absolute() else d / data_src
    # as written (newline=""): universal newlines would turn a lone \r
    # into the very line break this refuses
    with open(model_src, encoding="utf-8", newline="") as f:
        model = f.read()
    b = _BREAKS.search(model)
    if b:
        raise Untranslatable(
            f"{model_src.name} line {model.count(chr(10), 0, b.start()) + 1}"
            f": {b.group()!r} is a line break to PyBNF, which reads the model "
            "too, and not to BNG2.pl, so the two would read different lines; "
            "write a newline or a space instead")
    w = d / LWF_DIR
    w.mkdir(exist_ok=True)
    model = strip_actions(model.replace("\r\n", "\n"))
    (w / MODEL_NAME).write_text(model, newline="\n", encoding="utf-8")
    vals, rec = lwf_rows(data_src.read_text(encoding="utf-8"))
    sfx = data_src.stem
    lines = [f"# time\t{obs}"] + [f"{i}\t{v}" for i, v in enumerate(vals, 1)]
    (w / data_src.name).write_text("\n".join(lines) + "\n", newline="\n",
                                   encoding="utf-8")
    # the order the equivalence study wrote: initialization, then lwf_*
    settings = [f"{_MAPPED[k]} = {v}" for k, v in conf if k == "initialization"]
    settings += [f"{_MAPPED[k]} = {v}" for k, v in conf
                 if k in _MAPPED and k != "initialization"]
    if "pf_resample_threshold" not in one:
        settings.append(f"lwf_resample_threshold = {RESAMPLE_THRESHOLD:g}")
    # Paths are the lwf/ folder's own names, never a folder: the runner
    # works inside it, and a profile folder outside ASCII (José) or holding
    # '.con' broke the private engine's conf grammar when written out.
    # BNG2.pl: pf.conf's line (prepare), else BNGPATH from the runner's
    # environment (the Sandbox's bng_env).
    bng = ([f"bng_command = {one['bng_command']}"]
           if one.get("bng_command") else [])
    text = "\n".join([
        "edition = 2",
        *bng,
        f"model: {MODEL_NAME}",
        "bngl_backend = bngsim",
        f"output_dir = {OUT_DIR}",
        "job_type = lwf",
        f"noise_model = neg_bin, dispersion = fit {DISPERSION}, location = mean",
        f"noise_model {obs} = neg_bin, dispersion = fit {DISPERSION}, "
        "location = mean, cumulative",
        f"experiment: {sfx}, data: {data_src.name}",
        *priors,
        *settings,
        f"random_seed = {seed}",
    ]) + "\n"
    # the locale's encoding, as PyBNF opens a conf (bng_command is the one
    # path in it, written by prepare in that encoding)
    (w / CONF_NAME).write_text(text, newline="\n")
    (w / "translate.json").write_text(json.dumps(
        {**rec, "pf_seed": int(one["pf_seed"]), "random_seed": seed,
         "observable": obs, "engine": PUBLIC_ENGINE_COMMIT}),
        encoding="utf-8")
    return w / CONF_NAME


def translate_cells(cells: list) -> dict:
    """translate_cell for every cell; {key: "FAIL: ..."} for those that
    cannot be (a cell that cannot be translated is a failed cell, its
    reason in words, never a silent private run)."""
    failed = {}
    for c in cells:
        try:
            translate_cell(c)
        except (Untranslatable, OSError, ValueError) as e:
            failed[c["key"]] = f"FAIL: public engine: {e}"[:200]
    return failed


# --- runners --------------------------------------------------------------------

#: one cell on the public engine, pasted into both runners after
#: pf.RUNNER_COMMON. Plain text (single braces), raw.
LWF_CELL = r'''
import subprocess

_MAIN = "import sys; from pybnf.pybnf import main; sys.argv[0] = 'pybnf'; main()"


def _lwf_env():
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)          # the venv's pybnf, nothing shadowing it
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
              "VECLIB_MAXIMUM_THREADS"):
        env.setdefault(k, "1")
    return env


def _lwf_reason(text):
    """PyBNF's own sentence: main() prints "Error: ..." for a refusal or a
    degenerate update, "Sorry, an unknown error ..." for anything else."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in reversed(lines):
        if ln.startswith(("Error:", "Sorry, an unknown error")):
            return ln
    return lines[-1] if lines else "it printed nothing"


def _dies_with_runner(proc):
    """Windows: put the cell's PyBNF process in a job that closes, killing
    it, when this runner ends however it ends (the console stops a runner
    with TerminateProcess and cannot list its children there). POSIX needs
    nothing: the console signals the runner's whole tree. Best effort."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class _Io(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in (
                "ReadOperationCount", "WriteOperationCount",
                "OtherOperationCount", "ReadTransferCount",
                "WriteTransferCount", "OtherTransferCount")]

        class _Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", _Basic), ("IoInfo", _Io),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        job = k32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _Extended()
        info.BasicLimitInformation.LimitFlags = 0x2000   # KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(job, 9, ctypes.byref(info),
                                           ctypes.sizeof(info)):
            return None
        if not k32.AssignProcessToJobObject(job, wintypes.HANDLE(int(proc._handle))):
            return None
        return job          # held open until the runner ends
    except Exception:
        return None


def _run_lwf(c):
    """Run one cell: PyBNF's main() in its own process, its output kept in
    lwf/run.log. "ok", or the status a failed cell records."""
    d = Path(c["dir"])
    w = d / "lwf"
    shutil.rmtree(w / "out", ignore_errors=True)
    log = w / "run.log"
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        with open(log, "w", encoding="utf-8", errors="replace") as fh:
            proc = subprocess.Popen(
                [sys.executable, "-I", "-W", "ignore::SyntaxWarning", "-c",
                 _MAIN, "-c", str(w / "lwf.conf"), "-o", "-l",
                 str(w / "pybnf")],
                cwd=str(w), stdout=fh, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, env=_lwf_env(), **kw)
            _job = _dies_with_runner(proc)
            rc = proc.wait()
    except OSError as e:
        rc, text = None, f"{type(e).__name__}: {e}"
    else:
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
    # every finished run writes parameters.txt; forecasts.txt only when it
    # forecasts (a Sandbox run may ask for 0 weeks)
    if rc == 0 and (w / "out" / "Results" / "LWF" / "parameters.txt").is_file():
        return "ok"
    msg = (f"the public engine stopped (exit code {rc}): {_lwf_reason(text)}"
           if rc is not None else f"the public engine did not start: {text}")
    sys.stderr.write(f"{c['key']} failed: {msg}\n")
    sys.stderr.flush()
    return ("FAIL: " + msg)[:600]
'''

#: the forecast path's shard runner (cf. pf._RUNNER): the same halt check
#: between cells and status after every cell; {lwf_cell} runs each one
RUNNER = '''"""Auto-generated public-engine runner. Executes one shard's cells
sequentially (job_type = lwf, one PyBNF process per cell)."""
import json, os, shutil, sys
import time as _t
from pathlib import Path
{common}
{lwf_cell}
cells = json.load(open({cells_json!r}))
out = {out_json!r}
halt = Path({halt_path!r})
results = {{}}
_t0 = _t.time()


def _write(path, payload, tries=10):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(payload, fh)
    _replace(tmp, path, tries)


def _publish(done):
    try:
        _write(out, results)
    except OSError as e:
        sys.stderr.write(f"status not written after {{done}} cell(s): "
                         f"{{e}}\\n")
        return False
    try:
        _write(out + ".prog", {{"done": done, "total": len(cells),
                               "t0": _t0, "now": _t.time()}})
    except OSError:
        pass
    return True


published = _publish(0)
for _i, c in enumerate(cells, 1):
    if halt.exists():
        break
    results[c["key"]] = _run_lwf(c)
    published = _publish(_i)
if not published:
    try:
        _write(out, results, tries=40)
    except OSError:
        with open(out, "w") as fh:
            json.dump(results, fh)
'''

#: the replay path's shard runner (cf. retro._RETRO_RUNNER): a marker per
#: finished cell, halt between cells
RETRO_RUNNER = '''"""Auto-generated public-engine retro runner: runs its shard's cells
sequentially (job_type = lwf), marks each finished cell, halts between
cells on HALT."""
import json, os, shutil, sys
from pathlib import Path
{common}
{lwf_cell}
cells = json.load(open({cells_json!r}))
halt = Path({halt_path!r})
done = Path({done_dir!r})
for c in cells:
    if halt.exists():
        break
    status = _run_lwf(c)
    tmp = done / (c["key"] + ".tmp")
    try:
        tmp.write_text(json.dumps({{"key": c["key"], "status": status}}))
        _replace(tmp, done / (c["key"] + ".json"))
    except OSError as e:
        sys.stderr.write(f"{{c['key']}} not marked: {{e}}\\n")
'''


def runner_text(template: str, common: str, **fields) -> str:
    return template.format(common=common, lwf_cell=LWF_CELL, **fields)


# --- outputs ----------------------------------------------------------------------

class Unreadable(ValueError):
    """A cell whose Results/LWF tables cannot be read as a forecast."""


def results_dir(cell: dict) -> Path:
    return Path(cell["dir"]).joinpath(*RESULTS)


def has_outputs(cell: dict) -> bool:
    """Whether the cell was run by the public engine (its tables are there:
    parameters.txt, which every finished run writes); a workroot's cells are
    read by what they hold."""
    return (results_dir(cell) / "parameters.txt").is_file()


def read_table(path: Path):
    """(header, numbers) of one Results/LWF table: '#' note lines, a header
    row, then one whitespace-separated row per particle."""
    import numpy as np
    try:
        lines = [ln for ln in Path(path).read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.startswith("#")]
    except OSError as e:
        raise Unreadable(f"{Path(path).name} unreadable ({e})") from None
    if len(lines) < 2:
        raise Unreadable(f"{Path(path).name} is torn "
                         f"({'empty' if not lines else 'a header alone'})")
    header = lines[0].split()
    try:
        rows = [[float(x) for x in ln.split()] for ln in lines[1:]]
    except ValueError as e:
        raise Unreadable(f"{Path(path).name} holds a value that is not a "
                         f"number ({e})") from None
    if any(len(r) != len(header) for r in rows):
        raise Unreadable(f"{Path(path).name} is ragged: not every row has "
                         f"the header's {len(header)} columns")
    return header, np.asarray(rows, dtype=float)


def cell_blocks(cell: dict):
    """(origin, as_of, horizons) of one public cell, unanchored: the fit
    origin's predicted count (the last column of predicted_counts.txt), the
    as-of week's (the origin itself, or the forecast k weeks on when k
    newest weeks were trimmed), and the four as-of-relative horizons
    (forecasts.txt columns k to k + 3). Raises Unreadable."""
    r = results_dir(cell)
    ph, pc = read_table(r / "predicted_counts.txt")
    fh, fc = read_table(r / "forecasts.txt")
    if pc.shape[0] != fc.shape[0]:
        raise Unreadable(f"predicted_counts.txt holds {pc.shape[0]} "
                         f"particles and forecasts.txt {fc.shape[0]}")
    k = int(cell.get("weeks_dropped", 0) or 0)
    n = int(cell["n_obs"])
    lwo = int(cell.get("last_week_offset", n - 1))
    try:
        last_t = float(ph[-1])
        f_t = [float(x) for x in fh]
    except ValueError:
        raise Unreadable("a table's header is not its times") from None
    # the fit origin is the data's last week, lwf time last week + 1
    if last_t != lwo + 1:
        raise Unreadable(f"predicted_counts.txt ends at t = {last_t:g}; the "
                         f"cell's last data week {lwo} is t = {lwo + 1}")
    if f_t[:1] != [last_t + 1]:
        raise Unreadable(f"forecasts.txt starts at t = {f_t[0]:g}, not "
                         f"{last_t + 1:g}")
    if fc.shape[1] < k + 4:
        raise Unreadable(f"forecasts.txt has {fc.shape[1]} intervals, "
                         f"{k + 4} needed for weeks_dropped={k}; rerun the "
                         "forecast")
    origin = pc[:, -1]
    as_of = origin if k == 0 else fc[:, k - 1]
    return origin, as_of, [fc[:, k + h - 1] for h in (1, 2, 3, 4)]


def parameter_table(cell: dict):
    """(names, particles x parameters) at the fit origin, from
    parameters.txt; None when the cell holds none."""
    p = results_dir(cell) / "parameters.txt"
    if not p.is_file():
        return None
    try:
        return read_table(p)
    except Unreadable:
        return None


def weight_ess(cell: dict) -> list[float]:
    """The weight ESS after each assimilated row (weight_ess.txt)."""
    p = results_dir(cell) / "weight_ess.txt"
    try:
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.startswith("#")]
    except OSError:
        return []
    if not lines:
        return []
    head = lines[0].split()
    try:
        j = head.index("weight_ess")
        return [float(ln.split()[j]) for ln in lines[1:]]
    except (ValueError, IndexError):
        return []


def lock_sha256() -> str:
    try:
        return hashlib.sha256(lock_path().read_bytes()).hexdigest()
    except OSError:
        return ""


# --- the Sandbox's views ------------------------------------------------------
# The private engine's run is read as a parameter sample, an ESS record by
# data week and a trajectory with one column per data row then one per
# forecast week; these give the public run in the same shapes, its times
# moved back one week (lwf time t + 1 is the data's week t).

def ess_record(cell: dict) -> list[dict]:
    """[{t, ess, distinct, degenerate}] per assimilated row, t the data's
    week. A degenerate update fails a public run, so degenerate is 0 on
    every row of a finished one."""
    p = results_dir(cell) / "weight_ess.txt"
    try:
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.startswith("#")]
    except OSError:
        return []
    if len(lines) < 2:
        return []
    head = lines[0].split()
    try:
        jt, je, jd = (head.index(k) for k in ("time", "weight_ess", "distinct"))
        return [{"t": float(r[jt]) - 1.0, "ess": float(r[je]),
                 "distinct": int(float(r[jd])), "degenerate": 0}
                for r in (ln.split() for ln in lines[1:])]
    except (ValueError, IndexError):
        return []


def trajectory(cell: dict, times) -> "object":
    """particles x (one column per data row, then one per forecast week):
    the predicted count at each data row's week (predicted_counts.txt, the
    expected count) and the forecast draws (forecasts.txt). Raises
    Unreadable."""
    import numpy as np
    r = results_dir(cell)
    ph, pc = read_table(r / "predicted_counts.txt")
    if (r / "forecasts.txt").is_file():
        _, fc = read_table(r / "forecasts.txt")
    else:                                   # a run asked for no forecast
        fc = np.zeros((pc.shape[0], 0))
    try:
        at = {float(h): j for j, h in enumerate(ph)}
        idx = [at[float(t) + 1.0] for t in times]
    except (KeyError, ValueError):
        raise Unreadable("predicted_counts.txt has no column for a data "
                         "row's week") from None
    if pc.shape[0] != fc.shape[0]:
        raise Unreadable("the two tables hold different particle counts")
    return np.column_stack([pc[:, idx], fc])
