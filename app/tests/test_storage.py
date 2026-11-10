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
    row (a dash for disk use, never an error);
  * on the runner computer's main console (the students' Mac Studio) the
    panel lists the students' experiments by folder, outside the total,
    each deleted with its confirmation (a queued one leaves the queue),
    never while the runner has it, never by an ident that leaves its
    folder or through a link; a student's console (any clone in
    ~/Students) and a laptop see the page as before, and a crafted delete
    from either is refused.
"""
import os
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                     # noqa: E402
from app.core.runs import Ledger, RunSpec            # noqa: E402
from app.ui import server as srv                     # noqa: E402
from app.ui.routes import storage as ui_storage      # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons  # noqa: E402
from app.ui import shared as ui_shared               # noqa: E402
from app.ui import state as ui_state                 # noqa: E402
from test_runner_folders import (LINKS, calendar, experiment,  # noqa: E402
                                 student, students)  # noqa: F401
from test_runner_queue import state as runner_state  # noqa: E402

client = TestClient(srv.app)

SEASON, OTHER = "2098-99", "2097-98"
ARCH_STAMP = "20980204T101500Z"


@pytest.fixture(autouse=True)
def _isolated_status():
    status_before = dict(ui_state._status)
    retro_before = dict(ui_retro_seasons._retro_status)
    stop_before = set(ui_retro_seasons._retro_stop)
    yield
    ui_state._status.clear(); ui_state._status.update(status_before)
    ui_retro_seasons._retro_status.clear(); ui_retro_seasons._retro_status.update(retro_before)
    ui_retro_seasons._retro_stop.clear(); ui_retro_seasons._retro_stop.update(stop_before)
    ui_shared._invalidate_scans()


@pytest.fixture()
def state(tmp_path, monkeypatch):
    """A full tmp state: two closed runs plus one live one in the ledger
    with workroots on disk, a retro season, an archived retro run, a report
    archive, and protected seal and hub trees."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    # the dataset store too: the panel lists (and totals) your datasets
    from app.core import datasets as datasets_mod
    monkeypatch.setattr(datasets_mod, "ROOT", tmp_path / "datasets")
    retro_root = tmp_path / "retro"
    seal_root = tmp_path / "retro_seal"
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", retro_root)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", seal_root)
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
        _t.sleep(0.02)          # deterministic created_utc order
    live = led.open_run(RunSpec(engine="all", forecast_date="2098-01-10"),
                        Path("pending"), {})
    (tmp_path / "workroots" / live).mkdir(parents=True)
    rids["running"] = live
    ui_state._status["running"] = f"all:{live}"
    ui_state._status["workroot"] = str(tmp_path / "workroots" / live)
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
    ui_shared._invalidate_scans()
    return {"root": tmp_path, "rids": rids, "ledger": led,
            "retro_root": retro_root, "seal": seal_root, "hub": hub}


def _flash():
    return ui_state._status.get("flash", "")


# ------------------------------------------------------------- ledger clear

def test_clear_removes_completed_rows_never_the_active_one(state):
    led = state["ledger"]
    assert len(ui_storage._clearable_run_ids(led)) == 3
    r = client.post("/runs/clear", data={"confirm": "3"},
                    follow_redirects=False)
    assert r.status_code == 303
    left = led.rows(50)
    assert [x["run_id"] for x in left] == [state["rids"]["running"]]
    assert "Cleared 3 ledger rows" in _flash()
    # the confirm copy's promise holds: clearing deleted NO disk data
    for rid in state["rids"].values():
        assert (state["root"] / "workroots" / rid).is_dir()
    assert "No data on disk was deleted" in ui_state._status.get(
        "flash_detail", "")


