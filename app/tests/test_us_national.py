"""The US national series: resolution order, provenance wording, and the
scoring policy that keeps US out of every pooled figure.

The published pooled record is a 52-JURISDICTION figure; US is the sum of
those same constituents, so pooling it would change the convention of a
published number. These tests fail if a US cell ever reaches one.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import playback, report_season, scoring   # noqa: E402
from app.core import us_national as usn                 # noqa: E402


# ------------------------------------------------------------ identification

def test_every_national_spelling_is_recognised():
    for name in ("US", "us", " US ", "US (national)", "US (NATIONAL)",
                 "United States", "USA"):
        assert usn.is_us(name), name
    for name in ("Ohio", "Utah", "Puerto Rico", "District of Columbia",
                 "Austria", ""):
        assert not usn.is_us(name), name


def test_with_us_is_idempotent_and_keeps_an_existing_spelling():
    assert usn.with_us(["Ohio"]) == ["Ohio", "US"]
    # an existing national entry keeps its OWN spelling (never rewritten)
    assert usn.with_us(["Ohio", "US (national)"]) == ["Ohio", "US (national)"]
    assert usn.state_names(["Ohio", "US"]) == ["Ohio"]


# ----------------------------------------------------------- scoring policy

#: Every published number is a RATIO, so the synthetic US cell is ~50x a
#: state's in magnitude (like the real sum-of-states row) AND a different
#: ratio: a leak then moves the value, not only the count.
POOLED_REL = 0.5                       # 8 state cells: 8.0 / 16.0
US_REL = 1.5                           # 4 national cells: 600.0 / 400.0
LEAKED_REL = 608.0 / 416.0             # 1.4615...: the 53-location figure


def _frame(with_us=True):
    rows = []
    for loc in (["Ohio", "Utah"] + (["US"] if with_us else [])):
        us = usn.is_us(loc)
        for h in range(4):
            rows.append({"model": "pf", "location": loc, "fips": loc,
                         "asof": "2098-01-03", "horizon": h,
                         "wis": 150.0 if us else 1.0,
                         "base_wis": 100.0 if us else 2.0})
    return pd.DataFrame(rows)


def _rel_of(df):
    return float(df.wis.sum()) / float(df.base_wis.sum())


def test_the_policy_is_named_and_off():
    # the only way US joins a pooled figure (would republish every headline)
    assert usn.POOLED_INCLUDES_US is False
    assert "never joins the pooled average" in usn.POOLED_SCOPE_NOTE


def test_the_synthetic_national_cell_can_actually_move_a_ratio():
    """The fixture can witness a leak: US scores a different relWIS."""
    df = _frame()
    assert _rel_of(df[~df.location.map(usn.is_us)]) == POOLED_REL
    assert _rel_of(df[df.location.map(usn.is_us)]) == US_REL
    assert _rel_of(df) == pytest.approx(LEAKED_REL)
    assert LEAKED_REL != POOLED_REL           # a leak is observable at all


def test_pooled_frame_drops_the_national_cell():
    df = _frame()
    pooled = usn.pooled_frame(df)
    assert len(pooled) == 8                      # two states, four horizons
    assert not pooled.location.map(usn.is_us).any()
    # the VALUE, not only the cell count
    a = _rel_of(pooled)
    b = _rel_of(usn.pooled_frame(_frame(with_us=False)))
    assert a == b == POOLED_REL
    assert a != pytest.approx(LEAKED_REL)     # 1.462 is the leaked figure


def test_pooled_locations_drops_the_national_name():
    assert usn.pooled_locations(["Ohio", "US", "Utah"]) == ["Ohio", "Utah"]


def test_a_fitted_us_row_moves_no_pooled_figure():
    """THE headline guard: scored with and without a fitted US row, every
    pooled figure is identical AND equals the state-only value."""
    def _figures(with_us):
        df = _frame(with_us=with_us)
        pooled = usn.pooled_frame(df)
        return {"pooled": _rel_of(pooled),
                "cells": len(pooled),
                "curve": report_season._cumulative_curve(df)}

    a, b = _figures(True), _figures(False)
    assert a == b
    # the shared value is the state-only one (not an agreed leaked number)
    assert a["pooled"] == POOLED_REL
    assert a["cells"] == 8
    assert [round(v, 6) for _w, v in a["curve"]] == [POOLED_REL]
    # 1.462 is the leaked figure
    assert a["curve"][-1][1] != pytest.approx(LEAKED_REL)


def test_season_scores_hands_back_the_full_frame(tmp_path):
    """The loader drops nothing: gating belongs at each reader."""
    root = tmp_path / "season"
    root.mkdir()
    (root / "scores.json").write_text(_frame().to_json(orient="records"))
    got = playback._season_scores(root)
    assert got.location.map(usn.is_us).any()


# ------------------------------------------- the gate at every call site
# Each test drives a production call site end to end and asserts the VALUE,
# so deleting its `usn.pooled_frame(...)` fails here (a source grep would
# survive a gutted function body).

def test_playback_stats_never_pool_a_fitted_us_cell(tmp_path):
    """playback._stats: the player's relWIS table (copied by verdict tiles)."""
    root = tmp_path / "season"
    root.mkdir()
    (root / "scores.json").write_text(_frame().to_json(orient="records"))
    stats = playback._stats(root, "2098-99", "2098-01-03", {}, {},
                            {"pf": {}}, {})
    assert stats["pf"]["week_rel"] == pytest.approx(POOLED_REL)
    assert stats["pf"]["cum_rel"] == pytest.approx(POOLED_REL)
    # 1.462 would be the figure with US pooled in
    assert stats["pf"]["cum_rel"] != pytest.approx(LEAKED_REL)


