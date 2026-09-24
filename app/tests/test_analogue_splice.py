"""The ILI+ splice: an optional second donor pool, vincentized in.

The default path stays byte-identical to the single-pool analogue (every
published figure was measured on it). Pinned: that identity, the blend's
algebra, the loud failures and the engine helper's gating. Synthetic banks
and dummy specs only.
"""
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flubnf import analogue as AN                      # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL  # noqa: E402

ASOF = date(2025, 12, 20)     # season 2025; every bank season below is prior
ANCHOR = 123.0


def _bank(phase: float = 0.0, amp: float = 30.0, base: float = 80.0) -> dict:
    """Two full prior seasons, eight locations, smooth positive values, so
    every epiweek clears MIN_DONORS on both sides of the blend."""
    bank = {}
    d0 = date(2023, 8, 5)
    for li in range(8):
        loc = f"L{li}"
        for w in range(104):
            d = d0 + timedelta(days=7 * w)
            bank[(loc, d)] = base + amp * math.sin(w / 6.0 + li + phase) + 2.0 * li
    return bank


def _aux_bank() -> dict:
    """A second stream on a different scale and phase, so a blend that
    silently used the primary pool twice would be visible."""
    return _bank(phase=1.3, amp=12.0, base=40.0)


def _pool(**kw):
    kw.setdefault("bank", _aux_bank())
    kw.setdefault("weight", 0.5)
    return AN.AuxPool(**kw)


def _splice(**kw):
    """One auxiliary pool, the shape every single-stream test wants."""
    return AN.DonorSplice(pools=(_pool(**kw),))


# ---------------------------------------------------------------------------
# The guarantee: the default path does not move
# ---------------------------------------------------------------------------

def test_default_identity():
    """An explicit splice=None is byte-identical to omitting it."""
    bank = _bank()
    for h in (1, 2, 3, 4):
        base = AN.forecast(ANCHOR, ASOF, h, bank, QL)
        same = AN.forecast(ANCHOR, ASOF, h, bank, QL, splice=None)
        assert base is not None
        assert same == base


def test_weight_zero_is_the_single_pool():
    """weight=0.0 puts no mass on the auxiliary pool, so the result must be
    the single-pool forecast exactly, not merely close to it."""
    bank = _bank()
    for h in (1, 4):
        base = AN.forecast(ANCHOR, ASOF, h, bank, QL)
        spliced = AN.forecast(ANCHOR, ASOF, h, bank, QL,
                              splice=_splice(weight=0.0))
        assert base is not None and spliced is not None
        assert spliced == base


def test_weight_one_is_the_auxiliary_pool_alone():
    aux = _aux_bank()
    bank = _bank()
    spliced = AN.forecast(ANCHOR, ASOF, 2, bank, QL,
                          splice=AN.DonorSplice(pools=(AN.AuxPool(bank=aux, weight=1.0),)))
    only_aux = AN.forecast(ANCHOR, ASOF, 2, aux, QL)
    assert spliced is not None and only_aux is not None
    assert spliced == only_aux


# ---------------------------------------------------------------------------
# The algebra of the blend
# ---------------------------------------------------------------------------

def test_vincentization_is_a_quantile_average():
    """The blend averages the two RATIO quantile functions level by level.
    Averaging the pooled donors instead would weight by donor count."""
    bank, aux = _bank(), _aux_bank()
    h = 3
    r = AN.donor_ratios(bank, AN.epiweek(ASOF), AN.season_of(ASOF), h)
    a = AN.donor_ratios(aux, AN.epiweek(ASOF), AN.season_of(ASOF), h)
    got = AN.forecast(ANCHOR, ASOF, h, bank, QL,
                      splice=AN.DonorSplice(pools=(AN.AuxPool(bank=aux, weight=0.5),)))
    assert got is not None
    for L in QL:
        want = float(ANCHOR * (0.5 * np.quantile(r, L) + 0.5 * np.quantile(a, L)))
        assert got[float(L)] == want


