"""REGISTRY: the model knobs, every tunable of the two shipped models, typed,
with its shipped value, bounds, the members it affects and whether the
model card states it.

Each default is READ from the constant the engine uses (never restated),
and app/tests/test_knobs.py holds the defaults, the source labels and the
card phrases in step with the code and model-metadata/*.yml. The console
(/run), the retrospective (/retro/run, `flubnf retro --knob`) and the
Model settings panel go through resolve() and write_extra() below; see
"Stage 2" for the record a modified run carries and what reads it.

Members use the submit.MODEL_ABBR keys: "pf" is the Oracle SIHRS (the
particle filter plus the Oracle step), "analogue" the Groundhog. A knob
whose members do not run under the chosen engine, or an Oracle-step knob
when the step is off, is ignored by parse() and never recorded.

Classes: "run" knobs change how much is computed or which rows are fitted;
"method" knobs change what the model is. Any value that differs from the
shipped one marks a run as modified; LOCKED lists what is not settable.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Optional

from flubnf import analogue as AN
from flubnf import oracle as OR
from flubnf import oracle_bank as OB
from flubnf import oracle_mix as MX
from app.core import floor as FL
from app.core import horizons as HZ
from app.core import submit as SB
from app.core.engines import analogue as EA
from app.core.engines import pf as PF
from app.core.runs import RunSpec, default_season_start

MEMBERS = ("pf", "analogue")
PF_ONLY = frozenset({"pf"})
GH_ONLY = frozenset({"analogue"})
BOTH = frozenset(MEMBERS)
#: Console engine -> members that run. The retrospective's "pf" runs both
#: members, so a retro caller passes "all" (or the member set itself).
ENGINE_MEMBERS = {"all": BOTH, "pf": PF_ONLY, "analogue": GH_ONLY}

KINDS = ("int", "float", "bool", "choice", "date", "range")
STAGES = ("fit", "step", "groundhog", "output")
ORACLE_CARD = "NAU_PyBNF-OracleSIHRS.yml"
GROUNDHOG_CARD = "NAU_PyBNF-GroundHogCGR.yml"
#: The console's fit-start rule (server.run_forecast): before the forecast
#: week and within this many days of it.
SEASON_START_WINDOW_DAYS = 400


class KnobError(ValueError):
    """A refused knob value, key or combination."""


def _shipped_aux_weight() -> float:
    return float(sum(p["weight"] for p in EA.AUX_PRESETS[EA.SHIPPED_AUX]))


def _prior_defaults() -> dict:
    """{name: (lo, hi)} parsed from the filter's own prior block."""
    out = {}
    for line in PF.VARS_1S.splitlines():
        name, lo, hi = line.split("=", 1)[1].split()
        out[name] = (float(lo), float(hi))
    return out


PRIOR_DEFAULTS = _prior_defaults()


@dataclass(frozen=True)
class Knob:
    key: str
    label: str
    affects: frozenset          # subset of MEMBERS
    stage: str                  # fit | step | groundhog | output
    klass: str                  # run | method
    kind: str                   # one of KINDS
    default: Any                # the source constant's value; a callable of
                                # the forecast date for a date-dependent one
    source: str                 # where the default lives, "module:NAME"
    help: str                   # one line, for a UI tooltip
    lo: Optional[float] = None
    hi: Optional[float] = None
    choices: tuple = ()
    unit: str = ""
    #: (card file, {shipped value: phrase the card prints for it})
    card: Optional[tuple] = None
    #: an engine validator: raises ValueError on a value the engine refuses
    check: Optional[Callable[[Any], None]] = field(default=None, repr=False)

    @property
    def overridable(self) -> bool:
        """May a modified run still write hub-named files, by override.
        Every unlocked knob may (owner's rule): the override and its typed
        reason are recorded with the run; without one the run exports
        under a non-hub name."""
        return True

    def default_for(self, forecast_date: Optional[str] = None):
        if callable(self.default):
            if not forecast_date:
                raise KnobError(f"{self.key}: the default depends on the "
                                f"forecast date; none was given")
            return self.default(forecast_date)
        return self.default

    def range_text(self) -> str:
        if self.kind == "choice":
            return " | ".join(str(c) for c in self.choices)
        if self.kind == "bool":
            return "on | off"
        if self.kind == "date":
            return f"before the forecast date, within {SEASON_START_WINDOW_DAYS} days"
        if self.kind == "range":
            return "lo < hi (the engine's rule)"
        return f"{_fmt(self.lo)} to {_fmt(self.hi)}"


# --- engine validators ---------------------------------------------------------

def _check_prior(name: str):
    def check(v):
        PF.priors_for(SimpleNamespace(extra={"prior_ranges": {name: list(v)}}))
    return check


def _check_initialization(v):
    PF.initialization_for(SimpleNamespace(extra={"initialization": v}))


def _check_aux(v):
    if v != "none":
        EA.aux_preset(v)            # unknown name or a bad bank raises


def _check_w_aux(v):
    MX.resolve_w_aux(True, True, w_aux=v)


# --- the registry ----------------------------------------------------------------

def _prior_knob(name: str) -> Knob:
    short = name.split("__", 1)[0]
    return Knob(
        key=f"pf.prior.{short}", label=f"Prior range for {short}",
        affects=PF_ONLY, stage="fit", klass="method", kind="range",
        default=PRIOR_DEFAULTS[name], source="app.core.engines.pf:VARS_1S",
        help=f"Range of the {short} prior; the distribution type stays as shipped.",
        check=_check_prior(name))


