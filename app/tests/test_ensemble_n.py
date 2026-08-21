"""N-member vincentization and the two-strain member's app surfaces."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _levels():
    from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
    return [float(q) for q in QL]


def _flat(v, hs=("1", "2", "3", "4")):
    return {h: {L: v for L in _levels()} for h in hs}


def test_equal_weights_helper():
    from app.core.ensemble import equal_weights
    w = equal_weights({"pf": {}, "analogue": {}, "pf2s": {}})
    assert set(w) == {"pf", "analogue", "pf2s"}
    assert abs(sum(w.values()) - 1.0) < 1e-12
    assert all(abs(x - 1 / 3) < 1e-12 for x in w.values())


def test_vincentize_equal_thirds():
    from app.core.ensemble import equal_weights, vincentize
    members = {"pf": _flat(100.0), "analogue": _flat(200.0),
               "pf2s": _flat(600.0)}
    out = vincentize(members, weights=equal_weights(members))
    for h in ("1", "2", "3", "4"):
        assert abs(out[h][0.5] - 300.0) < 1e-9
        assert len(out[h]) == len(_levels())


def test_vincentize_missing_member_renormalizes():
    from app.core.ensemble import equal_weights, vincentize
    members = {"pf": _flat(100.0), "analogue": _flat(200.0),
               "pf2s": _flat(600.0, hs=("1",))}      # pf2s absent at h 2-4
    out = vincentize(members, weights=equal_weights(members))
    assert abs(out["1"][0.5] - 300.0) < 1e-9         # thirds where all present
    assert abs(out["2"][0.5] - 150.0) < 1e-9         # halves after renormalizing
    assert abs(out["4"][0.5] - 150.0) < 1e-9


def test_vincentize_unequal_member_weights():
    from app.core.ensemble import vincentize
    members = {"pf": _flat(100.0), "analogue": _flat(200.0)}
    out = vincentize(members, weights={"pf": 3.0, "analogue": 1.0})
    assert abs(out["1"][0.5] - 125.0) < 1e-9         # normalized 0.75/0.25


def test_vincentize_two_member_regression():
    """weights=None with {pf, analogue} must reproduce the frozen pf_share
    path exactly, per-horizon and with the per-state override."""
    from app.core.ensemble import frozen_weights, pf_share, vincentize
    qa, qb = _flat(100.0), _flat(200.0)
    w = frozen_weights()
    out = vincentize({"pf": qa, "analogue": qb})
    for h in ("1", "2", "3", "4"):
        s = pf_share(w, int(h) - 1)
        assert abs(out[h][0.5] - (s * 100 + (1 - s) * 200)) < 1e-9
    vt = vincentize({"pf": qa, "analogue": qb}, location_fips="50")
    s_vt = pf_share(w, 0, "50")
    assert abs(vt["1"][0.5] - (s_vt * 100 + (1 - s_vt) * 200)) < 1e-9
    # lone member keeps weight 1
    lone = vincentize({"pf": _flat(100.0, hs=("1",))})
    assert abs(lone["1"][0.5] - 100.0) < 1e-9


def test_pf2s_model_page_renders():
    from fastapi.testclient import TestClient
    from app.ui.server import app as srv
    r = TestClient(srv).get("/model/pf2s")
    assert r.status_code == 200
    assert "Two-strain SIHRS" in r.text and "NREVSS" in r.text


def test_forecast_form_offers_member_select():
    from fastapi.testclient import TestClient
    from app.ui.server import app as srv
    r = TestClient(srv).get("/forecast")
    assert r.status_code == 200
    assert "Ensemble members" in r.text
    assert "PF + analogue + two-strain (research: turn-validated, not ensemble-validated)" in r.text


def test_methods_page_covers_two_strain():
    from fastapi.testclient import TestClient
    from app.ui.server import app as srv
    r = TestClient(srv).get("/methods")
    assert r.status_code == 200
    assert "The two-strain variant" in r.text and "NREVSS" in r.text
