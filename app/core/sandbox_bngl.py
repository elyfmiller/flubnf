"""The three files of a sandbox model as text: model.bngl, data.exp and
priors.conf. app/core/sandbox.py is the facade; every name here imports
from it too. Nothing here touches the disk or the engine.

Sections: the engine keys; the skeleton; the BNGL text (blocks,
parameters, outputs); data.exp; priors.conf; the engine settings a run
writes.
"""
from __future__ import annotations

import math
import re

from app.core.engines import pf as pf_engine
from app.core.sandbox import DRY_RUN_PARTICLES, SandboxError

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
    k, scale, n = 0.5, 0.5, 100000
    rows = []
    for t in range(SKELETON_WEEKS):
        rows.append(f"{t} {scale * n * (math.exp(-k * t) - math.exp(-k * (t + 1))):.0f}")
    data = "# time T_weekly\n" + "\n".join(rows) + "\n"
    return {"model.bngl": SKELETON_BNGL.format(name=name, t_end=SKELETON_WEEKS),
            "data.exp": data, "priors.conf": SKELETON_PRIORS}


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
    """The lines without comments, a line ending in a backslash joined to
    the next (BNGL's continuation), so a parameter or rule written over two
    lines reads as one."""
    out, carry = [], ""
    for l in text.splitlines():
        s = l.split("#", 1)[0].strip()
        if s.endswith("\\"):
            carry += s[:-1] + " "
            continue
        out.append((carry + s).strip())
        carry = ""
    if carry:
        out.append(carry.strip())
    return out


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


def _tokens(line: str, equals: bool = False) -> list:
    """A block line's tokens, an index before the name dropped; with
    equals, '=' reads as a space ('k = 0.5' as 'k 0.5')."""
    toks = (line.replace("=", " ") if equals else line).split()
    return toks[1:] if toks and toks[0].isdigit() else toks


def bngl_parameters(bngl: str) -> list:
    """The names the parameters block defines ('k 0.5', 'k = 0.5' and an
    index before the name all read)."""
    names = []
    for s in _block(bngl, "parameters"):
        toks = _tokens(s, equals=True)
        if toks:
            names.append(toks[0])
    return names


def bngl_parameter_values(bngl: str) -> dict:
    """{name: its value as written} for each parameters-block line (the
    rest of the line after the name: a number or a whole expression, so
    'N N_y + N_o' reads 'N_y + N_o', never 'N_y')."""
    out = {}
    for s in _block(bngl, "parameters"):
        toks = _tokens(s, equals=True)
        if len(toks) >= 2:
            out.setdefault(toks[0], " ".join(toks[1:]))
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
        toks = _tokens(s)
        if len(toks) >= 2:
            names.append(toks[1])
    for s in _block(bngl, "functions"):
        toks = _tokens(s)
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


def sihrs_shaped(bngl: str) -> bool:
    """A model whose initial state is derived from N and the data (the
    Oracle SIHRS filter's i0), where N cannot be changed on its own."""
    params = set(bngl_parameters(bngl))
    return "N" in params and "i0" in params


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
