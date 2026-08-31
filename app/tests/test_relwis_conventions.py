"""The scoring-convention switch: two definitions of relWIS, never mixed.

Two quantities are called relative WIS. The ratio of sums is this project's
home convention and needs only its own sealed scores; the pairwise scaled
figure is what the CDC FluSight dashboard reports and needs every other
team's per-cell WIS, which a given machine may simply not have. They give
different numbers for the same forecasts, so the tests below pin three
things: the arithmetic of each, that the pairwise one obeys the rules that
make it the CDC figure (shared cells only, baseline at exactly 1.0), and
that its absence is stated rather than papered over with the other one.

Everything here builds its own frames. No hub clone, no app/state, no
cached field data: the last of those is explicitly pointed at an empty
directory so a development machine that HAS the cache cannot make the
unavailable path pass for the wrong reason.
"""
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import relwis                          # noqa: E402
from app.ui import server as srv                     # noqa: E402

#: Three cells, two weeks, one jurisdiction. Small enough to check by hand.
C1 = ("2024-01-06", "01", 0)
C2 = ("2024-01-06", "01", 1)
C3 = ("2024-01-13", "01", 0)

#: The hand-computable field. FluSight-baseline and TeamA submitted all
#: three cells; OURS submitted only the first two, which is what makes the
#: "cells both models submitted" rule visible: the baseline's third cell is
#: enormous, so a mean taken over each model's own cells instead of the
#: shared ones would move our figure by a factor of three.
FIELD_WIS = {
    relwis.BASELINE: {C1: 4.0, C2: 4.0, C3: 100.0},
    "TeamA": {C1: 2.0, C2: 2.0, C3: 50.0},
    "FluBNF-PF": {C1: 1.0, C2: 1.0},
}


def _cells(wis_by_model=None):
    rows = []
    for model, cells in (wis_by_model or FIELD_WIS).items():
        for (ref, loc, hor), w in cells.items():
            rows.append({"model": model, "reference_date": ref,
                         "location": loc, "horizon": hor, "wis": w})
    return pd.DataFrame(rows, columns=list(relwis.CELL_COLUMNS))


def _seal_frame():
    """A seal-shaped scores table: two horizons, one week, one state."""
    rows = []
    for hor, (pf, an, ens) in enumerate([(1.0, 2.0, 1.0), (3.0, 2.0, 1.0)]):
        for model, w in (("pf", pf), ("analogue", an), ("ensemble", ens)):
            rows.append({"model": model, "location": "Ohio", "fips": 39,
                         "asof": "2024-01-06", "horizon": hor, "wis": w,
                         "base_wis": 4.0, "rel": w / 4.0})
    return pd.DataFrame(rows)


@pytest.fixture()
def no_field(tmp_path, monkeypatch):
    """Point the field-cell loader at an empty directory.

    Without this a development machine with the real cache would satisfy
    the unavailable tests by accident, which is the one way this suite
    could go green while the feature was broken.
    """
    d = tmp_path / "no-field-cells"
    d.mkdir()
    monkeypatch.setenv(relwis.FIELD_CELLS_ENV, str(d))
    relwis._FIELD_CACHE.clear()
    return d


# ---------------------------------------------------- convention A: sums

def test_ratio_of_sums_is_summed_wis_over_summed_baseline():
    cells = _cells()
    # TeamA shares all three cells: (2 + 2 + 50) / (4 + 4 + 100) = 0.5
    v, n = relwis.ratio_of_sums(cells, "TeamA")
    assert (round(v, 12), n) == (0.5, 3)
    # ours shares only the first two: (1 + 1) / (4 + 4) = 0.25, and the
    # baseline's third cell must not enter the denominator
    v, n = relwis.ratio_of_sums(cells, "FluBNF-PF")
    assert (round(v, 12), n) == (0.25, 2)
    # the baseline against itself is exactly 1
    v, _ = relwis.ratio_of_sums(cells, relwis.BASELINE)
    assert v == 1.0


def test_ratio_of_sums_says_nothing_when_there_is_no_overlap():
    cells = _cells({relwis.BASELINE: {C1: 4.0}, "TeamA": {C3: 2.0}})
    v, n = relwis.ratio_of_sums(cells, "TeamA")
    assert v != v and n == 0                      # nan, no cells
    assert relwis.ratio_of_sums(cells, "NobodyHere") == (float("nan"), 0) \
        or relwis.ratio_of_sums(cells, "NobodyHere")[1] == 0


