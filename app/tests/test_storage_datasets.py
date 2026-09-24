"""Your datasets on the Storage tab (server._storage_inventory,
datasets_ui.storage_rows, POST /storage/datasets/{id}/delete).

Each dataset is listed with its size holding everything it owns: the
upload, its replays and its runs' workroots. The panel's total counts
every byte once, as it counts the other items: a dataset adds its own
folder, its runs being counted as workroots (where they stay listed, named
after it). The delete takes all of it, needs the dataset's name, keeps the
runs' ledger rows, and is refused while a run or replay uses the dataset.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.core.runs as runs_mod
from app.core import custom_retro as CX
from app.core import datasets as D
from app.core import retro
from app.core.runs import Ledger, RunSpec
from app.ui import datasets_ui as DU
from app.ui import server as srv
from app.ui import retro_seasons as ui_retro_seasons
from app.ui import shared as ui_shared
from app.ui import state as ui_state

from test_datasets_ui import TEMPLATE                   # noqa: E402

client = TestClient(srv.app)


@pytest.fixture()
def state(tmp_path, monkeypatch):
    """A dataset with one run and one replay, plus one hub run."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path / "state")
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    import flubnf.settings as settings_mod
    monkeypatch.setattr(settings_mod, "HUB", tmp_path / "hub")
    before = dict(ui_state._status)
    ui_state._status["running"] = None
    DU._REPLAY.clear()
    ui_shared._invalidate_scans()
    r = client.post("/data/datasets",
                    files={"file": ("t.csv", TEMPLATE.read_bytes(),
                                    "text/csv")},
                    data={"name": "Template", "kind": "count"},
                    follow_redirects=False)
    ds = D.get(r.headers["location"].split("source=")[1].split("#")[0])
    client.post("/run/dataset", data={"dataset": ds.id,
                                      "forecast_date": "2024-03-02",
                                      "locations": "all",
                                      "engine": "analogue"})
    client.post("/retro/dataset/run", data={
        "dataset": ds.id, "first": "2024-01-06", "last": "2024-02-03",
        "engine": "analogue"})
    (ds_run,) = [r["run_id"] for r in Ledger().rows(10)]
    hub_run = Ledger().open_run(RunSpec(engine="all",
                                        forecast_date="2098-01-03"),
                                Path("pending"), {})
    Ledger().close_run(hub_run, "ok", {})
    hub_wr = tmp_path / "state" / "workroots" / hub_run
    hub_wr.mkdir(parents=True)
    (hub_wr / "results.json").write_text("{}" * 500)
    ui_state._status.pop("flash", None)
    ui_shared._invalidate_scans()
    yield {"ds": ds, "ds_run": ds_run, "hub_run": hub_run,
           "wr": tmp_path / "state" / "workroots"}
    ui_state._status.clear(); ui_state._status.update(before)
    DU._REPLAY.clear()
    ui_shared._invalidate_scans()


def test_a_dataset_row_holds_its_upload_replays_and_runs(state):
    ds, wr = state["ds"], state["wr"]
    inv = srv._storage_inventory()
    (row,) = inv["datasets"]
    own = retro.dir_size(ds.path)
    rep = retro.dir_size(CX.replay_root(ds))
    run = retro.dir_size(wr / state["ds_run"])
    assert rep > 0 and run > 0
    assert (row["own_bytes"], row["bytes"]) == (own, own + run)
    assert (row["replays"], row["runs"]) == (1, 1)
    assert row["data_h"] == retro.human_bytes(own - rep)
    assert row["size_h"] == retro.human_bytes(own + run)
    # the run stays listed as a workroot, named after its dataset
    by_id = {w["id"]: w for w in inv["workroots"]}
    assert by_id[state["ds_run"]]["dataset_name"] == "Template"
    assert "dataset_name" not in by_id[state["hub_run"]]


def test_the_total_counts_every_byte_once(state):
    ds, wr = state["ds"], state["wr"]
    inv = srv._storage_inventory()
    want = (retro.dir_size(wr / state["ds_run"])
            + retro.dir_size(wr / state["hub_run"])
            + retro.dir_size(ds.path))
    assert inv["total_bytes"] == want
    html = client.get("/storage").text
    assert f'<span class="big">{inv["total_h"]}</span>' in html
    joined = " ".join(html.split())
    assert "your datasets, each counted once" in joined
    assert "listed but not counted" in joined


def test_the_page_lists_it_with_a_name_confirmed_delete(state):
    ds = state["ds"]
    html = " ".join(client.get("/storage").text.split())
    (row,) = srv._storage_inventory()["datasets"]
    assert "Your datasets" in html
    assert (f'<a href="/data?source={ds.id}#browser">Template</a></strong> '
            f'<span class="hint">· {row["size_h"]} · data') in html
    assert "· 1 replay " in html and "· 1 run " in html
    assert f'action="/storage/datasets/{ds.id}/delete"' in html
    assert 'data-confirm="Template"' in html
    # the shared delete script fills the name when a row carries one
    assert "f.confirm.value=d.confirm||f.ident.value" in html
    # its run's workroot row names it, and its groups as groups
    assert "· on Template · 3 groups: Adult, Overall, Pediatric ·" in html