def test_blend_is_not_the_pooled_donors():
    """A guard against the failure this design exists to avoid: concatenating
    the two pools is a linear pool weighted by donor COUNT, and gives a
    different answer from averaging the quantile functions."""
    bank, aux = _bank(), _aux_bank()
    h = 2
    r = AN.donor_ratios(bank, AN.epiweek(ASOF), AN.season_of(ASOF), h)
    a = AN.donor_ratios(aux, AN.epiweek(ASOF), AN.season_of(ASOF), h)
    blended = AN.forecast(ANCHOR, ASOF, h, bank, QL,
                          splice=AN.DonorSplice(pools=(AN.AuxPool(bank=aux, weight=0.5),)))
    concat = AN.analogue_quantiles(ANCHOR, np.concatenate([r, a]), QL)
    assert blended is not None and concat is not None
    assert blended != concat


def test_quantiles_stay_monotone():
    bank = _bank()
    for w in (0.0, 0.25, 0.5, 0.75, 1.0):
        q = AN.forecast(ANCHOR, ASOF, 2, bank, QL, splice=_splice(weight=w))
        assert q is not None
        vals = [q[float(L)] for L in sorted(q)]
        assert vals == sorted(vals)


def test_completeness_still_applies_on_the_spliced_path():
    bank = _bank()
    base = AN.forecast(ANCHOR, ASOF, 1, bank, QL, splice=_splice())
    corr = AN.forecast(ANCHOR, ASOF, 1, bank, QL, splice=_splice(),
                       completeness=0.8)
    assert base is not None and corr is not None
    for L in base:
        assert corr[L] == pytest.approx(base[L] / 0.8, rel=1e-12)


def test_widening_still_applies_on_the_spliced_path():
    bank = _bank()
    base = AN.forecast(ANCHOR, ASOF, 1, bank, QL, splice=_splice())
    wide = AN.forecast(ANCHOR, ASOF, 1, bank, QL, splice=_splice(),
                       widen_log_sd=0.2)
    assert base is not None and wide is not None
    assert wide[0.5] == pytest.approx(base[0.5], rel=1e-12)   # median fixed
    assert wide[0.975] > base[0.975]
    assert wide[0.025] < base[0.025]


# ---------------------------------------------------------------------------
# The shrink
# ---------------------------------------------------------------------------

def test_shrink_compresses_the_auxiliary_spread():
    """A shrink below 1 pulls the auxiliary ratios toward 1, so the blended
    distribution is narrower than the unshrunk blend."""
    bank = _bank()
    plain = AN.forecast(ANCHOR, ASOF, 2, bank, QL, splice=_splice())
    shrunk = AN.forecast(ANCHOR, ASOF, 2, bank, QL,
                         splice=_splice(shrink=0.5))
    assert plain is not None and shrunk is not None
    assert (shrunk[0.975] - shrunk[0.025]) < (plain[0.975] - plain[0.025])


def test_shrink_of_one_is_a_no_op():
    """exp(1 * log r) is r up to floating point, so shrink=1.0 must not
    move the answer materially."""
    bank = _bank()
    plain = AN.forecast(ANCHOR, ASOF, 3, bank, QL, splice=_splice())
    unit = AN.forecast(ANCHOR, ASOF, 3, bank, QL, splice=_splice(shrink=1.0))
    assert plain is not None and unit is not None
    for L in plain:
        assert unit[L] == pytest.approx(plain[L], rel=1e-12)


def test_shrink_fit_recovers_a_known_ratio():
    """If the auxiliary stream's log-ratios are exactly c times the primary's,
    the fitted shrink is 1/c. Built by raising the primary to the power c,
    which multiplies every log-ratio by c."""
    prim = _bank()
    c = 2.0
    aux = {k: v ** c for k, v in prim.items()}
    s = AN.fit_log_ratio_shrink(prim, aux, 2025)
    assert s == pytest.approx(1.0 / c, rel=1e-12)


def test_shrink_fit_uses_only_strictly_prior_seasons():
    """Target-season data must not reach the fit. Adding a wildly volatile
    target season to both banks must leave the fitted value unchanged."""
    prim, aux = _bank(), _aux_bank()
    before = AN.fit_log_ratio_shrink(prim, aux, 2025)
    d = date(2025, 12, 6)                      # season 2025, the target
    for i in range(20):
        prim[("X", d + timedelta(days=7 * i))] = 1.0 + 900.0 * (i % 2)
        aux[("X", d + timedelta(days=7 * i))] = 1.0 + 3.0 * (i % 2)
    after = AN.fit_log_ratio_shrink(prim, aux, 2025)
    assert after == before