# ------------------------------------------------- convention B: pairwise

def test_pairwise_uses_only_cells_both_models_submitted():
    """The whole hand computation, and the rule that makes it CDC's figure.

    theta_i is the geometric mean over j of (mean WIS of i on the cells i
    and j share) / (mean WIS of j on those same cells):

      baseline: vs TeamA 36/18 = 2, vs ours 4/1 = 4    -> sqrt(8)
      TeamA:    vs baseline 0.5,    vs ours 2/1 = 2    -> 1
      ours:     vs baseline 1/4,    vs TeamA 1/2       -> sqrt(0.125)

    scaled by the baseline's own skill: baseline 1, TeamA 1/sqrt(8) =
    0.353553, ours sqrt(0.125)/sqrt(8) = 0.125.
    """
    scaled, n = relwis.pairwise_scaled(
        _cells(), [relwis.BASELINE, "TeamA", "FluBNF-PF"])
    assert scaled[relwis.BASELINE] == 1.0          # exactly, by construction
    assert round(scaled["TeamA"], 9) == 0.353553391
    assert round(scaled["FluBNF-PF"], 9) == 0.125
    # coverage travels with a field-dependent number
    assert n["FluBNF-PF"] == 2 and n["TeamA"] == 3


def test_pairwise_scaling_puts_the_baseline_at_one_whatever_the_field():
    """Baseline == 1.0 is the definition, not a property of this fixture."""
    for extra in ({}, {"TeamB": {C1: 8.0, C2: 1.0, C3: 7.0}},
                  {"TeamB": {C3: 1.0}}):
        wis = dict(FIELD_WIS)
        wis.update(extra)
        scaled, _ = relwis.pairwise_scaled(_cells(wis), list(wis))
        assert scaled[relwis.BASELINE] == 1.0


def test_pairwise_ignores_a_model_with_no_shared_cells():
    """A team that overlaps nobody contributes no pair and is not counted."""
    wis = dict(FIELD_WIS)
    wis["Hermit"] = {("2019-01-05", "99", 3): 1.0}
    scaled, _ = relwis.pairwise_scaled(_cells(wis), list(wis))
    assert scaled["Hermit"] != scaled["Hermit"]     # nan: no pair exists
    assert round(scaled["FluBNF-PF"], 9) == 0.125   # and nobody else moved


def test_insert_model_ranks_us_inside_the_real_field():
    got = relwis.insert_model(_cells(), "FluBNF-PF",
                              [relwis.BASELINE, "TeamA"])
    assert round(got["value"], 9) == 0.125
    assert (got["rank"], got["n_models"]) == (1, 3)
    assert got["n_cells"] == 2


def test_a_model_the_field_never_met_yields_no_figure_rather_than_a_crash():
    """Our cells in a jurisdiction the cache's weeks do not reach.

    The field cells are a cached artifact built out of repo at some past
    moment, so one jurisdiction where its weeks and this run's weeks never
    meet is an ordinary coverage gap, not a corrupt cache. The rest of the
    field still overlaps itself there, so the baseline scaling exists and
    the tournament runs; only OUR model has no pair. That model has no
    figure, which is the documented empty result. It used to raise
    ValueError out of the rank lookup instead, and nothing between here and
    the route caught it, so one such jurisdiction turned the whole pairwise
    season page into a 500.
    """
    wis = {relwis.BASELINE: {C1: 4.0, C2: 4.0}, "TeamA": {C1: 2.0, C2: 2.0},
           "FluBNF-PF": {C3: 1.0}}           # a week nobody else submitted
    cells = _cells(wis)
    scaled, _ = relwis.pairwise_scaled(cells, list(wis))
    assert scaled["FluBNF-PF"] != scaled["FluBNF-PF"]        # nan, no pair
    assert relwis.insert_model(cells, "FluBNF-PF",
                               [relwis.BASELINE, "TeamA"]) == {}


