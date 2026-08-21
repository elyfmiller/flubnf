"""BUILD 1: the exogenous national-growth term in the per-state PF.

Everything here is synthetic and offline. The point of a synthetic grid is that
the leave-one-out arithmetic, the vintage dependence, the week alignment and
the missing-week policy all have exact expected answers, which real NHSN data
cannot give you.

Three properties are load-bearing and each has its own test:

  * the national series LEAVES THE STATE OUT and is population-weighted,
  * both series come from the SINGLE vintage file the caller hands over,
  * the emitted BNGL puts gap[w] on [w, w+1) and holds gap[last] forever
    after, which is the pre-registered forecast rule.

Plus the guarantee that matters most operationally: with the variant absent,
the production path writes a BYTE-IDENTICAL model file.
"""
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flubnf import natgrowth as ng  # noqa: E402

SEASON_START = "2024-08-03"          # a Saturday, so week offsets are exact
N_WEEKS = 20
TARGET = "Targetland"


# ---------------------------------------------------------------------------
# synthetic fixtures
# ---------------------------------------------------------------------------
def _locations(tmp_path, n_peers=30, target_pop=5_000_000,
               peer_pop=1_000_000) -> Path:
    rows = [{"abbreviation": "US", "location": "US", "location_name": "US",
             "population": 300_000_000},
            {"abbreviation": "TG", "location": "01",
             "location_name": TARGET, "population": target_pop}]
    for i in range(n_peers):
        rows.append({"abbreviation": f"P{i:02d}",
                     "location": f"{i + 2:02d}",
                     "location_name": f"Peer{i:02d}",
                     "population": peer_pop * (2 if i == 0 else 1)})
    p = tmp_path / "locations.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    return p


def _truth(tmp_path, name, series_by_fips, weeks=None) -> Path:
    """`series_by_fips` maps fips -> {week_offset: value}. Missing keys are
    missing ROWS, which is how NHSN's reporting pause actually looks."""
    start = pd.Timestamp(SEASON_START)
    rows = []
    for fips, by_week in series_by_fips.items():
        for w, v in by_week.items():
            if weeks is not None and w not in weeks:
                continue
            rows.append({"date": (start + pd.Timedelta(days=7 * w)).date(),
                         "location": fips, "location_name": fips,
                         "value": v, "weekly_rate": 1.0})
    p = tmp_path / name
    pd.DataFrame(rows).to_csv(p, index=False)
    return p


def _flat_grid(n_peers=30, level=100.0, growth=0.2):
    """Every peer grows at exactly `growth`/week; the target is flat."""
    out = {"01": {w: level for w in range(N_WEEKS)}}
    for i in range(n_peers):
        out[f"{i + 2:02d}"] = {w: level * float(np.exp(growth * w))
                               for w in range(N_WEEKS)}
    return out


def _series(tmp_path, truth, locations, **kw):
    return ng.growth_gap_series(TARGET, truth_csv=truth,
                                locations_csv=locations,
                                season_start=SEASON_START,
                                as_of=str((pd.Timestamp(SEASON_START)
                                           + pd.Timedelta(days=7 * (N_WEEKS - 1))
                                           ).date()), **kw)


# ---------------------------------------------------------------------------
# 1. leave-one-out, population weighting
# ---------------------------------------------------------------------------
def test_national_series_leaves_the_state_out_and_is_population_weighted(tmp_path):
    loc = _locations(tmp_path)
    grid = _flat_grid()
    gg = _series(tmp_path, _truth(tmp_path, "v.csv", grid), loc)

    # peers all grow at 0.2; the target is flat. If the target leaked into the
    # national mean it would drag g_nat below 0.2 (it carries 5/35 of the
    # weight), so this is a real exclusion test, not a tautology.
    live = np.isfinite(gg.g_nat)
    assert live.sum() >= N_WEEKS - 2
    assert np.allclose(gg.g_nat[live], 0.2, atol=1e-9)
    assert np.allclose(gg.g_own[live], 0.0, atol=1e-9)
    assert np.allclose(gg.gap[live], 0.2, atol=1e-9)
    assert (gg.n_peers[live] == 30).all()