def test_clear_refuses_a_stale_count(state):
    r = client.post("/runs/clear", data={"confirm": "7"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert len(state["ledger"].rows(50)) == 4        # nothing removed
    assert "Not cleared" in _flash()
    assert ui_state._status.get("flash_kind") == "warn"


def test_clear_control_names_the_count_and_the_no_disk_promise(state):
    html = client.get("/runs").text
    # the rows counted are every row not running (interrupted and partial
    # runs too), as the dialog says (review of #88, ST-11)
    assert "Clear 3 rows not running (files kept)" in " ".join(html.split())
    # the second-confirmation copy states the ledger-only scope
    assert "does NOT delete run data on disk" in html
    assert "window.FluBNFConfirm" in html


def test_interrupted_rows_are_clearable(state):
    """A 'running' row with no live worker (the app closed mid-run) is a
    completed row for clearing purposes."""
    ui_state._status["running"] = None
    ui_state._status["workroot"] = None
    assert len(ui_storage._clearable_run_ids(state["ledger"])) == 4


# ------------------------------------------------------------ storage panel

def test_storage_panel_lists_everything_with_sizes(state):
    html = client.get("/runs").text
    for rid in state["rids"].values():
        assert rid in html
    assert SEASON in html
    # the archived run, in this computer's time as the workroot rows read
    # (bug hunt G28/G29, ST-10: one page, one clock)
    assert ui_storage._local_when("20980204T101500Z") in html
    assert "2098-02-04 10:15 UTC" not in html
    assert "2098-01-03" in html                      # the report archive
    assert "Sealed validation record" in html
    assert "FluSight hub clone" in html
    assert html.count(" B<") or " KB" in html or " B\n" in html  # sizes shown


def test_workroot_rows_read_as_human_labels_with_the_id_secondary(state):
    """A recorded run's row leads with its ledger label (kind, forecast date,
    wall clock, scope), linked to its run page; the raw id stays visible but
    secondary, in the row's meta line."""
    html = client.get("/storage").text
    rid = state["rids"]["ok"]
    row = html.split(f'data-wid="{rid}"', 1)[1].split("</div>", 1)[0]
    # a hub forecast reads by its round, as Output heads its cards
    assert (f'<strong><a href="/runs/{rid}">Round 2098-01-10 (as of '
            '2098-01-03)</a></strong>') in row
    meta = row.split('class="uk-meta"', 1)[1]
    assert f"<span>run {rid[4:6]}-{rid[6:8]} " in meta   # the wall clock
    assert f"<code" in meta and rid in meta       # the id, small and mono
    # an unrecorded workroot (no ledger row) says so instead of guessing,
    # and its page still opens (ST-13)
    orphan = "20980118T093000-0aacd0"
    (state["root"] / "workroots" / orphan).mkdir()
    ui_shared._invalidate_scans()
    html = client.get("/storage").text
    row = html.split(f'data-wid="{orphan}"', 1)[1].split("</div>", 1)[0]
    assert (f'<strong><a href="/runs/{orphan}">Unrecorded run</a></strong>'
            in row)
    assert "run 01-18 09:30:00" in row            # parsed from the id


def test_protected_trees_render_no_delete_controls(state):
    html = client.get("/runs").text
    protected = html.split('id="st-protected"', 1)[1].split("</section>", 1)[0]
    assert ">Protected</h3>" in protected
    assert "<form" not in protected
    assert "data-del-storage" not in protected
    # each tree says so with a badge (lock icon and word), not a button
    assert protected.count('<span class="uk-badge-t">protected</span>') \
        == protected.count('class="st-row"') == 2      # seal and hub
    # the section's count is the kit's neutral badge, as on other tabs
    assert '<span class="uk-badge-t">2 entries</span>' in protected


def test_busy_rows_render_no_delete_controls(state):
    ui_retro_seasons._retro_status[SEASON] = "running"
    html = client.get("/runs").text
    live = state["rids"]["running"]
    # workroot rows are found by their data-wid attribute
    row = html.split(f'data-wid="{live}"', 1)[1].split("</div>", 1)[0]
    assert "data-del-storage" not in row             # the live workroot
    # its Delete is disabled with no "?" of its own; why, in the refusal's
    # words, is said once above the sections (ST-08)
    assert " disabled " in row and "running now" in row and "tip" not in row
    busy = html.split('id="st-busy"', 1)[1].split("</div>", 1)[0]
    assert (f"The run {live} is active; its workroot cannot be deleted "
            "while it runs.") in busy
    srow = html.split(f">{SEASON} retrospective</a></strong>",
                      1)[1].split("</div>", 1)[0]
    assert "data-del-storage" not in srow            # the replaying season
    assert " disabled " in srow
    assert f"{SEASON} is replaying (status: running); stop it first." in busy


# ---------------------------------------------------------------- deletions

def test_delete_workroot_leaves_an_honest_dangling_ledger_row(state):
    rid = state["rids"]["ok"]
    r = client.post("/storage/delete",
                    data={"kind": "workroot", "ident": rid, "confirm": rid},
                    follow_redirects=False)
    assert r.status_code == 303
    assert not (state["root"] / "workroots" / rid).exists()
    assert "ledger row remains" in ui_state._status.get("flash_detail", "")
    # the row survives and reads honestly: a dash, not an error
    html = client.get("/runs").text
    assert rid in html
    row = html.split(f'href="/runs/{rid}"', 1)[1].split("</tr>", 1)[0]
    assert '<span title="workroot deleted">--</span></td>' in row
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
    ui_retro_seasons._retro_status[SEASON] = "running"
    r = client.post("/storage/delete",
                    data={"kind": "retro-season", "ident": SEASON,
                          "confirm": SEASON}, follow_redirects=False)
    assert r.status_code == 303
    assert (state["retro_root"] / SEASON).is_dir()
    assert "replaying" in _flash()
    ui_retro_seasons._retro_status.pop(SEASON, None)
    client.post("/storage/delete",
                data={"kind": "retro-season", "ident": SEASON,
                      "confirm": SEASON}, follow_redirects=False)
    assert not (state["retro_root"] / SEASON).exists()
    # the seal's copy of the same season is untouched
    assert (state["seal"] / SEASON / "weeks" / "sealed.json").is_file()


def test_delete_retro_archive_and_report_archive(state):
    name = f"{SEASON}__archived_{ARCH_STAMP}"
    ui_retro_seasons._retro_status[SEASON] = "paused"             # paused blocks too
    client.post("/storage/delete", data={"kind": "retro-archive",
                                         "ident": name, "confirm": name},
                follow_redirects=False)
    assert (state["retro_root"] / name).is_dir()
    ui_retro_seasons._retro_status.pop(SEASON, None)
    client.post("/storage/delete", data={"kind": "retro-archive",
                                         "ident": name, "confirm": name},
                follow_redirects=False)
    assert not (state["retro_root"] / name).exists()
    # report archive: the live run (both models, 2098-01-10) may write its
    # own date's, so that one is refused while it runs; another date's is
    # not its to write (bug hunt G29, ST-08: every archive was held)
    own = state["root"] / "archive" / "2098-01-10"
    (own / "submission").mkdir(parents=True)
    client.post("/storage/delete", data={"kind": "report-archive",
                                         "ident": "2098-01-10",
                                         "confirm": "2098-01-10"},
                follow_redirects=False)
    assert own.is_dir()
    ui_state._status["running"] = None
    ui_state._status["workroot"] = None
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
    inv = ui_storage._storage_inventory()
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
    # the copy says so, on the protected trees themselves
    prot = joined.split('id="st-protected"', 1)[1].split("</h3>", 1)[1][:1500]
    assert '<span class="uk-tag">not in the total</span>' in prot


def test_clear_all_control_names_count_and_total_size(state):
    from app.core import retro
    cw = ui_storage._clearable_workroots()
    assert len(cw) == 3                    # the live run's is excluded
    assert state["rids"]["running"] not in [w["id"] for w in cw]
    html = client.get("/runs").text
    joined = " ".join(html.split())
    # "not running", not "completed": an interrupted run's counts too (ST-11)
    assert "Delete all 3 workroots not running" in joined
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
    assert "Not deleted" in _flash()
    assert ui_state._status.get("flash_kind") == "warn"


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
    assert "Deleted 3 run workroots" in _flash()          # G29: not "completed"
    assert "ledger row" in ui_state._status.get("flash_detail", "")
    # every ledger row remains, the cleared ones honestly dangling
    html = client.get("/runs").text
    for rid in state["rids"].values():
        assert rid in html
    row = html.split(f'href="/runs/{state["rids"]["ok"]}"', 1)[1] \
              .split("</tr>", 1)[0]
    assert '<span title="workroot deleted">--</span></td>' in row
    # the other storage categories were not touched
    assert (state["retro_root"] / SEASON).is_dir()
    assert (state["root"] / "archive" / "2098-01-03").is_dir()


def test_clear_all_never_reaches_protected_trees(state):
    """A workroot-shaped symlink into the seal is excluded from the sweep
    (and from its count), and the seal survives a confirmed clear-all."""
    link = state["root"] / "workroots" / "sneaky"
    link.symlink_to(state["seal"] / SEASON)
    ui_shared._invalidate_scans()
    cw = ui_storage._clearable_workroots()
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
    ui_shared._invalidate_scans()
    r = client.post("/storage/clear-workroots", data={"confirm": "0"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "no run workroots on disk" in _flash()
    # and the control disappears from the page
    html = client.get("/runs").text
    assert "Delete all" not in html


# ------------------------------------------------------------ hard barriers

def test_seal_and_hub_are_refused_on_any_crafted_request(state):
    assert ui_storage._storage_protected(state["seal"] / SEASON)
    assert ui_storage._storage_protected(state["hub"])
    assert ui_storage._storage_protected(state["hub"] / "auxiliary-data")
    # traversal-shaped identifiers never pass validation
    for kind, ident in (("workroot", "../retro_seal"),
                        ("workroot", "/etc"),
                        ("retro-season", "../retro_seal/" + SEASON),
                        ("report-archive", "../../retro_seal")):
        r = client.post("/storage/delete",
                        data={"kind": kind, "ident": ident,
                              "confirm": ident}, follow_redirects=False)
        assert r.status_code == 303
        assert "Not deleted" in _flash(), (kind, ident)
        assert ui_state._status.get("flash_kind") == "warn"
    assert (state["seal"] / SEASON / "weeks" / "sealed.json").is_file()
    assert (state["hub"] / "auxiliary-data" / "truth.csv").is_file()


def test_a_symlink_into_a_protected_tree_is_refused(state):
    """Even a workroot-shaped name that LINKS into the seal is caught: the
    protection resolves the target before comparing."""
    link = state["root"] / "workroots" / "sneaky"
    link.symlink_to(state["seal"] / SEASON)
    ui_shared._invalidate_scans()
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
    assert "Not deleted" in _flash()


# ------------------------------------------------------------- ledger fold

def test_ledger_leads_the_page_in_a_fold_open_by_default(state):
    """The ledger folds behind a summary (row count, newest entry); it leads
    the page and ships open, the disk inventory folded below it."""
    html = client.get("/runs").text
    joined = " ".join(html.split())
    assert '<details class="ledgerfold" id="ledgerfold" open>' in html
    assert "4 runs recorded" in joined
    # the newest entry (the live run) is named in the summary line, which
    # carries the ledger's own heading on the Storage page
    summary = html.split('id="ledgerfold" open>', 1)[1].split("</summary>", 1)[0]
    assert 'id="h-st-ledger">Run ledger</h2>' in summary
    assert "newest" in summary
    # the table and the clear control live INSIDE the fold
    fold = html.split('<details class="ledgerfold" id="ledgerfold" open>',
                      1)[1].split("</details>", 1)[0]
    assert "<table>" in fold and "clear-ledger-btn" in fold
    # the ledger leads the page, the disk inventory in its fold below
    assert html.index('id="ledgerfold"') < html.index('id="storagefold"')


def test_ledger_fold_state_persists_per_local_storage(state):
    html = client.get("/runs").text
    assert "localStorage.getItem('ledgerfold-open')" in html
    assert "localStorage.setItem('ledgerfold-open'" in html
    assert "addEventListener('toggle'" in html


def test_storage_panel_folds_and_defaults_folded(state):
    """The storage panel folds too and ships FOLDED, its summary carrying the
    total-disk figure; a reader's open state persists."""
    html = client.get("/runs").text
    # the fold ships folded by default
    assert '<details class="ledgerfold" id="storagefold">' in html
    assert 'id="storagefold" open>' not in html
    # the summary carries the heading and the total disk figure
    summary = html.split('id="storagefold">', 1)[1] \
                  .split("</summary>", 1)[0]
    assert "On disk</h2>" in summary
    assert 'class="big"' in summary
    inv = ui_storage._storage_inventory()
    assert inv["total_h"] in summary
    # the panel body (workroots, deletes) lives INSIDE the fold
    fold = html.split('id="storagefold">', 1)[1] \
               .split("</details>", 1)[0]
    assert "Run workroots" in fold
    assert "data-del-storage" in fold


def test_storage_fold_state_persists_per_local_storage(state):
    html = client.get("/runs").text
    # a fresh key: the old one held '1' wherever the old open default was seen
    assert "localStorage.getItem('storagefold-v2')" in html
    assert "localStorage.setItem('storagefold-v2'" in html
    assert "storagefold-open" not in html
    # a stored open wins over the server's folded default
    assert "==='1')d.open=true" in html.replace(" ", "")


def test_empty_ledger_keeps_the_plain_hint_no_fold(state, monkeypatch):
    monkeypatch.setattr(runs_mod.Ledger, "rows", lambda self, n=50: [])
    html = client.get("/runs").text
    # no ledger fold with nothing to fold (the storage panel keeps its own)
    assert 'id="ledgerfold"' not in html
    # an empty state (icon, title, one action), not a sentence
    empty = html.split('id="st-ledger-empty"', 1)[1].split("</div></div>", 1)[0]
    # a cleared ledger beside workroots on disk says so (ST-12)
    assert "No runs in the ledger" in empty and 'href="/forecast"' in empty


# ------------------------------- the runner computer's student experiments

PILOT = {"model": "sihrs", "season": "2024-25", "size": "pilot"}
SMOKE = {"model": "sihrs", "season": "2024-25"}
NATG = {"model": "sihrs-natg", "season": "2024-25"}
#: a pid no process has (above every pid_max)
DEAD = 2_147_483_646


@pytest.fixture()
def runner_pc(state, students, monkeypatch):
    """The runner computer's main console (its Sandbox not a student's),
    the runner running: alice's folder holds a queued pilot and a smoke
    done with both weeks stored, bob's a smoke never started, and alice's
    library one file. {"alice", "bob": Sandbox folders, "pilot", "smoke",
    "idle": experiment folders, "students": STUDENTS}."""
    from app.core import retro
    from app.core import runner
    from app.core.engines import pf
    calendar(monkeypatch)
    monkeypatch.setattr(runner, "_free", lambda: 412 * runner.GiB)
    monkeypatch.setattr(pf, "DEFAULT_SHARD_WIDTH", 16)
    alice, bob = student(students, "alice"), student(students, "bob")
    smoke = experiment(alice, SMOKE, weeks=["2024-12-28", "2025-01-11"],
                       meta={"started_utc": 1_790_000_000.0})
    for w in ("2024-12-28", "2025-01-11"):
        (smoke / "weeks" / w).mkdir(parents=True)
        (smoke / "weeks" / w / retro.QUANTILES_NAME).write_text(
            "{}", encoding="utf-8")
        (smoke / "weeks" / w / "samples.dropped.json").write_text(
            "{}", encoding="utf-8")
    pilot = experiment(alice, PILOT, queued=True)
    idle = experiment(bob, NATG)
    (alice / "library" / "beta" / "1").mkdir(parents=True)
    (alice / "library" / "beta" / "1" / "model.bngl").write_text(
        "# beta\n", encoding="utf-8")
    runner_state(students)
    ui_shared._invalidate_scans()
    return {"alice": alice, "bob": bob, "pilot": pilot, "smoke": smoke,
            "idle": idle, "students": students}


def _stu(html: str) -> str:
    """The Student experiments section of the Storage page."""
    return html.split('aria-labelledby="h-st-stu"', 1)[1].split(
        "</section>", 1)[0]


def _row(section: str, ident: str) -> str:
    return section.split(f"<strong>{ident}</strong>", 1)[1].split(
        "</div>", 1)[0]


def _delete(ident: str, confirm=None):
    ui_state._status.pop("flash", None)
    return client.post("/storage/delete",
                       data={"kind": "experiment", "ident": ident,
                             "confirm": ident if confirm is None else confirm},
                       follow_redirects=False)


def test_the_runner_computer_lists_student_experiments_by_folder(state,
                                                                 runner_pc):
    from app.core import retro
    from app.core import sandbox as sb
    inv = ui_storage._storage_inventory()
    rows = inv["students"]["rows"]
    pid, sid = runner_pc["pilot"].name, runner_pc["smoke"].name
    iid = runner_pc["idle"].name
    # by folder, newest first within each (the pilot, never started, by
    # its experiment.json, newer than the smoke's start)
    assert [r["ident"] for r in rows] == [f"alice/{pid}", f"alice/{sid}",
                                          f"bob/{iid}"]
    assert [r["badge"] for r in rows] == [
        ("pending", "queued · 1st in line"), ("ok", "done"),
        ("neutral", "not started")]
    # outside the total: the total is the managed categories' alone
    expect = sum(retro.dir_size(state["root"] / "workroots" / rid)
                 for rid in state["rids"].values())
    expect += retro.dir_size(state["retro_root"] / SEASON)
    expect += retro.dir_size(
        state["retro_root"] / f"{SEASON}__archived_{ARCH_STAMP}")
    expect += retro.dir_size(state["root"] / "archive" / "2098-01-03")
    assert inv["total_bytes"] == expect
    html = client.get("/storage").text
    fold = html.split('id="storagefold">', 1)[1].split("</details>", 1)[0]
    assert fold.index('id="h-st-protected"') < fold.index('id="h-st-stu"')
    stu = _stu(fold)
    assert ">Student experiments</h3>" in stu
    assert '<span class="uk-badge-t">3 entries</span>' in stu
    assert '<span class="uk-tag">not in the total</span>' in stu
    assert ('<ul class="uk-meta"><li>The runner: idle</li><li>412.0 GB free '
            '· FluBNF keeps 20.0 GB free</li></ul>') in stu
    assert 'id="st-stu-down"' not in stu
    # the queued row: when it was queued, about how long it runs, its disk
    row = _row(stu, f"alice/{pid}")
    mtime = os.lstat(runner_pc["pilot"] / "QUEUED").st_mtime
    q = rows[0]["queued"]
    for part in (time.strftime("queued %m-%d %H:%M", time.localtime(mtime)),
                 "runs " + sb.eta_words(q["seconds"], q["seconds"]),
                 f"needs about {retro.human_bytes(q['peak_bytes'])}"):
        assert f"<li>{part}</li>" in row, part
    # each row has its Delete, confirmed by its ident
    for r in rows:
        row = _row(stu, r["ident"])
        assert '<input type="hidden" name="kind" value="experiment">' in row
        assert f'<input type="hidden" name="ident" value="{r["ident"]}">' \
            in row
        assert "data-del-storage" in row
        assert f"Its model stays in {r['folder']}&#39;s library." in row


def test_a_student_experiment_is_deleted_with_its_confirmation(state,
                                                               runner_pc):
    from app.core import runner
    pilot, smoke = runner_pc["pilot"], runner_pc["smoke"]
    ident = f"alice/{pilot.name}"
    _delete(ident, confirm="yes")
    assert pilot.is_dir() and "not confirmed" in _flash()
    # a queued one: deleting it takes it out of the queue
    assert [j["id"] for j in runner.queue()] == [pilot.name]
    _delete(ident)
    assert not pilot.exists() and runner.queue() == []
    assert _flash().startswith(f"Deleted the student experiment {ident}: ")
    assert _flash().endswith(" freed.")
    assert ui_state._status.get("flash_kind") == "ok"
    _delete(f"alice/{smoke.name}")
    assert not smoke.exists()
    # the library, and every other folder, stay
    assert (runner_pc["alice"] / "library" / "beta" / "1"
            / "model.bngl").is_file()
    assert runner_pc["idle"].is_dir()


def test_a_student_experiment_is_kept_while_the_runner_has_it(state,
                                                              runner_pc):
    from app.core import retro
    students, smoke = runner_pc["students"], runner_pc["smoke"]
    ident = f"alice/{smoke.name}"
    why = (f"{ident} is replaying on the runner; stop it from its page in "
           "alice's console first.")
    job = {"kind": "run", "folder": "alice", "id": smoke.name,
           "size": "smoke", "pid": os.getpid(), "keep_bytes": 0,
           "started_utc": "2026-11-02T10:24:02Z"}
    runner_state(students, job=job)
    row = _row(_stu(client.get("/storage").text), ident)
    assert "data-del-storage" not in row and " disabled " in row
    page = client.get("/storage").text            # why: the one notice
    assert why.replace("'", "&#39;") in page.split('id="st-busy"', 1)[1]
    _delete(ident)
    assert smoke.is_dir() and _flash() == f"Not deleted: {why}"
    # its record under way, the runner's job another
    runner_state(students)
    now = time.time()
    retro.write_meta(smoke, {**retro.read_meta(smoke), "status": "running",
                             "pid": os.getpid(), "heartbeat_utc": now,
                             "segment_start_utc": now})
    _delete(ident)
    assert smoke.is_dir() and _flash() == f"Not deleted: {why}"
    retro.write_meta(smoke, {**retro.read_meta(smoke), "status": "done"})
    # a tidy of it: kept until it ends
    runner_state(students, job={**job, "kind": "tidy"})
    _delete(ident)
    assert smoke.is_dir() and "is tidying" in _flash()
    # a runner that is not running holds nothing, and says so
    runner_state(students, job=job, pid=DEAD)
    stu = _stu(client.get("/storage").text)
    assert ("<strong>The runner is not running.</strong> Its last heartbeat "
            "was at ") in stu
    assert "Queued experiments wait until it is started" in stu
    _delete(ident)
    assert not smoke.exists()


def test_student_experiment_idents_never_leave_their_folder(state,
                                                            runner_pc):
    eid = runner_pc["smoke"].name
    for ident in ("alice/../x", f"../alice/{eid}", f"alice:{eid}", "alice/",
                  f"/{eid}", f"alice/{eid}/weeks", f"zed/{eid}", "alice",
                  f"alice/../bob/{runner_pc['idle'].name}"):
        _delete(ident)
        assert _flash() == "Not deleted: unrecognized student experiment.", \
            ident
    assert runner_pc["smoke"].is_dir() and runner_pc["idle"].is_dir()


@LINKS
def test_a_linked_student_experiment_is_refused(state, runner_pc):
    bob_idle = runner_pc["idle"]
    link = runner_pc["alice"] / "experiments" / bob_idle.name
    link.symlink_to(bob_idle, target_is_directory=True)
    ui_shared._invalidate_scans()
    stu = _stu(client.get("/storage").text)
    assert f"<strong>alice/{bob_idle.name}</strong>" not in stu
    _delete(f"alice/{bob_idle.name}")
    assert _flash() == (f"Not deleted: experiments/{bob_idle.name} is a "
                        "link, and the runner follows no link in a student "
                        "folder.")
    assert link.is_symlink() and bob_idle.is_dir()


def test_a_student_console_and_a_laptop_see_the_page_as_before(
        state, students, monkeypatch):
    from app.core import runner
    from app.core import sandbox as sb
    # a laptop: no runner here, no section, a crafted delete refused
    (students / runner.STATE_NAME).rmdir()
    assert ui_storage._storage_inventory()["students"] is None
    laptop = client.get("/storage").text
    assert "h-st-stu" not in laptop and "Student experiments" not in laptop
    alice = student(students, "alice")
    eid = experiment(alice, SMOKE).name
    _delete(f"alice/{eid}")
    assert _flash() == "Not deleted: unrecognized storage kind."
    # a student's console on the runner computer: as with no runner
    (students / runner.STATE_NAME).mkdir()
    monkeypatch.setattr(sb, "SANDBOX", alice)
    monkeypatch.setattr(sb, "MODELS", alice / "models")
    monkeypatch.setattr(sb, "RUNS", alice / "runs")
    runner_state(students)
    ui_shared._invalidate_scans()
    assert runner.folder_of(sb.SANDBOX) == "alice"
    assert ui_storage._storage_inventory()["students"] is None
    there = client.get("/storage").text
    _delete(f"alice/{eid}")
    assert _flash() == "Not deleted: unrecognized storage kind."
    assert (alice / "experiments" / eid).is_dir()
    # a clone in ~/Students the runner does not take (a name folders()
    # refuses): still a student's console, never the main one
    jane = students / "jane.doe" / "sandbox"
    jane.mkdir(parents=True)
    monkeypatch.setattr(sb, "SANDBOX", jane)
    monkeypatch.setattr(sb, "MODELS", jane / "models")
    monkeypatch.setattr(sb, "RUNS", jane / "runs")
    assert runner.folder_of(sb.SANDBOX) is None
    assert ui_storage._storage_inventory()["students"] is None
    _delete(f"alice/{eid}")
    assert _flash() == "Not deleted: unrecognized storage kind."
    assert (alice / "experiments" / eid).is_dir()
    monkeypatch.setattr(sb, "SANDBOX", alice)
    monkeypatch.setattr(sb, "MODELS", alice / "models")
    monkeypatch.setattr(sb, "RUNS", alice / "runs")
    os.unlink(students / runner.STATE_NAME / runner.STATE_FILE)
    (students / runner.STATE_NAME).rmdir()
    ui_shared._invalidate_scans()
    assert there == client.get("/storage").text
    assert "h-st-stu" not in there