def test_one_jurisdiction_with_no_overlap_does_not_cost_the_season(tmp_path):
    """The whole page survives that gap, and the good state still scores."""
    d = tmp_path / "cells"
    d.mkdir()
    for model, w in ((relwis.BASELINE, 4.0), ("TeamA", 2.0)):
        rows = [{"model": model, "reference_date": r, "location": loc,
                 "horizon": h, "wis": w}
                # "39" meets our week, "02" only has a week we never scored
                for r, loc in (("2024-01-13", "39"), ("2024-01-20", "02"))
                for h in (0, 1)]
        pd.DataFrame(rows, columns=list(relwis.CELL_COLUMNS)).to_csv(
            d / f"{model}.csv", index=False)
    frame = pd.concat([_seal_frame(),
                       _seal_frame().assign(location="Alaska", fips=2)],
                      ignore_index=True)
    figs = relwis.season_figures(frame, relwis.PAIRWISE,
                                 field=relwis.load_field_cells(d))
    assert figs.available and figs.convention == relwis.PAIRWISE
    # Ohio is the jurisdiction the field actually met; Alaska has no figure
    # and is left out rather than printed as "nan"
    assert [r["name"] for r in figs.states] == ["Ohio"]


# ------------------------------------------------------- the seal's shape

def test_seal_cells_applies_the_frozen_reference_date_join():
    cells = relwis.seal_cells(_seal_frame())
    # reference_date = asof + 7 days, the project's frozen hub join
    assert set(cells["reference_date"]) == {"2024-01-13"}
    assert set(cells["location"]) == {"39"}
    # our three members plus ONE baseline row per cell, not one per member
    ours = cells[cells["model"] != relwis.BASELINE]
    base = cells[cells["model"] == relwis.BASELINE]
    assert len(ours) == 6 and len(base) == 2
    assert set(ours["model"]) == set(relwis.SEAL_MODEL_NAMES.values())
    # and the arithmetic reads through: PF (1 + 3) / (4 + 4)
    v, n = relwis.ratio_of_sums(cells, "FluBNF-PF")
    assert (v, n) == (0.5, 2)


def test_seal_cells_returns_an_empty_frame_for_unusable_input():
    for bad in (None, pd.DataFrame(), pd.DataFrame({"nothing": [1]})):
        out = relwis.seal_cells(bad)
        assert list(out.columns) == list(relwis.CELL_COLUMNS)
        assert len(out) == 0


# --------------------------------------------------- the unavailable path

def test_a_missing_cache_is_a_normal_state_with_a_reason(tmp_path):
    f = relwis.load_field_cells(tmp_path / "not-here")
    assert not f.available
    assert "no hub field data cached" in f.reason
    assert "not-here" in f.reason               # names where it looked
    assert f.cells is None


def test_an_empty_cache_directory_says_so(no_field):
    f = relwis.load_field_cells()
    assert not f.available
    assert "no per-model score files" in f.reason


def test_a_cache_without_the_baseline_cannot_scale_and_says_why(tmp_path):
    d = tmp_path / "cells"
    d.mkdir()
    _cells({"TeamA": {C1: 2.0}}).to_csv(d / "TeamA.csv", index=False)
    f = relwis.load_field_cells(d)
    assert not f.available
    assert relwis.BASELINE in f.reason


def test_the_env_var_overrides_where_the_cache_is_looked_for(tmp_path,
                                                             monkeypatch):
    monkeypatch.setenv(relwis.FIELD_CELLS_ENV, str(tmp_path / "elsewhere"))
    assert relwis.field_cells_dir() == tmp_path / "elsewhere"
    monkeypatch.delenv(relwis.FIELD_CELLS_ENV)
    # with nothing set the answer is a real path, never None, so an
    # unavailability message can always name one
    assert isinstance(relwis.field_cells_dir(), Path)


def test_the_unavailable_pairwise_view_never_becomes_the_other_convention(
        no_field):
    """THE safety requirement. No numbers, and a reason instead."""
    df = _seal_frame()
    ratio = relwis.season_figures(df, relwis.RATIO_OF_SUMS)
    assert ratio.available and ratio.values["pf"] == 0.5

    pair = relwis.season_figures(df, relwis.PAIRWISE)
    assert not pair.available
    assert pair.values == {} and pair.states == ()
    assert pair.convention == relwis.PAIRWISE      # never silently switched
    assert "no hub field data cached" in pair.reason
    # and specifically: not the ratio-of-sums answer wearing a new label
    assert 0.5 not in (pair.values or {}).values()


