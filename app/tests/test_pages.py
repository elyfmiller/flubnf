"""Page renders: home mechanism visual, model-tab diagrams and collapsible
intros, methods anchors and backlinks, ensemble member overlay wiring."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

from app.ui.server import app as srv                # noqa: E402

client = TestClient(srv)


def test_home_renders_mechanism_and_component_cards():
    r = client.get("/")
    assert r.status_code == 200
    assert "mechanistically" in r.text              # tagline restored
    assert "SIHRS compartment diagram" in r.text    # inline diagram present
    assert 'id="d1-beta1"' in r.text                # annotation slots
    assert "const DIAG" in r.text                   # interactive feed
    # component cards with home links and versions
    assert "github.com/lanl/PyBNF" in r.text
    assert "github.com/lanl/bngsim" in r.text
    assert "bionetgen.org" in r.text
    assert 'target="_blank"' in r.text
    assert "/methods#sihrs" in r.text               # anchor into methods


def test_model_pages_render_mechanism_and_collapsed_intro():
    markers = {
        "pf": "SIHRS compartment diagram",
        "pf2s": "Influenza A circuit",
        "analogue": "forecast date",                # analogue mechanism svg
        "ensemble": "quantile average",             # blend node
    }
    for name, marker in markers.items():
        r = client.get(f"/model/{name}")
        assert r.status_code == 200, name
        assert marker in r.text, name
        # intro collapsed by default: a details block without `open`
        assert '<details class="card intro">' in r.text, name
        assert 'href="/methods#' in r.text, name


def test_ensemble_page_carries_member_overlay():
    r = client.get("/model/ensemble")
    assert r.status_code == 200
    assert "const OVERLAY" in r.text
    assert "legendonly" in r.text


def test_forecast_page_renders_with_ensemble_overlay_js():
    r = client.get("/forecast")
    assert r.status_code == 200
    assert "legendonly" in r.text


def test_methods_anchors_and_backlinks():
    r = client.get("/methods")
    assert r.status_code == 200
    for anchor in ('id="sihrs"', 'id="fitting"', 'id="two-strain"',
                   'id="analogue"', 'id="ensemble"'):
        assert anchor in r.text, anchor
    for back in ('href="/model/pf"', 'href="/model/pf2s"',
                 'href="/model/analogue"', 'href="/model/ensemble"'):
        assert back in r.text, back
    # the respread diagram: no label sits on the return arc anymore
    assert "M762,182 C762,330 87,330 87,182" in r.text


def test_diagram_data_shapes():
    from app.ui.server import _diagram_data
    assert _diagram_data(None) == {"date": "", "has_pf2s": False,
                                   "locations": {}, "order": []}
    res = {"forecast_date": "2026-08-15",
           "params": {"pf": {"Ohio": {"Reff": 1.07, "phi1": 27.2}},
                      "pf2s": {"Ohio": {"ReffA": 1.0, "ReffB": 1.04}}},
           "observed": {"Ohio": [["2026-08-08", 12.0]],
                        "US": [["2026-08-08", 300.0]]},
           "models": {"ensemble": {"Ohio": {"1": {"0.5": 14.0}}}}}
    d = _diagram_data(res)
    assert d["has_pf2s"] is True
    assert d["order"][0] == "US"                    # national listed first
    assert d["locations"]["Ohio"]["pf"]["Reff"] == 1.07
    assert d["locations"]["Ohio"]["med1"] == 14.0
    assert d["locations"]["Ohio"]["obs"] == [["2026-08-08", 12.0]][-1]
    assert "pf" not in d["locations"]["US"]         # graceful omission