REGISTRY: tuple = (
    # -- Oracle SIHRS: the particle filter (a change refits) --
    Knob("pf.particles", "Particles", PF_ONLY, "fit", "run", "int",
         RunSpec.particles, "app.core.runs:RunSpec.particles",
         "Candidate epidemics per jurisdiction; run time grows linearly.",
         lo=1_000, hi=100_000, unit="particles",
         card=(ORACLE_CARD, {10_000: "10,000 candidate epidemics"})),
    Knob("pf.replicates", "Replicates", PF_ONLY, "fit", "run", "int",
         RunSpec.replicates, "app.core.runs:RunSpec.replicates",
         "Seeded filter runs per jurisdiction, pooled; fewer than 3 breaks rule 3.",
         lo=1, hi=10, unit="runs"),
    Knob("pf.jitter", "Kernel jitter", PF_ONLY, "fit", "method", "float",
         RunSpec.jitter, "app.core.runs:RunSpec.jitter",
         "Liu-West kernel scale h; the sealed record ran 0.30.",
         lo=0.01, hi=1.0),
    *(_prior_knob(n) for n in PRIOR_DEFAULTS),
    Knob("pf.initialization", "Particle initialization", PF_ONLY, "fit",
         "method", "choice", "rand", "app.core.engines.pf:initialization_for",
         "rand draws the first cloud from the priors; lh is Latin hypercube.",
         choices=("rand", "lh"), check=_check_initialization),
    Knob("run.season_start", "Season start", PF_ONLY, "fit", "run", "date",
         default_season_start, "app.core.runs:default_season_start",
         "First week the filter fits; August 1 of the forecast's season.",
         card=(ORACLE_CARD, {"08-01": "season start (August 1)"})),
    Knob("run.weeks_to_drop", "Weeks to drop", BOTH, "fit", "run", "int",
         RunSpec.weeks_to_drop, "app.core.runs:RunSpec.weeks_to_drop",
         "Ignore the newest N reported weeks; both members move their anchor.",
         lo=0, hi=4, unit="weeks"),
    Knob("run.drop_same_day", "Drop the same-day week", BOTH, "fit", "run",
         "bool", RunSpec.drop_same_day, "app.core.runs:RunSpec.drop_same_day",
         "Treat the vintage's partly reported same-day week as unreported."),
    # -- Oracle SIHRS: the Oracle step (post-fit) --
    Knob("oracle.w", "Oracle blend weight", PF_ONLY, "step", "method", "float",
         OR.W_PRODUCTION, "flubnf.oracle:W_PRODUCTION",
         "Weight of the donor's growth in the geometric blend; 1 is not the plain filter.",
         lo=0.0, hi=1.0,
         card=(ORACLE_CARD, {0.5: "at weight one half"})),
    Knob("oracle.w_aux", "FluSurv-NET donor share", PF_ONLY, "step", "method",
         "float", MX.W_AUX, "flubnf.oracle_mix:W_AUX",
         "Chance a path draws a FluSurv-NET donor when both streams qualify.",
         lo=0.0, hi=1.0, check=_check_w_aux,
         card=(ORACLE_CARD, {0.5: "with probability one half"})),
    Knob("oracle.submitted_seed", "Submitted donor seed", PF_ONLY, "step",
         "method", "choice", OR.SUBMITTED_SEED, "flubnf.oracle:SUBMITTED_SEED",
         "Which of the five logged donor-draw seeds is submitted.",
         choices=tuple(OR.SEEDS),
         card=(ORACLE_CARD, {OR.SEEDS[0]: "the first is submitted"})),
    Knob("oracle.bandwidth", "Oracle donor window", PF_ONLY, "step", "method",
         "int", AN.DEFAULT_BANDWIDTH, "flubnf.analogue:DEFAULT_BANDWIDTH",
         "Donor weeks within this many epiweeks of the forecast week.",
         lo=0, hi=8, unit="epiweeks",
         card=(ORACLE_CARD, {2: "within two epiweeks of the forecast date"})),
    Knob("oracle.count_floor", "Admissions donor floor", PF_ONLY, "step",
         "method", "float", OB.COUNT_FLOOR, "flubnf.oracle_bank:COUNT_FLOOR",
         "An admissions donor path needs at least this many admissions.",
         lo=0.0, hi=100.0, unit="admissions",
         card=(ORACLE_CARD, {10.0: "at least 10 admissions"})),
    Knob("oracle.min_donor_seasons", "Minimum donor seasons", PF_ONLY, "step",
         "method", "int", OB.MIN_DONOR_SEASONS,
         "flubnf.oracle_bank:MIN_DONOR_SEASONS",
         "The admissions stream qualifies with at least this many seasons.",
         lo=1, hi=10, unit="seasons",
         card=(ORACLE_CARD, {2: "two donor seasons"})),
    Knob("oracle.min_paths", "Minimum donor paths", PF_ONLY, "step", "method",
         "int", AN.MIN_DONORS, "flubnf.analogue:MIN_DONORS",
         "A donor stream qualifies with at least this many paths.",
         lo=1, hi=1_000, unit="paths",
         card=(ORACLE_CARD, {30: "30 paths"})),
    # -- Groundhog (instant) --
    Knob("groundhog.aux", "Auxiliary donor bank", GH_ONLY, "groundhog",
         "method", "choice", EA.SHIPPED_AUX,
         "app.core.engines.analogue:SHIPPED_AUX",
         "Auxiliary donor pool spliced in; none is the bare analogue.",
         choices=(*EA.AUX_PRESETS, "none"), check=_check_aux,
         card=(GROUNDHOG_CARD, {"flusurv": "with FluSurv-NET donors"})),
    Knob("groundhog.aux_weight", "Auxiliary pool weight", GH_ONLY, "groundhog",
         "method", "float", _shipped_aux_weight(),
         "app.core.engines.analogue:AUX_PRESETS[SHIPPED_AUX]",
         "Total weight on the auxiliary pools; independent of the Oracle's share.",
         lo=0.0, hi=1.0,
         card=(GROUNDHOG_CARD, {0.5: "at fixed equal weight"})),
    Knob("groundhog.bandwidth", "Groundhog donor window", GH_ONLY, "groundhog",
         "method", "int", AN.DEFAULT_BANDWIDTH,
         "flubnf.analogue:DEFAULT_BANDWIDTH",
         "Donor weeks within this many epiweeks; the seal ran 2.",
         lo=0, hi=8, unit="epiweeks",
         card=(GROUNDHOG_CARD, {2: "within two MMWR epiweeks"})),
    Knob("groundhog.min_donors", "Groundhog minimum donors", GH_ONLY,
         "groundhog", "method", "int", AN.MIN_DONORS,
         "flubnf.analogue:MIN_DONORS",
         "Fewer donor ratios than this and the Groundhog abstains.",
         lo=1, hi=1_000, unit="ratios"),
    # -- Output floor (console runs only) --
    Knob("output.floor_lam", "Output floor rate", BOTH, "output", "method",
         "float", FL.LAM, "app.core.floor:LAM",
         "Poisson noise floor so no cell is a point mass; console runs only.",
         lo=0.0, hi=5.0),
)