def test_shrink_fit_skips_registry_excluded_seasons():
    """A season the registry excludes is out of the fit as well as out of the
    pool, so injecting noise into it must not move the fitted value."""
    prim, aux = _bank(), _aux_bank()
    before = AN.fit_log_ratio_shrink(prim, aux, 2025)
    d = date(2021, 12, 4)                      # season 2021, registry-excluded
    for i in range(20):
        prim[("Y", d + timedelta(days=7 * i))] = 1.0 + 900.0 * (i % 2)
        aux[("Y", d + timedelta(days=7 * i))] = 1.0 + 3.0 * (i % 2)
    assert AN.fit_log_ratio_shrink(prim, aux, 2025) == before


def test_shrink_fit_returns_none_without_a_shared_prior_season():
    prim, aux = _bank(), _aux_bank()
    # Target season 2023 leaves nothing strictly prior in either bank.
    assert AN.fit_log_ratio_shrink(prim, aux, 2023) is None


def test_in_season_window_excludes_the_summer():
    """The comparison runs on the stretch of calendar that carries signal;
    off-season weeks are near-zero denominators in both streams. Checked by
    counting: the sample must hold exactly the in-window pairs, no more."""
    bank = _bank()
    seasons = {2023, 2024}
    h = 1
    want = sum(1 for (loc, d) in bank
               if AN.season_of(d) in seasons
               and (AN.epiweek(d) >= 47 or AN.epiweek(d) <= 20)
               and bank.get((loc, d + timedelta(days=7 * h))))
    got = AN.in_season_log_ratios(bank, h, seasons)
    assert want > 0
    assert got.size == want
    # widening the window to the whole year must admit strictly more
    whole = AN.in_season_log_ratios(bank, h, seasons,
                                    first_epiweek=1, last_epiweek=53)
    assert whole.size > got.size


def test_in_season_log_ratios_are_the_right_numbers():
    """Not just the right count: the values themselves."""
    bank = {("A", date(2024, 12, 7)): 10.0,      # epiweek 49, in window
            ("A", date(2024, 12, 14)): 20.0,
            ("B", date(2024, 7, 6)): 10.0,       # epiweek 27, summer
            ("B", date(2024, 7, 13)): 40.0}
    got = AN.in_season_log_ratios(bank, 1, {2024, 2023})
    assert got.size == 1
    assert got[0] == pytest.approx(math.log(2.0), rel=1e-15)


# ---------------------------------------------------------------------------
# Loud failures
# ---------------------------------------------------------------------------

def test_both_pools_must_clear_min_donors():
    """A blend whose auxiliary half rests on a handful of donors is the
    primary pool with noise added at a fixed weight, so it is refused."""
    bank = _bank()
    thin = {("T", date(2024, 12, 7) + timedelta(days=7 * i)): 10.0 + i
            for i in range(3)}
    assert AN.forecast(ANCHOR, ASOF, 1, bank, QL,
                       splice=AN.DonorSplice(pools=(AN.AuxPool(bank=thin, weight=0.5),))) is None
    # and the primary side is still enforced
    assert AN.forecast(ANCHOR, ASOF, 1, thin, QL,
                       splice=_splice()) is None


def test_bad_weight_fails_loudly():
    bank = _bank()
    for bad in (-0.1, 1.1, float("nan")):
        with pytest.raises(ValueError):
            AN.forecast(ANCHOR, ASOF, 1, bank, QL, splice=_splice(weight=bad))


def test_bad_shrink_fails_loudly():
    bank = _bank()
    for bad in (0.0, -1.0, float("nan")):
        with pytest.raises(ValueError):
            AN.forecast(ANCHOR, ASOF, 1, bank, QL, splice=_splice(shrink=bad))