def test_a_pairwise_view_with_no_overlapping_season_says_so(tmp_path):
    """A cache that holds real cells for the WRONG season is unavailable
    too, and says which problem it is."""
    d = tmp_path / "cells"
    d.mkdir()
    old = _cells({relwis.BASELINE: {("2019-01-05", "39", 0): 4.0},
                  "TeamA": {("2019-01-05", "39", 0): 2.0}})
    old.to_csv(d / "field.csv", index=False)
    field = relwis.load_field_cells(d)
    assert field.available
    figs = relwis.season_figures(_seal_frame(), relwis.PAIRWISE, field=field)
    assert not figs.available
    assert "season" in figs.reason


# --------------------------------------------------------- what a page gets

def _multi_state_seal():
    """A seal frame over three jurisdictions whose FIPS order and whose
    alphabetical order disagree: Puerto Rico is FIPS 72, so a table sorted
    on the cell key drops it past Wyoming."""
    rows = []
    for loc, fips in (("Ohio", 39), ("Puerto Rico", 72), ("Wyoming", 56)):
        for model, w in (("pf", 1.0), ("analogue", 2.0), ("ensemble", 1.0)):
            rows.append({"model": model, "location": loc, "fips": fips,
                         "asof": "2024-01-06", "horizon": 0, "wis": w,
                         "base_wis": 4.0, "rel": w / 4.0})
    return pd.DataFrame(rows)


def test_the_state_table_is_ordered_by_the_name_it_prints():
    """Alphabetical by jurisdiction name, which the table's own script
    documents as the order the page loads in. Sorting on the FIPS the
    cells are keyed by agrees for the states and not for the territories."""
    figs = relwis.season_figures(_multi_state_seal(), relwis.RATIO_OF_SUMS)
    assert [r["name"] for r in figs.states] == ["Ohio", "Puerto Rico",
                                                "Wyoming"]


def test_season_figures_carry_their_own_convention_and_per_state_rows():
    figs = relwis.season_figures(_seal_frame(), relwis.RATIO_OF_SUMS)
    assert figs.convention == relwis.RATIO_OF_SUMS
    assert figs.label == "ratio of sums"
    assert [r["name"] for r in figs.states] == ["Ohio"]
    assert figs.states[0]["ensemble"] == 0.25      # (1 + 1) / (4 + 4)
    assert figs.detail["pf"]["n_cells"] == 2


def test_pairwise_season_figures_carry_rank_and_field_size(tmp_path):
    """Computed, and deliberately not printed.

    Placement against the FluSight field is withdrawn (methods.html,
    docs/RELEASE-1.0.md) because the field's own scores come from a builder
    outside this repository. The machinery stays covered here so that
    lifting the withdrawal is a template change; the page tests below pin
    that nothing renders it.
    """
    d = tmp_path / "cells"
    d.mkdir()
    # a field on the cells the seal frame lands on: asof + 7 days
    ref = "2024-01-13"
    _cells({relwis.BASELINE: {(ref, "39", 0): 4.0, (ref, "39", 1): 4.0},
            "TeamA": {(ref, "39", 0): 2.0, (ref, "39", 1): 2.0}}
           ).to_csv(d / "field.csv", index=False)
    figs = relwis.season_figures(_seal_frame(), relwis.PAIRWISE,
                                 field=relwis.load_field_cells(d))
    assert figs.available and figs.convention == relwis.PAIRWISE
    assert figs.n_field == 2                      # baseline and TeamA
    assert figs.detail["ensemble"]["rank"] >= 1
    assert figs.detail["ensemble"]["n_models"] == 3
    assert [r["name"] for r in figs.states] == ["Ohio"]


def test_the_field_size_is_the_field_the_ranks_were_taken_in(tmp_path):
    """`n_field` and the ranks have to describe ONE tournament.

    A cache spans every season it was built from; teams that submitted only
    in some OTHER season were never in this figure's field and must not be
    counted into it. Neither number reaches a page today (placement is
    withdrawn), but they are carried together and would be read together,
    so a field size counted off the cache instead of off the tournament
    would contradict the ranks beside it the moment either is shown.
    """
    d = tmp_path / "cells"
    d.mkdir()
    ref = "2024-01-13"
    _cells({relwis.BASELINE: {(ref, "39", 0): 4.0, (ref, "39", 1): 4.0},
            "TeamA": {(ref, "39", 0): 2.0, (ref, "39", 1): 2.0},
            # a whole season earlier, and the national row: neither is in
            # the field this season's jurisdiction figures are scored in
            "OldTeam": {("2019-01-05", "39", 0): 2.0},
            "UsOnlyTeam": {(ref, "US", 0): 2.0}}
           ).to_csv(d / "field.csv", index=False)
    figs = relwis.season_figures(_seal_frame(), relwis.PAIRWISE,
                                 field=relwis.load_field_cells(d))
    assert figs.available
    assert figs.n_field == 2                      # baseline and TeamA only
    for m, det in figs.detail.items():
        assert det["n_models"] == figs.n_field + 1, m