def test_population_weighting_is_not_a_plain_mean(tmp_path):
    loc = _locations(tmp_path, n_peers=30)     # Peer00 has DOUBLE population
    grid = _flat_grid()
    for w in range(N_WEEKS):                   # Peer00 alone grows at 1.0
        grid["02"][w] = 100.0 * float(np.exp(1.0 * w))
    gg = _series(tmp_path, _truth(tmp_path, "v.csv", grid), loc)

    # weights: Peer00 = 2M, the other 29 = 1M each -> (2*1.0 + 29*0.2)/31
    expected = (2 * 1.0 + 29 * 0.2) / 31
    live = np.isfinite(gg.g_nat)
    assert np.allclose(gg.g_nat[live], expected, atol=1e-9)
    assert not np.allclose(gg.g_nat[live], (1.0 + 29 * 0.2) / 30, atol=1e-6)


def test_national_series_is_silent_below_min_peers(tmp_path):
    loc = _locations(tmp_path, n_peers=ng.MIN_PEERS - 1)
    gg = _series(tmp_path, _truth(tmp_path, "v.csv",
                                  _flat_grid(n_peers=ng.MIN_PEERS - 1)), loc)
    assert not np.isfinite(gg.g_nat).any()
    assert (gg.gap == 0.0).all()               # undefined -> neutral, never NaN
    assert gg.n_active == 0


# ---------------------------------------------------------------------------
# 2. vintage discipline
# ---------------------------------------------------------------------------
def test_series_follows_the_vintage_it_is_handed(tmp_path):
    """The same week, two vintages, two answers. If this test ever passes with
    identical numbers, something is reading the latest file."""
    loc = _locations(tmp_path)
    early = _flat_grid()
    late = {k: dict(v) for k, v in early.items()}
    # the newest point was under-reported at first issue and later revised up
    late["01"][N_WEEKS - 1] = early["01"][N_WEEKS - 1] * 2.0

    g_early = _series(tmp_path, _truth(tmp_path, "e.csv", early), loc)
    g_late = _series(tmp_path, _truth(tmp_path, "l.csv", late), loc)

    w = N_WEEKS - 1
    assert g_early.g_own[w] == pytest.approx(0.0, abs=1e-12)
    assert g_late.g_own[w] == pytest.approx(np.log(2.0), abs=1e-12)
    assert g_early.last_gap != g_late.last_gap
    # the national side is untouched by a revision to the target's own column
    assert g_early.g_nat[w] == pytest.approx(g_late.g_nat[w], abs=1e-12)


# ---------------------------------------------------------------------------
# 3. missing weeks and the level floor
# ---------------------------------------------------------------------------
def test_growth_is_never_computed_across_a_reporting_hole(tmp_path):
    loc = _locations(tmp_path)
    grid = _flat_grid()
    grid["01"] = {w: 100.0 * float(np.exp(0.1 * w)) for w in range(N_WEEKS)}
    hole = 8
    del grid["01"][hole]                       # the row simply is not there
    gg = _series(tmp_path, _truth(tmp_path, "v.csv", grid), loc)

    assert not np.isfinite(gg.g_own[hole])     # no value: no growth INTO it
    assert not np.isfinite(gg.g_own[hole + 1])  # and none ACROSS it
    assert gg.gap[hole] == 0.0 and gg.gap[hole + 1] == 0.0
    assert gg.g_own[hole + 2] == pytest.approx(0.1, abs=1e-9)   # recovers


def test_weeks_under_the_level_floor_carry_no_growth(tmp_path):
    loc = _locations(tmp_path)
    grid = _flat_grid()
    grid["01"] = {w: (1.0 if w < 5 else 100.0) for w in range(N_WEEKS)}
    gg = _series(tmp_path, _truth(tmp_path, "v.csv", grid), loc)

    assert ng.MIN_LEVEL > 1.0
    for w in range(6):                         # both endpoints must clear it
        assert not np.isfinite(gg.g_own[w])
        assert gg.gap[w] == 0.0
    assert gg.g_own[6] == pytest.approx(0.0, abs=1e-9)