def test_auxiliary_pool_cannot_drop_an_unregistered_season():
    """The auxiliary pool goes through the same registry as the admissions
    pool: a season may leave only through a DonorSeasonExclusion record."""
    bank = _bank()
    with pytest.raises(ValueError, match="not registered"):
        AN.forecast(ANCHOR, ASOF, 1, bank, QL,
                    splice=_splice(exclude_seasons=(2019,)))


def test_non_positive_anchor_gives_no_forecast():
    bank = _bank()
    for bad in (0.0, -5.0):
        assert AN.forecast(bad, ASOF, 1, bank, QL, splice=_splice()) is None


# ---------------------------------------------------------------------------
# More than one auxiliary pool
# ---------------------------------------------------------------------------

def test_two_pools_are_a_weighted_quantile_average():
    """Two pools at 0.25 leave the admissions pool 0.5, and the blend is the
    weighted average of the three ratio quantile functions."""
    bank = _bank()
    a1, a2 = _aux_bank(), _bank(phase=2.2, amp=50.0, base=200.0)
    h = 2
    r = AN.donor_ratios(bank, AN.epiweek(ASOF), AN.season_of(ASOF), h)
    q1 = AN.donor_ratios(a1, AN.epiweek(ASOF), AN.season_of(ASOF), h)
    q2 = AN.donor_ratios(a2, AN.epiweek(ASOF), AN.season_of(ASOF), h)
    sp = AN.DonorSplice(pools=(AN.AuxPool(bank=a1, weight=0.25, label="one"),
                               AN.AuxPool(bank=a2, weight=0.25, label="two")))
    assert sp.primary_weight == 0.5
    got = AN.forecast(ANCHOR, ASOF, h, bank, QL, splice=sp)
    assert got is not None
    for L in QL:
        want = float(ANCHOR * (0.5 * np.quantile(r, L)
                               + 0.25 * np.quantile(q1, L)
                               + 0.25 * np.quantile(q2, L)))
        assert got[float(L)] == want


def test_one_pool_at_half_equals_two_at_a_quarter_of_the_same_bank():
    """A pool listed twice at half its weight is the same blend. Cheap, and
    it catches a memo keyed on the bank rather than on the pool index."""
    bank, aux = _bank(), _aux_bank()
    one = AN.DonorSplice(pools=(AN.AuxPool(bank=aux, weight=0.5),))
    two = AN.DonorSplice(pools=(AN.AuxPool(bank=aux, weight=0.25, label="a"),
                                AN.AuxPool(bank=aux, weight=0.25, label="b")))
    a = AN.forecast(ANCHOR, ASOF, 3, bank, QL, splice=one)
    b = AN.forecast(ANCHOR, ASOF, 3, bank, QL, splice=two)
    assert a is not None
    for L in a:
        assert b[L] == pytest.approx(a[L], rel=1e-12)


def test_weights_over_one_fail_loudly():
    bank = _bank()
    sp = AN.DonorSplice(pools=(AN.AuxPool(bank=_aux_bank(), weight=0.7),
                               AN.AuxPool(bank=_aux_bank(), weight=0.7)))
    with pytest.raises(ValueError, match="negative weight"):
        AN.forecast(ANCHOR, ASOF, 1, bank, QL, splice=sp)


def test_every_pool_must_clear_min_donors():
    """Not just the blend: one thin pool sinks the forecast rather than
    riding along at a fixed weight."""
    bank = _bank()
    thin = {("T", date(2024, 12, 7) + timedelta(days=7 * i)): 10.0 + i
            for i in range(3)}
    sp = AN.DonorSplice(pools=(AN.AuxPool(bank=_aux_bank(), weight=0.25),
                               AN.AuxPool(bank=thin, weight=0.25)))
    assert AN.forecast(ANCHOR, ASOF, 1, bank, QL, splice=sp) is None


def test_engine_builds_two_pools_of_different_streams(tmp_path):
    from app.core.engines.analogue import splice_args
    fp = _write_bank(tmp_path)
    fs = _write_bank(tmp_path, _bank(phase=1.0, amp=9.0, base=20.0), "fs.json")
    sp = splice_args(_spec({"aux_pools": [
        {"stream": "iliplus", "weight": 0.25, "bank": str(fp), "shrink": None},
        {"stream": "flusurv", "weight": 0.25, "bank": str(fs), "shrink": None},
    ]}), _bank())
    assert [p.label for p in sp.pools] == ["iliplus", "flusurv"]
    assert sp.primary_weight == 0.5


