"""LocalPooling (RESEARCH, prereg c66c50adc20bdf84): the shipped path is
untouched, the weights mean what they say, a thin own site falls back."""
from datetime import date, timedelta
import random

import numpy as np
import pytest

from flubnf import analogue as AN

LEVELS = (0.025, 0.25, 0.5, 0.75, 0.975)


def _bank(locations, seasons, growth_by_loc, seed=20261014):
    """Weekly series per location and season with a location-specific
    multiplicative growth, so own-location donors differ from the pool."""
    rng = random.Random(seed)
    bank = {}
    for s in seasons:
        for loc in locations:
            d = date(s, 8, 1)
            d += timedelta(days=(5 - d.weekday()) % 7)      # a Saturday
            v = 50.0
            for _ in range(52):
                v = max(v * growth_by_loc[loc] * (1 + rng.uniform(-0.05, 0.05)), 1.0)
                bank[(loc, d)] = v
                d += timedelta(days=7)
    return bank


LOCS = ["A", "B", "C", "D", "E", "F"]
GROWTH = {"A": 1.15, "B": 0.95, "C": 0.95, "D": 1.0, "E": 1.0, "F": 1.0}
BANK = _bank(LOCS, range(2016, 2026), GROWTH)
ASOF = date(2026, 12, 12)


def test_weighted_quantile_uniform_is_close_to_numpy_and_monotone():
    v = np.array([3.0, 1.0, 4.0, 1.5, 9.0, 2.6, 5.0])
    q = AN.weighted_quantile(v, np.ones_like(v), LEVELS)
    vals = [q[L] for L in LEVELS]
    assert vals == sorted(vals)
    assert q[0.5] == pytest.approx(float(np.median(v)))
    assert q[0.025] >= v.min() and q[0.975] <= v.max()


def test_weighted_quantile_follows_the_weight():
    v = np.array([1.0, 10.0])
    assert AN.weighted_quantile(v, np.array([1.0, 0.0]), (0.5,))[0.5] == 1.0
    assert AN.weighted_quantile(v, np.array([0.0, 1.0]), (0.5,))[0.5] == 10.0
    with pytest.raises(ValueError):
        AN.weighted_quantile(v, np.array([0.0, 0.0]), (0.5,))


def test_shares_are_validated():
    with pytest.raises(ValueError):
        AN.LocalPooling(own_share=1.2)
    with pytest.raises(ValueError):
        AN.LocalPooling(own_share=0.6, region_share=0.6)


def test_local_weights_sum_to_their_shares():
    region = {"A": 1, "B": 1, "C": 2, "D": 2, "E": 3, "F": 3}
    lp = AN.LocalPooling(own_share=0.3, region_share=0.2, region_of=region)
    locs = np.array(["A", "A", "B", "C", "D", "E", "F"], dtype=object)
    w = AN.local_weights(locs, "A", lp)
    assert w.sum() == pytest.approx(1.0)
    assert w[locs == "A"].sum() == pytest.approx(0.3)
    assert w[locs == "B"].sum() == pytest.approx(0.2)
    # a location with no own donors passes its share to the rest
    w2 = AN.local_weights(locs, "Z", lp)
    assert w2.sum() == pytest.approx(1.0) and np.allclose(w2, w2[0])


def test_local_none_is_the_shipped_call():
    r0 = AN.forecast(100.0, ASOF, 2, BANK, LEVELS)
    r1 = AN.forecast(100.0, ASOF, 2, BANK, LEVELS, local=None, location="A")
    assert r0 == r1


def test_own_share_moves_a_growing_location_up_and_a_falling_one_down():
    pooled = AN.forecast(100.0, ASOF, 2, BANK, LEVELS)
    lp = AN.LocalPooling(own_share=0.5)
    up = AN.forecast(100.0, ASOF, 2, BANK, LEVELS, local=lp, location="A")
    down = AN.forecast(100.0, ASOF, 2, BANK, LEVELS, local=lp, location="B")
    assert up[0.5] > pooled[0.5] > down[0.5]
    # shares of zero: the shipped quantile rule, byte for byte
    flat = AN.forecast(100.0, ASOF, 2, BANK, LEVELS,
                       local=AN.LocalPooling(), location="A")
    assert flat == pooled