def test_extreme_gaps_are_clipped_and_counted(tmp_path):
    loc = _locations(tmp_path)
    grid = _flat_grid()
    spike = 12
    grid["01"][spike] = grid["01"][spike - 1] / 100.0   # -4.6 log growth
    grid["01"][spike] = max(grid["01"][spike], ng.MIN_LEVEL)
    gg = _series(tmp_path, _truth(tmp_path, "v.csv", grid), loc)

    assert gg.gap[spike] == pytest.approx(ng.GAP_CLIP)
    assert gg.clipped[spike]
    assert gg.n_clipped >= 1
    assert np.abs(gg.gap).max() <= ng.GAP_CLIP + 1e-12


# ---------------------------------------------------------------------------
# 4. alignment: what the BNGL actually evaluates to
# ---------------------------------------------------------------------------
def _eval_bngl(expr: str, t: float) -> float:
    """Evaluate BNGL's nested if() in Python. `if(c,a,b)` is C's ternary."""
    return float(eval(expr.replace("if(", "_if("),                  # noqa: S307
                      {"__builtins__": {}},
                      {"_if": lambda c, a, b: a if c else b, "t": t}))


def test_expression_puts_each_gap_on_its_own_week(tmp_path):
    loc = _locations(tmp_path)
    grid = _flat_grid()
    # a distinct own-growth every week so no two gaps collide
    grid["01"] = {0: 100.0}
    for w in range(1, N_WEEKS):
        grid["01"][w] = grid["01"][w - 1] * float(np.exp(0.01 * w))
    gg = _series(tmp_path, _truth(tmp_path, "v.csv", grid), loc)
    expr = ng.bngl_gap_expression(gg)

    for w in range(gg.last_week + 1):
        for frac in (0.0, 0.5, 0.999):
            assert _eval_bngl(expr, w + frac) == pytest.approx(
                round(float(gg.gap[w]), 6), abs=1e-9), f"week {w}+{frac}"


def test_forecast_holds_the_last_observed_gap(tmp_path):
    """The pre-registered rule, asserted on the emitted model text: every t at
    or beyond the last observed week evaluates to the last observed gap."""
    loc = _locations(tmp_path)
    grid = _flat_grid()
    gg = _series(tmp_path, _truth(tmp_path, "v.csv", grid), loc)
    expr = ng.bngl_gap_expression(gg)
    last = round(gg.last_gap, 6)

    assert last != 0.0                          # a real hold, not a silent one
    for h in (0, 1, 2, 3, 4, 40):
        assert _eval_bngl(expr, gg.last_week + h) == pytest.approx(last,
                                                                   abs=1e-9)
    # structurally: the final branch carries no upper guard
    assert re.search(r",-?\d+\.\d+\)*$", expr)


def test_truncate_moves_the_hold_to_the_filters_last_week(tmp_path):
    loc = _locations(tmp_path)
    grid = _flat_grid()
    grid["01"] = {0: 100.0}
    for w in range(1, N_WEEKS):
        grid["01"][w] = grid["01"][w - 1] * float(np.exp(0.05 * w))
    gg = _series(tmp_path, _truth(tmp_path, "v.csv", grid), loc)

    cut = gg.last_week - 2                      # e.g. weeks_to_drop = 2
    tr = gg.truncate(cut)
    assert tr.last_week == cut
    assert tr.gap.size == cut + 1
    assert np.allclose(tr.gap, gg.gap[:cut + 1])           # nothing recomputed
    assert tr.last_gap == pytest.approx(gg.gap[cut])
    assert _eval_bngl(ng.bngl_gap_expression(tr), cut + 4) == pytest.approx(
        round(float(gg.gap[cut]), 6), abs=1e-9)

    # extending past the data repeats the hold; it never invents growth
    ex = gg.truncate(gg.last_week + 3)
    assert ex.last_week == gg.last_week + 3
    assert ex.last_gap == pytest.approx(gg.last_gap)
    assert not np.isfinite(ex.g_nat[-1])