def test_an_unknown_convention_resolves_to_the_project_default():
    for junk in ("", None, "PAIRWISE-ish", "cdc", 7):
        assert relwis.convention_of(junk) == relwis.RATIO_OF_SUMS
    assert relwis.convention_of("pairwise") == relwis.PAIRWISE
    assert relwis.convention_of(" Ratio_Of_Sums ") == relwis.RATIO_OF_SUMS


# ------------------------------------------------------- the server helper

def test_the_server_helper_caches_on_the_scores_file_identity(tmp_path):
    root = tmp_path / "2098-99"
    root.mkdir()
    _seal_frame().to_json(root / "scores.json")
    a = srv._relwis_figures(root, relwis.RATIO_OF_SUMS)
    b = srv._relwis_figures(root, relwis.RATIO_OF_SUMS)
    assert a is b                                  # same inputs, same object
    assert a.values["pf"] == 0.5


def test_the_server_helper_survives_a_root_with_no_scores(tmp_path,
                                                          no_field):
    figs = srv._relwis_figures(tmp_path / "empty", relwis.PAIRWISE)
    assert not figs.available and figs.reason
    assert figs.convention == relwis.PAIRWISE


# ----------------------------------------------------------- the page copy

def _flat(html: str) -> str:
    """Rendered copy with its line wrapping collapsed.

    Template sentences wrap at the source's column limit, so asserting on
    prose against the raw render pins the wrapping rather than the words.
    """
    return re.sub(r"\s+", " ", html)


def _season_page(**kw):
    ctx = dict(active="Retrospective", season="2098-99",
               heads={"ensemble": 0.9}, curve=[("2098-11-07", 0.95),
                                               ("2098-11-14", 0.9)],
               states=[{"name": "Ohio", "pf": 0.9, "analogue": 1.1,
                        "ensemble": None}],
               us_row=None, us=None, pooled_note="", preparing=None,
               archive="", archive_when="", prog=None,
               conv=relwis.RATIO_OF_SUMS, figs=None,
               conventions=srv._relwis_conventions(),
               weeks=["2098-11-07", "2098-11-14"], week="2098-11-14",
               map_html="<div id='usmap-wrap'></div>",
               official_catalog=[], n_weeks=2, score_error="")
    ctx.update(kw)
    return srv.templates.env.get_template("retro_season.html").render(**ctx)


def test_the_page_offers_both_conventions_and_marks_the_live_one():
    html = _season_page(figs=relwis.season_figures(_seal_frame(),
                                                   relwis.RATIO_OF_SUMS))
    for c in srv._relwis_conventions():
        assert f"conv={c['key']}" in html
        assert c["name"] in html
    assert 'aria-pressed="true"' in html
    # the warning is on the page, not only in the code
    assert "must never be compared with a figure from the other" in _flat(html)


def test_every_head_tile_names_the_convention_that_produced_it():
    ratio = _season_page(figs=relwis.season_figures(_seal_frame(),
                                                    relwis.RATIO_OF_SUMS))
    assert "relWIS vs the FluSight baseline, ratio of sums" in _flat(ratio)
    tiles = _flat(ratio).split("Scoring convention")[1].split("Cumulative")[0]
    assert "pairwise scaled" not in tiles

    figs = relwis.season_figures(_seal_frame(), relwis.RATIO_OF_SUMS)
    pair = _season_page(conv=relwis.PAIRWISE, figs=relwis.Figures(
        convention=relwis.PAIRWISE, values={"ensemble": 0.629},
        detail={"ensemble": {"n_cells": 4922, "rank": 6, "n_models": 48}},
        states=tuple(figs.states), n_field=47, source="/tmp/cells"))
    assert ("relWIS vs the FluSight baseline, pairwise scaled, the CDC "
            "dashboard convention") in _flat(pair)
    # the coverage rides beside the value; the placement does not
    assert "(4,922 cells)" in _flat(pair)


