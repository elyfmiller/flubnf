"""What the Results table's Data issues row counts (app/core/runs.py
data_issues_row; review of #90, FC-26 and FC-27).

  * A state a model made no forecast for reads "no forecast", not "as
    reported": the Groundhog's own notes for a state chosen "No forecast"
    (its newest week reads 0) and for a "From ..." state it skips carry no
    data flag, so the row counts the notes. The states' notes come from
    the real Groundhog walk (app/core/engines/analogue.py) on a synthetic
    series; the Oracle SIHRS's are its engine's strings (pf.py).
  * Each count is of states: one state both models anchored earlier, or
    both skipped, reads 1.
  * "as reported" stays for a state whose data was kept and that no model
    left out; the donors' abstention keeps its own row.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import missing as MS                           # noqa: E402
from app.core import runs as runs_mod                        # noqa: E402
from app.core.engines import analogue as EA                  # noqa: E402
from app.core.runs import RunSpec                            # noqa: E402

NAMES = runs_mod.HUB_MEMBER_NAMES
#: six weeks, newest last; the as-of week T is the last
WEEKS = [str(d.date()) for d in pd.date_range("2098-10-25", periods=6, freq="7D")]
T = WEEKS[-1]
#: None: no row that week
SERIES = {"Utah": [1, 0, 4, 2, 0, 0],             # newest reads 0
          "Vermont": [3, 4, 5, 6, 7, 0],          # newest reads 0
          "Alaska": [5, 6, 7, None, None, None],  # 3 weeks old: skipped
          "Idaho": [5, 6, 7, 8, 0, None],         # last reported reads 0
          "Nevada": [5, 6, 7, 8, 9, None],        # 1 week old
          "Ohio": [70, 71, 72, 73, 74, 75]}
FIPS = {"Utah": "49", "Vermont": "50", "Alaska": "02", "Idaho": "16",
        "Nevada": "32", "Ohio": "39"}


def _fake_forecast(anchor, as_of, horizon, bank, levels, **kw):
    """A stand-in for flubnf.analogue.forecast: None for an anchor of 0,
    as the library does."""
    if anchor is None or anchor <= 0:
        return None
    return {float(L): float(anchor) * horizon for L in levels}


@pytest.fixture
def series(tmp_path, monkeypatch):
    rows = ["date,location,location_name,value"]
    for loc, vals in SERIES.items():
        rows += [f"{w},{FIPS[loc]},{loc},{v}"
                 for w, v in zip(WEEKS, vals) if v is not None]
    v = tmp_path / "v.csv"
    v.write_text("\n".join(rows) + "\n")
    locs = tmp_path / "locations.csv"
    locs.write_text("location,location_name,abbreviation\n"
                    + "".join(f"{f},{n},{n[:2].upper()}\n" for n, f in FIPS.items()))
    monkeypatch.setattr(EA, "vintage_path", lambda d: str(v))
    monkeypatch.setattr(EA, "LOCATIONS", str(locs))
    monkeypatch.setattr(EA.AN, "forecast", _fake_forecast)
    return v


def _extra(**choices):
    """A choices record as the Forecast tab writes it: {state: choice}."""
    states = {}
    for loc, choice in choices.items():
        zero = choice in MS.ZERO_CHOICES
        states[loc] = {"issue": "zero" if zero else "no row",
                       "what": "reads 0 after 4, 2" if zero else "no row",
                       "choice": choice, "followed": True}
    return {"data_choices": {"week": T, "states": states}}


def _outcome(extra, pf_notes=None):
    """A run record as the pipeline writes it: the Groundhog's real notes
    and flags for the chosen states and Ohio, the Oracle SIHRS's given."""
    spec = RunSpec(engine="retro", forecast_date=T,
                   locations=list(MS.choices_of(extra)) + ["Ohio"],
                   extra=extra)
    notes, flags = {}, []
    EA.run(spec, notes=notes, flags=flags)
    return {"analogue_anchor_notes": notes, "pf_anchor_notes": pf_notes or {},
            "data_flags": {"analogue": flags, "pf": []}}


