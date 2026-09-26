"""What can be known about a sandbox model without the engine: check(),
and the model at its written values (expected_counts, synthetic_exp).
app/core/sandbox.py is the facade; every name here imports from it too.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np

from app.core import sandbox as _sb  # BNG, which the tests patch there
from app.core.engines import pf as pf_engine
from app.core.sandbox import DEFAULT_HEADER, SandboxError, _fmt
from app.core.sandbox_bngl import (
    _check_prior,
    _number,
    _prior_start_warnings,
    _strip_comments,
    bngl_outputs,
    bngl_parameter_values,
    bngl_parameters,
    read_exp,
    simulate_suffix,
    split_priors,
)


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
    for p in sorted(n for n in named if n in params
                    and not n.endswith("__FREE")):
        warnings.append(f"{p} has a prior line but its name does not end in "
                        "__FREE: only a __FREE parameter is fitted, so "
                        f"rename it {p}__FREE in both files")
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
    # the model starts at pf_start_time and each row is the increment over
    # the week before it: a row at or before the start has no week
    t_start = _number(keys.get("pf_start_time", "-1"))
    if times and t_start is not None and min(times) <= t_start:
        warnings.append(f"data.exp has a row at t = {min(times):g}, at or "
                        f"before the model's start time {t_start:g} "
                        "(pf_start_time): every row must come after it, as "
                        "the first week's count is the increment from the "
                        "start")
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
    if not pf_engine.perl_available() or not Path(_sb.BNG).is_file():
        facts["network"] = "not checked (no Perl or BNG2.pl here)"
    else:
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