def test_own_site_replaces_the_pooled_aux_and_falls_back_when_thin():
    aux = _bank(["a", "b", "c", "d"], range(2012, 2026),
                {"a": 1.2, "b": 0.9, "c": 0.9, "d": 1.0}, seed=7)
    pool = AN.AuxPool(bank=aux, weight=0.5, shrink=None, label="aux")
    sp = AN.DonorSplice(pools=(pool,))
    base = AN.forecast(100.0, ASOF, 2, BANK, LEVELS, splice=sp,
                       local=AN.LocalPooling(), location="A")
    lp = AN.LocalPooling(own_site=True, aux_sites={"A": ("a",), "B": ("zz",)})
    own = AN.forecast(100.0, ASOF, 2, BANK, LEVELS, splice=sp, local=lp,
                      location="A")
    assert own[0.5] > base[0.5]                       # site a grows faster
    # a location whose own site is absent (thin) gets the pooled aux
    thin = AN.forecast(100.0, ASOF, 2, BANK, LEVELS, splice=sp, local=lp,
                       location="B")
    ref = AN.forecast(100.0, ASOF, 2, BANK, LEVELS, splice=sp,
                      local=AN.LocalPooling(), location="B")
    assert thin == ref


LOCATIONS_CSV = """abbreviation,location,location_name
US,US,US
TX,48,Texas
PR,72,Puerto Rico
NY,36,New York
GA,13,Georgia
DC,11,District of Columbia
"""


def test_engine_local_args_parses_and_refuses(tmp_path, monkeypatch):
    """No hub needed (CI runs with FLUBNF_HUB=/nonexistent): the locations
    table is a small copy of the hub's columns."""
    from types import SimpleNamespace
    from app.core.engines import analogue as eng
    csv = tmp_path / "locations.csv"
    csv.write_text(LOCATIONS_CSV, encoding="utf-8")
    monkeypatch.setattr(eng, "LOCATIONS", csv)
    # the shipped form rides in the record, as aux_pools does
    assert eng.shipped_local_pools() == {"own_share": AN.SHIPPED_OWN_SHARE}
    shipped = eng.local_args(SimpleNamespace(
        extra={"local_pools": eng.shipped_local_pools()}))
    assert shipped.own_share == 0.5 and not shipped.own_site
    assert shipped.region_share == 0
    # an absent key is the pooled form (every record before 2026-10-15);
    # so are None, False and a zero share
    assert eng.local_args(SimpleNamespace(extra={})) is None
    assert eng.local_args(SimpleNamespace(extra={"local_pools": None})) is None
    assert eng.local_args(SimpleNamespace(extra={"local_pools": {"own_share": 0}})) is None
    # the knob sets the share, with or without the record's key
    assert eng.local_args(SimpleNamespace(
        extra={"knobs": {"groundhog.own_share": 0.75}})).own_share == 0.75
    assert eng.local_args(SimpleNamespace(
        extra={"local_pools": eng.shipped_local_pools(),
               "knobs": {"groundhog.own_share": 0}})) is None
    # the effective form drops zero entries, so an equivalent dict is shipped
    assert eng.effective_local_pools(
        {"local_pools": {"own_share": 0.5, "region_share": 0, "own_site": False}}
    ) == eng.SHIPPED_LOCAL_POOLS
    lp = eng.local_args(SimpleNamespace(
        extra={"local_pools": {"own_share": 0.25, "own_site": True}}))
    assert lp.own_share == 0.25 and lp.own_site
    # keyed by FIPS, the admissions bank's key space (a name-keyed map
    # would silently never match a donor: the 2026-10-14 first run)
    assert lp.region_of["48"] == 6 and lp.region_of["72"] == 2
    assert lp.region_of["11"] == 3
    assert lp.aux_sites["36"] == ("ny_albany", "ny_rochester")
    assert lp.aux_sites["13"] == ("ga",)
    assert set(lp.region_of) == {"48", "72", "36", "13", "11"}   # US left out
    with pytest.raises(ValueError):
        eng.local_args(SimpleNamespace(extra={"local_pools": {"bogus": 1}}))
    with pytest.raises(ValueError):
        eng.local_args(SimpleNamespace(extra={"local_pools": {"own_share": 2}}))


