"""The Model settings knobs on a dataset replay (the Retrospective tab's
"Replay your own data" card).

The card carries the same panel partial as the FluSight replay form on
the hub tab (templates/_model_settings.html, ids prefixed dsr-), built
by datasets_ui.dataset_panel: no Oracle step, no auxiliary-bank rows, no
hub-name override; weeks to drop and the output floor are in it (a
dataset replay drops weeks and floors counts), the floor for counts only.
A knob that does not apply is never recorded; a replay off the shipped
values records them (run_meta.json "knobs" and its digest) and wears a
"modified settings" label, as a hub replay does. The FluSight panel is
untouched by the second one.
"""
from __future__ import annotations

import json
import re
from collections import Counter

import pytest

from app.core import custom_retro as CX
from app.core import datasets as D
from app.core import knobs as K
from app.core.runs import RunSpec, default_season_start
from app.ui import datasets_ui as DU
from app.ui import pipeline as ui_pipeline
from app.ui import state as ui_state

from test_dataset_engines import grouped_bytes              # noqa: E402
from test_datasets_ui import TEMPLATE, client, isolated, stored  # noqa: F401
from test_knobs_panel import _Form, _panel_form              # noqa: E402

FIRST, LAST = "2024-01-06", "2024-02-24"


def _replay(ds, **data):
    """Post the card's form; (response, the stored replay's meta)."""
    body = {"dataset": ds.id, "first": FIRST, "last": LAST,
            "engine": "analogue", **data}
    r = client.post("/retro/dataset/run", data=body, follow_redirects=False)
    reps = CX.list_replays(D.get(ds.id))
    return r, (reps[0][1] if reps else None)


class _CardForm(_Form):
    """The card's form as a browser posts it; its week and group selects
    are rendered by the server; an empty one would post nothing."""

    def handle_endtag(self, tag):
        if tag == "select" and self._select is not None and not self._opts:
            self._select = None
            return
        super().handle_endtag(tag)


def _card_form(html):
    f = _CardForm("dsr-form")
    f.feed(html)
    return f


def test_the_card_carries_the_shared_panel_with_what_applies():
    stored()
    html = client.get("/retro?tab=own").text
    # the Your data tab's panel alone, no id twice
    ids = Counter(re.findall(r'\bid="([^"]+)"', html))
    assert [i for i, n in ids.items() if n > 1] == []
    assert 'id="model-settings"' not in html
    assert 'id="dsr-model-settings"' in html
    f = _panel_form(html, root="dsr-model-settings")
    names = {n for n, _ in f.fields} | f.disabled
    # a dataset replay drops weeks and floors counts: both are in it
    assert {"weeks_to_drop", "drop_same_day", "particles", "replicates",
            "knob.groundhog.bandwidth", "knob.output.floor_lam"} <= names
    # never the Oracle step, the auxiliary bank or the hub-name override
    assert not {n for n in names if n.startswith("knob.oracle.")}
    assert not names & {"knob.groundhog.aux", "knob.groundhog.aux_weight",
                        "submit_modified", "modified_reason"}
    panel = html.split('id="dsr-model-settings"')[1].split("</details>\n<")[0]
    assert 'data-engine="dsr-engine"' in html
    assert 'data-only="count"' in panel
    assert "Groundhog (own data)" in panel
    assert "Oracle SIHRS" not in panel.split("Fixed by the model")[0]
    # every input labelled, and the card has one weeks_to_drop field
    ids = [i for i in f.ids if i]
    assert ids and all(i.startswith("dsr-") for i in ids)
    assert [i for i in ids if i not in f.label_for] == []
    card = _card_form(html)
    assert [n for n, _ in card.fields].count("weeks_to_drop") == 1


def test_the_flusight_panel_is_untouched_by_the_second_one():
    before = client.get("/retro").text
    stored()
    after = client.get("/retro").text

    def hub_panel(html):
        return html.split('id="model-settings"')[1].split(
            '<input type="hidden" name="mode"')[0]
    assert hub_panel(before) == hub_panel(after)


def test_posting_the_rendered_card_untouched_replays_shipped(monkeypatch):
    stored(TEMPLATE.read_bytes(), "Template")
    calls = []
    monkeypatch.setattr(DU, "replay_worker",
                        lambda *a, **k: calls.append((a, k)))
    card = _card_form(client.get("/retro?tab=own").text)
    body = {}
    for n, v in card.fields:
        body.setdefault(n, v)
    body.update({"first": FIRST, "last": LAST})
    client.post("/retro/dataset/run", data=body, follow_redirects=False)
    ((args, kw),) = calls
    assert kw == {}                        # no knob keyword: the shipped call
    ds_id, stamp, weeks, groups, engine, k, extra = args
    assert (engine, k, extra) == ("analogue", 0, {})
    DU._REPLAY.clear()
    ui_state._status["running"] = None


