"""The seed denominator (research knob pf.seed_denominator): prepare()
reads extra["seed_denominator"], hands it to resolve_state, records the
pin in the cell only off the shipped value (the shipped cells.json is
unchanged), re-derives it with the expectation after a trim and refuses
it beside fit_i0; the knob round-trips through the registry.

Hub-free: resolve_state, the materializer, the exp writer, the vintage
path and netgen are faked as test_swarm_carry fakes them.
"""
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import knobs as K                          # noqa: E402
from app.core.engines import pf                          # noqa: E402
from app.core.runs import RunSpec, derive_seed           # noqa: E402
from flubnf.sihrs_fit import pin_from                    # noqa: E402
from flubnf.sihrs_priors import SEED_DENOMINATOR         # noqa: E402

FD = "2098-11-07"
POP, AR, GAMMA = 1_000_000, 0.18, 7.0 / 3.2
EXPECTED_PC = 2.0e-3            # the fake vintage's expectation per capita
RECORD = {"seasons": {"2096-97": 1.5e-3, "2097-98": 2.5e-3},
          "min_weeks": 35, "median": 2.0e-3, "mean": 2.0e-3}


class _State:
    """resolve_state's answer under the denominator it was asked for."""

    def __init__(self, seed_denominator=SEED_DENOMINATOR):
        self.times = [12, 13, 14]   # true offsets: newest = the as-of week
        self.observed = [4.0, 5.0, 6.0]
        self.n_obs = 3
        self.last_week_offset = 14
        self.population, self.attack_rate, self.gamma = POP, AR, GAMMA
        self.seed_denominator = seed_denominator
        if seed_denominator == "season_total":
            self.expected_total_pc, self.seed_record = EXPECTED_PC, dict(RECORD)
        else:
            self.expected_total_pc, self.seed_record = None, {}
        self.rhomult, self.i0, self.seed_factor = pin_from(
            self.observed, POP, AR, self.expected_total_pc, GAMMA)


def _spec(extra=None, weeks_to_drop=0):
    return type("S", (), {
        "forecast_date": FD, "season_start": "2098-08-01",
        "weeks_to_drop": weeks_to_drop, "drop_same_day": False,
        "locations": ["Ohio"], "replicates": 1,
        "particles": 100, "jitter": 0.3,
        "observable_mode": "integrated", "extra": extra})()


def _prep_env(monkeypatch, tmp_path):
    """test_swarm_carry's fakes; returns the list the fake resolve_state
    appends each denominator it is asked for to."""
    import app.core.data as data
    import flubnf.sihrs_fit as sf
    asked = []

    def fake_resolve(loc, **kw):
        asked.append(kw["seed_denominator"])
        return _State(kw["seed_denominator"])

    def fake_materialize(s, template, out_path, suffix, extra_tokens=None,
                         **kw):
        p = Path(out_path)
        p.write_text("begin parameters\nend parameters\n")
        return p

    def fake_netgen(cmd, **kw):
        (Path(kw.get("cwd", ".")) / "m.net").write_text("# net\n")
        return types.SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(sf, "resolve_state", fake_resolve)
    monkeypatch.setattr(sf, "materialize_model", fake_materialize)
    monkeypatch.setattr(sf, "write_exp",
                        lambda s, p: Path(p).write_text("# t v\n"))
    vfile = tmp_path / "vintage.csv"
    vfile.write_text("date,location,location_name,value\n")
    monkeypatch.setattr(data, "vintage_path", lambda d: str(vfile))
    monkeypatch.setattr(pf.subprocess, "run", fake_netgen)
    return asked


# ------------------------------------------------------------------ prepare()

def test_prepare_records_the_pin_off_the_shipped_denominator(monkeypatch,
                                                              tmp_path):
    asked = _prep_env(monkeypatch, tmp_path)
    c = pf.prepare(_spec({"seed_denominator": "season_total"}),
                   tmp_path / "wr")[0]
    assert asked == ["season_total"]
    want = _State("season_total")
    assert c["seed_pin"] == {"denominator": "season_total",
                             "rhomult": want.rhomult,
                             "factor": want.seed_factor,
                             "expected_total_pc": EXPECTED_PC, **RECORD}
    assert c["seed_pin"]["factor"] == pytest.approx(EXPECTED_PC / (15.0 / POP))
    assert c["i0"] == want.i0
    # the engine seed beside it is untouched
    assert c["seed"] == derive_seed("Ohio", FD, 0)
    cells = json.loads((tmp_path / "wr" / "cells.json").read_text())
    assert cells[0]["seed_pin"]["denominator"] == "season_total"