def test_every_hub_jurisdiction_has_an_hhs_region():
    from app.core.engines import analogue as eng
    abbrs = {a for abbrs in eng.HHS_REGION.values() for a in abbrs}
    assert len(abbrs) == 52                                 # 50 states, DC, PR
    assert {"DC", "PR", "AK", "HI"} <= abbrs


def _name_keyed_vintage(tmp_path):
    """A truth csv whose `location` column holds names, not FIPS."""
    import pandas as pd
    rows = []
    for loc, base in (("Alabama", 40.0), ("Alaska", 8.0)):
        d = date(2022, 8, 6)
        v = base
        for _ in range(130):
            rows.append({"date": d.isoformat(), "location": loc,
                         "location_name": loc, "value": v})
            v = max(v * 1.02, 1.0)
            d += timedelta(days=7)
    p = tmp_path / "truth.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    return p


def test_engine_refuses_a_bank_whose_keys_miss_the_region_map(tmp_path, monkeypatch):
    """The guard behind the FIPS keying, driven through the engine: a
    name-keyed bank with local pools on raises instead of weighting
    nothing (the 2026-10-14 first run)."""
    from types import SimpleNamespace
    from app.core.engines import analogue as eng
    csv = tmp_path / "locations.csv"
    csv.write_text(LOCATIONS_CSV + "AL,01,Alabama\nAK,02,Alaska\n",
                   encoding="utf-8")
    monkeypatch.setattr(eng, "LOCATIONS", csv)
    truth = _name_keyed_vintage(tmp_path)
    monkeypatch.setattr(eng, "_source", lambda spec: (truth, csv, {}))
    spec = SimpleNamespace(forecast_date="2024-12-28", locations=["Alabama"],
                           extra={"local_pools": eng.shipped_local_pools()},
                           weeks_to_drop=0, drop_same_day=False)
    with pytest.raises(ValueError, match="share nothing"):
        list(eng._walk(spec))
    # the pooled form (no key) has no map to check: the mismatch stays
    # silent and every location is skipped (no rows under its FIPS), as
    # the engine always did
    spec.extra = {}
    assert list(eng._walk(spec)) == []


def test_zero_share_classes_stay_in_the_rest():
    """region_share 0 with a populated region map must POOL the region's
    cells, not drop them (found in review 2026-10-15); mirror for own."""
    region = {"A": 1, "B": 1, "C": 2, "D": 2, "E": 3, "F": 3}
    locs = np.array(["A", "A", "B", "C", "D", "E", "F"], dtype=object)
    w = AN.local_weights(locs, "A", AN.LocalPooling(own_share=0.5, region_of=region))
    assert w[locs == "A"].sum() == pytest.approx(0.5)
    rest = w[locs != "A"]
    assert rest.min() > 0 and np.allclose(rest, rest[0])     # B pooled with C..F
    w2 = AN.local_weights(locs, "A", AN.LocalPooling(region_share=0.25, region_of=region))
    assert w2[locs == "B"].sum() == pytest.approx(0.25)
    others = w2[locs != "B"]
    assert others.min() > 0 and np.allclose(others, others[0])   # own cells pooled