def test_the_season_report_curve_never_pools_a_fitted_us_cell():
    """report_season._cumulative_curve draws the season's published line."""
    curve = report_season._cumulative_curve(_frame())
    assert [round(v, 6) for _w, v in curve] == [POOLED_REL]
    assert curve[-1][1] != pytest.approx(LEAKED_REL)


def test_the_season_report_table_reports_us_apart_from_its_pooled_figures(
        tmp_path, monkeypatch):
    """report_season._summary_block (exported verdict): US appears on its own
    labelled row; no pooled figure beside it contains it."""
    root = tmp_path / "season"
    root.mkdir()
    (root / "scores.json").write_text(_frame().to_json(orient="records"))
    html = report_season._summary_block(root, ["2098-01-03"], {})
    # the pooled scope: 8 state cells, never the 12 a leak gives
    pf = report_season.names_for_root(root)["pf"]
    assert f"the season's 8 scored {pf} cells" in html
    assert "12 scored" not in html
    # the cumulative curve endpoint is the state-only value
    assert ">0.500<" in html
    # the national figure IS reported, on its own labelled row and tile
    assert "US (fitted)" in html
    assert "1.500" in html
    # 1.462 (US pooled in) appears nowhere
    assert "1.462" not in html
    assert usn.POOLED_SCOPE_NOTE in html


def test_site_builder_excludes_the_national_row_from_ours_and_theirs(
        monkeypatch):
    """The public site RESCORES from playback payloads (docs/SITE.md), so
    site_build._score_payload is the path to hold: count and value."""
    from app.core import horizons as hz
    from app.core import scoring as _scoring
    from app.core import site_build
    from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
    from flubnf.wis import wis as wis_fn

    asof = "2098-01-03"
    n2f = {"Ohio": "39", "Utah": "49", "US": "US"}
    T = pd.Timestamp(asof) + pd.Timedelta(days=7)
    # the national truth row is the sum of the states'
    truth = {("39", T): 40.0, ("49", T): 60.0, ("US", T): 100.0}
    med = {"Ohio": 50.0, "Utah": 50.0, "US": 250.0}

    def _degenerate(v):
        return {str(L): v for L in QL}           # a point mass: WIS = |v - y|

    # payload horizons are canonical: HORIZONS[0] is the first forecast week,
    # the only one the truth and baseline stubs cover
    h0 = hz.HORIZONS[0]
    payload = {"asof": asof, "official": {},
               "models": {"ensemble": {loc: {h0: _degenerate(med[loc])}
                                       for loc in n2f}}}
    handed = []
    monkeypatch.setattr(_scoring, "_baseline_cells",
                        lambda a, fips_set, tr: handed.append(set(fips_set))
                        or {(f, a, 0): 20.0 for f in fips_set})

    out = site_build._score_payload(payload, truth, n2f, {})

    def _wis(loc, actual):
        return float(wis_fn({float(L): med[loc] for L in QL}, actual).wis)

    wis_states = _wis("Ohio", 40.0) + _wis("Utah", 60.0)
    pooled = wis_states / 40.0                   # two cells, base 20 each
    leaked = (wis_states + _wis("US", 100.0)) / 60.0
    assert out["ensemble"][2] == 2               # two cells, never three
    assert site_build._rel(out["ensemble"]) == pytest.approx(pooled)
    assert site_build._rel(out["ensemble"]) != pytest.approx(leaked)
    # the national row never even reaches the baseline builder
    assert handed and all("US" not in s for s in handed)


