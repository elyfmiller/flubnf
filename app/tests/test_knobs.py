"""Drift guards for the model-knob registry (app/core/knobs.py).

Every shipped value is read from its source constant, so the registry cannot
drift from the code; these tests hold the other ends: the source labels
resolve, each card phrase is bound to the shipped VALUE (a changed constant
fails until the card is updated), and parse refuses what the engines refuse.
"""
import dataclasses
import importlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.core import floor as FL
from app.core import submit as SB
from app.core import knobs as K
from app.core import missing as MS
from app.core.engines import analogue as EA
from app.core.engines import pf as PF
from app.core.runs import RunSpec, default_season_start
from flubnf import analogue as AN
from flubnf import oracle as OR
from flubnf import oracle_bank as OB
from flubnf import oracle_mix as MX

REPO = Path(__file__).resolve().parents[2]
FD = "2026-10-03"                       # a Saturday in the 2026-27 season


# --- defaults and sources --------------------------------------------------------

SOURCES = {
    "pf.particles": RunSpec.particles,
    "pf.replicates": RunSpec.replicates,
    "pf.jitter": RunSpec.jitter,
    "pf.prior.Reff": (0.6, 2.5),
    "pf.prior.eps1": (0.0, 1.0),
    "pf.prior.phi1": (0.0, 52.0),
    "pf.prior.mult": (0.002, 1.0),
    "pf.prior.r": (0.1, 40.0),
    "pf.initialization": PF.initialization_for(RunSpec("pf", FD)),
    "run.weeks_to_drop": RunSpec.weeks_to_drop,
    "run.drop_same_day": RunSpec.drop_same_day,
    "data.trailing_zero": MS.TRAILING_ZERO,
    "data.partial_week": MS.PARTIAL_WEEK,
    "oracle.w": OR.W_PRODUCTION,
    "oracle.w_aux": MX.W_AUX,
    "oracle.submitted_seed": OR.SUBMITTED_SEED,
    "oracle.bandwidth": AN.DEFAULT_BANDWIDTH,
    "oracle.count_floor": OB.COUNT_FLOOR,
    "oracle.min_donor_seasons": OB.MIN_DONOR_SEASONS,
    "oracle.min_paths": AN.MIN_DONORS,
    "groundhog.aux": EA.SHIPPED_AUX,
    "groundhog.aux_weight": sum(p["weight"]
                                for p in EA.AUX_PRESETS[EA.SHIPPED_AUX]),
    "groundhog.bandwidth": AN.DEFAULT_BANDWIDTH,
    "groundhog.min_donors": AN.MIN_DONORS,
    "output.floor_lam": FL.LAM,
    "output.horizon_minus1": SB.HORIZON_MINUS1,
    "output.rate_change_pmf": SB.RATE_CHANGE_PMF,
}


def test_every_knob_has_a_source_test():
    assert set(SOURCES) | {"run.season_start"} == set(K.BY_KEY)


@pytest.mark.parametrize("key", sorted(SOURCES))
def test_default_equals_its_source_constant(key):
    assert K.BY_KEY[key].default == SOURCES[key]


def test_prior_defaults_are_the_filters_prior_block():
    block = PF.priors_for(RunSpec("pf", FD))
    parsed = {}
    for line in block.splitlines():
        name, lo, hi = line.split("=", 1)[1].split()
        parsed[name] = (float(lo), float(hi))
    assert parsed == K.PRIOR_DEFAULTS
    assert len(K.PRIOR_DEFAULTS) == len(PF.VARS_1S.strip().splitlines())


def test_season_start_default_is_date_dependent():
    k = K.BY_KEY["run.season_start"]
    assert k.default is default_season_start
    assert k.default_for("2026-10-03") == "2026-08-01"
    assert k.default_for("2027-02-06") == "2026-08-01"
    assert RunSpec("pf", FD).season_start == k.default_for(FD)
    with pytest.raises(K.KnobError):
        k.default_for(None)


@pytest.mark.parametrize("k", K.REGISTRY + K.LOCKED, ids=lambda k: k.key)
def test_source_label_resolves(k):
    mod, _, path = k.source.partition(":")
    obj = importlib.import_module(mod)
    for part in path.split("[", 1)[0].split("."):
        obj = getattr(obj, part)


def test_registry_is_well_formed():
    assert len(K.BY_KEY) == len(K.REGISTRY)
    assert not K.LOCKED_KEYS & set(K.BY_KEY)
    for k in K.REGISTRY:
        assert k.kind in K.KINDS and k.stage in K.STAGES, k.key
        assert k.klass in ("run", "method", "optional"), k.key
        assert k.affects and k.affects <= K.BOTH, k.key
        assert k.label and k.help and "\n" not in k.help, k.key
        assert len(k.help) <= 100, k.key
        assert k.overridable
        if k.kind in ("int", "float"):
            assert k.lo <= k.default <= k.hi, k.key
        if k.kind == "choice":
            assert k.default in k.choices, k.key
        if k.stage == "step":
            assert k.affects == K.PF_ONLY, k.key
    assert {k.key for k in K.REGISTRY if k.klass == "run"} == {
        "pf.particles", "pf.replicates", "run.season_start",
        "run.weeks_to_drop", "run.drop_same_day", "data.trailing_zero",
        "data.partial_week"}
    # the optional hub rows: off by default, both members, the output stage
    assert K.OPTIONAL_KEYS == {"output.horizon_minus1",
                               "output.rate_change_pmf"}
    for key in K.OPTIONAL_KEYS:
        k = K.BY_KEY[key]
        assert (k.kind, k.default, k.affects, k.stage) == (
            "bool", False, K.BOTH, "output"), key
        assert k.help.startswith("Optional;"), key