def test_location_is_required_under_local_pooling():
    with pytest.raises(ValueError, match="location"):
        AN.forecast(100.0, ASOF, 2, BANK, LEVELS,
                    local=AN.LocalPooling(own_share=0.5))


def test_zero_shares_with_a_splice_are_the_shipped_spliced_call():
    aux = _bank(["a", "b", "c", "d"], range(2012, 2026),
                {"a": 1.2, "b": 0.9, "c": 0.9, "d": 1.0}, seed=7)
    sp = AN.DonorSplice(pools=(AN.AuxPool(bank=aux, weight=0.5, label="aux"),))
    shipped = AN.forecast(100.0, ASOF, 2, BANK, LEVELS, splice=sp)
    assert AN.forecast(100.0, ASOF, 2, BANK, LEVELS, splice=sp,
                       local=AN.LocalPooling(), location="A") == shipped


def test_own_site_memo_is_bound_to_the_pool():
    """One LocalPooling reused with a second splice must not hand back the
    first pool's own-site ratios (review 2026-10-15)."""
    aux1 = _bank(["a"], range(2012, 2026), {"a": 1.2}, seed=1)
    aux2 = _bank(["a"], range(2012, 2026), {"a": 0.8}, seed=2)
    lp = AN.LocalPooling(own_site=True, aux_sites={"A": ("a",)})
    sp1 = AN.DonorSplice(pools=(AN.AuxPool(bank=aux1, weight=0.5, label="aux"),))
    sp2 = AN.DonorSplice(pools=(AN.AuxPool(bank=aux2, weight=0.5, label="aux"),))
    r1 = AN.forecast(100.0, ASOF, 2, BANK, LEVELS, splice=sp1, local=lp, location="A")
    r2 = AN.forecast(100.0, ASOF, 2, BANK, LEVELS, splice=sp2, local=lp, location="A")
    fresh = AN.forecast(100.0, ASOF, 2, BANK, LEVELS, splice=sp2,
                        local=AN.LocalPooling(own_site=True, aux_sites={"A": ("a",)}),
                        location="A")
    assert r2 == fresh and r1 != r2


def test_a_local_pools_run_is_labelled_and_is_research():
    """A console or replay run with local pools must not pass for the
    shipped Groundhog in the ledger (review 2026-10-15)."""
    from app.core import runs
    from app.core.engines import analogue as eng
    from app.ui.routes.forecast import _run_extra
    old = {"aux_pools": [{"stream": "flusurv", "weight": 0.5, "committed": True}],
           "analogue_aux": "flusurv+flusurv@06eff6a7"}
    # a record from before 2026-10-15 (no key) ran, and reads as, the
    # pooled form; it is not research
    assert runs.analogue_donors_label(old) == (
        "flusurv+flusurv@06eff6a7, pooled (no own-state weight)")
    assert not runs.is_research({"extra": old})
    # the console records the shipped form; the record is named, not research
    shipped = _run_extra(2, "vintage")
    assert shipped["local_pools"] == eng.shipped_local_pools()
    assert runs.analogue_donors_label(shipped) == (
        "flusurv+flusurv@06eff6a7, own-state donors 0.50")
    assert not runs.is_research({"extra": shipped})
    assert not runs.is_research({"extra": {
        **shipped, "local_pools": {"own_share": 0.5, "region_share": 0}}})
    # the bare analogue (no aux) stays the pooled form and carries no key
    assert "local_pools" not in _run_extra(2, "vintage", aux="")
    # the pooled form, asked for, is a research run and says so
    pooled = {**shipped, "local_pools": None}
    assert runs.analogue_donors_label(pooled).endswith("pooled (no own-state weight)")
    assert runs.is_research({"extra": pooled})
    other = {**shipped, "local_pools": {"own_share": 0.25}}
    assert runs.analogue_donors_label(other).endswith("own-state donors 0.25")
    assert runs.is_research({"extra": other})
    # a knob off its default is a modified run, named, not research; the
    # knob at 0 names the pooled form too
    knob = {**shipped, "knobs": {"groundhog.own_share": 0.75}}
    assert runs.analogue_donors_label(knob).endswith("own-state donors 0.75")
    assert not runs.is_research({"extra": knob})
    zero = {**shipped, "knobs": {"groundhog.own_share": 0}}
    assert runs.analogue_donors_label(zero).endswith("pooled (no own-state weight)")
    assert not runs.is_research({"extra": zero})
    # the replay presets carry the form too
    assert eng.aux_preset("flusurv")(None, 0, None)["local_pools"] == eng.shipped_local_pools()


