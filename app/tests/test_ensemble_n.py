"""The two-strain research member's app surfaces (app.core.ensemble keeps
only the member-quantile formula; the N-member blend is gone)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_pf2s_model_page_renders():
    from fastapi.testclient import TestClient
    from app.ui.server import app as srv
    r = TestClient(srv).get("/model/pf2s")
    assert r.status_code == 200
    assert "Two-strain SIHRS" in r.text and "NREVSS" in r.text


def test_forecast_form_drops_member_select_but_server_accepts_three():
    """The two-strain member failed its full-grid ensemble gate, so the UI
    affordance is gone; members=3 stays a valid request for research use."""
    import inspect

    from fastapi.testclient import TestClient
    from app.ui.routes import forecast as ui_forecast
    from app.ui.server import app as srv
    r = TestClient(srv).get("/forecast")
    assert r.status_code == 200
    assert "Ensemble members" not in r.text
    assert "two-strain" not in r.text
    assert 'name="members"' not in r.text
    # the endpoint still takes a members parameter, defaulting to the two
    # shipped members
    sig = inspect.signature(ui_forecast.run_models)
    assert "members" in sig.parameters
    assert sig.parameters["members"].default.default == 2


def test_methods_page_carries_two_strain_research_section():
    from fastapi.testclient import TestClient
    from app.ui.server import app as srv
    r = TestClient(srv).get("/methods")
    assert r.status_code == 200
    assert "the two-strain variant" in r.text and "NREVSS" in r.text
    # the A/B parallel-circuit diagram moved here with the section
    assert "Two-strain SIHRS compartment diagram" in r.text
    # the verdict survives the condensed copy without the retired blend's
    # figures, which described a comparison that no longer exists
    assert "Why it does not ship" in r.text
    assert "remains a research run" in r.text
    # that it does not ship is said by the card's own title ("Research:")
    # and by its fold "Why it does not ship", so no mark beside the title
    # repeats it on the console; the public site, whose page has no marks,
    # keeps the words after its title
    card = r.text.split('id="two-strain"', 1)[1].split('id="analogue"', 1)[0]
    head = card.split("</h2>", 1)
    assert head[0].endswith("<h2>Research: the two-strain variant")
    assert "Why it does not ship</span>" in card
    assert "not a shipped model" not in r.text
    assert "uk-badge" not in head[1].split("uk-heading-aside", 1)[0]
    from app.core import site_build
    site = site_build.harvest_methods(
        {k: "x" for k in ("pybnf", "bngsim", "bionetgen", "fastapi",
                          "plotly")})
    assert ("<h2>Research: the two-strain variant</h2>"
            "<em>(not a shipped model)</em>") in site
    assert "validation is in progress" not in r.text
    assert "validation now in progress" not in r.text