BY_KEY: dict = {k.key: k for k in REGISTRY}


@dataclass(frozen=True)
class Locked:
    key: str
    value: Any
    source: str
    why: str


LOCKED: tuple = (
    Locked("horizons", len(HZ.HORIZONS), "app.core.horizons:HORIZONS",
           "The hub's target: four weekly horizons, 0 to 3."),
    Locked("quantile_levels", len(SB.QUANTILES), "app.core.submit:QUANTILES",
           "The hub's 23 quantile levels and integer rounding."),
    Locked("epiweek_53", 52.5, "flubnf.analogue:calendar_distance",
           "Week 53 sits between 52 and 1 for the calendar match."),
    Locked("season_boundary_month", AN.SEASON_BOUNDARY_MONTH,
           "flubnf.analogue:SEASON_BOUNDARY_MONTH",
           "Seasons start in August; donors come from strictly earlier seasons."),
    Locked("gamma", OB.GAMMA, "flubnf.oracle_bank:GAMMA",
           "The fit's recovery rate must equal the Oracle step's."),
    Locked("oracle.w_secondary", OR.W_SECONDARY, "flubnf.oracle:W_SECONDARY",
           "The registered secondary: logged beside the primary, ships nothing."),
    Locked("oracle.identity_rule", MX.IDENTITY_RULE,
           "flubnf.oracle_mix:IDENTITY_RULE",
           "Which stream serves a week when only one qualifies; pre-registered."),
    Locked("oracle.smoother", OB.SMOOTHER_ID, "flubnf.oracle_bank:SMOOTHER_ID",
           "The donor-path smoother fixed by the pre-registration."),
    Locked("oracle.prereg", OR.PREREG_SHA256[:16], "flubnf.oracle:PREREG_SHA256",
           "The frozen pre-registration; recorded in every week."),
    Locked("donor_exclusions", tuple(sorted(AN.EXCLUDED_DONOR_SEASONS)),
           "flubnf.analogue:EXCLUDED_DONOR_SEASONS",
           "A season leaves the pools only through a registered record."),
    Locked("pf.template", PF.TEMPLATE.name, "app.core.engines.pf:TEMPLATE",
           "The SIHRS compartment model the card describes."),
    Locked("pf.engine_keys", "neg_bin_dynamic, reflect, start -1, Hobs",
           "app.core.engines.pf:prepare",
           "Objective, bounds and start time pinned to the records' conventions."),
    Locked("pf.starting_values", "DEFAULTS_BLOCK", "app.core.engines.pf:DEFAULTS_BLOCK",
           "Inert under initialization=rand."),
    Locked("pooling", "all jurisdictions", "app.core.engines.analogue:run",
           "Donor pools pool every location; jurisdictions fit independently."),
)
LOCKED_KEYS = frozenset(l.key for l in LOCKED)


# --- parsing ---------------------------------------------------------------------

_TRUE = {"1", "true", "on", "yes"}
_FALSE = {"0", "false", "off", "no"}
FORM_PREFIX = "knob."


def members_for(engine) -> frozenset:
    """The members an engine runs: a console engine name or a member set."""
    if isinstance(engine, str):
        if engine not in ENGINE_MEMBERS:
            raise KnobError(f"unknown engine {engine!r}; known: "
                            f"{sorted(ENGINE_MEMBERS)}")
        return ENGINE_MEMBERS[engine]
    out = frozenset(engine)
    if not out or not out <= BOTH:
        raise KnobError(f"members must be a non-empty subset of {MEMBERS}")
    return out