W1, W2 = "2098-11-07", "2098-11-14"


def _fake_retro(monkeypatch, got):
    """A two-week season whose weeks are faked, as test_swarm_carry does."""
    import json as _json
    from pathlib import Path as _P
    from app.core import retro
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(retro, "_now", lambda: clock["t"])
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])

    def fake_week(r, season, asof, locations, replicates, particles, width,
                  **kw):
        clock["t"] += 60.0
        got.append((asof, kw.get("extra")))
        wd = _P(r) / "weeks" / asof
        wd.mkdir(parents=True, exist_ok=True)
        (wd / "samples.json").write_text(_json.dumps({"asof": asof}))
        return {"asof": asof}
    monkeypatch.setattr(retro, "run_week", fake_week)
    return retro


def test_a_season_record_names_the_form_without_calling_the_week_dictionary(
        tmp_path, monkeypatch):
    from app.core import knobs as K
    from app.core.engines import analogue as eng
    got = []
    retro = _fake_retro(monkeypatch, got)
    calls = []

    def carry(asof, i, vintages):          # a callable with side effects
        calls.append(asof)
        return {"continue_states": None}
    root = tmp_path / "s"
    retro.run_season(root, "2098-99", ["Ohio"], width=1, week_extra=carry,
                     engine="analogue")
    assert calls == [W1, W2]               # asked once per week, never probed
    assert retro.read_meta(root)["settings"]["groundhog_local_pools"] is None
    # the shipped preset declares the form; the knob wrapper keeps it and
    # the knob rides on top
    base = eng.aux_preset("flusurv")
    assert base.local_pools == eng.shipped_local_pools()
    wrapped = K.retro_week_extra(base, {"groundhog.own_share": 0.75})
    assert wrapped.local_pools == eng.shipped_local_pools()
    root2 = tmp_path / "t"
    retro.run_season(root2, "2098-99", ["Ohio"], width=1, engine="analogue",
                     week_extra=wrapped,
                     settings={"knobs": {"groundhog.own_share": 0.75}})
    assert retro.read_meta(root2)["settings"]["groundhog_local_pools"] == {
        "own_share": 0.75}
    root3 = tmp_path / "u"
    retro.run_season(root3, "2098-99", ["Ohio"], width=1, engine="analogue")
    assert retro.read_meta(root3)["settings"]["groundhog_local_pools"] == {
        "own_share": 0.5}


def test_a_resume_refuses_to_mix_the_groundhog_forms(tmp_path, monkeypatch):
    """A tree replayed pooled (every tree from before 2026-10-15 has no
    key) is not resumed under the shipped form, and the other way round."""
    import json as _json
    from app.core import retro as _retro
    got = []
    retro = _fake_retro(monkeypatch, got)
    root = tmp_path / "s"
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1])
    retro.run_season(root, "2098-99", ["Ohio"], width=1, engine="analogue")
    meta = retro.read_meta(root)
    assert meta["settings"]["groundhog_local_pools"] == {"own_share": 0.5}
    # pretend the tree predates the key: a pooled-era record
    p = root / "run_meta.json"
    d = _json.loads(p.read_text()); d["settings"].pop("groundhog_local_pools")
    p.write_text(_json.dumps(d))
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])
    with pytest.raises(_retro.GroundhogFormMismatch, match="pooled Groundhog"):
        retro.run_season(root, "2098-99", ["Ohio"], width=1, engine="analogue")
    assert isinstance(_retro.GroundhogFormMismatch(""), _retro.KnobsMismatch)
    # and the shipped tree is not resumed by a pooled replay
    root2 = tmp_path / "t"
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1])
    retro.run_season(root2, "2098-99", ["Ohio"], width=1, engine="analogue")
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])
    with pytest.raises(_retro.GroundhogFormMismatch, match="own_share 0.5"):
        retro.run_season(root2, "2098-99", ["Ohio"], width=1, engine="analogue",
                         week_extra=lambda a, i, v: {})