def test_engine_refuses_weights_that_sum_over_one(tmp_path):
    from app.core.engines.analogue import splice_args
    fp = _write_bank(tmp_path)
    with pytest.raises(ValueError, match="negative weight"):
        splice_args(_spec({"aux_pools": [
            {"stream": "iliplus", "weight": 0.8, "bank": str(fp), "shrink": None},
            {"stream": "flusurv", "weight": 0.8, "bank": str(fp), "shrink": None},
        ]}), _bank())


# ---------------------------------------------------------------------------
# The auxiliary ratio memo
# ---------------------------------------------------------------------------

def test_memo_matches_an_unmemoized_recompute():
    """The memo exists because donor_ratios does not depend on the location
    being forecast. It must not change the answer."""
    bank = _bank()
    sp = _splice()
    first = AN.forecast(ANCHOR, ASOF, 2, bank, QL, splice=sp)
    assert sp._ratio_memo                      # populated
    again = AN.forecast(ANCHOR, ASOF, 2, bank, QL, splice=sp)   # memo hit
    fresh = AN.forecast(ANCHOR, ASOF, 2, bank, QL, splice=_splice())
    assert first == again == fresh


def test_memo_is_keyed_on_pool_horizon_and_calendar():
    bank = _bank()
    sp = _splice()
    for h in (1, 2, 3, 4):
        AN.forecast(ANCHOR, ASOF, h, bank, QL, splice=sp)
    assert len(sp._ratio_memo) == 4
    other = date(2025, 11, 15)
    AN.forecast(ANCHOR, other, 1, bank, QL, splice=sp)
    assert len(sp._ratio_memo) == 5


def test_memo_does_not_leak_between_splices():
    bank = _bank()
    a, b = _splice(), _splice()
    AN.forecast(ANCHOR, ASOF, 1, bank, QL, splice=a)
    assert a._ratio_memo and not b._ratio_memo


# ---------------------------------------------------------------------------
# The engine helper
# ---------------------------------------------------------------------------

def _write_bank(tmp_path, bank=None, name="aux.json"):
    bank = _aux_bank() if bank is None else bank
    fp = tmp_path / name
    fp.write_text(json.dumps({f"{loc}|{d.isoformat()}": v
                              for (loc, d), v in bank.items()}))
    return fp


def _spec(extra, asof="2025-12-20"):
    return SimpleNamespace(forecast_date=asof, extra=extra)


def _cfg(**kw):
    """One iliplus pool config for spec.extra['aux_pools']."""
    kw.setdefault("stream", "iliplus")
    kw.setdefault("weight", 0.5)
    return {"aux_pools": [kw]}


def test_splice_args_is_dormant_by_default():
    from app.core.engines.analogue import splice_args
    bank = _bank()
    assert splice_args(object(), bank) is None
    assert splice_args(_spec(None), bank) is None
    assert splice_args(_spec({}), bank) is None
    assert splice_args(_spec({"analogue_completeness": {"06": 0.9}}),
                       bank) is None
    assert splice_args(_spec({"aux_pools": False}), bank) is None


def test_splice_args_refuses_an_empty_config(tmp_path):
    """An empty list means the caller asked to splice and named no pools.
    Returning None there would label a run spliced that was not."""
    from app.core.engines.analogue import splice_args
    with pytest.raises(ValueError, match="is empty"):
        splice_args(_spec({"aux_pools": []}), _bank())
    with pytest.raises(ValueError, match="must be a list"):
        splice_args(_spec({"aux_pools": {"stream": "iliplus"}}), _bank())


def test_splice_args_refuses_both_sources(tmp_path):
    from app.core.engines.analogue import splice_args
    fp = _write_bank(tmp_path)
    with pytest.raises(ValueError, match="exactly one of.*got 2 of them"):
        splice_args(_spec(_cfg(bank=str(fp), build={})),
                    _bank())