def test_a_dataset_alone_lists_no_empty_parts(state):
    """A dataset with no replay and no run read '· 0 replays 0 B · 0 runs
    0 B' (and its delete 'With it go its 0 replays and 0 run
    workroots')."""
    r = client.post("/data/datasets",
                    files={"file": ("t.csv", TEMPLATE.read_bytes(),
                                    "text/csv")},
                    data={"name": "Alone", "kind": "count"},
                    follow_redirects=False)
    assert r.status_code == 303
    ui_shared._invalidate_scans()
    rows = {d["name"]: d for d in srv._storage_inventory()["datasets"]}
    alone, tpl = rows["Alone"], rows["Template"]
    assert alone["parts"] == [] and alone["goes"] == ""
    assert tpl["parts"][1:] == [f"1 replay {tpl['replays_h']}",
                                f"1 run {tpl['runs_h']}"]
    assert tpl["goes"] == ("With it go its 1 replay and its 1 run "
                           "workroot; the runs' ledger rows are kept.")
    html = " ".join(client.get("/storage").text.split())
    row = html.split(">Alone</a></strong>")[1].split("</span></span>")[0]
    assert row == f' <span class="hint">· {alone["size_h"]}'
    assert "0 replays" not in html and "0 runs" not in html
    assert 'data-confirm="Alone" data-what="the dataset Alone" ' in html
    assert 'data-hint="">Delete' in html


def test_delete_needs_the_name_and_takes_everything_it_counts(state):
    ds, wr = state["ds"], state["wr"]
    url = f"/storage/datasets/{ds.id}/delete"
    for wrong in ("", ds.id, "template"):
        client.post(url, data={"confirm": wrong}, follow_redirects=False)
        assert "not confirmed" in ui_state._status.get("flash", "")
        assert ds.path.is_dir() and (wr / state["ds_run"]).is_dir()
    size = srv._storage_inventory()["datasets"][0]["size_h"]
    r = client.post(url, data={"confirm": "Template"},
                    headers={"referer": "http://testserver/storage"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/storage"
    assert not ds.path.exists() and not (wr / state["ds_run"]).exists()
    assert (wr / state["hub_run"]).is_dir()             # a hub run stays
    assert ("Deleted the dataset Template, its replays and 1 run "
            f"workroot: {size} freed. The runs' ledger rows are kept.") \
        in ui_state._status["flash"]
    # the ledger rows stand, the run's with a dash for disk use
    ids = {r["run_id"] for r in Ledger().rows(10)}
    assert {state["ds_run"], state["hub_run"]} <= ids
    inv = srv._storage_inventory()
    assert inv["datasets"] == []
    assert inv["total_bytes"] == retro.dir_size(wr / state["hub_run"])


def test_the_data_tab_delete_frees_what_storage_counts(state):
    """Deleting from the Data tab takes the same things as from Storage:
    the upload, its replays and its runs' workroots; ledger rows stay."""
    ds, wr = state["ds"], state["wr"]
    r = client.post(f"/data/datasets/{ds.id}/delete",
                    data={"confirm": "Template"}, follow_redirects=False)
    assert r.status_code == 303
    assert not ds.path.exists() and not (wr / state["ds_run"]).exists()
    assert (wr / state["hub_run"]).is_dir()
    assert "its replays and 1 run workroot" in ui_state._status["flash"]
    assert state["ds_run"] in {r["run_id"] for r in Ledger().rows(10)}


def test_a_busy_dataset_has_no_delete_and_is_refused(state):
    ds = state["ds"]
    DU._REPLAY.update({"id": ds.id, "stamp": "20260101T000000Z"})
    ui_shared._invalidate_scans()
    html = client.get("/storage").text
    assert f'action="/storage/datasets/{ds.id}/delete"' not in html
    assert "a replay on it is in progress" in html
    client.post(f"/storage/datasets/{ds.id}/delete",
                data={"confirm": "Template"}, follow_redirects=False)
    assert "was not deleted: a replay on it is in progress" in \
        ui_state._status["flash"]
    assert ds.path.is_dir()


def test_no_datasets_no_section(state):
    client.post(f"/storage/datasets/{state['ds'].id}/delete",
                data={"confirm": "Template"}, follow_redirects=False)
    assert "Your datasets" not in client.get("/storage").text
    assert not re.search(r"/storage/datasets/[^/]+/delete",
                         client.get("/storage").text)