def applies(knob: Knob, members: frozenset, oracle_step: bool = True) -> bool:
    if knob.stage == "step" and not oracle_step:
        return False
    return bool(knob.affects & members)


def _finite(key: str, x: float) -> float:
    if not math.isfinite(x):
        raise KnobError(f"{key}: {x!r} is not a finite number")
    return x


def _coerce(knob: Knob, raw, forecast_date: Optional[str]):
    key = knob.key
    try:
        if knob.kind == "int":
            if isinstance(raw, bool):
                raise ValueError
            if isinstance(raw, float):
                if not raw.is_integer():
                    raise ValueError
                raw = int(raw)
            v = int(str(raw).strip().replace(",", "").replace("_", ""))
        elif knob.kind == "float":
            if isinstance(raw, bool):
                raise ValueError
            v = _finite(key, float(str(raw).strip()))
        elif knob.kind == "bool":
            if isinstance(raw, bool):
                v = raw
            else:
                s = str(raw).strip().lower()
                if s not in _TRUE | _FALSE:
                    raise ValueError
                v = s in _TRUE
        elif knob.kind == "choice":
            want = type(knob.choices[0])
            v = want(str(raw).strip())
            if v not in knob.choices:
                raise KnobError(f"{key}: {raw!r} is not one of "
                                f"{', '.join(map(str, knob.choices))}")
        elif knob.kind == "date":
            v = date.fromisoformat(str(raw).strip()).isoformat()
        elif knob.kind == "range":
            parts = (str(raw).split(",") if isinstance(raw, str) else list(raw))
            if len(parts) != 2:
                raise ValueError
            v = tuple(_finite(key, float(str(p).strip())) for p in parts)
        else:                                              # pragma: no cover
            raise KnobError(f"{key}: unknown kind {knob.kind!r}")
    except KnobError:
        raise
    except (TypeError, ValueError):
        raise KnobError(f"{key}: {raw!r} is not a valid {knob.kind}") from None

    if knob.kind in ("int", "float"):
        if (knob.lo is not None and v < knob.lo) or (knob.hi is not None and v > knob.hi):
            raise KnobError(f"{key}: {_fmt(v)} is outside {knob.range_text()}")
    if knob.kind == "date":
        if not forecast_date:
            raise KnobError(f"{key}: a forecast date is needed to check it")
        fd = date.fromisoformat(forecast_date)
        ss = date.fromisoformat(v)
        if not (fd - timedelta(days=SEASON_START_WINDOW_DAYS) <= ss < fd):
            raise KnobError(f"{key}: {v} is not before the forecast date "
                            f"{forecast_date} and within "
                            f"{SEASON_START_WINDOW_DAYS} days of it")
    if knob.check is not None:
        try:
            knob.check(v)
        except ValueError as e:
            raise KnobError(f"{key}: {e}") from None
    return v


def _is_blank(raw) -> bool:
    return raw is None or (isinstance(raw, str) and not raw.strip())


def parse(form: Mapping, engine="all", *, forecast_date: Optional[str] = None,
          oracle_step: bool = True) -> dict:
    """Typed values from a form or dict of {key: value}; keys may carry the
    form prefix "knob.". Blank means shipped and is dropped, as is a knob
    that does not apply to `engine` (see members_for) or an Oracle-step
    knob when the step is off. Raises KnobError for an unknown or locked
    key, a wrong type, NaN/inf, an out-of-range value or anything the
    engine's own validator refuses."""
    members = members_for(engine)
    out = {}
    for raw_key, raw in form.items():
        key = raw_key[len(FORM_PREFIX):] if raw_key.startswith(FORM_PREFIX) else raw_key
        if key in LOCKED_KEYS:
            why = next(l.why for l in LOCKED if l.key == key)
            raise KnobError(f"{key} is locked: {why}")
        knob = BY_KEY.get(key)
        if knob is None:
            raise KnobError(f"unknown knob {key!r}")
        if _is_blank(raw) or not applies(knob, members, oracle_step):
            continue
        out[key] = _coerce(knob, raw, forecast_date)
    # dependent knob: the auxiliary weight means nothing without a pool
    if out.get("groundhog.aux") == "none":
        out.pop("groundhog.aux_weight", None)
    return out


def defaults(forecast_date: Optional[str] = None) -> dict:
    """{key: shipped value}; a date-dependent knob is left out without a date."""
    return {k.key: k.default_for(forecast_date) for k in REGISTRY
            if forecast_date or not callable(k.default)}


def non_default(values: Mapping, forecast_date: Optional[str] = None) -> dict:
    """The values that differ from the shipped ones (a date-dependent knob
    is compared against its default for `forecast_date`)."""
    out = {}
    for key, v in values.items():
        knob = BY_KEY.get(key)
        if knob is None:
            raise KnobError(f"unknown knob {key!r}")
        if v != knob.default_for(forecast_date):
            out[key] = v
    return out


def _canonical(values: Mapping) -> str:
    return json.dumps({k: list(v) if isinstance(v, tuple) else v
                       for k, v in values.items()},
                      sort_keys=True, separators=(",", ":"))