def test_splice_args_builds_a_splice(tmp_path):
    from app.core.engines.analogue import splice_args
    fp = _write_bank(tmp_path)
    sp = splice_args(_spec(_cfg(bank=str(fp))), _bank())
    assert isinstance(sp, AN.DonorSplice) and len(sp.pools) == 1
    pool = sp.pools[0]
    assert pool.weight == 0.5 and pool.label == "iliplus"
    assert pool.shrink is not None and pool.shrink > 0
    assert pool.exclude_seasons == tuple(sorted(AN.EXCLUDED_DONOR_SEASONS))
    assert sp.primary_weight == 0.5


def test_splice_args_honours_explicit_settings(tmp_path):
    from app.core.engines.analogue import splice_args
    fp = _write_bank(tmp_path)
    sp = splice_args(_spec(_cfg(bank=str(fp), weight=0.25, shrink=0.8, bandwidth=3)),
                     _bank())
    p = sp.pools[0]
    assert (p.weight, p.shrink, p.bandwidth) == (0.25, 0.8, 3)
    none_shrink = splice_args(
        _spec(_cfg(bank=str(fp), shrink=None)), _bank())
    assert none_shrink.pools[0].shrink is None


def test_splice_args_fails_loudly(tmp_path):
    from app.core.engines.analogue import splice_args
    fp = _write_bank(tmp_path)
    bank = _bank()
    with pytest.raises(ValueError, match="must be a dict"):
        splice_args(_spec({"aux_pools": ["not a dict"]}), bank)
    with pytest.raises(ValueError, match="exactly one of.*got none"):
        splice_args(_spec({"aux_pools": [{"stream": "iliplus", "weight": 0.5}]}), bank)
    with pytest.raises(ValueError, match="must be one of"):
        splice_args(_spec({"aux_pools": [{"stream": "nope", "weight": 0.5}]}), bank)
    with pytest.raises(ValueError, match="must be 'auto'"):
        splice_args(_spec(_cfg(bank=str(fp), shrink="fitted")),
                    bank)
    with pytest.raises(ValueError, match="not registered"):
        splice_args(_spec(_cfg(bank=str(fp), exclude_seasons=[2019])), bank)


def test_splice_args_raises_when_auto_shrink_cannot_be_fitted(tmp_path):
    """Falling back to the single-pool path would make a replay labelled
    spliced silently unspliced for some weeks."""
    from app.core.engines.analogue import splice_args
    fp = _write_bank(tmp_path)
    with pytest.raises(ValueError, match="could not be fitted"):
        splice_args(_spec(_cfg(bank=str(fp)),
                          asof="2023-12-20"), _bank())


def test_load_aux_bank_reads_and_caches(tmp_path):
    from app.core.engines.analogue import load_aux_bank
    fp = _write_bank(tmp_path)
    first = load_aux_bank(str(fp))
    assert first and all(isinstance(k[1], date) for k in first)
    assert load_aux_bank(str(fp)) is first          # cache hit, same object


def test_load_aux_bank_drops_non_positive(tmp_path):
    from app.core.engines.analogue import load_aux_bank
    bank = {("A", date(2024, 1, 6)): 5.0, ("A", date(2024, 1, 13)): 0.0,
            ("A", date(2024, 1, 20)): -2.0}
    fp = _write_bank(tmp_path, bank, name="mixed.json")
    assert load_aux_bank(str(fp)) == {("A", date(2024, 1, 6)): 5.0}


def test_load_aux_bank_fails_loudly(tmp_path):
    from app.core.engines.analogue import load_aux_bank
    # The bare open() would raise FileNotFoundError on its own, so assert on
    # the guard's MESSAGE: that is the part carrying the diagnosis.
    with pytest.raises(FileNotFoundError, match="auxiliary donor bank not found"):
        load_aux_bank(str(tmp_path / "absent.json"))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"no-pipe-separator": 1.0}))
    with pytest.raises(ValueError, match="location|YYYY-MM-DD"):
        load_aux_bank(str(bad))
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"A|2024-01-06": 0.0}))
    with pytest.raises(ValueError, match="no positive values"):
        load_aux_bank(str(empty))


