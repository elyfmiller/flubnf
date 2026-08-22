"""Storage management: the clearable run ledger and the storage panel.

The rules under test:
  * clearing removes only completed ledger rows, never the active run's,
    demands a confirmation naming the count, refuses a stale count, and
    never deletes workroot data on disk;
  * the storage panel lists workroots, retro seasons, archived retro runs,
    and report archives with sizes, and every delete is name-confirmed and
    busy-guarded server-side;
  * HARD protections: the sealed validation record and the hub clone are
    never deletable, render no delete controls, and a crafted request
    (including a symlink into a protected tree) is refused;
  * deleting a workroot whose ledger row remains leaves an honest dangling
    row (a dash for disk use, never an error).
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                     # noqa: E402
from app.core.runs import Ledger, RunSpec            # noqa: E402
from app.ui import server as srv                     # noqa: E402

client = TestClient(srv.app)

SEASON, OTHER = "2098-99", "2097-98"
ARCH_STAMP = "20980204T101500Z"


@pytest.fixture(autouse=True)
def _isolated_status():
    status_before = dict(srv._status)
    retro_before = dict(srv._retro_status)
    stop_before = set(srv._retro_stop)
    yield
    srv._status.clear(); srv._status.update(status_before)
    srv._retro_status.clear(); srv._retro_status.update(retro_before)
    srv._retro_stop.clear(); srv._retro_stop.update(stop_before)
    srv._invalidate_scans()


@pytest.fixture()
def state(tmp_path, monkeypatch):
    """A full tmp state: two closed runs plus one live one in the ledger
    with workroots on disk, a retro season, an archived retro run, a report
    archive, and protected seal and hub trees."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    retro_root = tmp_path / "retro"
    seal_root = tmp_path / "retro_seal"
    monkeypatch.setattr(srv, "RETRO_ROOT", retro_root)
    monkeypatch.setattr(srv, "RETRO_SEAL", seal_root)
    hub = tmp_path / "hub"
    import flubnf.settings as settings_mod
    monkeypatch.setattr(settings_mod, "HUB", hub)
    led = Ledger()
    rids = {}
    for status in ("ok", "stopped", "error"):
        rid = led.open_run(RunSpec(engine="all", forecast_date="2098-01-03"),
                           Path("pending"), {})
        led.close_run(rid, status, {})
        (tmp_path / "workroots" / rid).mkdir(parents=True)
        (tmp_path / "workroots" / rid / "results.json").write_text("{}")
        rids[status] = rid
        import time as _t
        _t.sleep(0.02)          # keeps created_utc ordering deterministic
        # for the newest-first listing (run_id uniqueness rides the uuid)
    live = led.open_run(RunSpec(engine="all", forecast_date="2098-01-10"),
                        Path("pending"), {})
    (tmp_path / "workroots" / live).mkdir(parents=True)
    rids["running"] = live
    srv._status["running"] = f"all:{live}"
    srv._status["workroot"] = str(tmp_path / "workroots" / live)
    (retro_root / SEASON / "weeks").mkdir(parents=True)
    (retro_root / SEASON / "weeks" / "x.json").write_text("{}")
    arch = retro_root / f"{SEASON}__archived_{ARCH_STAMP}"
    arch.mkdir(parents=True)
    (arch / "scores.json").write_text("{}")
    (tmp_path / "archive" / "2098-01-03").mkdir(parents=True)
    (tmp_path / "archive" / "2098-01-03" / "report.html").write_text("<p>r</p>")
    (seal_root / SEASON / "weeks").mkdir(parents=True)
    (seal_root / SEASON / "weeks" / "sealed.json").write_text("{}")
    (hub / "auxiliary-data").mkdir(parents=True)
    (hub / "auxiliary-data" / "truth.csv").write_text("d")
    srv._invalidate_scans()
    return {"root": tmp_path, "rids": rids, "ledger": led,
            "retro_root": retro_root, "seal": seal_root, "hub": hub}


def _flash():
    return srv._status.get("flash", "")


# ------------------------------------------------------------- ledger clear

