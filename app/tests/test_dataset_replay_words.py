"""A dataset replay refused over its model settings (the Retrospective
tab's "Replay your own data" card) says the setting by the panel's label
and the value in plain words, as the dataset's Forecast form does
(forms._refusal_words), never the knob's key or the type's own words.

Review of #85 (S3, the "same kind" note): a replicates value of 3.5 read
"Not started: model settings: pf.replicates: '3.5' is not a valid int."
"""
from __future__ import annotations

from app.ui import datasets_ui as DU
from app.ui import pipeline as ui_pipeline
from app.ui import state as ui_state

from test_dataset_replay_knobs import _replay                 # noqa: E402
from test_datasets_ui import TEMPLATE, isolated, stored       # noqa: F401


def _refused(ds, **data) -> str:
    """Post the card's form; the one notice it leaves (nothing started)."""
    ui_state._status.pop("flash", None)
    r, meta = _replay(ds, **data)
    assert meta is None and r.status_code == 303
    assert r.headers["location"] == f"/retro?dataset={ds.id}"
    assert ui_state._status.get("flash_kind") == "warn"
    assert not DU._REPLAY and not ui_state._status.get("running")
    return ui_state._status.get("flash", "")


def test_a_refused_replicates_value_is_said_in_plain_words(monkeypatch):
    # the particle filter's replicates: a replay with the filter (a ready
    # engine, an eligible dataset); the worker is never reached
    ds = stored(TEMPLATE.read_bytes(), "Template")
    assert ds.pf_eligible
    monkeypatch.setattr(ui_pipeline, "_pf_engine_state", lambda: "ready")
    calls = []
    monkeypatch.setattr(DU, "replay_worker",
                        lambda *a, **k: calls.append((a, k)))
    flash = _refused(ds, engine="all", replicates="3.5")
    assert flash == "Not started: Replicates: '3.5' is not a whole number."
    assert "pf.replicates" not in flash and "valid int" not in flash
    assert calls == []


def test_a_value_out_of_range_names_the_setting_by_its_label():
    ds = stored(TEMPLATE.read_bytes(), "Template")
    assert _refused(ds, weeks_to_drop="9") == (
        "Not started: Weeks to drop: 9 is outside 0 to 4.")