# ---------------------------------------------------------------------------
# Named presets and the console path
# ---------------------------------------------------------------------------

def test_presets_are_valid_pool_configs():
    from app.core.engines.analogue import AUX_PRESETS, AUX_STREAMS
    assert set(AUX_PRESETS) == {"flusurv", "iliplus", "both"}
    for name, pools in AUX_PRESETS.items():
        assert pools, name
        for pcfg in pools:
            assert pcfg["stream"] in AUX_STREAMS, name
            assert "weight" in pcfg and 0 < pcfg["weight"] <= 1, name
            # exactly one source, the same rule _one_pool enforces, and
            # for a PRESET that source is the committed bank: a preset is
            # the shipped path and must not fetch at forecast time
            assert sum(k in pcfg for k in ("committed", "bank", "build")) == 1, name
            assert pcfg.get("committed") is True, name
        assert sum(p["weight"] for p in pools) <= 1.0 + 1e-12, name


def test_the_selected_preset_is_flusurv_at_half():
    """C1 of prereg ea72d194af8318a5, selected 2026-09-20. Pinned so the
    choice cannot drift without a test saying so."""
    from app.core.engines.analogue import AUX_PRESETS
    assert AUX_PRESETS["flusurv"] == (
        {"stream": "flusurv", "weight": 0.5, "committed": True},)


def test_aux_preset_carries_its_name_for_the_run_record():
    """app.core.retro writes week_extra.__name__ into run_meta.json, so a
    replay built from a preset says which one without anyone remembering."""
    from app.core.engines.analogue import aux_preset
    f = aux_preset("flusurv")
    # the configuration, then WHICH DONORS: the committed bank's digest.
    # run_meta.json outlives the week manifests, so this string is the
    # only durable record of what a replay actually spliced.
    import re
    assert re.fullmatch(r"aux_preset:flusurv\+flusurv@[0-9a-f]{8}", f.__name__)
    got = f("2025-12-20", 0, None)
    assert got == {"aux_pools": [
        {"stream": "flusurv", "weight": 0.5, "committed": True}]}


def test_aux_preset_hands_out_copies():
    """A caller mutating what it gets back must not edit the registry."""
    from app.core.engines.analogue import aux_preset, AUX_PRESETS
    f = aux_preset("both")
    a = f("2025-12-20", 0, None)
    a["aux_pools"][0]["weight"] = 0.99
    b = f("2025-12-20", 1, None)
    assert b["aux_pools"][0]["weight"] == 0.25
    assert AUX_PRESETS["both"][0]["weight"] == 0.25


def test_an_unknown_preset_raises():
    """Rather than running an unspliced season under a spliced label."""
    from app.core.engines.analogue import aux_preset
    with pytest.raises(ValueError, match="unknown auxiliary preset"):
        aux_preset("flusrv")


def test_every_preset_builds_a_splice_from_prebuilt_banks(tmp_path):
    """The presets say committed, so swap in a tiny bank path: this test
    is about the pool arithmetic, not about the shipped artefact (which
    app/tests/test_bank.py covers)."""
    from app.core.engines.analogue import AUX_PRESETS, splice_args
    fp = _write_bank(tmp_path)
    for name, pools in AUX_PRESETS.items():
        cfg = [{**dict(p), "bank": str(fp), "shrink": None} for p in pools]
        for c in cfg:
            c.pop("build", None)
            c.pop("committed", None)
        sp = splice_args(_spec({"aux_pools": cfg}), _bank())
        assert len(sp.pools) == len(pools), name
        assert sp.primary_weight == pytest.approx(
            1 - sum(p["weight"] for p in pools)), name


def test_the_retro_command_accepts_an_aux_preset():
    """Without this the console cannot run a spliced replay at all:
    retro.run_season takes week_extra, and the CLI has to pass one."""
    import inspect
    from flubnf import cli
    sig = inspect.signature(cli.retro_cmd)
    assert "aux" in sig.parameters
    assert sig.parameters["aux"].default == ""
    src = inspect.getsource(cli.retro_cmd)
    assert "week_extra=week_extra" in src
    assert "aux_preset(aux)" in src