def test_shipped_defaults_parse_back_to_themselves():
    form = {}
    for k in K.REGISTRY:
        d = k.default_for(FD)
        form[k.key] = ",".join(map(str, d)) if isinstance(d, tuple) else str(d)
    got = K.parse(form, "all", forecast_date=FD)
    assert got == K.defaults(FD)
    assert K.non_default(got, FD) == {}


# --- model cards: the phrase is bound to the value --------------------------------

def _card_text(name):
    return " ".join((REPO / "model-metadata" / name).read_text().split())


CARD_KNOBS = [k for k in K.REGISTRY if k.card]


@pytest.mark.parametrize("k", CARD_KNOBS, ids=lambda k: k.key)
def test_card_states_the_shipped_value(k):
    card, phrases = k.card
    key = K._card_key(k)
    assert key in phrases, (
        f"{k.key}: the shipped value {key!r} has no card phrase bound to it; "
        f"update the model card (and its model_version) and the binding")
    assert phrases[key] in _card_text(card)


def test_a_changed_constant_fails_the_card_binding():
    k = dataclasses.replace(K.BY_KEY["oracle.w"], default=0.4)
    assert K._card_key(k) not in k.card[1]


def test_the_cards_named_exist():
    for k in CARD_KNOBS:
        assert (REPO / "model-metadata" / k.card[0]).is_file()


# --- parse --------------------------------------------------------------------------

def test_parse_canonicalises():
    got = K.parse({"knob.pf.particles": "10,000", "oracle.w": "0.50",
                   "run.drop_same_day": "off", "pf.prior.r": "0.1, 40"},
                  "all", forecast_date=FD)
    assert got == {"pf.particles": 10_000, "oracle.w": 0.5,
                   "run.drop_same_day": False, "pf.prior.r": (0.1, 40.0)}
    assert K.non_default(got) == {}


def test_parse_drops_blanks():
    assert K.parse({"pf.particles": "", "oracle.w": None,
                    "run.season_start": " "}, "all") == {}


@pytest.mark.parametrize("form, msg", [
    ({"pf.particle": "10"}, "unknown knob"),
    ({"gamma": "2"}, "locked"),
    ({"horizons": "5"}, "locked"),
    ({"pf.particles": "500"}, "outside"),
    ({"pf.particles": "100001"}, "outside"),
    ({"pf.particles": "2.5"}, "not a valid int"),
    ({"pf.particles": 2.5}, "not a valid int"),
    ({"pf.particles": True}, "not a valid int"),
    ({"pf.particles": "lots"}, "not a valid int"),
    ({"oracle.w": "nan"}, "finite"),
    ({"oracle.w": "inf"}, "finite"),
    ({"oracle.w": "1.5"}, "outside"),
    ({"pf.jitter": "0"}, "outside"),
    ({"run.drop_same_day": "maybe"}, "not a valid bool"),
    ({"pf.initialization": "sobol"}, "not one of"),
    ({"oracle.submitted_seed": "12"}, "not one of"),
    ({"groundhog.aux": "nrevss"}, "not one of"),
    ({"pf.prior.mult": "0, 1"}, "loguniform"),          # the engine's rule
    ({"pf.prior.r": "5, 1"}, "not a valid"),
    ({"pf.prior.r": "0.1, inf"}, "finite"),
    ({"pf.prior.r": "0.1"}, "not a valid range"),
    ({"run.season_start": "2026-13-01"}, "not a valid date"),
    ({"run.season_start": "2026-10-03"}, "not before"),
    ({"run.season_start": "2025-08-01"}, "within 400"),
])
def test_parse_refuses(form, msg):
    with pytest.raises(K.KnobError, match=msg):
        K.parse(form, "all", forecast_date=FD)


def test_parse_needs_a_date_for_season_start():
    with pytest.raises(K.KnobError, match="forecast date"):
        K.parse({"run.season_start": "2026-08-01"}, "all")


def test_season_start_is_compared_against_its_date_default():
    got = K.parse({"run.season_start": "2026-08-01"}, "all", forecast_date=FD)
    assert K.non_default(got, FD) == {}
    got = K.parse({"run.season_start": "2026-09-01"}, "all", forecast_date=FD)
    assert K.non_default(got, FD) == {"run.season_start": "2026-09-01"}
    with pytest.raises(K.KnobError):
        K.non_default(got)