def digest(values: Mapping) -> str:
    """8 hex characters of sha256 over the canonical JSON; pass
    non_default(...) for a run's identity (the shipped set is {})."""
    return hashlib.sha256(_canonical(values).encode()).hexdigest()[:8]


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "on" if v else "off"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, tuple):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    return str(v)


def label(values: Mapping) -> str:
    """'shipped', or 'modified: oracle.w=0.25, pf.particles=2,000 (a1b2c3d4)'
    for a non_default(...) set."""
    if not values:
        return "shipped"
    body = ", ".join(f"{k}={_fmt(values[k])}" for k in sorted(values))
    return f"modified: {body} ({digest(values)})"


# --- reading a spec ----------------------------------------------------------------

def _get(spec, name, default=None):
    if isinstance(spec, Mapping):
        return spec.get(name, default)
    return getattr(spec, name, default)


def _aux_preset_of(extra: Mapping) -> str:
    pools = extra.get("aux_pools")
    if not pools:
        return "none"
    name = str(extra.get("analogue_aux") or "").split("+", 1)[0]
    if name in EA.AUX_PRESETS:
        return name
    streams = sorted(p.get("stream") for p in pools)
    for preset, cfg in EA.AUX_PRESETS.items():
        if sorted(p["stream"] for p in cfg) == streams:
            return preset
    return "custom"


def _read(knob: Knob, spec, extra: Mapping):
    key = knob.key
    if key == "pf.particles":
        return int(_get(spec, "particles"))
    if key == "pf.replicates":
        return int(_get(spec, "replicates"))
    if key == "pf.jitter":
        return float(_get(spec, "jitter"))
    if key == "run.season_start":
        return str(_get(spec, "season_start") or "") or knob.default_for(
            _get(spec, "forecast_date"))
    if key == "run.weeks_to_drop":
        return int(_get(spec, "weeks_to_drop") or 0)
    if key == "run.drop_same_day":
        return bool(_get(spec, "drop_same_day"))
    if key.startswith("pf.prior."):
        name = f"{key.rsplit('.', 1)[1]}__FREE"
        got = (extra.get("prior_ranges") or {}).get(name)
        return tuple(float(x) for x in got) if got else knob.default
    if key == "pf.initialization":
        return str(extra.get("initialization") or "rand")
    if key == "groundhog.aux":
        return _aux_preset_of(extra)
    if key == "groundhog.aux_weight":
        pools = extra.get("aux_pools") or ()
        return float(sum(float(p.get("weight", 0)) for p in pools))
    # knobs with no engine key yet live in extra["knobs"] (Stage 2)
    return (extra.get("knobs") or {}).get(key, knob.default)


def effective(spec) -> list:
    """The full knob table of a RunSpec (or its JSON dict): one row per
    knob with key, value, default, modified, applies, klass, affects."""
    extra = _get(spec, "extra") or {}
    engine = str(_get(spec, "engine") or "all")
    members = ENGINE_MEMBERS.get(engine, BOTH)
    step = str(extra.get("oracle") or "") != "none"
    fd = _get(spec, "forecast_date")
    no_aux = _aux_preset_of(extra) == "none"
    rows = []
    for k in REGISTRY:
        ok = applies(k, members, step) and not (
            no_aux and k.key == "groundhog.aux_weight")
        default = k.default_for(fd) if (fd or not callable(k.default)) else None
        value = _read(k, spec, extra) if ok else None
        rows.append({"key": k.key, "value": value, "default": default,
                     "modified": ok and value != default, "applies": ok,
                     "klass": k.klass, "affects": sorted(k.affects)})
    return rows


def describe() -> list:
    """JSON-safe registry rows, for `flubnf knobs --json` and the panel."""
    rows = []
    for k in REGISTRY:
        dflt = ("August 1 of the forecast's season" if callable(k.default)
                else list(k.default) if isinstance(k.default, tuple) else k.default)
        rows.append({
            "key": k.key, "label": k.label, "default": dflt,
            "kind": k.kind, "lo": k.lo, "hi": k.hi,
            "choices": list(k.choices), "range": k.range_text(),
            "unit": k.unit, "affects": sorted(k.affects), "stage": k.stage,
            "class": k.klass, "overridable": k.overridable,
            "source": k.source, "help": k.help,
            "card": ({"file": k.card[0],
                      "phrase": k.card[1].get(_card_key(k))} if k.card else None)})
    return rows


def _card_key(knob: Knob):
    """The shipped value as the card binding keys it (a season start by
    its month and day)."""
    if callable(knob.default):
        return knob.default("2000-10-07")[5:]
    return knob.default


# --- Stage 2: knobs reach the models ------------------------------------------------
#
# THE RECORD. A run built through the knob channel with any value off the
# shipped one carries spec.extra["knobs"] = its non-default values (JSON
# form) and, when the operator exported under the hub names anyway,
# spec.extra["knobs_override"] = the typed reason. A spec without the key is
# shipped whatever its legacy fields say: old ledger rows (replicates=1 test
# runs, 20,000-particle research runs, bare-analogue rows) are never
# reclassified. Each value is ALSO written where its engine reads it
# (RunSpec fields, extra["prior_ranges"], extra["initialization"], the
# resolved aux pools); knobs with no engine key are read from the record.