def test_a_modified_replay_records_its_knobs_and_says_so():
    ds = stored(TEMPLATE.read_bytes(), "Template")
    r, meta = _replay(ds, **{"knob.groundhog.bandwidth": "3",
                             "weeks_to_drop": "1",
                             "knob.output.floor_lam": "0.5"})
    assert meta["status"] == "done", meta.get("error")
    want = {"groundhog.bandwidth": 3, "output.floor_lam": 0.5,
            "run.weeks_to_drop": 1}
    assert meta["knobs"] == want
    assert meta["knobs_digest"] == K.digest(want)
    assert meta["weeks_to_drop"] == 1
    page = " ".join(client.get(r.headers["location"]).text.split())
    assert "<dt>model settings</dt><dd>modified: groundhog.bandwidth=3" in page
    assert '<span class="pill warn">modified settings</span>' in page
    card = client.get(f"/retro?dataset={ds.id}").text.split('id="dataset-replay"')[1]
    assert "modified settings" in card


def test_a_shipped_replay_records_no_knobs():
    ds = stored(TEMPLATE.read_bytes(), "Template")
    r, meta = _replay(ds, weeks_to_drop="0", particles="10000")
    assert meta["status"] == "done" and "knobs" not in meta
    assert "modified settings" not in client.get(r.headers["location"]).text


def test_knobs_that_do_not_apply_are_never_recorded():
    ds = stored(TEMPLATE.read_bytes(), "Template")
    # the particle filter does not run (Groundhog only), the Oracle step
    # never runs on a dataset, and the auxiliary bank is the box's
    _, meta = _replay(ds, particles="2000", **{"knob.oracle.w": "0.25",
                                               "knob.groundhog.aux": "none"})
    assert meta["status"] == "done" and "knobs" not in meta
    # a rate dataset is never floored, so its floor is never recorded
    rate = stored(grouped_bytes(rate=True), "Rates", kind="rate")
    DU._REPLAY.clear()
    ui_state._status["running"] = None
    _, meta = _replay(rate, **{"knob.output.floor_lam": "0.5"})
    assert meta["status"] == "done" and "knobs" not in meta


def test_a_refused_value_starts_nothing():
    ds = stored(TEMPLATE.read_bytes(), "Template")
    r, meta = _replay(ds, weeks_to_drop="9")
    assert meta is None and r.headers["location"] == f"/retro?dataset={ds.id}"
    assert ("Model settings: run.weeks_to_drop: 9 is outside 0 to 4. "
            "Nothing was started.") in ui_state._status.get("flash", "")
    assert not DU._REPLAY and not ui_state._status.get("running")


def test_the_filter_knobs_ride_to_the_worker_when_it_runs(monkeypatch):
    """With the particle filter (a ready engine, an eligible dataset): its
    knobs reach custom_retro.run as RunSpec fields and the record, and a
    fixed season start must precede every replayed week."""
    ds = stored(TEMPLATE.read_bytes(), "Template")
    assert ds.pf_eligible
    monkeypatch.setattr(ui_pipeline, "_pf_engine_state", lambda: "ready")
    calls = []
    monkeypatch.setattr(DU, "replay_worker",
                        lambda *a, **k: calls.append((a, k)))
    r, _ = _replay(ds, engine="all", season_start=LAST)
    assert calls == [] and "run.season_start" in ui_state._status["flash"]
    _replay(ds, engine="all", particles="2000", season_start="2023-09-02",
            **{"knob.pf.jitter": "0.3", "knob.pf.initialization": "lh"})
    ((args, kw),) = calls
    assert kw == {"particles": 2000, "jitter": 0.3,
                  "season_start": "2023-09-02"}
    extra = args[-1]
    assert extra["initialization"] == "lh"
    assert extra["knobs"] == {"pf.initialization": "lh", "pf.jitter": 0.3,
                              "pf.particles": 2000,
                              "run.season_start": "2023-09-02"}
    DU._REPLAY.clear()
    ui_state._status["running"] = None