def test_the_shipped_prepare_records_no_pin(monkeypatch, tmp_path):
    """Without the key, or with it at the shipped value, the cell has no
    seed_pin: cells.json is byte-identical to before the knob."""
    asked = _prep_env(monkeypatch, tmp_path)
    plain = pf.prepare(_spec(None), tmp_path / "wr")[0]
    named = pf.prepare(_spec({"seed_denominator": "to_date"}),
                       tmp_path / "wr2")[0]
    assert asked == ["to_date", "to_date"]
    assert "seed_pin" not in plain and "seed_pin" not in named
    assert plain["i0"] == named["i0"] == _State().i0
    assert plain["seed"] == derive_seed("Ohio", FD, 0)


def test_a_trim_rederives_the_pin_with_the_expectation(monkeypatch, tmp_path):
    """weeks_to_drop: the trimmed series re-pins, still floored at the
    expectation (the to-date count shrinks, so the factor grows); the
    shipped trim re-pins on the to-date count as before."""
    _prep_env(monkeypatch, tmp_path)
    c = pf.prepare(_spec({"seed_denominator": "season_total"}, weeks_to_drop=1),
                   tmp_path / "wr")[0]
    rm, i0, factor = pin_from([4.0, 5.0], POP, AR, EXPECTED_PC, GAMMA)
    assert c["weeks_dropped"] == 1 and c["n_obs"] == 2
    assert c["seed_pin"]["rhomult"] == rm and c["seed_pin"]["factor"] == factor
    assert c["i0"] == i0 and factor > _State("season_total").seed_factor
    plain = pf.prepare(_spec(None, weeks_to_drop=1), tmp_path / "wr2")[0]
    rm, i0, factor = pin_from([4.0, 5.0], POP, AR, None, GAMMA)
    assert plain["i0"] == i0 and factor == 1.0 and "seed_pin" not in plain


def test_fit_i0_and_season_total_are_refused(monkeypatch, tmp_path):
    _prep_env(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="fit_i0 and seed_denominator"):
        pf.prepare(_spec({"seed_denominator": "season_total",
                          "fit_i0": [1e-6, 1e-3]}), tmp_path / "wr")
    assert not list((tmp_path / "wr").glob("*/m.bngl"))
    with pytest.raises(ValueError, match="seed_denominator must be one of"):
        pf.prepare(_spec({"seed_denominator": "median"}), tmp_path / "wr2")


# ------------------------------------------------------------------ the knob

def test_the_knob_round_trips_through_the_registry():
    """resolve -> write_extra puts the engine key where prepare() reads it,
    effective() reads it back, label() shows it; the retro scope carries
    it and its fit manifest keeps it."""
    form = {"pf.seed_denominator": "season_total"}
    nd = K.resolve(form, "all", forecast_date=FD)
    assert nd == form
    assert K.resolve(form, "all", scope="retro", forecast_date=FD) == nd
    extra = K.write_extra(nd, {})
    assert extra["seed_denominator"] == "season_total"
    assert extra[K.RECORD_KEY] == form
    spec = RunSpec("pf", FD, ["Ohio"], extra=extra)
    rows = {r["key"]: r for r in K.effective(spec)}
    assert rows["pf.seed_denominator"]["value"] == "season_total"
    assert rows["pf.seed_denominator"]["modified"] and K.modified(spec)
    assert "pf.seed_denominator=season_total" in K.label(nd)
    # a fit-stage knob: a retro week's fit manifest keeps it, so a tree
    # built with the other value is refused rather than resumed
    assert K.fit_extra(extra)[K.RECORD_KEY] == form
    # the shipped spec reads the default, unmodified
    shipped = {r["key"]: r for r in K.effective(RunSpec("pf", FD, ["Ohio"]))}
    assert shipped["pf.seed_denominator"]["value"] == SEED_DENOMINATOR == "to_date"
    assert not shipped["pf.seed_denominator"]["modified"]
    assert K.resolve({"pf.seed_denominator": "to_date"}, "all",
                     forecast_date=FD) == {}
    with pytest.raises(K.KnobError, match="not one of"):
        K.resolve({"pf.seed_denominator": "median"}, "all", forecast_date=FD)
    # the panel offers it as a select in the particle-filter group, right
    # after the initialization
    rows = [r for g in K.panel("retro")["groups"] if g["id"] == "fit"
            for r in g["rows"]]
    keys = [r["key"] for r in rows]
    assert keys.index("pf.seed_denominator") == keys.index("pf.initialization") + 1
    row = rows[keys.index("pf.seed_denominator")]
    assert row["kind"] == "choice"
    assert [v for v, _ in row["choices"]] == ["to_date", "season_total"]