RECORD_KEY = "knobs"
OVERRIDE_KEY = "knobs_override"
#: appended to the hub model id of a modified run's files
MODIFIED_SUFFIX = "-modified"

#: knobs with no engine parameter yet: shown disabled ("coming later") and
#: refused when set off their default; every run uses the shipped value
LATER = frozenset({"oracle.bandwidth", "oracle.count_floor",
                   "oracle.min_donor_seasons", "oracle.min_paths",
                   "groundhog.min_donors"})

#: knobs the retrospective cannot carry: retro.run_week drops no weeks and
#: stores unfloored samples (the floor is a console output rule)
NOT_IN_RETRO = frozenset({"run.weeks_to_drop", "output.floor_lam"})

#: form fields that predate the registry -> the knob they now set
LEGACY_FIELDS = {"particles": "pf.particles", "replicates": "pf.replicates",
                 "season_start": "run.season_start",
                 "weeks_to_drop": "run.weeks_to_drop",
                 "drop_same_day": "run.drop_same_day"}
FIELD_OF = {v: k for k, v in LEGACY_FIELDS.items()}

#: knob -> RunSpec field on a console run
_SPEC_FIELDS = {"pf.particles": "particles", "pf.replicates": "replicates",
                "pf.jitter": "jitter", "run.season_start": "season_start",
                "run.weeks_to_drop": "weeks_to_drop",
                "run.drop_same_day": "drop_same_day"}


def wired(key: str) -> bool:
    return key in BY_KEY and key not in LATER


def in_scope(key: str, scope: str) -> bool:
    """scope: "forecast" (the console) or "retro"."""
    return not (scope == "retro" and key in NOT_IN_RETRO)


def jsonable(values: Mapping) -> dict:
    """The record form: tuples become lists, keys sorted."""
    return {k: (list(v) if isinstance(v, tuple) else v)
            for k, v in sorted(values.items())}


def resolve(form: Mapping, engine="all", *, scope: str = "forecast",
            forecast_date: Optional[str] = None, oracle_step: bool = True,
            legacy: Optional[Mapping] = None, two_strain: bool = False,
            check_dates: tuple = ()) -> dict:
    """A run's non-default knob values from the panel's `knob.<key>` fields
    (or a CLI/JSON dict) plus the legacy form fields (`legacy`: {field:
    raw}, LEGACY_FIELDS). One source of truth: a legacy field left at the
    shipped value yields to its knob; two different off-shipped values are
    refused. Also refuses (KnobError) what parse refuses, a coming-later
    knob set off its default, a knob the scope cannot carry, and a prior
    knob with the two-strain member (its parameters differ).
    `check_dates`: further dates a date knob must also precede (a
    season's later weeks)."""
    typed = parse(form, engine, forecast_date=forecast_date,
                  oracle_step=oracle_step)
    for field_name, raw in (legacy or {}).items():
        key = LEGACY_FIELDS.get(field_name)
        if key is None:
            raise KnobError(f"unknown legacy field {field_name!r}")
        got = parse({key: raw}, engine, forecast_date=forecast_date,
                    oracle_step=oracle_step)
        if key not in got:
            continue
        v, shipped = got[key], BY_KEY[key].default_for(forecast_date)
        if v == shipped:
            continue                    # the untouched legacy field yields
        if key in typed and typed[key] not in (shipped, v):
            raise KnobError(f"{key}: the form gives two values ({_fmt(v)} "
                            f"and {_fmt(typed[key])}); give one")
        typed[key] = v
    nd = non_default(typed, forecast_date)
    for key, v in nd.items():
        if key in LATER:
            raise KnobError(f"{key} is not wired to its engine yet (coming "
                            f"later); every run uses "
                            f"{_fmt(BY_KEY[key].default)}")
        if not in_scope(key, scope):
            raise KnobError(f"{key} cannot be set for a retrospective")
        if two_strain and key.startswith("pf.prior."):
            raise KnobError(f"{key}: the two-strain research member has "
                            f"other parameters; prior knobs are refused "
                            f"with it")
        if BY_KEY[key].kind == "date":
            for d in check_dates:
                _coerce(BY_KEY[key], v, d)
    return nd


def from_record(record: Mapping) -> dict:
    """Typed values from a recorded knobs dict (lists back to tuples)."""
    out = {}
    for key, v in (record or {}).items():
        knob = BY_KEY.get(key)
        if knob is None:
            raise KnobError(f"unknown knob {key!r} in the record")
        out[key] = tuple(float(x) for x in v) if knob.kind == "range" else v
    return out


def aux_choice(nd: Mapping, fallback):
    """The Groundhog preset a run asks for: nd's groundhog.aux ("none" ->
    "", the bare analogue), else `fallback` (None = the shipped preset)."""
    if "groundhog.aux" in nd:
        return "" if nd["groundhog.aux"] == "none" else nd["groundhog.aux"]
    return fallback