# --- the research anchor options (prereg 0815e4709ab06b2f) ------------------

def _sized_bank():
    """Six locations, ten seasons, growth 1.05 everywhere, but the
    LEVELS differ: A and B start at 4, the rest at 400, so a count floor
    or an anchor weighting tells them apart; the ratios are made to differ
    by size (small series: noisier)."""
    rng = random.Random(3)
    bank = {}
    for s in range(2016, 2026):
        for loc, base, noise in (("A", 4.0, 0.6), ("B", 4.0, 0.6), ("C", 400.0, 0.05),
                                 ("D", 400.0, 0.05), ("E", 400.0, 0.05), ("F", 400.0, 0.05)):
            d = date(s, 8, 1); d += timedelta(days=(5 - d.weekday()) % 7)
            v = base
            for _ in range(52):
                v = max(v * 1.05 * (1 + rng.uniform(-noise, noise)), 1.0)
                bank[(loc, d)] = v
                d += timedelta(days=7)
    return bank


def test_anchor_options_are_validated():
    with pytest.raises(ValueError):
        AN.LocalPooling(anchor_floor=-1)
    with pytest.raises(ValueError):
        AN.LocalPooling(anchor_weight="cube")
    with pytest.raises(ValueError):
        AN.LocalPooling(anchor_weight="kernel", kernel_sd=0)


def test_a_floor_drops_small_donors_and_falls_back_under_min_donors():
    bank = _sized_bank()
    r, locs, v0 = AN.keyed_ratios(bank, AN.epiweek(ASOF), AN.season_of(ASOF), 2,
                                  with_anchor=True)
    assert v0.size == r.size and (v0 > 0).all()
    small = (v0 < 10).sum(); assert small > 0
    plain = AN.forecast(400.0, ASOF, 2, bank, LEVELS,
                        local=AN.LocalPooling(own_share=0.5), location="C")
    floored = AN.forecast(400.0, ASOF, 2, bank, LEVELS,
                          local=AN.LocalPooling(own_share=0.5, anchor_floor=10),
                          location="C")
    # the same forecast from the floored pool computed by hand: own cells
    # at half weight, the rest shared, over the donors at 10 or more
    keep = v0 >= 10
    lp = AN.LocalPooling(own_share=0.5)
    wq = AN.weighted_quantile(r[keep], AN.local_weights(locs[keep], "C", lp), LEVELS)
    manual = {L: 400.0 * wq[L] for L in LEVELS}
    assert floored == pytest.approx(manual) and floored != plain
    assert floored[0.975] - floored[0.025] < plain[0.975] - plain[0.025]
    # a floor nobody clears falls back to the unfloored pool
    back = AN.forecast(400.0, ASOF, 2, bank, LEVELS,
                       local=AN.LocalPooling(own_share=0.5, anchor_floor=1e9),
                       location="C")
    assert back == plain