def _cell(row) -> str:
    assert row[0] == "Data issues"
    return row[1].split("<", 1)[0]


def test_a_state_chosen_no_forecast_is_counted(series):
    extra = _extra(Utah="abstain", Vermont="level")
    o = _outcome(extra)
    # the engine names Utah's absence in a note and flags only Vermont
    assert o["analogue_anchor_notes"]["Utah"] == "no forecast: newest week reads 0"
    assert [r["location"] for r in o["data_flags"]["analogue"]] == ["Vermont"]
    assert _cell(runs_mod.data_issues_row(o, extra, NAMES)) == \
        "1 no forecast, 1 level"
    only = _extra(Utah="abstain")
    assert _cell(runs_mod.data_issues_row(_outcome(only), only, NAMES)) == \
        "1 no forecast"
    # on the page: the Data issues row says it, the zero row leaves Utah to it
    html = runs_mod.results_html(o, RunSpec(engine="retro", forecast_date=T,
                                            locations=["Utah"], extra=extra))
    assert "<th scope=\"row\">Data issues</th><td>1 no forecast, 1 level<" in html
    assert "as reported" not in html and "Newest week reading 0" not in html


def test_a_from_state_both_models_skip_is_one_no_forecast(series):
    extra = _extra(Alaska="carry")
    pf = {"Alaska": f"abstained: newest reported week {WEEKS[2]} is 3 weeks "
                    "before the as-of"}
    o = _outcome(extra, pf)
    assert o["analogue_anchor_notes"]["Alaska"] == (
        f"abstained: newest reported week {WEEKS[2]} is 3 weeks before the as-of")
    row = runs_mod.data_issues_row(o, extra, NAMES)
    assert _cell(row) == "1 no forecast"
    assert ("Oracle SIHRS, Alaska: abstained: newest reported week "
            f"{WEEKS[2]} is 3 weeks before the as-of.") in row[1]


def test_a_from_state_whose_last_week_reads_0_says_both(series):
    extra = _extra(Idaho="carry")
    pf = {"Idaho": f"anchored on {WEEKS[4]}: 1 newer week(s) unreported"}
    o = _outcome(extra, pf)
    assert o["analogue_anchor_notes"]["Idaho"] == (
        f"abstained: newest reported week {WEEKS[4]} reads 0 "
        "(1 newer week(s) unreported)")
    assert _cell(runs_mod.data_issues_row(o, extra, NAMES)) == \
        "1 no forecast, 1 anchored earlier"


def test_counts_are_of_states_not_of_models(series):
    extra = _extra(Nevada="carry")
    pf = {"Nevada": f"anchored on {WEEKS[4]}: 1 newer week(s) unreported"}
    o = _outcome(extra, pf)
    assert o["analogue_anchor_notes"]["Nevada"] == pf["Nevada"]
    assert _cell(runs_mod.data_issues_row(o, extra, NAMES)) == "1 anchored earlier"
    # the same for a set-aside the data no longer matched, in both models
    na = f"{MS.NOT_APPLIED_NOTE}: {T} now reads 0"
    o = {"pf_anchor_notes": {"Utah": na}, "analogue_anchor_notes": {"Utah": na}}
    assert _cell(runs_mod.data_issues_row(o, _extra(Utah="set_aside"), NAMES)) \
        == "1 not applied (the data changed)"


def test_as_reported_only_when_no_chosen_state_has_a_note():
    kept = {"data_choices": {"states": {"Ohio": {
        "issue": "collapsed", "what": "reads 5 after 40", "choice": "keep"}}}}
    # Utah has a note but no choice: its own rows say it
    o = {"analogue_anchor_notes": {"Utah": "no forecast: newest week reads 0"}}
    assert _cell(runs_mod.data_issues_row(o, kept, NAMES)) == "as reported"
    # the donors' abstention is the Too few donors row's
    o = {"analogue_anchor_notes": {"Ohio": runs_mod.NO_DONORS}}
    assert _cell(runs_mod.data_issues_row(o, kept, NAMES)) == "as reported"
    assert runs_mod.no_donors_row(o, NAMES)[1].startswith("Groundhog: 1 abstain")