def write_extra(nd: Mapping, extra: dict, *, retro: bool = False,
                override: str = "") -> dict:
    """Write non-default values where the engines read them, plus the
    record. `extra` must already hold the resolved aux pools (the weight
    knob rescales them). A retrospective has no RunSpec-field channel, so
    its jitter and season start go through extra (retro.run_week reads
    both). An empty nd writes nothing: a shipped spec is unchanged."""
    if not nd:
        return extra
    for key, v in nd.items():
        if key.startswith("pf.prior."):
            name = f"{key.rsplit('.', 1)[1]}__FREE"
            extra.setdefault("prior_ranges", {})[name] = [float(x) for x in v]
        elif key == "pf.initialization":
            extra["initialization"] = v
        elif retro and key == "pf.jitter":
            extra["jitter"] = float(v)
        elif retro and key == "run.season_start":
            extra["season_start"] = v
        elif key == "groundhog.aux_weight":
            pools = extra.get("aux_pools") or []
            total = sum(float(p.get("weight", 0)) for p in pools)
            if pools and total > 0:
                extra["aux_pools"] = [
                    {**p, "weight": float(p["weight"]) * float(v) / total}
                    for p in pools]
    extra[RECORD_KEY] = jsonable(nd)
    if override:
        extra[OVERRIDE_KEY] = str(override)
    return extra


def spec_fields(nd: Mapping) -> dict:
    """RunSpec keyword arguments a console run's knobs set."""
    return {_SPEC_FIELDS[k]: v for k, v in nd.items() if k in _SPEC_FIELDS}


def _extra_of(spec) -> Mapping:
    if isinstance(spec, str):
        try:
            spec = json.loads(spec or "{}")
        except (TypeError, ValueError):
            return {}
    extra = _get(spec, "extra") if spec is not None else None
    return extra if isinstance(extra, Mapping) else {}


def record_of(spec) -> dict:
    """The knobs record a spec (RunSpec, dict or JSON) carries; {} for a
    shipped or legacy spec."""
    rec = _extra_of(spec).get(RECORD_KEY)
    return dict(rec) if isinstance(rec, Mapping) else {}


def modified(spec) -> bool:
    """True only for a spec carrying a non-empty knobs record."""
    return bool(record_of(spec))


def override_reason(spec) -> str:
    return str(_extra_of(spec).get(OVERRIDE_KEY) or "")


def hub_names(spec) -> bool:
    """Whether a run's files go out under the hub model names: shipped, or
    modified with an override and its reason."""
    return not modified(spec) or bool(override_reason(spec))


def step_values(extra) -> dict:
    """The Oracle-step knob values a spec's extra records (apply_week)."""
    rec = extra.get(RECORD_KEY) if isinstance(extra, Mapping) else None
    return {k: v for k, v in (rec or {}).items()
            if k in BY_KEY and BY_KEY[k].stage == "step"}


def value_of(extra, key: str):
    """A recorded knob value from a spec's extra; None when shipped."""
    rec = extra.get(RECORD_KEY) if isinstance(extra, Mapping) else None
    return (rec or {}).get(key)


def fit_extra(extra: Mapping) -> dict:
    """extra as a retro week's FIT manifest records it: post-fit knobs
    (Oracle step, Groundhog) are left out of the record copy, so a change
    to them alone never invalidates fitted cells."""
    out = dict(extra)
    rec = out.get(RECORD_KEY)
    if isinstance(rec, Mapping):
        fit = {k: v for k, v in rec.items()
               if k in BY_KEY and BY_KEY[k].stage == "fit"}
        if fit:
            out[RECORD_KEY] = fit
        else:
            out.pop(RECORD_KEY)
    return out


def summary(record: Mapping, override: str = "") -> dict:
    """What a modified run's records carry (results.json, knobs.json)."""
    return {"values": jsonable(record), "digest": digest(record),
            "label": label(from_record(record)),
            "override": ({"reason": override} if override else None),
            "files": ("hub names, by override" if override
                      else f"non-hub names (<hub id>{MODIFIED_SUFFIX})")}


def _json_value(v):
    return list(v) if isinstance(v, tuple) else v


def write_record(path, spec) -> bool:
    """knobs.json for a modified run: values, digest, override and the full
    effective table. Nothing for a shipped run (its files are unchanged)."""
    rec = record_of(spec)
    if not rec:
        return False
    import os
    from pathlib import Path
    body = {**summary(rec, override_reason(spec)),
            "effective": [{**r, "value": _json_value(r["value"]),
                           "default": _json_value(r["default"])}
                          for r in effective(spec)]}
    p = Path(path)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(body, indent=1, sort_keys=True))
    os.replace(tmp, p)
    return True


def legacy_settings_knobs(settings: Mapping) -> dict:
    """The non-default knob set a retrospective's run record implies: its
    recorded knobs, or, for a record from before the registry, what its
    particles, replicates and same-day choice state."""
    s = settings if isinstance(settings, Mapping) else {}
    if isinstance(s.get(RECORD_KEY), Mapping):
        return jsonable(s[RECORD_KEY])
    out = {}
    for field_name, key in (("particles", "pf.particles"),
                            ("replicates", "pf.replicates")):
        try:
            v = int(s.get(field_name) or 0)
        except (TypeError, ValueError):
            v = 0
        if v and v != BY_KEY[key].default:
            out[key] = v
    if bool(s.get("drop_same_day")) != BY_KEY["run.drop_same_day"].default:
        out["run.drop_same_day"] = bool(s.get("drop_same_day"))
    return out


#: knobs a retrospective takes as run_season ARGUMENTS, not week extra
RETRO_ARG_KEYS = frozenset({"pf.particles", "pf.replicates",
                            "run.drop_same_day"})


# --- Stage 3: the Model settings panel (templates/_model_settings.html) --------------