def test_expression_refuses_anything_that_is_not_a_number(tmp_path):
    loc = _locations(tmp_path)
    gg = _series(tmp_path, _truth(tmp_path, "v.csv", _flat_grid()), loc)
    gg.gap[3] = float("nan")
    with pytest.raises(ValueError, match="non-numeric"):
        ng.bngl_gap_expression(gg)


# ---------------------------------------------------------------------------
# 5. the template
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parents[2]
TPL_MIN = REPO / "flubnf/templates/SIHRS_pop_min.bngl"
TPL_NATG = REPO / "flubnf/templates/SIHRS_pop_natg.bngl"


def _setup(tmp_path):
    from flubnf.sihrs_fit import resolve_state
    loc = _locations(tmp_path)
    grid = _flat_grid()
    grid["01"] = {w: 100.0 * float(np.exp(0.1 * w)) for w in range(N_WEEKS)}
    truth = _truth(tmp_path, "v.csv", grid)
    as_of = str((pd.Timestamp(SEASON_START)
                 + pd.Timedelta(days=7 * (N_WEEKS - 1))).date())
    s = resolve_state(TARGET, truth_csv=truth, locations_csv=loc,
                      season_start=SEASON_START, as_of=as_of)
    gg = ng.growth_gap_series(TARGET, truth_csv=truth, locations_csv=loc,
                              season_start=SEASON_START, as_of=as_of)
    return s, gg, truth, loc, as_of


def test_natg_template_materializes_with_no_unresolved_tokens(tmp_path):
    from flubnf.sihrs_fit import materialize_model
    s, gg, *_ = _setup(tmp_path)
    out = materialize_model(s, TPL_NATG, tmp_path / "m.bngl", "x_flu",
                            extra_tokens=ng.natg_tokens(gg))
    txt = out.read_text()
    assert not re.findall(r"\{\{[A-Z0-9_]+\}\}", txt)
    assert f"iota    {ng.IOTA_FROZEN:g}" in txt
    assert "natgap() = if(" in txt or "natgap() = -" in txt or "natgap() = 0" in txt
    assert "exp( iota*natgap() )" in txt


def test_natg_template_omitting_its_tokens_fails_loudly(tmp_path):
    from flubnf.sihrs_fit import materialize_model
    s, *_ = _setup(tmp_path)
    with pytest.raises(ValueError, match="unresolved tokens"):
        materialize_model(s, TPL_NATG, tmp_path / "m.bngl", "x_flu")


def test_iota_is_a_constant_and_never_a_fitted_variable():
    """Law 1 as a test: a coupling strength must not become a var line."""
    from app.core.engines.pf import VARS_1S, DEFAULTS_BLOCK
    txt = TPL_NATG.read_text()
    assert "iota__FREE" not in txt
    assert "iota" not in VARS_1S and "iota" not in DEFAULTS_BLOCK
    # the same five fitted parameters as production, no more
    assert (sorted(set(re.findall(r"(\w+)__FREE", txt)))
            == sorted(set(re.findall(r"(\w+)__FREE", TPL_MIN.read_text()))))


def test_natg_template_is_production_min_plus_one_factor():
    """The control must stay recognisable inside the variant: identical model
    machinery, one extra factor on beta and one extra fixed parameter."""
    a, b = TPL_MIN.read_text(), TPL_NATG.read_text()
    for block in ("molecule types", "seed species", "observables",
                  "reaction rules", "actions"):
        ra = a.split(f"begin {block}")[1].split(f"end {block}")[0]
        rb = b.split(f"begin {block}")[1].split(f"end {block}")[0]
        assert ra == rb, f"{block} differs between production and natg"
    assert "beta() = beta0*exp( eps1*cos(2*pi*(t-phi1)/52) )" in a
    assert ("beta() = beta0*exp( eps1*cos(2*pi*(t-phi1)/52) )"
            "*exp( iota*natgap() )" in b)
    assert "natgap" not in a and "iota" not in a