def test_clear_removes_completed_rows_never_the_active_one(state):
    led = state["ledger"]
    assert len(srv._clearable_run_ids(led)) == 3
    r = client.post("/runs/clear", data={"confirm": "3"},
                    follow_redirects=False)
    assert r.status_code == 303
    left = led.rows(50)
    assert [x["run_id"] for x in left] == [state["rids"]["running"]]
    assert "Cleared 3 completed rows" in _flash()
    # the confirm copy's promise holds: clearing deleted NO disk data
    for rid in state["rids"].values():
        assert (state["root"] / "workroots" / rid).is_dir()
    assert "No data on disk was deleted" in _flash()


def test_clear_refuses_a_stale_count(state):
    r = client.post("/runs/clear", data={"confirm": "7"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert len(state["ledger"].rows(50)) == 4        # nothing removed
    assert "Nothing was cleared" in _flash()


def test_clear_control_names_the_count_and_the_no_disk_promise(state):
    html = client.get("/runs").text
    assert "Clear 3 completed\n   rows" in html or \
        "Clear 3 completed rows" in " ".join(html.split())
    # the second-confirmation copy states the ledger-only scope
    assert "does NOT delete run data on disk" in html
    assert "window.FluBNFConfirm" in html


def test_interrupted_rows_are_clearable(state):
    """A 'running' row with no live worker (the app closed mid-run) is a
    completed row for clearing purposes."""
    srv._status["running"] = None
    srv._status["workroot"] = None
    assert len(srv._clearable_run_ids(state["ledger"])) == 4


# ------------------------------------------------------------ storage panel

def test_storage_panel_lists_everything_with_sizes(state):
    html = client.get("/runs").text
    for rid in state["rids"].values():
        assert rid in html
    assert SEASON in html
    assert "2098-02-04 10:15 UTC" in html            # the archived run
    assert "2098-01-03" in html                      # the report archive
    assert "Sealed validation record" in html
    assert "FluSight hub clone" in html
    assert html.count(" B<") or " KB" in html or " B\n" in html  # sizes shown


def test_protected_trees_render_no_delete_controls(state):
    html = client.get("/runs").text
    protected = html.split("Protected</h3>", 1)[1].split("</div>\n<script>", 1)[0]
    assert "<form" not in protected
    assert "data-del-storage" not in protected
    assert 'class="pill">protected' in protected


def test_busy_rows_render_no_delete_controls(state):
    srv._retro_status[SEASON] = "running"
    html = client.get("/runs").text
    live = state["rids"]["running"]
    row = html.split(f"<strong>{live}</strong>", 1)[1].split("</div>", 1)[0]
    assert "data-del-storage" not in row             # the live workroot
    srow = html.split(f"<strong>{SEASON}</strong>", 1)[1].split("</div>", 1)[0]
    assert "data-del-storage" not in srow            # the replaying season


# ---------------------------------------------------------------- deletions

def test_delete_workroot_leaves_an_honest_dangling_ledger_row(state):
    rid = state["rids"]["ok"]
    r = client.post("/storage/delete",
                    data={"kind": "workroot", "ident": rid, "confirm": rid},
                    follow_redirects=False)
    assert r.status_code == 303
    assert not (state["root"] / "workroots" / rid).exists()
    assert "ledger row remains" in _flash()
    # the row survives and reads honestly: a dash, not an error
    html = client.get("/runs").text
    assert rid in html
    row = html.split(f'href="/runs/{rid}"', 1)[1].split("</tr>", 1)[0]
    assert ">--</td>" in row
    assert client.get(f"/runs/{rid}").status_code == 200


def test_delete_refuses_the_active_workroot(state):
    live = state["rids"]["running"]
    r = client.post("/storage/delete",
                    data={"kind": "workroot", "ident": live, "confirm": live},
                    follow_redirects=False)
    assert r.status_code == 303
    assert (state["root"] / "workroots" / live).is_dir()
    assert "cannot\nbe deleted" in _flash() or "cannot be deleted" in _flash()


def test_delete_needs_the_confirmation_naming_the_entry(state):
    rid = state["rids"]["ok"]
    r = client.post("/storage/delete",
                    data={"kind": "workroot", "ident": rid, "confirm": "yes"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert (state["root"] / "workroots" / rid).is_dir()
    assert "not confirmed" in _flash()


def test_delete_retro_season_refused_while_replaying(state):
    srv._retro_status[SEASON] = "running"
    r = client.post("/storage/delete",
                    data={"kind": "retro-season", "ident": SEASON,
                          "confirm": SEASON}, follow_redirects=False)
    assert r.status_code == 303
    assert (state["retro_root"] / SEASON).is_dir()
    assert "replaying" in _flash()
    srv._retro_status.pop(SEASON, None)
    client.post("/storage/delete",
                data={"kind": "retro-season", "ident": SEASON,
                      "confirm": SEASON}, follow_redirects=False)
    assert not (state["retro_root"] / SEASON).exists()
    # the seal's copy of the same season is untouched
    assert (state["seal"] / SEASON / "weeks" / "sealed.json").is_file()


def test_delete_retro_archive_and_report_archive(state):
    name = f"{SEASON}__archived_{ARCH_STAMP}"
    srv._retro_status[SEASON] = "paused"             # paused blocks too
    client.post("/storage/delete", data={"kind": "retro-archive",
                                         "ident": name, "confirm": name},
                follow_redirects=False)
    assert (state["retro_root"] / name).is_dir()
    srv._retro_status.pop(SEASON, None)
    client.post("/storage/delete", data={"kind": "retro-archive",
                                         "ident": name, "confirm": name},
                follow_redirects=False)
    assert not (state["retro_root"] / name).exists()
    # report archive: refused while a console run is live, allowed after
    client.post("/storage/delete", data={"kind": "report-archive",
                                         "ident": "2098-01-03",
                                         "confirm": "2098-01-03"},
                follow_redirects=False)
    assert (state["root"] / "archive" / "2098-01-03").is_dir()
    srv._status["running"] = None
    srv._status["workroot"] = None
    client.post("/storage/delete", data={"kind": "report-archive",
                                         "ident": "2098-01-03",
                                         "confirm": "2098-01-03"},
                follow_redirects=False)
    assert not (state["root"] / "archive" / "2098-01-03").exists()


# ------------------------------------------------- total and clear-all sweep

def test_total_disk_metric_sums_the_managed_categories_only(state):
    """The panel's headline figure: workroots + retro seasons + archived
    retro runs + report archives, with the protected trees (seal, hub)
    deliberately outside the total."""
    from app.core import retro
    inv = srv._storage_inventory()
    expect = 0
    for rid in state["rids"].values():
        expect += retro.dir_size(state["root"] / "workroots" / rid)
    expect += retro.dir_size(state["retro_root"] / SEASON)
    expect += retro.dir_size(
        state["retro_root"] / f"{SEASON}__archived_{ARCH_STAMP}")
    expect += retro.dir_size(state["root"] / "archive" / "2098-01-03")
    assert inv["total_bytes"] == expect
    assert inv["total_h"] == retro.human_bytes(expect)
    # protected trees are excluded from the figure but still listed
    assert any(p["label"] == "Sealed validation record"
               for p in inv["protected"])
    html = client.get("/runs").text
    joined = " ".join(html.split())
    assert f'<span class="big">{inv["total_h"]}</span>' in html
    assert "not counted here" in joined                # the copy says so


def test_clear_all_control_names_count_and_total_size(state):
    from app.core import retro
    cw = srv._clearable_workroots()
    assert len(cw) == 3                    # the live run's is excluded
    assert state["rids"]["running"] not in [w["id"] for w in cw]
    html = client.get("/runs").text
    joined = " ".join(html.split())
    assert "Delete all 3 completed workroots" in joined
    size_h = retro.human_bytes(sum(w["bytes"] for w in cw))
    assert f'data-size="{size_h}"' in html
    assert 'data-count="3"' in html
    # the confirmation goes through the shared shell and names both
    assert "totaling '+s+' on disk" in html
    assert "window.FluBNFConfirm" in html


def test_clear_all_refuses_a_stale_count(state):
    r = client.post("/storage/clear-workroots", data={"confirm": "9"},
                    follow_redirects=False)
    assert r.status_code == 303
    for rid in state["rids"].values():
        assert (state["root"] / "workroots" / rid).is_dir()
    assert "Nothing was deleted" in _flash() \
        or "Nothing was\ndeleted" in _flash()


def test_clear_all_deletes_completed_keeps_active_and_ledger_rows(state):
    r = client.post("/storage/clear-workroots", data={"confirm": "3"},
                    follow_redirects=False)
    assert r.status_code == 303
    # the three completed runs' workroots are gone; the active one stays
    for status in ("ok", "stopped", "error"):
        assert not (state["root"] / "workroots"
                    / state["rids"][status]).exists()
    assert (state["root"] / "workroots"
            / state["rids"]["running"]).is_dir()
    assert "Deleted 3 completed run workroots" in _flash()
    assert "ledger row" in _flash()
    # every ledger row remains, the cleared ones honestly dangling
    html = client.get("/runs").text
    for rid in state["rids"].values():
        assert rid in html
    row = html.split(f'href="/runs/{state["rids"]["ok"]}"', 1)[1] \
              .split("</tr>", 1)[0]
    assert ">--</td>" in row
    # the other storage categories were not touched
    assert (state["retro_root"] / SEASON).is_dir()
    assert (state["root"] / "archive" / "2098-01-03").is_dir()


def test_clear_all_never_reaches_protected_trees(state):
    """A workroot-shaped symlink into the seal is excluded from the sweep
    (and from its count), and the seal survives a confirmed clear-all."""
    link = state["root"] / "workroots" / "sneaky"
    link.symlink_to(state["seal"] / SEASON)
    srv._invalidate_scans()
    cw = srv._clearable_workroots()
    assert "sneaky" not in [w["id"] for w in cw]
    assert len(cw) == 3
    r = client.post("/storage/clear-workroots", data={"confirm": "3"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert (state["seal"] / SEASON / "weeks" / "sealed.json").is_file()
    assert link.is_symlink()               # not even the link went


def test_clear_all_with_nothing_to_do_says_so(state):
    for status in ("ok", "stopped", "error"):
        import shutil
        shutil.rmtree(state["root"] / "workroots" / state["rids"][status])
    srv._invalidate_scans()
    r = client.post("/storage/clear-workroots", data={"confirm": "0"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "No completed run workroots" in _flash()
    # and the control disappears from the page
    html = client.get("/runs").text
    assert "Delete all" not in html


# ------------------------------------------------------------ hard barriers

def test_seal_and_hub_are_refused_on_any_crafted_request(state):
    assert srv._storage_protected(state["seal"] / SEASON)
    assert srv._storage_protected(state["hub"])
    assert srv._storage_protected(state["hub"] / "auxiliary-data")
    # traversal-shaped identifiers never pass validation
    for kind, ident in (("workroot", "../retro_seal"),
                        ("workroot", "/etc"),
                        ("retro-season", "../retro_seal/" + SEASON),
                        ("report-archive", "../../retro_seal")):
        r = client.post("/storage/delete",
                        data={"kind": kind, "ident": ident,
                              "confirm": ident}, follow_redirects=False)
        assert r.status_code == 303
        assert "Nothing was deleted" in _flash(), (kind, ident)
    assert (state["seal"] / SEASON / "weeks" / "sealed.json").is_file()
    assert (state["hub"] / "auxiliary-data" / "truth.csv").is_file()


def test_a_symlink_into_a_protected_tree_is_refused(state):
    """Even a workroot-shaped name that LINKS into the seal is caught: the
    protection resolves the target before comparing."""
    link = state["root"] / "workroots" / "sneaky"
    link.symlink_to(state["seal"] / SEASON)
    srv._invalidate_scans()
    r = client.post("/storage/delete",
                    data={"kind": "workroot", "ident": "sneaky",
                          "confirm": "sneaky"}, follow_redirects=False)
    assert r.status_code == 303
    assert "protected" in _flash()
    assert (state["seal"] / SEASON / "weeks" / "sealed.json").is_file()
    assert link.is_symlink()                          # not even the link went


def test_unknown_kind_is_refused(state):
    r = client.post("/storage/delete",
                    data={"kind": "ledger", "ident": "x", "confirm": "x"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "Nothing was deleted" in _flash()