#: (group id, heading, one-line tip) in panel order
PANEL_GROUPS = (
    ("data", "Fit window",
     "Which reported weeks the models see. A change refits the Oracle SIHRS."),
    ("fit", "Oracle SIHRS: particle filter",
     "Settings of the fit itself; a change refits every state."),
    ("step", "Oracle SIHRS: Oracle step",
     "Runs after the fit on its samples; a change costs no refit."),
    ("groundhog", "Groundhog",
     "The calendar analogue; instant. Its donor settings are independent "
     "of the Oracle step's."),
    ("output", "Output",
     "Applied to the finished forecasts of a console run."),
)
#: the fit group's order: run-class first (what a person changes most)
_FIT_ORDER = ("pf.replicates", "pf.particles", "pf.jitter",
              "pf.initialization")
MEMBER_NAMES = {"pf": "Oracle SIHRS", "analogue": "Groundhog"}


def _group_of(knob: Knob) -> str:
    return "data" if knob.key.startswith("run.") else knob.stage


def _raw(knob: Knob, v) -> str:
    """A value as the panel's input holds it."""
    if v is None:
        return ""
    if knob.kind == "bool":
        return "1" if v else "0"
    if knob.kind == "range":
        return ", ".join(f"{float(x):g}" for x in v)
    if knob.kind == "float":
        return f"{float(v):g}"
    return str(v)


def _tip(knob: Knob, scope: str) -> str:
    who = " and ".join(MEMBER_NAMES[m] for m in MEMBERS if m in knob.affects)
    dflt = ("August 1 of the forecast's season" if callable(knob.default)
            else _fmt(knob.default))
    unit = f" {knob.unit}" if knob.unit and knob.kind in ("int", "float") else ""
    bits = [knob.help, f"Range: {knob.range_text()}{unit}.",
            f"Shipped: {dflt}.", f"Affects: {who}."]
    if knob.card:
        bits.append("The model card states the shipped value.")
    if knob.key in LATER:
        bits.append("Coming later: not wired to its engine yet, so every "
                    "run uses the shipped value.")
    return " ".join(bits)


def panel(scope: str, values: Optional[Mapping] = None) -> dict:
    """The Model settings panel, rendered by templates/_model_settings.html.

    `scope` "forecast" or "retro"; `values` {key: raw} the form held (a
    refused submission keeps what was typed). Knobs with an older field
    name keep it (season_start, weeks_to_drop, drop_same_day, replicates,
    particles), so every earlier poster still works; the rest post as
    knob.<key>. Coming-later knobs render disabled."""
    values = dict(values or {})
    groups = []
    for gid, title, tip in PANEL_GROUPS:
        ks = [k for k in REGISTRY if _group_of(k) == gid
              and in_scope(k.key, scope)]
        if gid == "fit":
            rank = {key: i for i, key in enumerate(_FIT_ORDER)}
            ks.sort(key=lambda k: rank.get(k.key, len(rank)))
        rows = []
        for k in ks:
            dflt = "" if callable(k.default) else _raw(k, k.default)
            got = values.get(k.key)
            val = dflt if got is None else str(got)
            if k.key in LATER:
                val = dflt
            rows.append({
                "key": k.key, "label": k.label, "kind": k.kind,
                "name": FIELD_OF.get(k.key, FORM_PREFIX + k.key),
                "id": "ks-" + k.key.replace(".", "-"),
                "value": val, "default": dflt,
                "placeholder": ("" if callable(k.default)
                                else f"shipped: {_fmt(k.default)}"),
                "min": k.lo, "max": k.hi,
                "step": "any" if k.kind == "float" else "1",
                "choices": [(str(c), f"{c}" + (" (shipped)" if c == k.default
                                               else "")) for c in k.choices],
                "later": k.key in LATER,
                "affects": " ".join(sorted(k.affects)),
                "unit": k.unit, "tip": _tip(k, scope)})
        if rows:
            groups.append({"id": gid, "title": title, "tip": tip,
                           "affects": " ".join(sorted(
                               {m for r in rows for m in r["affects"].split()})),
                           "rows": rows})
    modified = any(r["value"].strip() not in ("", r["default"])
                   for g in groups for r in g["rows"] if not r["later"])
    return {"scope": scope, "groups": groups, "modified": modified,
            "locked": [{"key": l.key, "value": _fmt(l.value)
                        if not isinstance(l.value, tuple)
                        else ", ".join(map(str, l.value)),
                        "why": l.why} for l in LOCKED],
            "override": scope == "forecast",
            "suffix": MODIFIED_SUFFIX}


def retro_week_extra(base, nd: Mapping):
    """Wrap a retro week_extra callable so each week's extra carries the
    knobs that travel in extra (not RETRO_ARG_KEYS, which are run_season
    arguments), renamed '<base>+knobs@<digest>'; `base` itself when none
    is set, so a shipped replay's recorded name is unchanged."""
    snap = {k: v for k, v in nd.items() if k not in RETRO_ARG_KEYS}
    if not snap:
        return base

    def _extra(asof, i, vintages):
        d = dict(base(asof, i, vintages) or {}) if base else {}
        return write_extra(snap, d, retro=True)

    _extra.__name__ = (f"{getattr(base, '__name__', 'custom')}"
                       f"+knobs@{digest(jsonable(snap))}")
    return _extra
