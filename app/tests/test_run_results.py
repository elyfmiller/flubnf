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
from app.core import horizons as hz                      # noqa: E402
from app.core.runs import RunSpec, results_html          # noqa: E402
from app.ui import server as srv                         # noqa: E402

client = TestClient(srv.app)


def _q(med):
    """A full 23-level quantile set around `med`, monotone, in the canonical
    horizons the members carry in memory (the WIS needs every hub level).
    No anchor key: hz.ORIGIN is not a forecast and score_quantiles must
    never find one to score."""
    from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
    return {h: {float(L): med * (0.5 + float(L)) for L in QL}
            for h in hz.HORIZONS}


def test_score_quantiles_applies_the_sample_scorers_cell_rule(monkeypatch):
    T = pd.Timestamp("2098-01-03")
    # truth is keyed by week-ending date, which is PHYSICAL weeks past the
    # as-of and knows nothing of horizon labels: canonical horizon h lands
    # on T + 7*(h+1), so these four weeks cover horizons "0".."3"
    truth = {("39", T + pd.Timedelta(days=7 * h)): 100.0 for h in (1, 2, 3, 4)}
    truth[("49", T + pd.Timedelta(days=7))] = 50.0          # Utah: one week only
    truth[("49", T + pd.Timedelta(days=14))] = 0.0          # zero truth: no cell
    n2f = {"Ohio": "39", "Utah": "49", "Nowhere": None}
    # the baseline is keyed on the hub's horizons, the same labels the rows
    # now carry, so the join is straight through
    monkeypatch.setattr(scoring, "_baseline_cells",
                        lambda fd, fips, tr: {(f, fd, int(h)): 10.0
                                              for f in fips
                                              for h in hz.HORIZONS})
    df = scoring.score_quantiles({"Ohio": _q(100.0), "Utah": _q(100.0), "Nowhere": _q(5.0),
                                  "Zero": {"0": {0.5: 0.0}}}, "2098-01-03", n2f, truth)
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
    # the blend's row still renders for a ledger row that carries its
    # score (a run from before 2026-09-22), after the two models that ship
    assert html.index("Oracle SIHRS") < html.index("Groundhog") < html.index("FluBNF ensemble (retired)")
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
    # the shipped donors ride on every console spec; "" asks for the bare
    # analogue (a research configuration, no Groundhog file), and a named
    # preset resolves like the shipped one
    x = srv._run_extra(2, "vintage")
    assert x["mode"] == "vintage" and "members" not in x
    assert x["aux_pools"] == [{"stream": "flusurv", "weight": 0.5,
                               "committed": True}]
    assert x["analogue_aux"].startswith("flusurv+flusurv@")
    assert srv._run_extra(2, "vintage", "") == {"mode": "vintage"}
    y = srv._run_extra(3, "nonsense")
    assert y["mode"] == "realtime" and y["members"] == 3
    assert srv._run_extra(2, "realtime", "iliplus")["aux_pools"] == [
        {"stream": "iliplus", "weight": 0.5, "committed": True}]
    import pytest
    with pytest.raises(ValueError, match="unknown auxiliary preset"):
        srv._run_extra(2, "realtime", "nope")
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