def test_the_page_shows_the_pairwise_value_and_never_the_placement():
    """THE withdrawal, enforced on the surface that used to break it.

    Methods says placement against the FluSight field is not restated. The
    season page under the pairwise convention used to print "ranked 6 of
    48" and "Field: 47 FluSight teams" anyway, so the application asserted
    a rank and denied it in the same build. The VALUE stays: it is this
    project's own score under one stated convention, reproducible from the
    sealed cells. The rank needs the whole field scored on that convention,
    which this repository cannot rebuild.
    """
    figs = relwis.season_figures(_seal_frame(), relwis.RATIO_OF_SUMS)
    pair = _season_page(conv=relwis.PAIRWISE, heads={"ensemble": 0.629},
                        figs=relwis.Figures(
        convention=relwis.PAIRWISE, values={"ensemble": 0.629},
        detail={"ensemble": {"n_cells": 4922, "rank": 6, "n_models": 48}},
        states=tuple(figs.states), n_field=47, source="/tmp/cells"))
    flat = _flat(pair)
    assert "0.629" in flat                          # the value is published
    for gone in ("ranked 6 of 48", "ranked ", "Field: 47",
                 "47 FluSight teams"):
        assert gone not in flat, gone
    # and the page says WHY, rather than leaving a silent gap
    assert "is not restated here" in flat

    # the rank is still computed: withdrawing the display must not have
    # quietly deleted the machinery that would restore it
    assert relwis.insert_model(_cells(), "FluBNF-PF",
                               [relwis.BASELINE, "TeamA"])["rank"] == 1


def test_the_methods_withdrawal_stays_true_and_names_the_convention():
    """The two claims Methods makes about relWIS, checked against it.

    First: placement is withdrawn and not restated, with a reason that
    survives the console now computing the pairwise VALUE. Second: the
    page names WHICH ratio its figures are, since both conventions are
    ratios scaled to put the baseline at 1.0 and "a ratio against the
    FluSight baseline" therefore labels neither.
    """
    html = _flat(srv.templates.env.get_template("methods.html").render(
        active="Methods", versions={}))
    assert "was withdrawn on 2026-08-24 and is not restated" in html
    assert "cannot be rerun from it" in html
    assert relwis.PUBLISHED_CONVENTION_NOTE in html
    # the sentence that looked like a label and was not
    assert "is a ratio against the FluSight baseline" not in html


def test_the_pairwise_view_withholds_the_ratio_only_panels():
    pair = _season_page(conv=relwis.PAIRWISE, curve=[],
                        figs=relwis.Figures(convention=relwis.PAIRWISE,
                                            values={"ensemble": 0.629},
                                            detail={"ensemble": {}},
                                            n_field=47))
    flat = _flat(pair)
    # the cumulative curve is a running ratio of sums by construction
    assert "Not available under this convention" in flat
    assert "<polyline" not in pair
    # the US national figure is a ratio of sums, so it is named as absent
    assert "The US national row is not shown under this convention" in flat
    # and the player's own running figures say which convention they are
    assert "beats the CDC FluSight baseline, ratio of sums" in flat
    assert "not comparable with the pairwise scores" in flat


def test_the_unavailable_page_states_the_reason_and_offers_no_numbers():
    figs = relwis.Figures(convention=relwis.PAIRWISE, values={}, detail={},
                          reason="no hub field data cached: the other "
                                 "teams' per-cell scores are not on this "
                                 "machine")
    html = _season_page(conv=relwis.PAIRWISE, heads={}, states=[], curve=[],
                        figs=figs, week="2098-11-07")
    flat = _flat(html)
    assert "No scores under this convention" in flat
    assert "no hub field data cached" in flat
    # the ratio-of-sums view is OFFERED, and named as a different quantity
    assert "conv=ratio_of_sums" in html
    assert "not a substitute for the figure missing here" in flat
    # and it keeps the reader's place: the same week the convention switch
    # itself carries, not a silent jump back to the last week
    assert "conv=ratio_of_sums&amp;week=2098-11-07" in html
    # nothing numeric slipped through under the pairwise heading
    assert 'class="big' not in html
    # THE panels that used to go on describing a table that is not there:
    # an empty per-state fold with its full caption, and a warning against
    # comparing the player with pairwise scores the page has just said it
    # does not have
    assert "Per-state scores" not in flat
    assert "0 states scored" not in flat
    assert "Each jurisdiction is its own tournament" not in flat
    assert "not comparable with the pairwise scores" not in flat