def _console_season(tmp_path, monkeypatch):
    """One scored week, two states and a fitted US row, laid out so the real
    season-page route renders complete in one request."""
    import json

    from app.core import playback as _pb
    from app.core import retro as _retro
    from app.core import scoring as _scoring
    from flubnf.quantiles import FLUSIGHT_QUANTILES as QL

    asof, season = "2098-01-03", "2098-99"
    n2f = {"Ohio": "39", "Utah": "49"}
    truth = {}
    for fips in ("39", "49", "US"):
        for k in range(-8, 8):
            truth[(fips, pd.Timestamp(asof) + pd.Timedelta(days=7 * k))] = 100.0

    def _bases(a, fips_set, _t):
        return {(f, a, h): 2.0 for f in fips_set for h in range(4)}

    monkeypatch.setattr(_pb, "load_truth", lambda: (truth, dict(n2f)))
    monkeypatch.setattr(_pb, "_baseline_cells", _bases)
    monkeypatch.setattr(_pb, "HUB", tmp_path / "hub")      # no officials
    monkeypatch.setattr(_scoring, "load_truth", lambda: (truth, dict(n2f)))
    monkeypatch.setattr(_scoring, "_baseline_cells", _bases)

    root = tmp_path / season
    wd = root / "weeks" / asof
    wd.mkdir(parents=True)
    pf = {loc: {str(h): [99.0, 100.0, 101.0] for h in range(5)} for loc in n2f}
    an = {loc: {str(h): {str(L): 100.0 + (L - 0.5) * 10 for L in QL}
                for h in range(1, 5)} for loc in n2f}
    (wd / "samples.json").write_text(
        json.dumps({"asof": asof, "pf": pf, "analogue": an}))
    _frame().to_json(root / "scores.json")
    _retro.write_meta(root, {"status": "done", "weeks_completed": 1,
                             "total_weeks": 1})
    return root, season


def test_the_console_season_page_never_pools_a_fitted_us_cell(tmp_path,
                                                              monkeypatch):
    """server.retro_results (the console's verdict tiles, curve and table),
    driven through the real route."""
    from fastapi.testclient import TestClient

    from app.ui import server as srv

    _root, season = _console_season(tmp_path, monkeypatch)
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    html = TestClient(srv.app).get(f"/retro/{season}").text
    assert "preparing results" not in html       # a complete page, not a stub
    # the pooled ensemble verdict is the two-state figure
    assert "0.500" in html
    # the national figure is present, on its own row, labelled as fitted
    assert "1.500" in html
    assert "US (fitted)" in html
    # 1.462 would be the pooled figure with US in
    assert "1.462" not in html


def test_weekly_report_table_reports_us_apart_from_the_pooled_row():
    """Weekly table: US on its own labelled line; the total names its scope."""
    df = pd.DataFrame([
        {"location": "Ohio", "fips": "39", "horizon": 1,
         "wis": 1.0, "base_wis": 2.0},
        {"location": "US", "fips": "US", "horizon": 1,
         "wis": 90.0, "base_wis": 100.0},
    ])
    html = scoring.summary_table_html(df)
    assert "US (fitted)" in html                  # its own labelled row
    assert "All jurisdictions (US excluded)" in html
    assert '<td class="num ok">0.500</td>' in html   # Ohio alone, not 0.892
    assert "never joins the pooled average" in html
    # 0.892 would be the figure with US pooled in
    assert "0.892" not in html


# ------------------------------------------- provenance is never hardcoded

def test_the_weekly_report_claims_a_fitted_national_only_when_it_has_one(
        tmp_path):
    """The weekly report says "US (fitted)" only when a national forecast
    landed; provenance is derived from the run, never hardcoded."""
    from app.core.report_v2 import build_report

    empty = build_report("2098-01-03", {}, {}, {},
                         tmp_path / "none.html").read_text()
    assert "National fan and accuracy charts appear once" in empty
    assert usn.LABELS[usn.FITTED] not in empty
    assert usn.NOTES[usn.FITTED] not in empty
    assert usn.SHORT_LABELS[usn.FITTED] not in empty

    # the bundle's no-national shape: summary_html (the accuracy card) is
    # always filled and is not evidence of a fit
    shaped = build_report("2098-01-03", {}, {},
                          {"fan": None, "acc": None, "note": "",
                           "summary_html": "<div>accuracy card</div>"},
                          tmp_path / "shaped.html").read_text()
    assert "accuracy card" in shaped
    assert usn.LABELS[usn.FITTED] not in shaped
    assert usn.NOTES[usn.FITTED] not in shaped

    import plotly.graph_objects as go
    landed = build_report("2098-01-03", {}, {}, {"fan": go.Figure()},
                          tmp_path / "some.html").read_text()
    assert usn.LABELS[usn.FITTED] in landed
    assert usn.NOTES[usn.FITTED] in landed
    # and the placeholder is gone
    assert "National fan and accuracy charts appear once" not in landed


# ----------------------------------------------------------- resolution order

def _root_with_scores(tmp_path, df):
    root = tmp_path / "season"
    root.mkdir(exist_ok=True)
    (root / "scores.json").write_text(df.to_json(orient="records"))
    return root