def test_week_spec_is_the_shipped_one_without_knobs():
    ds = D.ingest(grouped_bytes(), "wave", kind="count")
    got = CX.week_spec(ds, "2023-12-02", ["Adult"], "all")
    x = {"dataset": ds.ref(), "oracle": "none", "dataset_final": True}
    assert got.to_json() == RunSpec(
        engine="all", forecast_date="2023-12-02", locations=["Adult"],
        season_start=default_season_start("2023-12-02"), weeks_to_drop=0,
        replicates=3, particles=10_000, drop_same_day=False,
        extra=x).to_json()
    mod = CX.week_spec(ds, "2023-12-02", ["Adult"], "all", jitter=0.3,
                       season_start="2023-09-02", drop_same_day=True)
    assert (mod.jitter, mod.season_start, mod.drop_same_day) == \
        (0.3, "2023-09-02", True)


def test_the_floor_knob_reaches_a_count_replay(monkeypatch):
    ds = D.ingest(grouped_bytes(), "wave", kind="count")
    seen = []
    import app.core.floor as FL
    real = FL.floor_quantiles

    def spy(q, lam=FL.LAM):
        seen.append(lam)
        return real(q, lam=lam)
    monkeypatch.setattr(FL, "floor_quantiles", spy)
    extra = K.write_extra({"output.floor_lam": 0.5}, {})
    out = CX.replay_dir(ds, CX.new_stamp(ds))
    meta = CX.run(ds, ["2023-12-02"], ds.groups, out_dir=out, extra=extra)
    assert set(seen) == {0.5}
    assert meta["knobs"] == {"output.floor_lam": 0.5}
    assert json.loads((out / CX.META).read_text())["knobs_digest"] == \
        K.digest({"output.floor_lam": 0.5})


@pytest.mark.parametrize("path", ["app/ui/static/model_settings.js"])
def test_the_panel_script_sets_each_panel_up_once(path):
    from pathlib import Path
    js = (Path(__file__).resolve().parents[2] / path).read_text()
    # every panel on the page, found by its data-scope, set up once
    assert "querySelectorAll('details[data-scope]')" in js
    assert "msReady" in js
    # never a page-wide id lookup of a panel part
    for part in ("ms-badge", "ms-reset", "ms-override", "ms-ovr",
                 "ms-reason", "model-settings"):
        assert f"getElementById('{part}')" not in js, part


# ------------------------------------ the same builder on the Forecast tab

def test_the_forecast_panel_names_the_members_as_they_run_on_the_data():
    ds = stored()
    html = client.get(f"/forecast?source={ds.id}").text
    panel = html.split('id="model-settings"')[1].split("Fixed by the model")[0]
    assert "Particle filter (plain SIHRS)" in panel
    assert "Groundhog (own data)" in panel
    assert "Affects: plain SIHRS particle filter." in panel
    assert "Oracle" not in panel
    assert "applied to counts only" in panel and 'data-only="count"' in panel
    # a rate dataset has no floor to set
    rate = stored(grouped_bytes(rate=True), "Rates", kind="rate")
    html = client.get(f"/forecast?source={rate.id}").text
    assert "knob.output.floor_lam" not in html


def test_a_rate_run_never_records_the_floor(monkeypatch):
    rate = stored(grouped_bytes(rate=True), "Rates", kind="rate")
    got = []
    monkeypatch.setattr(DU, "run_worker", lambda spec: got.append(spec))
    client.post("/run/dataset", data={
        "dataset": rate.id, "forecast_date": rate.forecast_dates()[-1],
        "locations": "all", "engine": "analogue",
        "knob.output.floor_lam": "0.5"}, follow_redirects=False)
    (spec,) = got
    assert "knobs" not in spec.extra


def test_a_repeated_knob_field_is_refused_on_a_dataset_run(monkeypatch):
    rate = stored(grouped_bytes(rate=True), "Rates", kind="rate")
    got = []
    monkeypatch.setattr(DU, "run_worker", lambda spec: got.append(spec))
    ui_state._status["running"] = None
    ui_state._status.pop("flash", None)
    r = client.post("/run/dataset", data={
        "dataset": rate.id, "forecast_date": rate.forecast_dates()[-1],
        "locations": "all", "engine": "analogue",
        "knob.groundhog.bandwidth": ["3", "4"]}, follow_redirects=False)
    assert r.status_code == 303 and got == []
    flash = ui_state._status.get("flash", "")
    assert "knob.groundhog.bandwidth more than once" in flash
    assert "Nothing was run" in flash
    assert not ui_state._status.get("running")