def test_the_unavailable_banner_does_not_send_a_reader_where_they_already_are():
    """The ratio of sums can come up empty too, on an unscored season.

    The banner then used to offer "the ratio of sums view, always
    available" to a reader standing on it. It names the state instead.
    """
    figs = relwis.Figures(convention=relwis.RATIO_OF_SUMS, values={},
                          detail={},
                          reason="no cells shared with the FluSight baseline")
    html = _season_page(conv=relwis.RATIO_OF_SUMS, heads={}, states=[],
                        curve=[], figs=figs)
    flat = _flat(html)
    assert "No scores under this convention" in flat
    assert "no cells shared with the FluSight baseline" in flat
    assert "This is the ratio of sums view" in flat
    # the banner's own offer of that view is gone; the switch above the
    # banner still carries its buttons, which is a different thing
    assert "ratio of sums view</a>" not in flat
    assert "always available" not in flat


def test_the_unavailability_message_says_what_would_populate_the_cache(
        tmp_path):
    """A reader on a normal machine gets more than "not here".

    The cache is built from a hub clone by a scorer that lives outside this
    repository, so the message has to name both the switch that points at
    it and where the app looks by default; otherwise a normal absence reads
    as the application being broken.
    """
    f = relwis.load_field_cells(tmp_path / "not-here")
    assert not f.available
    assert relwis.FIELD_CELLS_ENV in f.reason
    assert str(relwis.FIELD_CELLS_DEFAULT) in f.reason
    assert "score_hub" in f.reason


def test_the_field_cache_is_looked_for_in_two_places_and_no_home_directory(
        monkeypatch):
    """No fixed path under the running user's home directory.

    The loader used to fall back to the analysis archive the reference
    tournament happened to write into, which is not something a public
    runtime should probe. The environment variable says the same thing
    explicitly, and the unavailability message names it.
    """
    monkeypatch.delenv(relwis.FIELD_CELLS_ENV, raising=False)
    assert relwis.field_cells_dir() == relwis.FIELD_CELLS_DEFAULT
    src = Path(relwis.__file__).read_text()
    assert "FluBNF-local" not in src
    assert 'Path("~' not in src


def test_every_surface_that_prints_a_relwis_names_the_convention():
    """One wording, on every surface, from one string.

    The figures a reader is likeliest to hold up against the CDC dashboard
    were the ones with no label at all: the home page's Measured
    performance panel, the same panel on the published site, Methods, and
    the exported season report. Each of them now prints the shared
    sentence, and none of them types its own version of it.
    """
    ui = Path(srv.__file__).resolve().parent
    core = Path(relwis.__file__).resolve().parent
    assert (srv.templates.env.globals["relwis_convention_note"]
            == relwis.PUBLISHED_CONVENTION_NOTE)
    for t in ("home.html", "methods.html"):
        src = (ui / "templates" / t).read_text()
        assert "{{ relwis_convention_note }}" in src, t
    # the two builders that render outside the template environment reach
    # for the same constant rather than restating it
    for mod in ("site_page.py", "report_season.py"):
        assert "PUBLISHED_CONVENTION_NOTE" in (core / mod).read_text(), mod
    # and the short label rides beside the figures on the retro surfaces
    for t in ("retro.html", "retro_season.html"):
        assert "ratio of sums" in (ui / "templates" / t).read_text(), t


def test_the_index_labels_the_convention_beside_every_score():
    html = srv.templates.env.get_template("retro.html").render(
        active="Retrospective", state_names=["Ohio"], engine_ok=True,
        seasons=[{"name": "2098-99", "total": 30, "done": 30, "seal": False,
                  "running": False, "paused": False, "active": False,
                  "status": "done", "elapsed_s": None, "mean_s": None,
                  "weeks_measured": 0, "eta_s": None, "scored": True,
                  "rel": 0.877,
                  "archives": [{"id": "a", "when": "yesterday", "weeks": 3,
                                "elapsed_s": None, "rel": 0.9,
                                "size_h": "1 MB"}]}])
    assert 'relWIS <span class="ok">0.877</span>, ratio of sums' in html
    assert 'relWIS <span class="ok">0.900</span>, ratio of sums' in html