def test_anchor_weighting_keeps_the_class_shares():
    locs = np.array(["A", "A", "B", "C"], dtype=object)
    v0 = np.array([4.0, 16.0, 100.0, 400.0])
    for wname in ("count", "sqrt", "kernel"):
        lp = AN.LocalPooling(own_share=0.5, anchor_weight=wname, kernel_sd=1.0)
        w = AN.local_weights(locs, "A", lp, anchors=v0, target_anchor=100.0)
        assert w.sum() == pytest.approx(1.0)
        assert w[locs == "A"].sum() == pytest.approx(0.5)
    w = AN.local_weights(locs, "A", AN.LocalPooling(own_share=0.5, anchor_weight="count"),
                         anchors=v0, target_anchor=None)
    assert w[1] == pytest.approx(4 * w[0])                  # 16 against 4
    k = AN.local_weights(locs, "A", AN.LocalPooling(own_share=0.5, anchor_weight="kernel"),
                         anchors=v0, target_anchor=100.0)
    assert k[2] > k[3]                                       # 100 nearer 100 than 400


def test_the_engine_accepts_and_labels_the_anchor_options(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.core import runs
    from app.core.engines import analogue as eng
    csv = tmp_path / "locations.csv"; csv.write_text(LOCATIONS_CSV, encoding="utf-8")
    monkeypatch.setattr(eng, "LOCATIONS", csv)
    cfg = {"own_share": 0.5, "anchor_floor": 10, "anchor_weight": "kernel", "kernel_sd": 0.5}
    assert eng.effective_local_pools({"local_pools": cfg}) == cfg
    lp = eng.local_args(SimpleNamespace(extra={"local_pools": cfg}))
    assert lp.anchor_floor == 10 and lp.anchor_weight == "kernel" and lp.kernel_sd == 0.5
    extra = {"aux_pools": [{"stream": "flusurv", "weight": 0.5, "committed": True}],
             "analogue_aux": "flusurv+flusurv@06eff6a7", "local_pools": cfg}
    assert runs.analogue_donors_label(extra) == (
        "flusurv+flusurv@06eff6a7, own-state donors 0.50, donor floor 10, "
        "donors weighted by kernel s=0.5")
    assert runs.is_research({"extra": extra})


def test_the_engine_refuses_a_zero_kernel_width_and_an_unknown_weighting():
    from app.core.engines import analogue as eng
    with pytest.raises(ValueError):
        eng.effective_local_pools({"local_pools": {"anchor_weight": "cube"}})
    cfg = eng.effective_local_pools({"local_pools": {"own_share": 0.5, "anchor_weight": "kernel",
                                                      "kernel_sd": 0}})
    assert cfg["kernel_sd"] == 0                     # read literally ...
    with pytest.raises(ValueError):                  # ... and refused downstream
        AN.LocalPooling(**cfg)


def test_the_effective_donor_guard_falls_back_to_uniform():
    """A kernel that concentrates a class onto one donor takes uniform
    weights there when the guard is on (amendment 2)."""
    locs = np.array(["A"] + ["R"] * 40, dtype=object)
    v0 = np.array([100.0] + [100.0] + [1.0] * 39)   # one rest donor near the target
    lp = AN.LocalPooling(own_share=0.5, anchor_weight="kernel", kernel_sd=0.5)
    w = AN.local_weights(locs, "A", lp, anchors=v0, target_anchor=100.0)
    rest = locs == "R"
    ess = (w[rest].sum() ** 2) / (w[rest] ** 2).sum()
    assert ess < 2                                     # one donor carries it
    g = AN.LocalPooling(own_share=0.5, anchor_weight="kernel", kernel_sd=0.5, ess_floor=30)
    wg = AN.local_weights(locs, "A", g, anchors=v0, target_anchor=100.0)
    assert np.allclose(wg[rest], 0.5 / 40) and wg[locs == "A"].sum() == pytest.approx(0.5)
    from app.core.engines import analogue as eng
    from app.core import runs
    cfg = {"own_share": 0.5, "anchor_weight": "kernel", "kernel_sd": 1.0, "ess_floor": 30}
    assert eng.effective_local_pools({"local_pools": cfg}) == cfg
    assert runs.local_pools_label({"local_pools": cfg}).endswith("effective-donor floor 30")