def test_forecast_rule_is_documented_in_the_template():
    """Pre-registration is only pre-registration if it is written down."""
    txt = TPL_NATG.read_text().upper()
    assert "HELD CONSTANT ACROSS THE 1 TO 4" in txt
    assert "FROZEN" in txt and "0.3020" in TPL_NATG.read_text()


# ---------------------------------------------------------------------------
# 6. the production path is untouched
# ---------------------------------------------------------------------------
@pytest.fixture()
def fake_netgen(monkeypatch):
    """BNG2.pl replaced by a stub that writes the .net prepare() checks for.
    Network generation is BioNetGen's job and is exercised by the smoke run;
    what this file tests is which template prepare() reaches for."""
    real = subprocess.run

    def _run(cmd, *a, **kw):
        if cmd and cmd[0] == "perl":
            Path(kw.get("cwd", ".") or ".", "m.net").write_text("# stub\n")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return real(cmd, *a, **kw)

    import app.core.engines.pf as pfmod
    monkeypatch.setattr(pfmod.subprocess, "run", _run)
    return _run


def _prepare(tmp_path, monkeypatch, fake_netgen, extra, tag):
    import app.core.data as data
    import app.core.engines.pf as pfmod
    from app.core.runs import RunSpec
    s, gg, truth, loc, as_of = _setup(tmp_path)
    monkeypatch.setattr(data, "LOCATIONS", loc)
    monkeypatch.setattr(data, "vintage_path", lambda d: truth)
    wr = tmp_path / tag
    wr.mkdir()
    spec = RunSpec(engine="pf", forecast_date=as_of, locations=[TARGET],
                   season_start=SEASON_START, replicates=1, particles=100,
                   extra=extra)
    cells = pfmod.prepare(spec, wr)
    return cells, (wr / cells[0]["key"] / "m.bngl").read_bytes()


def test_production_path_is_byte_identical_without_the_variant(
        tmp_path, monkeypatch, fake_netgen):
    """No `variant` key, and an unrelated `extra`, must both give exactly the
    model file the production template has always produced."""
    from flubnf.sihrs_fit import materialize_model
    from app.core.engines.pf import DEFAULTS_BLOCK

    s, gg, truth, loc, as_of = _setup(tmp_path)
    ref = materialize_model(s, TPL_MIN, tmp_path / "ref.bngl",
                            f"{TARGET}_flu")
    expected = ref.read_text().replace("begin parameters\n",
                                       DEFAULTS_BLOCK, 1).encode()

    cells_a, got_a = _prepare(tmp_path, monkeypatch, fake_netgen, {}, "wa")
    cells_b, got_b = _prepare(tmp_path, monkeypatch, fake_netgen,
                              {"members": 2}, "wb")
    assert got_a == expected
    assert got_b == expected
    for c in (cells_a[0], cells_b[0]):
        assert c["variant"] == "1strain"
        assert c["iota"] is None and c["natg_last_gap"] is None


def test_natg_variant_selects_the_natg_template_and_records_iota(
        tmp_path, monkeypatch, fake_netgen):
    cells, got = _prepare(tmp_path, monkeypatch, fake_netgen,
                          {"variant": "natg", "iota": ng.IOTA_FROZEN}, "wc")
    txt = got.decode()
    assert cells[0]["variant"] == "natg"
    assert cells[0]["iota"] == pytest.approx(ng.IOTA_FROZEN)
    assert cells[0]["natg_last_gap"] is not None
    assert cells[0]["natg_clipped_weeks"] == 0
    assert "natgap()" in txt and not re.findall(r"\{\{[A-Z0-9_]+\}\}", txt)
    # the hold anchor agrees with the week the filter will forecast from
    assert f"last observed week {cells[0]['last_week_offset']}" in txt


def test_natg_defaults_to_the_frozen_iota_when_extra_omits_it(
        tmp_path, monkeypatch, fake_netgen):
    cells, got = _prepare(tmp_path, monkeypatch, fake_netgen,
                          {"variant": "natg"}, "wd")
    assert cells[0]["iota"] == pytest.approx(ng.IOTA_FROZEN)
    assert f"iota    {ng.IOTA_FROZEN:g}" in got.decode()
