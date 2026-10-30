"""What can be known about a sandbox model without the engine: check(),
and the model at its written values (expected_counts, synthetic_exp).
app/core/sandbox.py is the facade; every name here imports from it too.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from app.core import sandbox as _sb  # BNG, which the tests patch there
from app.core.engines import pf as pf_engine
from app.core.problem_codes import finding
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


def _free_name(p: str) -> str:
    """p with the fitted suffix: __free in any case becomes __FREE."""
    return (p[:-6] if p.lower().endswith("__free") else p) + "__FREE"


def check(files: dict, *, work: Path | None = None, name: str = "") -> dict:
    """What can be known about a model without the engine: fatal problems
    (a run would fail), warnings (it may run but likely not as meant) and
    facts. Network generation runs through BNG2.pl in `work` (a scratch
    folder, never the diagram's) with the model's actions replaced by
    generate_network; without Perl or BNG2.pl, in a folder Windows Perl
    cannot read, or when BNG2.pl does not start here (its self-test, or a
    run that stops before BioNetGen's banner) it reads 'not checked', and
    the reason is this computer's (facts["machine"]), never the model's.
    Never a precondition of a run: the run makes its own checks, and
    facts["machine"] says beforehand which of them this computer fails.
    "codes" holds a finding (app/core/problem_codes.py) per string, in
    their order: the problems, the warnings, then facts["machine"] when
    it is not ''.
    name: the Sandbox model whose data.source.json fills a model that
    keeps placeholders (sandbox_data.filled_bngl); only such a model's
    report has facts["placeholders"] and "replays"."""
    from app.core import contactmap
    problems, warnings = [], []
    # each string's code, in step with problems and warnings
    pcodes, wcodes = [], []

    def problem(code: str, text: str) -> None:
        problems.append(text)
        pcodes.append(code)

    def warning(code: str, text: str) -> None:
        warnings.append(text)
        wcodes.append(code)

    facts = {"suffix": "", "free": [], "priors": [], "rows": 0,
             "columns": [], "cumulative": "", "species": None,
             "reactions": None, "network": "not checked", "at_start": "",
             # why this computer cannot fit yet (the run's preflight), or
             # '': apart from the model's own problems; as the page's
             # notice says it, the remedy in machine_tip
             "machine": "", "machine_tip": ""}
    facts["machine"], facts["machine_tip"] = _sb.split_reason(
        _sb.machine_problem())
    bngl = str(files.get("model.bngl", ""))
    try:
        facts["suffix"] = simulate_suffix(bngl)
    except SandboxError as e:
        problem(e.code, str(e))
    code = "\n".join(_strip_comments(bngl))
    # BNG2.pl takes a space before the parenthesis too
    if not re.search(r"\bgenerate_network\s*\(", code):
        problem("NO_GENERATE_NETWORK", "the actions never call "
                "generate_network(...): the run generates the network with "
                "the model's own actions")
    params = bngl_parameters(bngl)
    facts["free"] = [p for p in params if p.endswith("__FREE")]
    outputs = bngl_outputs(bngl)
    times = None
    try:
        exp = read_exp(str(files.get("data.exp", "")))
        facts["rows"], facts["columns"] = len(exp["rows"]), exp["columns"]
        times = [r[0] for r in exp["rows"]]
        if any(b <= a for a, b in zip(times, times[1:])):
            problem("EXP_TIME_ORDER",
                    "data.exp: time must increase from row to row")
    except SandboxError as e:
        problem(e.code, str(e))
    except ValueError as e:
        problem("EXP_UNREADABLE",
                f"data.exp holds a value that is not a number ({e})")
    priors, keys, read = [], {}, False
    try:
        priors, keys = split_priors(str(files.get("priors.conf", "")))
        read = True
    except SandboxError as e:
        problem(e.code, str(e))
    named = set()
    for line in priors:
        k = line.split("=", 1)[0].strip()
        if k.endswith("_var"):
            prior = _check_prior(line, set(params), problems, pcodes)
            # a line too short to read still names its parameter: one
            # problem for it, not a second "has no prior line"
            toks = line.partition("=")[2].split()
            named.add(prior or (toks[0] if toks else ""))
    facts["priors"] = sorted(n for n in named if n)
    # the engine pairs them both ways and refuses a run that does not
    # (an unreadable priors.conf is its own problem, not one per parameter)
    unpaired = [p for p in facts["free"] if p not in named] if read else []
    gone = sorted(n for n in named if n and n not in params)
    if len(unpaired) == 1 and len(gone) == 1:
        # a rename made in one file only, or a typo: one problem naming
        # both ends, not two that each read as unrelated
        stale = f"names {gone[0]}, which the parameters block does not define"
        kept = [(c, p) for c, p in zip(pcodes, problems)
                if not p.endswith(stale)]
        pcodes[:], problems[:] = [c for c, _ in kept], [p for _, p in kept]
        problem("PRIOR_RENAMED", f"priors.conf names {gone[0]}, which "
                f"model.bngl does not define, and {unpaired[0]} has no "
                "prior line: use one name in both files")
        unpaired = []
    for p in unpaired:
        problem("FREE_NO_PRIOR", f"{p} ends in __FREE but has no prior "
                "line: give it one in priors.conf, or drop __FREE to keep "
                "its written value fixed")
    for p in sorted(n for n in named if n in params
                    and not n.endswith("__FREE")):
        problem("PRIOR_NOT_FREE", f"{p} has a prior line but its name does "
                "not end in __FREE: only a __FREE parameter is fitted, so "
                f"rename it {_free_name(p)} in both files")
    # __free in small letters reads as fitted but is not: the suffix is
    # matched exactly
    for p in sorted(n for n in params if n not in named
                    and n.lower().endswith("__free")
                    and not n.endswith("__FREE")):
        warning("FREE_LOWERCASE", f"{p} is not fitted: only __FREE in "
                f"capitals is, so rename it {_free_name(p)}")
    for w in _prior_start_warnings(bngl, priors):
        warning("START_OUTSIDE_PRIOR", w)
    cum = keys.get("pf_cumulative_observable", "")
    facts["cumulative"] = cum
    if not cum:
        warning("NO_CUMULATIVE", "no pf_cumulative_observable line: the "
                "filter reads the observation column itself, not a weekly "
                "increment")
    elif cum not in outputs:
        problem("CUMULATIVE_NOT_OUTPUT", f"pf_cumulative_observable names "
                f"{cum}, which is neither an observable nor a function of "
                "the model")
    # the model starts at pf_start_time and each row is the increment over
    # the week before it: a row at or before the start has no week
    t_start = _number(keys.get("pf_start_time", "-1"))
    if times and t_start is not None and min(times) <= t_start:
        warning("ROW_BEFORE_START", f"data.exp has a row at t = "
                f"{min(times):g}, at or before the model's start time "
                f"{t_start:g} (pf_start_time): every row must come after "
                "it, as the first week's count is the increment from the "
                "start")
    if "pf_observable_mode" in keys:
        warning("KEY_RETIRED", "pf_observable_mode is retired: the filter "
                "always fits the weekly increment, and runs drop this line, "
                "so it can be deleted")
    if pf_engine.engine_available():
        for line in priors:
            k = line.split("=", 1)[0].strip()
            if k.startswith("pf_") and not pf_engine.engine_accepts_pf_key(k):
                warning("KEY_UNKNOWN", f"{k} is not a setting the installed "
                        "engine knows (check the spelling), so a run would "
                        "stop on it")
    if (times is not None and len(times) == 1
            and "pf_sampling_interval" not in keys
            and not pf_engine.sampling_interval_line()):
        warning("ONE_ROW", "one data row: this engine needs two or more "
                "(it does not accept pf_sampling_interval)")
    # a model that keeps placeholders: BNG2.pl reads it filled as a run
    # would be (or with the sample values, when it cannot be), never the
    # placeholders themselves; the rules above read the text as written
    fill, net_files = {}, files
    if "{{" in bngl:
        from app.core.sandbox_data import filled_bngl
        try:                       # data.exp unreadable: its own problem above
            text, fill = filled_bngl(name, files, sample=times is None)
        except SandboxError as e:
            problem(e.code or "PLACEHOLDERS_UNFILLED", str(e))
            text, fill = filled_bngl(name, files, sample=True)
        if fill:
            net_files = {**files, "model.bngl": text}
            facts["placeholders"] = fill
    # each "not checked" is a machine problem the notice names, never the
    # model's: BNG2.pl cannot read any model here yet
    if not pf_engine.perl_available():
        facts["network"] = "not checked (no Perl here)"
    elif not Path(_sb.BNG).is_file():
        facts["network"] = "not checked (BNG2.pl not found)"
    elif pf_engine.perl_path(_sb.BNG) is None:
        facts["network"] = "not checked (Perl cannot read this folder's name)"
    elif _sb.bng_problem():
        facts["network"] = "not checked (BNG2.pl does not start here)"
    else:
        if work:
            Path(work).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(work) if work else None) as tmp:
            try:
                net = contactmap.parse_net(contactmap.network_from_bngl(
                    str(net_files.get("model.bngl", "")), Path(tmp)))
                facts["species"] = len(net["species"])
                facts["reactions"] = len(net["reactions"])
                facts["network"] = "generates"
            except subprocess.TimeoutExpired as e:
                facts["network"] = "fails"     # a network too large to make
                problem("NETWORK_FAILS", str(e).strip())
            except (contactmap.ContactMapError, OSError,
                    subprocess.SubprocessError) as e:
                said = str(e).strip()
                if isinstance(e, contactmap.ContactMapError) and (
                        pf_engine.bng_started(said)
                        or not said.startswith("BNG2.pl could not")):
                    facts["network"] = "fails"
                    problem("NETWORK_FAILS", said)
                else:
                    # BNG2.pl stopped before its banner, or perl did not
                    # start: this computer, which no edit of the model fixes
                    facts["network"] = "not checked (BNG2.pl did not start)"
                    if not facts["machine"]:
                        facts["machine"], facts["machine_tip"] = \
                            _sb.split_reason(pf_engine.bng_broken_message(
                                said.partition("\n")[2] or said))
        # the model at its written values beside the data: a scale that
        # is off tenfold is the commonest reason a first fit collapses
        if facts["network"] == "generates" and cum in outputs and times:
            if fill.get("from") == "sample":
                # sample values say nothing of this data's scale (no false
                # SCALE_OFF): say why, so the row is not just gone
                facts["at_start"] = ("not compared: the placeholders hold "
                                     "sample values")
            else:
                try:
                    ex = expected_counts(net_files, times=times, work=work)
                    observed = [r[1] for r in
                                read_exp(str(files["data.exp"]))["rows"]]
                    fact, warn = _scale_note(ex["expected"], observed)
                    facts["at_start"] = fact
                    if warn:
                        warning("SCALE_OFF", warn)
                except (SandboxError, ValueError, KeyError) as e:
                    # nothing to compare: say why, so the row is not just gone
                    facts["at_start"] = f"not compared: {str(e).strip()[:300]}"
    codes = ([finding(c, t) for c, t in zip(pcodes, problems)]
             + [finding(c, t) for c, t in zip(wcodes, warnings)])
    if facts["machine"]:
        codes.append(finding("MACHINE", facts["machine"]))
    out = {"ok": not problems, "problems": problems, "warnings": warnings,
           "facts": facts, "codes": codes}
    if fill:
        out["replays"] = _replays(files, out, name)
    return out


def _replays(files: dict, checked: dict, name: str) -> dict:
    """Ready for replays (library.readiness) of a model that keeps
    placeholders, from this Check; a failure of the verdict itself is its
    one finding, never the loss of Check's own report."""
    try:
        from app.core import library
        return library.readiness(files, checked, name)
    except Exception as e:
        said = f"the Ready for replays check failed: {e}"[:1500]
        return {"ready": False, "findings": [finding("CHECK_FAILED", said)],
                "registered": None}


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