def test_resolution_prefers_a_fitted_cell(tmp_path, monkeypatch):
    from app.core import retro
    called = []
    monkeypatch.setattr(retro, "national_aggregate",
                        lambda *a, **k: called.append(1) or {})
    root = _root_with_scores(tmp_path, _frame())
    us = usn.resolve(root, _frame())
    assert us.provenance == usn.FITTED
    assert us.is_fitted and not us.is_fallback
    assert us.scores["pf"] == pytest.approx(US_REL)
    assert us.short_label == "US (fitted)"
    assert us.label == "US national (fitted)"
    assert us.n_states == 2                      # Ohio and Utah, not three
    # a fitted cell short-circuits the expensive construction
    assert called == []


def test_resolution_falls_back_to_the_aggregate(tmp_path, monkeypatch):
    from app.core import retro
    monkeypatch.setattr(
        retro, "national_aggregate",
        lambda *a, **k: {"pf": 0.494, "analogue": 0.981, "ensemble": 0.629,
                         "cells": {"pf": 96, "analogue": 96,
                                   "ensemble": 96}, "weeks": 27})
    root = _root_with_scores(tmp_path, _frame(with_us=False))
    us = usn.resolve(root, _frame(with_us=False))
    assert us.provenance == usn.AGGREGATED
    assert us.is_fallback and not us.is_fitted
    assert us.scores["ensemble"] == pytest.approx(0.629)
    assert us.short_label == "US (aggregated)"
    assert us.label == "US national (sum of 2 states)"
    assert "fallback" in us.fallback_note
    assert "not a fitted national forecast" in us.note


def test_resolution_ends_at_officials_only(tmp_path, monkeypatch):
    from app.core import retro
    monkeypatch.setattr(retro, "national_aggregate", lambda *a, **k: None)
    root = _root_with_scores(tmp_path, _frame(with_us=False))
    us = usn.resolve(root, _frame(with_us=False))
    assert us.provenance == usn.OFFICIALS_ONLY
    assert us.is_fallback and not us.has_scores
    assert us.label == "US (official models only)"
    assert "fallback" in us.fallback_note
    assert us.reason                              # says why, never silent


def test_a_failing_aggregate_degrades_to_officials_with_a_reason(
        tmp_path, monkeypatch):
    from app.core import retro

    def boom(*a, **k):
        raise RuntimeError("cold cache, no samples")

    monkeypatch.setattr(retro, "national_aggregate", boom)
    root = _root_with_scores(tmp_path, _frame(with_us=False))
    us = usn.resolve(root, _frame(with_us=False))
    assert us.provenance == usn.OFFICIALS_ONLY
    assert "RuntimeError" in us.reason


def test_allow_aggregate_false_never_claims_an_aggregate(tmp_path,
                                                         monkeypatch):
    from app.core import retro

    def boom(*a, **k):
        raise AssertionError("the construction must not have been reached")

    monkeypatch.setattr(retro, "national_aggregate", boom)
    root = _root_with_scores(tmp_path, _frame(with_us=False))
    us = usn.resolve(root, _frame(with_us=False), allow_aggregate=False)
    assert us.provenance == usn.OFFICIALS_ONLY


# --------------------------------------------------------------- the wording

def test_every_provenance_has_a_distinct_label_and_note():
    labels = {p: usn.label(p) for p in usn.PROVENANCES}
    shorts = {p: usn.short_label(p) for p in usn.PROVENANCES}
    notes = {p: usn.note(p) for p in usn.PROVENANCES}
    assert len(set(labels.values())) == 3
    assert len(set(shorts.values())) == 3
    assert len(set(notes.values())) == 3
    # the aggregated label names its state count where the caller knows it
    assert usn.label(usn.AGGREGATED, 52) == "US national (sum of 52 states)"
    assert usn.label(usn.AGGREGATED, 6) == "US national (sum of 6 states)"
    # neither fallback may read as a plain fitted national forecast
    for p in (usn.AGGREGATED, usn.OFFICIALS_ONLY):
        assert "fitted" not in labels[p].lower()
        assert usn.FALLBACK_WORD in usn.FALLBACK_NOTES[p]


def test_the_player_and_python_share_one_wording():
    """Labels are defined once: player.js carries them as a marked JSON
    literal and Python parses that same literal."""
    js = report_season.player_us_labels()
    assert js == usn.LABELS, (js, usn.LABELS)


def test_the_serialised_form_carries_the_label_with_the_numbers():
    """A serialised US score always carries the words saying what kind it is."""
    d = usn.UsNational(usn.AGGREGATED, scores={"ensemble": 0.629},
                       cells={"ensemble": 96}, n_states=52).as_dict()
    assert d["ensemble"] == 0.629
    for key in ("provenance", "label", "short_label", "note", "fitted",
                "fallback", "fallback_note"):
        assert key in d, key
    assert d["fallback"] is True
    json.dumps(d)                                 # JSON-safe for both hosts
