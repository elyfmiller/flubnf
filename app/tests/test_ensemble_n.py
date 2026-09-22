"""The two-strain research member's app surfaces. The N-member blend tests
that opened this file went with the blend (2026-09-22); nothing computes
one, and app.core.ensemble keeps only the member-quantile formula."""
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
    from app.ui import server as srv_mod
    from app.ui.server import app as srv
    r = TestClient(srv).get("/forecast")
    assert r.status_code == 200
    assert "Ensemble members" not in r.text
    assert "two-strain" not in r.text
    assert 'name="members"' not in r.text
    # the endpoint still takes a members parameter, defaulting to the two
    # shipped members
    sig = inspect.signature(srv_mod.run_models)
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
    # the decisive full-grid comparison survives the condensed copy
    for n in ("0.719", "0.704"):
        assert n in r.text, n
    # and the note that both sides of that comparison predate the donor
    # exclusion, so a reader does not weigh 0.719 against today's 0.678
    assert "0.678" in r.text
    assert "not a shipped model" in r.text
    assert "validation is in progress" not in r.text
    assert "validation now in progress" not in r.text
