"""The partial-week rule (data.partial_week, app/core/missing.py) is a hub
rule: its floor (a prior week of 20 or more) assumes hospital admission
counts. A custom dataset's Model settings panels never show it, and a
dataset run or replay refuses it, the way the optional hub-output knobs
are kept off those panels (datasets_ui.dataset_panel). The trailing-zero
rule stays available everywhere; the FluSight panels keep both.
"""
from __future__ import annotations

import pytest

from app.core import custom_retro as CX
from app.core import datasets as D
from app.core import knobs as K
from app.core import missing as MS
from app.core.engines import analogue as EA
from app.core.engines import pf as PF
from app.core.runs import RunSpec
from app.ui import datasets_ui as DU
from app.ui import forms
from app.ui import state as ui_state

from test_datasets_ui import _capture, client, isolated, stored  # noqa: F401

PARTIAL = "data.partial_week"
ZERO = "data.trailing_zero"


def _keys(panel):
    return {r["key"] for g in panel["groups"] for r in g["rows"]}


def test_the_rule_is_named_hub_only():
    assert MS.HUB_ONLY_KEYS == (PARTIAL,)
    assert ZERO not in MS.HUB_ONLY_KEYS


@pytest.mark.parametrize("where", ["forecast", "replay"])
def test_own_data_panels_hide_it_and_keep_trailing_zero(where):
    hub = forms._knob_panel("forecast", {}, names=DU.PANEL_MEMBERS)
    assert {PARTIAL, ZERO} <= _keys(hub)
    own = DU.dataset_panel(forms._knob_panel("forecast", {},
                                             names=DU.PANEL_MEMBERS),
                           kind="count", where=where)
    assert PARTIAL not in _keys(own) and ZERO in _keys(own)


def test_the_pages_render_it_only_for_the_hub():
    ds = stored()
    own = client.get(f"/forecast?source={ds.id}").text
    assert f'name="knob.{ZERO}"' in own and f'name="knob.{PARTIAL}"' not in own
    card = client.get("/retro?tab=own").text
    assert f'name="knob.{ZERO}"' in card
    assert f'data-knob="{PARTIAL}"' not in card.split('id="dsr-model-settings"')[1]
    hub = client.get("/forecast").text
    assert f'name="knob.{PARTIAL}"' in hub and f'name="knob.{ZERO}"' in hub


def test_a_dataset_run_refuses_it(monkeypatch):
    ds = stored()
    got = _capture(monkeypatch)
    client.post("/run/dataset", data={
        "dataset": ds.id, "forecast_date": "2023-12-02", "locations": "all",
        "engine": "analogue", f"knob.{PARTIAL}": "missing"},
        follow_redirects=False)
    assert got == []
    flash = ui_state._status.get("flash", "")
    assert (f"Model settings: {PARTIAL}: this rule's floor (a prior week of "
            "20 or more) assumes hospital admission counts and cannot run on "
            "the custom dataset 'Kids'. Nothing was run.") in flash
    # the trailing-zero rule runs
    client.post("/run/dataset", data={
        "dataset": ds.id, "forecast_date": "2023-12-02", "locations": "all",
        "engine": "analogue", f"knob.{ZERO}": "missing"},
        follow_redirects=False)
    (spec,) = got
    assert spec.extra["knobs"] == {ZERO: "missing"}


def test_a_dataset_replay_refuses_it():
    ds = stored()
    r = client.post("/retro/dataset/run", data={
        "dataset": ds.id, "first": "2023-11-04", "last": "2023-12-02",
        "engine": "analogue", f"knob.{PARTIAL}": "missing"},
        follow_redirects=False)
    assert r.status_code == 303
    assert CX.list_replays(D.get(ds.id)) == []
    assert "assumes hospital admission counts" in ui_state._status.get(
        "flash", "")
    assert "Nothing was started." in ui_state._status["flash"]
    assert not DU._REPLAY


def test_the_engines_refuse_it_on_a_dataset(tmp_path, monkeypatch):
    ds = stored()
    on = K.write_extra({PARTIAL: "missing"}, {"dataset": ds.ref()})
    s = RunSpec(engine="analogue", forecast_date="2023-12-02",
                locations=list(ds.groups), extra=on)
    with pytest.raises(ValueError, match="assumes hospital admission counts"):
        EA.run(s)
    monkeypatch.setattr(PF, "perl_available", lambda: True)
    with pytest.raises(ValueError, match="assumes hospital admission counts"):
        PF.prepare(s, tmp_path / "w")
    # trailing zero is not refused
    s0 = RunSpec(engine="analogue", forecast_date="2023-12-02",
                 locations=list(ds.groups),
                 extra=K.write_extra({ZERO: "missing"}, {"dataset": ds.ref()}))
    assert set(EA.run(s0)) == set(ds.groups)
