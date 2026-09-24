"""Custom datasets in the console (app/ui/datasets_ui.py and its seams in
the tab routers): the Data tab's upload, list and browser; the Forecast tab's
data source; the run page; the Retrospective tab's own-data replay.

No hub and no engine: FLUBNF_HUB=/nonexistent; the dataset store, the
ledger and the workroots live in tmp_path. The Groundhog runs for real.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.core.runs as runs_mod
from app.core import datasets as D
from app.ui import datasets_ui as DU
from app.ui import server as srv
from app.ui import pipeline as ui_pipeline
from app.ui import retro_seasons as ui_retro_seasons
from app.ui import shared as ui_shared
from app.ui import state as ui_state

from test_dataset_engines import grouped_bytes         # noqa: E402

client = TestClient(srv.app)
FIX = Path(__file__).resolve().parent / "fixtures"
TEMPLATE = Path(__file__).resolve().parents[1] / "ui" / "static" / \
    "dataset-template.csv"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path / "state")
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path / "retro")
    status, form = dict(ui_state._status), dict(ui_state._last_form)
    ui_state._status["running"] = None
    ui_state._status.pop("flash", None)
    DU._LAST.clear()
    DU._REPLAY.clear()
    ui_shared._invalidate_scans()
    yield
    ui_state._status.clear(); ui_state._status.update(status)
    ui_state._last_form.clear(); ui_state._last_form.update(form)
    DU._LAST.clear()
    DU._REPLAY.clear()
    ui_shared._invalidate_scans()


def upload(raw, name="Kids", kind="count", **data):
    return client.post("/data/datasets",
                       files={"file": ("kids.csv", raw, "text/csv")},
                       data={"name": name, "kind": kind, **data},
                       follow_redirects=False)


def stored(raw=None, name="Kids", kind="count"):
    r = upload(raw if raw is not None else grouped_bytes(), name, kind)
    assert r.status_code == 303, r.text[:500]
    return D.get(r.headers["location"].split("source=")[1].split("#")[0])


# ---------------------------------------------------------------- Data tab

def test_upload_stores_and_lists_the_dataset():
    r = upload(FIX.joinpath("grouped-template-population-head.csv").read_bytes())
    assert r.status_code == 303
    assert r.headers["location"].startswith("/data?source=kids-")
    (ds,) = D.list_datasets()
    assert ds.groups == ["Adult", "Overall", "Pediatric"]
    page = client.get("/data").text
    assert "Your datasets" in page and ">Kids</a>" in page
    assert 'href="/forecast?source=' + ds.id in page
    assert "dataset-template.csv" in page


def test_a_bad_upload_shows_every_problem_inline_and_stores_nothing():
    raw = (b"date,target_group,value\n2024-08-04,A,-1\nbad,A/B,x\n"
           b"2024-08-10,A,2\n")
    r = upload(raw, "bad")
    assert r.status_code == 422
    assert "Nothing was stored." in r.text
    assert "negative" in r.text and "could not be parsed" in r.text
    assert "different weekdays" in r.text
    assert D.list_datasets() == []
    assert not ui_state._status.get("flash")          # inline, not the flash slot


def test_a_multi_target_file_offers_its_targets():
    raw = (b"target_end_date,target,location,observation\n"
           b"2024-08-03,a,01,1\n2024-08-03,b,01,2\n")
    r = upload(raw, "multi")
    assert r.status_code == 422
    assert '<select name="target"' in r.text
    assert "<option >a</option>" in r.text.replace("<option selected>", "<option >") \
        or ">a</option>" in r.text
    r2 = upload(raw, "multi", target="b")
    assert r2.status_code == 303


def test_an_undeclared_kind_comes_from_the_values_and_a_bad_one_is_refused():
    r = upload(grouped_bytes(), kind="percent")
    assert r.status_code == 400 and "counts or rates" in r.text
    ds = stored(kind="")
    assert ds.kind == "count" and ds.meta["options"]["kind_from"] == "values"


def test_oversize_is_refused_by_content_length(monkeypatch):
    monkeypatch.setattr(D, "DEFAULT_LIMITS", D.Limits(max_bytes=2000))
    monkeypatch.setattr(DU, "FORM_SLACK", 0)
    r = upload(b"date,target_group,value\n" + b"2024-08-03,A,1\n" * 500)
    assert r.status_code == 413 and "limit" in r.text
    assert D.list_datasets() == []


def test_oversize_is_cut_off_while_streaming_without_a_length():
    from starlette.requests import Request
    head = (b'--B\r\nContent-Disposition: form-data; name="file"; '
            b'filename="a.csv"\r\nContent-Type: text/csv\r\n\r\n')

    def request(n):
        body = head + b"x" * n + b"\r\n--B--\r\n"
        chunks = [body[i:i + 256] for i in range(0, len(body), 256)]

        async def receive():
            if chunks:
                c = chunks.pop(0)
                return {"type": "http.request", "body": c,
                        "more_body": bool(chunks)}
            return {"type": "http.request", "body": b"", "more_body": False}
        return Request({"type": "http", "method": "POST", "path": "/",
                        "query_string": b"", "headers": [
                            (b"content-type",
                             b"multipart/form-data; boundary=B")]}, receive)
    assert asyncio.run(DU._capped_form(request(5000), 1000)) is None
    form = asyncio.run(DU._capped_form(request(100), 1000))
    assert form["file"].filename == "a.csv"


def test_cross_origin_upload_is_refused():
    r = client.post("/data/datasets",
                    files={"file": ("a.csv", grouped_bytes())},
                    data={"kind": "count"}, headers={"origin": "http://evil.example"})
    assert r.status_code == 403
    assert D.list_datasets() == []


def test_dataset_content_is_not_served_to_a_foreign_host():
    ds = stored()
    for url in (f"/data?source={ds.id}", f"/api/series?source={ds.id}&locs=Adult",
                f"/forecast?source={ds.id}"):
        r = client.get(url, headers={"host": "rebind.example"})
        assert r.status_code == 403, url


def test_browse_view_plots_a_group_with_group_wording():
    ds = stored()
    page = client.get(f"/data?source={ds.id}&loc=Adult").text
    assert f"<h2>{ds.name}" in page
    assert '<label for="dv-loc">Group</label>' in page
    assert 'name="source" value="' + ds.id in page
    assert "final data (not vintage-true)" in page
    assert "const VDS = " + json.dumps(ds.name) in page
    series = json.loads(re.search(r"const VSERIES = (\{.*?\});", page).group(1))
    assert series["dates"][0] == "2019-08-03"
    assert len(series["dates"]) == len(ds.weeks())
    # no snapshot picker for a dataset without as_of
    assert 'id="dv-vintage"' not in page


def test_unknown_source_falls_back_to_the_hub():
    page = client.get("/data?source=nope-000000000000").text
    # the hub view, not a dataset view: no dataset links in the browser card
    assert "<h2>FluSight hub</h2>" in page
    assert "Back to the FluSight hub" not in page
    # the browser card shows only when there is something to browse
    from app.ui import state as ui_state
    assert ("Vintage browser" in page) == bool(ui_state.data_mod.vintages())


def test_delete_needs_the_name_and_is_refused_while_busy():
    ds = stored()
    client.post(f"/data/datasets/{ds.id}/delete", data={"confirm": "wrong"})
    assert D.list_datasets()
    ui_state._status.update({"running": "dataset:x", "dataset_id": ds.id})
    client.post(f"/data/datasets/{ds.id}/delete", data={"confirm": ds.name})
    assert D.list_datasets()
    ui_state._status.update({"running": None, "dataset_id": None})
    r = client.post(f"/data/datasets/{ds.id}/delete",
                    data={"confirm": ds.name}, follow_redirects=False)
    assert r.status_code == 303 and D.list_datasets() == []
    r = client.post("/data/datasets/../../etc/delete", data={"confirm": "x"})
    assert r.status_code in (303, 404)


def test_output_download_never_serves_the_dataset_store(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "state" / "datasets")
    ds = stored()
    r = client.get("/output/download", params={"path": str(ds.source_path)})
    assert r.status_code == 404


# ------------------------------------------------------------ Forecast tab

def test_hub_forecast_page_is_unchanged_without_datasets():
    page = client.get("/forecast").text
    assert "all 52 jurisdictions" in page and 'action="/run"' in page
    assert 'id="fc-source"' not in page             # no selector, no datasets
    assert "const SRCQ = \"\";" in page


def test_the_source_is_two_tabs_and_your_data_opens_a_dataset():
    page = client.get("/forecast").text
    assert '<a href="/forecast" aria-current="page">FluSight hub</a>' in page
    assert '<a href="/forecast?tab=own">Your data</a>' in page
    # no dataset yet: the Your data tab is the upload box alone
    own = client.get("/forecast?tab=own").text
    assert 'id="dsup-forecast"' in own and 'id="fcform"' not in own
    assert '<a href="/forecast?tab=own" aria-current="page">Your data</a>' in own
    ds = stored()
    page = client.get("/forecast").text
    assert 'id="fc-source"' not in page and 'action="/run"' in page   # the hub tab
    r = client.get("/forecast?tab=own", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/forecast?source={ds.id}"
    page = client.get(r.headers["location"]).text
    assert 'id="fc-source"' in page and f'value="{ds.id}"' in page


def test_forecast_with_a_dataset_lists_groups_and_its_weeks():
    ds = stored()
    page = client.get(f"/forecast?source={ds.id}").text
    assert 'action="/run/dataset"' in page
    assert f"all {len(ds.groups)} groups" in page
    assert "all 52 jurisdictions" not in page
    assert "US national is always fitted" not in page
    assert f'name="dataset" value="{ds.id}"' in page
    assert f'<option value="{ds.forecast_dates()[-1]}">' in page
    srcq = re.search(r"const SRCQ = (\"[^\"]*\");", page).group(1)
    assert json.loads(srcq) == "&source=" + ds.id
    assert "Add FluSurv-NET donors" in page
    # the PF needs the engine: offered, disabled, with the reason
    assert "particle-filter engine is not installed" in page
    # the Oracle step's knobs are not offered on custom data
    assert 'id="ms-step"' not in page and "groundhog.aux" not in page


def test_api_series_with_a_source_returns_the_dataset():
    ds = stored()
    got = client.get(f"/api/series?source={ds.id}&locs=Adult|Nope").json()
    assert list(got) == ["Adult"]
    assert got["Adult"]["dates"][-1] == ds.weeks()[-1]


def _capture(monkeypatch):
    got = []
    monkeypatch.setattr(DU, "run_worker", lambda spec: got.append(spec))
    monkeypatch.setattr(ui_pipeline, "_run_all", lambda spec: (_ for _ in ()).throw(
        AssertionError("the hub pipeline ran")))
    return got


def test_run_builds_a_dataset_spec_and_never_the_hub_pipeline(monkeypatch):
    ds = stored()
    got = _capture(monkeypatch)
    before = dict(ui_state._last_form)
    fd = "2023-12-02"
    r = client.post("/run/dataset", data={
        "dataset": ds.id, "forecast_date": fd, "locations": ["Adult", "Pediatric"],
        "engine": "analogue"}, follow_redirects=False)
    assert r.headers["location"] == f"/forecast?source={ds.id}#results"
    (spec,) = got
    assert spec.engine == "analogue" and spec.forecast_date == fd
    assert spec.locations == ["Adult", "Pediatric"]          # no US appended
    x = spec.extra
    assert x["dataset"] == ds.ref() and x["oracle"] == "none"
    assert "aux_pools" not in x and x["mode"] == "vintage"
    assert ui_state._last_form == before                # the hub form is untouched
    assert DU._LAST[ds.id]["forecast_date"] == fd


def test_run_all_groups_opt_in_flusurv_and_knobs(monkeypatch):
    ds = stored()
    got = _capture(monkeypatch)
    client.post("/run/dataset", data={
        "dataset": ds.id, "forecast_date": ds.forecast_dates()[-1],
        "locations": "all", "engine": "analogue", "flusurv": "1",
        "knob.groundhog.bandwidth": "3", "knob.oracle.w": "0.25",
        "knob.groundhog.aux": "iliplus"})
    (spec,) = got
    assert spec.locations == ds.groups and spec.extra["mode"] == "realtime"
    assert spec.extra["aux_pools"][0]["stream"] == "flusurv"
    assert spec.extra["knobs"] == {"groundhog.bandwidth": 3}


def test_run_refuses_a_week_the_dataset_lacks(monkeypatch):
    ds = stored()
    got = _capture(monkeypatch)
    client.post("/run/dataset", data={"dataset": ds.id,
                                      "forecast_date": "2030-01-05",
                                      "locations": "all"},
                follow_redirects=False)
    assert got == []
    assert f"Nearest earlier week: {ds.forecast_dates()[-1]}" in \
        ui_state._status.get("flash", "")
    assert not ui_state._status.get("running")


def test_run_refuses_the_pf_without_the_engine(monkeypatch):
    ds = stored()
    got = _capture(monkeypatch)
    client.post("/run/dataset", data={"dataset": ds.id,
                                      "forecast_date": "2023-12-02",
                                      "locations": "all", "engine": "all"},
                follow_redirects=False)
    assert got == [] and "cannot run" in ui_state._status.get("flash", "")


def test_a_real_run_shows_fans_and_exports_and_stays_off_the_hub(monkeypatch):
    ds = stored(TEMPLATE.read_bytes(), "Template")
    client.post("/run/dataset", data={"dataset": ds.id,
                                      "forecast_date": "2024-03-02",
                                      "locations": "all", "engine": "analogue"})
    assert not ui_state._status.get("running")         # released by the worker
    (row,) = runs_mod.Ledger().rows(5)
    assert row["status"] == "ok"
    o = json.loads(row["outcome"])
    assert list(o["exports"]) == ["FluBNF-Groundhog"]
    page = client.get(f"/runs/{row['run_id']}").text
    assert "Forecasts on Template" in page and "Export files" in page
    assert "Submission files" not in page
    assert "in-house persistence baseline" in page
    assert "Run again with these settings" not in page
    assert "FluSight baseline" not in page
    exp = o["exports"]["FluBNF-Groundhog"]
    r = client.get("/output/download", params={"path": exp})
    assert r.status_code == 200 and b"target_group" in r.content
    # the hub Forecast page: no dataset run in its latest-run card or fans
    hub = client.get("/forecast").text
    assert row["run_id"] not in hub and "Template" not in hub.split(
        'id="fc-source"')[0]
    ds_page = client.get(f"/forecast?source={ds.id}").text
    assert row["run_id"] in ds_page and "Fans and export files" in ds_page
    fanq = json.loads(re.search(r"const FANQ = (\{.*?\});",
                                ds_page).group(1))
    # the stored convention the fan script expects (as on the hub view):
    # stored "4" is four weeks ahead, never the canonical "0".."3"
    assert sorted(fanq["analogue"]["Adult"]) == ["1", "2", "3", "4"]
    # the Output tab and Home read shipped runs only
    assert ui_shared._latest_results() == (None, None)


# ----------------------------------------------------------- Retrospective

def test_retro_has_its_own_tab_for_datasets():
    page = client.get("/retro").text
    assert '<a href="/retro" aria-current="page">FluSight hub</a>' in page
    assert '<a href="/retro?tab=own">Your data</a>' in page
    assert 'id="dataset-replay"' not in page and 'action="/retro/run"' in page
    # no dataset yet: the Your data tab is the upload box alone
    own = client.get("/retro?tab=own").text
    assert 'id="dataset-replay"' in own and 'id="dsup-replay"' in own
    assert 'id="dsr-form"' not in own and 'action="/retro/run"' not in own
    assert '<a href="/retro?tab=own" aria-current="page">Your data</a>' in own
    ds = stored()
    r = client.get("/retro?tab=own", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == \
        f"/retro?dataset={ds.id}"
    page = client.get(r.headers["location"]).text
    assert f'<option value="{ds.id}" selected>' in page
    assert 'id="dsr-form"' in page and 'season-card' not in page
    assert 'id="dataset-replay"' not in client.get("/retro").text


def test_a_replay_runs_and_its_page_names_the_baseline_and_the_label():
    ds = stored(TEMPLATE.read_bytes(), "Template")
    r = client.post("/retro/dataset/run", data={
        "dataset": ds.id, "first": "2023-10-07", "last": "2024-02-24",
        "engine": "analogue"}, follow_redirects=False)
    loc = r.headers["location"]
    assert loc.startswith(f"/retro/dataset/{ds.id}/")
    page = client.get(loc).text
    assert "Final data, not vintage-true: 2023-10-07 to 2024-02-24" in page
    assert "in-house persistence baseline" in page and ">done<" in page
    assert "FluSight baseline" not in page
    # listed in its own card, not among the season cards
    idx = client.get(f"/retro?dataset={ds.id}").text
    assert idx.index(loc) > idx.index('id="dataset-replay"')
    assert loc not in client.get("/retro").text      # never on the hub tab
    assert not ui_state._status.get("running")


def test_a_second_replay_is_refused_while_one_runs():
    ds = stored()
    DU._REPLAY.update({"id": ds.id, "stamp": "20260101T000000Z"})
    r = client.post("/retro/dataset/run", data={"dataset": ds.id},
                    follow_redirects=False)
    assert "holds the engine" in ui_state._status.get("flash", "")
    assert r.headers["location"] == f"/retro?dataset={ds.id}"


def test_a_live_sandbox_fit_refuses_a_dataset_run_and_replay(monkeypatch):
    """The sandbox's claim holds the engine for the dataset forms too (the
    sandbox middleware guards /run and /retro/run only)."""
    ds = stored()
    got = _capture(monkeypatch)
    started = []
    monkeypatch.setattr(DU, "replay_worker", lambda *a, **k: started.append(a))
    monkeypatch.setitem(ui_state._sandbox_status, "running", "sb-run-1")
    client.post("/run/dataset", data={
        "dataset": ds.id, "forecast_date": ds.forecast_dates()[-1],
        "locations": "all", "engine": "analogue"}, follow_redirects=False)
    assert not got and not ui_state._status.get("running")
    assert "sandbox run sb-run-1" in ui_state._status.get("flash", "")
    ui_state._status.pop("flash", None)
    client.post("/retro/dataset/run", data={"dataset": ds.id},
                follow_redirects=False)
    assert not started and not DU._REPLAY
    assert "sandbox run sb-run-1" in ui_state._status.get("flash", "")


def test_replay_routes_refuse_bad_stamps_and_foreign_hosts():
    ds = stored()
    assert client.get(f"/retro/dataset/{ds.id}/nope").status_code == 404
    assert client.get(f"/retro/dataset/{ds.id}/20260101T000000Z",
                      headers={"host": "x.example"}).status_code == 403


def test_dataset_pages_never_call_the_plain_filter_the_oracle_member():
    """The Oracle SIHRS naming rule (test_oracle_text) on the dataset pages:
    SIHRS without 'Oracle ' only as the labelled plain filter."""
    from test_oracle_text import _ALLOWED
    ds = stored()
    for url in (f"/forecast?source={ds.id}", f"/data?source={ds.id}",
                "/retro", f"/retro?dataset={ds.id}"):
        html = re.sub(r"<pre>.*?</pre>", "", client.get(url).text, flags=re.S)
        text = " ".join(html.split())
        for m in re.finditer(r"(?<!Oracle )SIHRS", text):
            window = text[max(0, m.start() - 12):m.end() + 14]
            assert _ALLOWED.search(window), (url, window)
