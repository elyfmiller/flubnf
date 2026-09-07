"""The latest-run results table (lead, 2026-09-07): the run type, each
member's relWIS against the FluSight baseline with its cells, the fits,
the files, the report, in a table instead of one chip line; the quantile
members scored at run end with the sample scorer's own cell rule; the
mode recorded on the spec."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd                                      # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

import app.core.scoring as scoring                       # noqa: E402
from app.core.runs import RunSpec, results_html          # noqa: E402
from app.ui import server as srv                         # noqa: E402

client = TestClient(srv.app)


def _q(med):
    """A full 23-level quantile set around `med`, monotone, as the members
    store them (the WIS needs every hub level)."""
    from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
    return {str(h): {float(L): med * (0.5 + float(L)) for L in QL} for h in (1, 2, 3, 4)}


def test_score_quantiles_applies_the_sample_scorers_cell_rule(monkeypatch):
    T = pd.Timestamp("2098-01-03")
    truth = {("39", T + pd.Timedelta(days=7 * h)): 100.0 for h in (1, 2, 3, 4)}
    truth[("49", T + pd.Timedelta(days=7))] = 50.0          # Utah: one week only
    truth[("49", T + pd.Timedelta(days=14))] = 0.0          # zero truth: no cell
    n2f = {"Ohio": "39", "Utah": "49", "Nowhere": None}
    monkeypatch.setattr(scoring, "_baseline_cells",
                        lambda fd, fips, tr: {(f, fd, h): 10.0 for f in fips for h in range(4)})
    df = scoring.score_quantiles({"Ohio": _q(100.0), "Utah": _q(100.0), "Nowhere": _q(5.0),
                                  "Zero": {"1": {0.5: 0.0}}}, "2098-01-03", n2f, truth)
    assert sorted(df.location.unique()) == ["Ohio", "Utah"]
    assert len(df[df.location == "Ohio"]) == 4 and len(df[df.location == "Utah"]) == 1
    assert (df.base_wis == 10.0).all() and (df.rel == df.wis / 10.0).all()
    # the same forecast scores better where its median hits the truth
    # (Ohio, truth 100) than where it misses (Utah, truth 50)
    assert df[df.location == "Ohio"].wis.iloc[0] < df[df.location == "Utah"].wis.iloc[0]
    assert scoring.score_quantiles({}, "2098-01-03", n2f, truth).empty


def test_results_table_states_type_members_fits_files_and_report():
    outcome = {"pf_cells": 3, "pf_failures": {"Ohio_r1": "FAIL: x"},
               "pf_relwis": 1.774, "pf_relwis_cells": 4,
               "analogue_relwis": 0.913, "analogue_relwis_cells": 4,
               "ensemble_relwis": 0.842, "ensemble_relwis_cells": 4,
               "submissions": {"a": "x.csv", "b": "y.csv"}, "report": True}
    spec = RunSpec(engine="all", forecast_date="2098-01-03", locations=["Ohio"],
                   extra={"mode": "vintage"})
    html = results_html(outcome, spec)
    assert 'class="results"' in html
    assert "vintage run" in html and "real-time" not in html.split("vintage run")[0]
    assert '<span class="relwis bad">1.774</span>' in html
    assert '<span class="relwis ok">0.913</span>' in html
    assert '<span class="relwis ok">0.842</span>' in html and "(4 cells)" in html
    assert "3 fits" in html and '<span class="bad">1 failure</span>' in html
    assert "2 files" in html and "written" in html
    assert html.index("PF-SIHRS") < html.index("Calendar analogue") < html.index("FluBNF ensemble")
    # a JSON spec and outcome, as the ledger row carries them
    again = results_html(json.dumps(outcome), json.dumps({"extra": {"mode": "realtime"}}))
    assert "real-time run" in again
    # no members scored yet (truth not settled): the rows are simply absent
    early = results_html({"pf_cells": 2, "submissions": {"a": "x"}}, "{}")
    assert "relwis" not in early and "2 fits" in early and "none" in early
    assert results_html("", "") == "" and results_html("not json", None) == ""


def test_the_form_records_the_mode_and_reruns_carry_it():
    html = client.get("/forecast").text
    assert 'name="mode" id="mode-field" value="realtime"' in html
    assert "mf.value = mode" in html
    assert srv._run_extra(2, "vintage") == {"mode": "vintage"}
    assert srv._run_extra(3, "nonsense") == {"mode": "realtime", "members": 3}
    assert srv._spec_mode({"extra": {"mode": "vintage"}}) == "vintage"
    assert srv._spec_mode({}) == "realtime" and srv._spec_mode({"extra": "x"}) == "realtime"


def test_the_fan_card_keeps_the_location_across_model_buttons():
    src = (Path(srv.__file__).resolve().parent / "templates" / "forecast.html").read_text()
    assert "const cur=FLOCS[FIDX];" in src
    assert "FIDX=Math.max(0, nl.indexOf(cur));" in src
    assert "FIDX=0; drawFan();" not in src


def test_the_run_page_carries_the_results_table():
    html = srv.templates.env.get_template("run.html").render(
        active="Storage", run_id="r1", status="ok", error="", label="x",
        research=False, models={}, settings=[("engine", "pf")], versions=[],
        results=results_html({"pf_relwis": 0.7, "pf_cells": 1}, "{}"),
        pf_failures={}, step_errors={}, ensemble_analogue_only=[], ensemble_withheld="")
    assert "<h2>Results</h2>" in html and '<span class="relwis ok">0.700</span>' in html
