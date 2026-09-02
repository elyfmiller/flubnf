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


def test_vincentize_default_is_the_unfitted_blend():
    """weights=None with {pf, analogue} is the shipped 50/50, identical at
    every horizon and unmoved by a per-state override -- the contract every
    production call site relies on."""
    from app.core.ensemble import vincentize
    qa, qb = _flat(100.0), _flat(200.0)
    out = vincentize({"pf": qa, "analogue": qb})
    for h in ("1", "2", "3", "4"):
        assert abs(out[h][0.5] - 150.0) < 1e-9
    assert vincentize({"pf": qa, "analogue": qb}, location_fips="50") == out
    # the default is exactly what an explicit 50/50 request produces, which
    # is what every production call site passes today
    assert vincentize({"pf": qa, "analogue": qb},
                      weights={"pf": 0.5, "analogue": 0.5}) == out
    # lone member keeps weight 1
    lone = vincentize({"pf": _flat(100.0, hs=("1",))})
    assert abs(lone["1"][0.5] - 100.0) < 1e-9


def test_vincentize_frozen_path_requires_being_named():
    """The fitted table is still reachable, but only by name, and an
    unrecognized name is an error rather than a silent fallback."""
    import pytest

    from app.core.ensemble import FROZEN, frozen_weights, pf_share, vincentize
    qa, qb = _flat(100.0), _flat(200.0)
    w = frozen_weights()
    out = vincentize({"pf": qa, "analogue": qb}, weights=FROZEN)
    for h in ("1", "2", "3", "4"):
        s = pf_share(w, int(h) - 1)
        assert abs(out[h][0.5] - (s * 100 + (1 - s) * 200)) < 1e-9
    vt = vincentize({"pf": qa, "analogue": qb}, weights=FROZEN,
                    location_fips="50")
    s_vt = pf_share(w, 0, "50")
    assert abs(vt["1"][0.5] - (s_vt * 100 + (1 - s_vt) * 200)) < 1e-9
    # a member set the frozen table knows nothing about falls back to equal
    # weights rather than to an arbitrary member
    three = vincentize({"pf": _flat(100.0), "analogue": _flat(200.0),
                        "pf2s": _flat(600.0)}, weights=FROZEN)
    assert abs(three["1"][0.5] - 300.0) < 1e-9
    # lone member keeps weight 1 on the frozen path too
    assert abs(vincentize({"pf": _flat(100.0, hs=("1",))},
                          weights=FROZEN)["1"][0.5] - 100.0) < 1e-9
    with pytest.raises(ValueError):
        vincentize({"pf": qa, "analogue": qb}, weights="loso")


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
    # (1.023 stays as the PF-SIHRS 2023-24 cell of the performance table)
    for n in ("1.023", "0.719", "0.704"):
        assert n in r.text, n
    # and the note that both sides of that comparison predate the donor
    # exclusion, so a reader does not weigh 0.719 against today's 0.678
    assert "0.678" in r.text
    assert "not in the shipped ensemble" in r.text
    assert "validation is in progress" not in r.text
    assert "validation now in progress" not in r.text
