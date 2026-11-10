"""The state folder, what Storage protects and what downloads serve (bug
hunt 2026-10-25, G21).

  * FLUBNF_STATE_DIR moves the retro trees (replays, season reports, the
    sealed records) and engine_update.json with the rest of the state
    folder, so a fresh state folder starts empty.
  * Delete, Delete all and Reclaim refuse the same trees: the sealed
    records (the production reseal too), the hub clone and
    FLUBNF_PROTECT_ROOTS. A protected workroot's row has no Delete.
    Retrospective's two deletes (an archived run's Delete, the Run form's
    discard) refuse them too, and no refusal claims which record it is.
  * Reclaim keeps the cell trees of a run with fit failures, as the
    pipeline does.
  * /output/download serves only the CSVs the console links: a model's
    submission file or a dataset run's export.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                               # noqa: E402
from app.core import reclaim                                    # noqa: E402
from app.ui import server as srv                               # noqa: E402
from app.ui import shared as ui_shared                         # noqa: E402
from app.ui import state as ui_state                          # noqa: E402
from app.ui.routes import storage as ui_storage                # noqa: E402

REPO = Path(__file__).resolve().parents[2]
client = TestClient(srv.app)
GH = "NAU_PyBNF-GroundHogCGR"


# --------------------------------- WI-04: the state folder holds the trees

def test_the_retro_trees_and_engine_update_follow_the_state_folder(tmp_path):
    env = dict(os.environ, FLUBNF_STATE_DIR=str(tmp_path))
    out = subprocess.run(
        [sys.executable, "-c",
         "from app.ui import retro_seasons as r; "
         "from app.core import engine_update as e; "
         "print(r.RETRO_ROOT); print(r.RETRO_RESEAL); print(r.RETRO_SEAL); "
         "print(e.STATE_FILE)"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    paths = [Path(x) for x in out.stdout.split()]
    assert paths == [tmp_path / "retro", tmp_path / "retro_reseal",
                     tmp_path / "retro_seal", tmp_path / "engine_update.json"]


# ------------------------------------------- ST-06: one barrier for both

@pytest.fixture()
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    monkeypatch.setattr(reclaim, "APP_STATE", tmp_path)
    from app.core import datasets as datasets_mod
    monkeypatch.setattr(datasets_mod, "ROOT", tmp_path / "datasets")
    from app.ui import retro_seasons
    monkeypatch.setattr(retro_seasons, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(retro_seasons, "RETRO_RESEAL",
                        tmp_path / "retro_reseal")
    monkeypatch.setattr(retro_seasons, "RETRO_SEAL", tmp_path / "retro_seal")
    import flubnf.settings as settings_mod
    monkeypatch.setattr(settings_mod, "HUB", tmp_path / "hub")
    from app.ui import state as ui_state
    for k in ("running", "workroot", "flash", "flash_kind", "flash_detail"):
        monkeypatch.setitem(ui_state._status, k, None)
    ui_shared._invalidate_scans()
    yield tmp_path
    ui_shared._invalidate_scans()


def _workroot(root: Path, rid: str) -> Path:
    w = root / "workroots" / rid
    w.mkdir(parents=True)
    (w / "results.json").write_text("{}")
    return w


def test_delete_and_reclaim_refuse_the_same_trees(state, monkeypatch):
    kept = _workroot(state, "20261025T192005-13482c")
    other = _workroot(state, "20261025T193000-aaaaaa")
    monkeypatch.setenv("FLUBNF_PROTECT_ROOTS", str(kept))
    ui_shared._invalidate_scans()
    assert reclaim.is_protected(kept) and ui_storage._storage_protected(kept)
    # its row wears the lock and has no Delete; Delete all leaves it out
    page = client.get("/storage").text
    row = page.split(f'data-wid="{kept.name}"', 1)[1].split("</div>", 1)[0]
    assert "protected" in row and "/storage/delete" not in row
    assert [w["id"] for w in ui_storage._clearable_workroots()] == \
        [other.name]
    # a crafted delete is refused, and the folder stays
    client.post("/storage/delete", data={"kind": "workroot",
                                         "ident": kept.name,
                                         "confirm": kept.name})
    assert kept.is_dir()
    # the production reseal: Storage refused it, and now reclaim does too
    reseal = state / "retro_reseal" / "2023-24"
    reseal.mkdir(parents=True)
    assert ui_storage._storage_protected(reseal)
    assert reclaim.is_protected(reseal)


def test_retrospective_deletes_refuse_a_protected_season_and_archive(
        state, monkeypatch, request):
    """Review S3 (ST-06): an archived run's Delete and the Run form's
    discard went to delete_tree with no protection check. A protected
    archive or season is now refused in plain words and stays whole; the
    same posts go ahead once nothing protects them."""
    from app.core import retro
    from app.ui import retro_seasons
    from app.ui.routes import retro as ui_retro
    from test_retro_archive import (SEASON, STAMP, _roots, _season_tree,
                                    _tree_snapshot)
    # the season stores this test's claim changes, put back after it
    kept = [(d, type(d)(d)) for d in (retro_seasons._retro_status,
                                      retro_seasons._retro_claim_at,
                                      retro_seasons._retro_stop)]
    request.addfinalizer(lambda: [(d.clear(), d.update(v)) for d, v in kept])
    rr = _roots(state, monkeypatch)
    _season_tree(rr, SEASON)
    retro.archive_run(rr, SEASON, stamp=STAMP)
    arch = rr / f"{SEASON}__archived_{STAMP}"
    live = _season_tree(rr, SEASON)
    live_before, arch_before = _tree_snapshot(live), _tree_snapshot(arch)
    started = []
    monkeypatch.setattr(ui_retro, "_retro_bg",
                        lambda *a, **k: started.append(a[0]))
    discard = {"season": SEASON, "mode": "discard", "confirm": SEASON,
               "engine": "analogue", "locations": "panel6",
               "knob.groundhog.zero_anchor": "abstain"}

    def flash():
        f = ui_state._status.get("flash") or ""
        ui_state._status.pop("flash", None)
        return f
    # the archive protected: its Delete is refused, nothing goes
    monkeypatch.setenv("FLUBNF_PROTECT_ROOTS", str(arch))
    client.post(f"/retro/{SEASON}/archive/{STAMP}/delete",
                data={"confirm": SEASON}, follow_redirects=False)
    said = flash()
    assert said.startswith(f"Not deleted: the archived {SEASON} run from ")
    assert said.endswith(" is in a protected folder, which the console "
                         "never deletes."), said
    assert _tree_snapshot(arch) == arch_before
    # the season protected (in another spelling): the discard is refused
    # before anything is moved or started
    monkeypatch.setenv("FLUBNF_PROTECT_ROOTS", " " + str(live))
    client.post("/retro/run", data=discard, follow_redirects=False)
    assert flash() == (f"Not started: the {SEASON} results are in a "
                       "protected folder, which the console never deletes.")
    assert ui_state._status.get("flash_detail") == "Nothing was deleted."
    assert started == [] and _tree_snapshot(live) == live_before
    assert _tree_snapshot(arch) == arch_before
    # Storage says the same of a protected season, naming no record
    client.post("/storage/delete", data={"kind": "retro-season",
                                         "ident": SEASON,
                                         "confirm": SEASON},
                follow_redirects=False)
    assert flash() == ("Not deleted: that folder is protected; the console "
                       "never deletes it.")
    assert _tree_snapshot(live) == live_before
    # nothing protected: both posts go ahead (the barrier stopped them)
    monkeypatch.delenv("FLUBNF_PROTECT_ROOTS")
    client.post(f"/retro/{SEASON}/archive/{STAMP}/delete",
                data={"confirm": SEASON}, follow_redirects=False)
    assert flash().startswith(f"Deleted the archived {SEASON} run")
    assert not arch.exists()
    client.post("/retro/run", data=discard, follow_redirects=False)
    assert started == [SEASON] and not (live / "weeks").exists()


# ---------------------------- ST-07: a failed fit's trees are its evidence

def test_reclaim_keeps_the_cell_trees_of_a_run_with_fit_failures(tmp_path):
    w = tmp_path / "20261001T100000-aaaaaa"
    (w / "Arizona_r0").mkdir(parents=True)
    (w / "Arizona_r0" / "pf.log").write_text("x")
    (w / "results.json").write_text("{}")
    (w / "pf_status.json").write_text(json.dumps(
        {"Arizona_r0": "filter failed: weights collapsed"}))
    assert reclaim.workroot_intermediates(w) == []
    assert reclaim.prune_workroot(w) == 0 and (w / "Arizona_r0").is_dir()
    # every cell ok: the trees are intermediates again
    (w / "pf_status.json").write_text(json.dumps({"Arizona_r0": "ok"}))
    assert [p.name for p in reclaim.workroot_intermediates(w)] == \
        ["Arizona_r0"]
    # a research run's pf2s/ records its own cells' failures
    (w / "pf2s").mkdir()
    (w / "pf2s" / "pf_status.json").write_text(json.dumps(
        {"Arizona_r0": "filter failed"}))
    assert reclaim.workroot_intermediates(w) == []


# --------------------------- OU-15: downloads serve the linked CSVs only

def test_download_serves_only_submission_and_export_csvs(state):
    w = _workroot(state, "20261025T192005-13482c")
    sub = w / "submission" / GH / f"2026-10-24-{GH}.csv"
    exp = w / "export" / "FluBNF-Groundhog" / "2026-10-24-FluBNF-Groundhog.csv"
    for f in (sub, exp):
        f.parent.mkdir(parents=True)
        f.write_text("reference_date,target\n")
    (state / "ledger.sqlite").write_bytes(b"SQLite format 3\x00")
    (state / "last_form.json").write_text("{}")
    (w / "stray.csv").write_text("x\n")
    for f in (sub, exp):
        r = client.get("/output/download", params={"path": str(f)})
        assert r.status_code == 200, f
    for f in (state / "ledger.sqlite", state / "last_form.json",
              w / "results.json", w / "stray.csv"):
        r = client.get("/output/download", params={"path": str(f)})
        assert r.status_code == 404, f
        assert "attachment" not in r.headers.get("content-disposition", "")