def test_knobs_that_do_not_apply_are_ignored():
    form = {"pf.particles": "2000", "oracle.w": "0.25",
            "groundhog.bandwidth": "3", "run.weeks_to_drop": "1"}
    assert set(K.parse(form, "pf")) == {"pf.particles", "oracle.w",
                                        "run.weeks_to_drop"}
    assert set(K.parse(form, "analogue")) == {"groundhog.bandwidth",
                                              "run.weeks_to_drop"}
    assert set(K.parse(form, "all", oracle_step=False)) == {
        "pf.particles", "groundhog.bandwidth", "run.weeks_to_drop"}
    assert set(K.parse(form, {"pf", "analogue"})) == set(form)
    # an inapplicable knob is still checked for being a knob at all
    with pytest.raises(K.KnobError, match="unknown"):
        K.parse({"groundhog.bandwith": "3"}, "pf")


def test_aux_weight_is_dropped_without_an_aux_pool():
    got = K.parse({"groundhog.aux": "none", "groundhog.aux_weight": "0.3"},
                  "analogue")
    assert got == {"groundhog.aux": "none"}


def test_unknown_engine_refused():
    for bad in ("amcmc", set(), {"pf", "einn"}):
        with pytest.raises(K.KnobError):
            K.parse({}, bad)


# --- identity -----------------------------------------------------------------------

def test_digest_is_stable_order_independent_and_value_sensitive():
    a = {"pf.particles": 2000, "oracle.w": 0.25, "pf.prior.r": (0.1, 80.0)}
    b = dict(reversed(list(a.items())))
    assert K.digest(a) == K.digest(b) == "cd022d0d"
    assert K.digest({}) == "44136fa3"
    assert K.digest({**a, "oracle.w": 0.3}) != K.digest(a)
    assert K.digest({"pf.particles": 2000}) != K.digest({"pf.particles": 2001})


def test_label():
    assert K.label({}) == "default"
    nd = {"pf.particles": 2000, "oracle.w": 0.25}
    assert K.label(nd) == f"modified: oracle.w=0.25, pf.particles=2,000 ({K.digest(nd)})"


def test_non_default_refuses_unknown_keys():
    with pytest.raises(K.KnobError):
        K.non_default({"pf.particle": 2})


# --- effective(spec) ------------------------------------------------------------------

def _shipped(engine="all", **kw):
    extra = {"mode": "realtime", "aux_pools": EA.shipped_aux_pools(),
             "analogue_aux": EA.shipped_aux_label(), **kw.pop("extra", {})}
    return RunSpec(engine, FD, ["Ohio"], extra=extra, **kw)


def _modified(spec):
    return {r["key"]: r["value"] for r in K.effective(spec) if r["modified"]}


def test_effective_shipped_console_spec_is_unmodified():
    rows = K.effective(_shipped())
    assert {r["key"] for r in rows} == set(K.BY_KEY)
    assert not any(r["modified"] for r in rows)
    assert all(r["applies"] for r in rows)
    # the ledger's JSON form reads the same
    assert K.effective(json.loads(_shipped().to_json())) == rows


def test_effective_reads_fields_and_research_keys():
    spec = _shipped(particles=2000, jitter=0.30,
                    extra={"prior_ranges": {"r__FREE": [0.1, 200]},
                           "initialization": "lh"})
    assert _modified(spec) == {"pf.particles": 2000, "pf.jitter": 0.30,
                               "pf.prior.r": (0.1, 200.0),
                               "pf.initialization": "lh"}


def test_effective_skips_what_did_not_run():
    spec = _shipped("analogue", particles=2000)
    rows = {r["key"]: r for r in K.effective(spec)}
    assert not rows["pf.particles"]["applies"]
    assert not rows["pf.particles"]["modified"]
    spec = _shipped(extra={"oracle": "none", "knobs": {"oracle.w": 0.25}})
    rows = {r["key"]: r for r in K.effective(spec)}
    assert not rows["oracle.w"]["applies"] and not rows["oracle.w"]["modified"]
    assert rows["pf.particles"]["applies"]


def test_effective_bare_analogue_is_modified_and_drops_the_weight():
    spec = RunSpec("all", FD, ["Ohio"], extra={"mode": "realtime"})
    assert _modified(spec) == {"groundhog.aux": "none"}
    rows = {r["key"]: r for r in K.effective(spec)}
    assert not rows["groundhog.aux_weight"]["applies"]


# --- CLI ------------------------------------------------------------------------------

def test_cli_knobs_json_round_trips():
    from flubnf.cli import app
    r = CliRunner().invoke(app, ["knobs", "--json"])
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert [row["key"] for row in data["knobs"]] == [k.key for k in K.REGISTRY]
    row = {x["key"]: x for x in data["knobs"]}["pf.particles"]
    assert row["default"] == 10_000 and row["class"] == "run"
    assert row["affects"] == ["pf"] and row["lo"] == 1_000
    assert {x["key"] for x in data["locked"]} == K.LOCKED_KEYS


def test_cli_knobs_table_and_panel():
    from flubnf.cli import HELP_PANELS, app
    assert "knobs" in HELP_PANELS["Console"]
    r = CliRunner().invoke(app, ["knobs"], terminal_width=200)
    assert r.exit_code == 0, r.output
    assert "pf.particles" in r.output and "Locked" in r.output
