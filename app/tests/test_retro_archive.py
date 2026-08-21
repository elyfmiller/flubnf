"""Start over on a season that already has results.

Resumability protects an overnight replay; it must not become the only
option. This file covers the whole set of choices and the rules that keep
them safe:

  * the start-over prompt appears only when completed weeks exist, and a
    complete season is offered no Resume;
  * archiving is a MOVE that preserves every file, and an archived run stays
    fully usable -- the season page, the playback API, and the report builder
    all accept the archived run identifier;
  * discarding needs a second confirmation and removes only its target;
  * deleting an archive never touches the live season;
  * nothing destructive is permitted while a season is running or paused,
    and /api/busy sees a worker even when only its run record is on disk.
"""
import json
import sys
import time
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import playback, report_season, retro        # noqa: E402
from app.ui import server as srv                           # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL      # noqa: E402

client = TestClient(srv.app)

SEASON = "2098-99"
OTHER = "2097-98"
W1, W2 = "2098-01-03", "2098-01-10"
VINTAGES = [W1, W2, "2098-01-17"]
N2F = {"Ohio": "39", "Utah": "49"}
STAMP = "20980204T101500Z"


@pytest.fixture(autouse=True)
def _isolated_status():
    """Snapshot and restore the module-level status stores, so a mocked
    running season never leaks into the next test."""
    status_before = dict(srv._status)
    retro_before = dict(srv._retro_status)
    stop_before = set(srv._retro_stop)
    yield
    srv._status.clear(); srv._status.update(status_before)
    srv._retro_status.clear(); srv._retro_status.update(retro_before)
    srv._retro_stop.clear(); srv._retro_stop.update(stop_before)


# ------------------------------------------------------------------ fixtures

def _write_week(root: Path, asof: str, truth=None, n2f=None) -> Path:
    """One completed week, in the shape playback and scoring read."""
    wd = root / "weeks" / asof
    wd.mkdir(parents=True, exist_ok=True)
    if truth is None:
        (wd / "samples.json").write_text(json.dumps({"asof": asof, "pf": {}}))
        return wd
    pf, an = {}, {}
    for loc, fips in (n2f or N2F).items():
        pf[loc] = {str(h): [truth[(fips, pd.Timestamp(asof)
                                   + pd.Timedelta(days=7 * h))] + d
                            for d in (-1.0, 0.0, 1.0)] for h in range(5)}
        an[loc] = {str(h): {str(L): truth[(fips, pd.Timestamp(asof)
                                           + pd.Timedelta(days=7 * h))]
                            + (L - 0.5) * 10 for L in QL}
                   for h in range(1, 5)}
    (wd / "samples.json").write_text(
        json.dumps({"asof": asof, "pf": pf, "analogue": an}))
    return wd


def _season_tree(retro_root: Path, season: str, weeks=(W1, W2),
                 meta=True, truth=None) -> Path:
    """A season root with completed weeks, a run record, scores, and a
    playback cache -- one of everything an archive must carry."""
    root = retro_root / season
    for w in weeks:
        _write_week(root, w, truth)
    (root / "playback_cache").mkdir(parents=True, exist_ok=True)
    (root / "playback_cache" / "stats_cells.json").write_text('{"weeks":{}}')
    # scores.json in the exact shape score_season writes: pooled ensemble
    # relWIS works out to 0.500, the headline the index must show
    rows = [{"model": "ensemble", "location": "Ohio", "fips": "39",
             "asof": w, "horizon": 0, "wis": 1.0 + i * 2.0,
             "base_wis": 2.0 + i * 4.0, "rel": 0.5}
            for i, w in enumerate(weeks)]
    pd.DataFrame(rows).to_json(root / "scores.json")
    (root / "failures.log").write_text("none\n")
    if meta:
        retro.write_meta(root, {"season": season, "status": "done",
                                "total_weeks": len(VINTAGES),
                                "started_utc": 1.0e9,
                                "finished_utc": 1.0e9 + 3661.0,
                                "elapsed_s": 3661.0,
                                "segment_start_utc": None,
                                "heartbeat_utc": 1.0e9 + 3661.0,
                                "weeks_completed": len(weeks),
                                "week_seconds": {w: 100.0 for w in weeks}})
    return root


def _tree_snapshot(root: Path) -> dict:
    """Every file under a tree, by relative path, with its bytes."""
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _roots(tmp_path, monkeypatch):
    """Point the app at an empty retro root and a season list it controls."""
    rr = tmp_path / "retro"
    rr.mkdir()
    monkeypatch.setattr(srv, "RETRO_ROOT", rr)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(retro, "available_seasons", lambda: [SEASON, OTHER])
    monkeypatch.setattr(retro, "season_vintages", lambda s: list(VINTAGES))
    monkeypatch.setattr(srv, "_retro_bg", lambda *a, **k: None)
    srv._retro_status.clear()
    srv._retro_stop.clear()
    return rr


def _truth_map():
    t = {}
    for fips, base in (("39", 100.0), ("49", 50.0)):
        for k in range(-8, 8):
            t[(fips, pd.Timestamp(W1) + pd.Timedelta(days=7 * k))] = base + k
    return t, dict(N2F)


def _synthetic_data(monkeypatch, tmp_path):
    """Truth, the baseline denominator, and an empty hub, so playback and
    the report builder touch no real data."""
    truth, n2f = _truth_map()
    monkeypatch.setattr(playback, "load_truth", lambda: (truth, n2f))
    monkeypatch.setattr(playback, "_baseline_cells",
                        lambda asof, fips_set, tr: {(f, asof, h): 2.0
                                                    for f in fips_set
                                                    for h in range(4)})
    monkeypatch.setattr(playback, "HUB", tmp_path / "hub")
    monkeypatch.setattr(report_season, "_plotlyjs", lambda: "/* stub */")
    return truth


# -------------------------------------------------- core: the move itself

def test_archive_run_moves_the_tree_and_preserves_every_file(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    root = _season_tree(rr, SEASON)
    before = _tree_snapshot(root)
    assert "scores.json" in before and "run_meta.json" in before

    dst = retro.archive_run(rr, SEASON, stamp=STAMP)

    assert dst == rr / f"{SEASON}__archived_{STAMP}"
    assert not root.exists()                       # a move, not a copy
    assert _tree_snapshot(dst) == before           # byte for byte
    assert retro.archive_stamp_of(dst.name, SEASON) == STAMP
    assert [p.name for p in retro.list_archive_dirs(rr, SEASON)] == [dst.name]


def test_archive_run_on_a_missing_season_raises_and_changes_nothing(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    with pytest.raises(FileNotFoundError):
        retro.archive_run(rr, SEASON, stamp=STAMP)
    assert list(rr.iterdir()) == []


def test_archive_failure_leaves_the_original_intact(tmp_path, monkeypatch):
    """The move is atomic; a failure must be loud and must not consume the
    season it was asked to protect."""
    rr = tmp_path / "retro"; rr.mkdir()
    root = _season_tree(rr, SEASON)
    before = _tree_snapshot(root)

    def boom(src, dst):
        raise OSError("no space left on device")

    monkeypatch.setattr(retro.os, "rename", boom)
    with pytest.raises(OSError):
        retro.archive_run(rr, SEASON, stamp=STAMP)
    assert _tree_snapshot(root) == before
    assert retro.list_archive_dirs(rr, SEASON) == []


def test_two_archives_in_one_second_get_distinct_directories(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    _season_tree(rr, SEASON, weeks=(W1,))
    a = retro.archive_run(rr, SEASON, stamp=STAMP)
    _season_tree(rr, SEASON, weeks=(W2,))
    b = retro.archive_run(rr, SEASON, stamp=STAMP)
    assert a != b and a.is_dir() and b.is_dir()
    assert len(retro.list_archive_dirs(rr, SEASON)) == 2


def test_delete_tree_of_a_symlinked_season_removes_only_the_link(tmp_path):
    """A season parked on another volume is reached by symlink. Removing it
    must remove the link, never walk into data the app does not own."""
    rr = tmp_path / "retro"; rr.mkdir()
    real = tmp_path / "elsewhere"
    real.mkdir()
    (real / "keep.txt").write_text("precious")
    link = rr / SEASON
    link.symlink_to(real)

    retro.delete_tree(link)
    assert not link.exists() and not link.is_symlink()
    assert (real / "keep.txt").read_text() == "precious"


def test_archive_identifiers_that_could_escape_the_root_are_refused():
    assert retro.valid_stamp(STAMP)
    assert retro.valid_stamp(STAMP + "-2")
    for bad in ("", "..", "../../etc", "2098", "latest", STAMP + "/x",
                STAMP + "-", "20980204T101500"):
        assert not retro.valid_stamp(bad), bad
        assert not srv._valid_archive(bad), bad


def test_run_summary_reports_weeks_wall_time_and_headline(tmp_path):
    rr = tmp_path / "retro"; rr.mkdir()
    root = _season_tree(rr, SEASON)
    s = retro.run_summary(root)
    assert s["weeks"] == 2
    assert s["elapsed_s"] == pytest.approx(3661.0)
    assert s["scored"] is True
    assert s["headline_rel"] == pytest.approx(4.0 / 8.0)
    assert retro.stamp_human(STAMP) == "2098-02-04 10:15 UTC"


# ------------------------------------------- the prompt: only when it earns it

def test_startover_says_nothing_to_lose_on_an_empty_season(tmp_path,
                                                           monkeypatch):
    _roots(tmp_path, monkeypatch)
    b = client.get(f"/api/retro/startover?season={SEASON}").json()
    assert b["weeks"] == 0            # the client proceeds with no prompt
    assert b["complete"] is False
    assert b["archives"] == 0


def test_startover_states_plainly_what_exists(tmp_path, monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    _season_tree(rr, SEASON)
    b = client.get(f"/api/retro/startover?season={SEASON}").json()
    assert b["season"] == SEASON
    assert b["weeks"] == 2 and b["total"] == 3
    assert b["complete"] is False               # so Resume is still offered
    assert b["elapsed_hms"] == "1:01:01"        # h:mm:ss, as the spec words it
    assert b["finished"].endswith("UTC") and b["finished"].startswith("2001-")
    assert b["active"] is False


def test_a_complete_season_offers_no_resume(tmp_path, monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    _season_tree(rr, SEASON, weeks=tuple(VINTAGES))
    b = client.get(f"/api/retro/startover?season={SEASON}").json()
    assert b["weeks"] == 3 and b["total"] == 3
    assert b["complete"] is True
    # and the modal hides the Resume choice on exactly that flag
    html = client.get("/retro").text
    assert "so.resume.hidden=!!info.complete" in html


def test_startover_prompts_for_a_sealed_season(tmp_path, monkeypatch):
    """A season whose page shows a sealed validation run reads complete on
    its card, yet its live tree is empty: without this, Run started a
    multi-hour replay instantly, violating the stated prompt contract. The
    API must report the seal so the client can ask first; the seal itself
    is never a start-over target."""
    _roots(tmp_path, monkeypatch)
    seal = tmp_path / "seal"
    monkeypatch.setattr(srv, "RETRO_SEAL", seal)
    for w in (W1, W2):
        _write_week(seal / SEASON, w)
    b = client.get(f"/api/retro/startover?season={SEASON}").json()
    assert b["sealed"] is True
    assert b["weeks"] == 2 and b["total"] == 3   # the SEAL's weeks, named
    assert b["active"] is False


def test_startover_prefers_the_live_tree_over_the_seal(tmp_path,
                                                       monkeypatch):
    """Once the live tree holds weeks, the ordinary resume, archive, and
    discard choices apply to it, and the seal stays out of the answer."""
    rr = _roots(tmp_path, monkeypatch)
    seal = tmp_path / "seal"
    monkeypatch.setattr(srv, "RETRO_SEAL", seal)
    for w in VINTAGES:
        _write_week(seal / SEASON, w)
    _season_tree(rr, SEASON)                      # two live weeks
    b = client.get(f"/api/retro/startover?season={SEASON}").json()
    assert b["sealed"] is False
    assert b["weeks"] == 2                        # the LIVE tree's weeks


def test_base_template_carries_the_sealed_prompt_branch(tmp_path,
                                                        monkeypatch):
    _roots(tmp_path, monkeypatch)
    html = client.get("/retro").text
    assert "info.sealed" in html                 # the branch exists
    assert "sealed validation run" in html       # and names the situation
    assert "Run a fresh replay" in html          # one clear, safe confirm
    # the confirm submits mode=resume: the live tree is empty, so a resume
    # IS a fresh start, and no destructive mode can reach the form here
    seg = html.split("info.sealed")[1].split("so.title.textContent")[0]
    assert "f.mode.value='resume'" in seg


def test_startover_counts_archives_and_refuses_a_bad_season_name(tmp_path,
                                                                 monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    _season_tree(rr, SEASON)
    retro.archive_run(rr, SEASON, stamp=STAMP)
    _season_tree(rr, SEASON, weeks=(W1,))
    assert client.get(f"/api/retro/startover?season={SEASON}"
                      ).json()["archives"] == 1
    bad = client.get("/api/retro/startover?season=../../etc").json()
    assert bad["weeks"] == 0 and bad["total"] == 0


# ------------------------------------------------------------ prompt markup

def test_start_over_modal_offers_the_four_choices(tmp_path, monkeypatch):
    _roots(tmp_path, monkeypatch)
    html = client.get("/retro").text
    assert 'id="startover-modal"' in html
    for bid in ("so-cancel", "so-resume", "so-discard", "so-archive"):
        assert f'id="{bid}"' in html, bid
    # archive is the emphasized default; discard is quiet
    assert '<button type="button" class="gold" id="so-archive">' in html
    assert '<button type="button" class="quiet" id="so-discard">' in html
    # discard swaps in a second confirmation before the form may carry it
    assert 'id="so-confirm"' in html
    assert "Delete permanently" in html
    assert "/api/retro/startover?season=" in html


def test_run_button_asks_first_and_the_form_can_carry_the_answer(tmp_path,
                                                                 monkeypatch):
    _roots(tmp_path, monkeypatch)
    html = client.get("/retro").text
    assert 'data-startover="1"' in html
    form = html.split('action="/retro/run"')[1].split("</form>")[0]
    assert '<input type="hidden" name="mode" value="resume">' in form
    assert '<input type="hidden" name="confirm" value="">' in form
    assert 'data-guard="retro-run"' in form      # the older guard still stands


# -------------------------------------------------------------- the run modes

def test_resume_keeps_the_existing_weeks(tmp_path, monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    root = _season_tree(rr, SEASON)
    before = _tree_snapshot(root)
    r = client.post("/retro/run", data={"season": SEASON, "mode": "resume"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert _tree_snapshot(root) == before
    assert retro.list_archive_dirs(rr, SEASON) == []


def test_archive_and_start_fresh_moves_the_tree_and_starts_clean(tmp_path,
                                                                 monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    root = _season_tree(rr, SEASON)
    before = _tree_snapshot(root)
    started = []
    monkeypatch.setattr(srv, "_retro_bg",
                        lambda *a, **k: started.append(a[0]))

    r = client.post("/retro/run", data={"season": SEASON, "mode": "archive"},
                    follow_redirects=False)
    assert r.status_code == 303
    archives = retro.list_archive_dirs(rr, SEASON)
    assert len(archives) == 1
    assert _tree_snapshot(archives[0]) == before      # nothing lost
    assert not (root / "weeks").exists()              # the replay starts clean
    assert started == [SEASON]                        # and it does start
    assert "Archived" in srv._status.get("flash", "")


def test_discard_without_the_second_confirmation_changes_nothing(tmp_path,
                                                                 monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    root = _season_tree(rr, SEASON)
    before = _tree_snapshot(root)
    started = []
    monkeypatch.setattr(srv, "_retro_bg",
                        lambda *a, **k: started.append(a[0]))

    r = client.post("/retro/run", data={"season": SEASON, "mode": "discard"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert _tree_snapshot(root) == before
    assert started == []                              # nor was a run started
    assert "not confirmed" in srv._status.get("flash", "")

    # a confirmation naming a DIFFERENT season is no confirmation at all
    client.post("/retro/run", data={"season": SEASON, "mode": "discard",
                                    "confirm": OTHER}, follow_redirects=False)
    assert _tree_snapshot(root) == before
    assert started == []


def test_discard_with_confirmation_removes_only_its_target(tmp_path,
                                                           monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    root = _season_tree(rr, SEASON)
    other = _season_tree(rr, OTHER)
    other_before = _tree_snapshot(other)
    retro.archive_run(rr, SEASON, stamp=STAMP)        # an earlier archive
    _season_tree(rr, SEASON)                          # the live tree again
    arch = rr / f"{SEASON}__archived_{STAMP}"
    arch_before = _tree_snapshot(arch)

    r = client.post("/retro/run", data={"season": SEASON, "mode": "discard",
                                        "confirm": SEASON},
                    follow_redirects=False)
    assert r.status_code == 303
    assert not (root / "weeks").exists()              # the target is gone
    assert _tree_snapshot(arch) == arch_before        # the archive is not
    assert _tree_snapshot(other) == other_before      # nor another season


def test_an_unknown_mode_starts_nothing_and_destroys_nothing(tmp_path,
                                                             monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    root = _season_tree(rr, SEASON)
    before = _tree_snapshot(root)
    started = []
    monkeypatch.setattr(srv, "_retro_bg",
                        lambda *a, **k: started.append(a[0]))
    r = client.post("/retro/run", data={"season": SEASON, "mode": "nuke"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert _tree_snapshot(root) == before and started == []


# ------------------------------------------------------------- safety rules

@pytest.mark.parametrize("status", ["running", "paused", "stopping"])
def test_nothing_destructive_is_permitted_while_a_season_lives(status,
                                                               tmp_path,
                                                               monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    root = _season_tree(rr, SEASON)
    retro.archive_run(rr, SEASON, stamp=STAMP)
    _season_tree(rr, SEASON)
    arch = rr / f"{SEASON}__archived_{STAMP}"
    live_before, arch_before = _tree_snapshot(root), _tree_snapshot(arch)
    srv._retro_status[SEASON] = status

    for data in ({"season": SEASON, "mode": "archive"},
                 {"season": SEASON, "mode": "discard", "confirm": SEASON}):
        assert client.post("/retro/run", data=data,
                           follow_redirects=False).status_code == 303
    assert client.post(f"/retro/{SEASON}/archive/{STAMP}/delete",
                       data={"confirm": SEASON},
                       follow_redirects=False).status_code == 303

    assert _tree_snapshot(root) == live_before
    assert _tree_snapshot(arch) == arch_before


def test_busy_sees_a_worker_whose_only_trace_is_its_run_record(tmp_path,
                                                               monkeypatch):
    """The archive and discard guards rest on /api/busy. A season must never
    read as idle while a live worker is writing into its tree, even when the
    in-memory claim is missing."""
    rr = _roots(tmp_path, monkeypatch)
    root = rr / SEASON
    retro.write_meta(root, {"season": SEASON, "status": "running",
                            "heartbeat_utc": time.time(),
                            "segment_start_utc": time.time(),
                            "elapsed_s": 0.0})
    assert srv._retro_status == {}
    assert client.get("/api/busy").json()["retro"] == {SEASON: "running"}


def test_deleting_an_archive_needs_confirmation_and_spares_the_live_season(
        tmp_path, monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    _season_tree(rr, SEASON)
    retro.archive_run(rr, SEASON, stamp=STAMP)
    live = _season_tree(rr, SEASON)
    live_before = _tree_snapshot(live)
    arch = rr / f"{SEASON}__archived_{STAMP}"
    arch_before = _tree_snapshot(arch)

    # unconfirmed: nothing happens
    client.post(f"/retro/{SEASON}/archive/{STAMP}/delete",
                follow_redirects=False)
    assert _tree_snapshot(arch) == arch_before
    assert "not confirmed" in srv._status.get("flash", "")

    # confirmed: the archive goes, the live season stays whole
    r = client.post(f"/retro/{SEASON}/archive/{STAMP}/delete",
                    data={"confirm": SEASON}, follow_redirects=False)
    assert r.status_code == 303
    assert not arch.exists()
    assert _tree_snapshot(live) == live_before
    flash = srv._status.get("flash", "")
    assert "2 completed weeks" in flash and "was not touched" in flash


def test_deleting_an_archive_refuses_an_identifier_it_cannot_verify(
        tmp_path, monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    _season_tree(rr, SEASON)
    retro.archive_run(rr, SEASON, stamp=STAMP)
    arch = rr / f"{SEASON}__archived_{STAMP}"
    for stamp in ("nonsense", "20990101T000000Z"):
        client.post(f"/retro/{SEASON}/archive/{stamp}/delete",
                    data={"confirm": SEASON}, follow_redirects=False)
    assert arch.is_dir()


# ------------------------------------------- an archived run stays usable

def test_the_index_lists_archives_with_their_facts_and_a_delete_control(
        tmp_path, monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    _season_tree(rr, SEASON)
    retro.archive_run(rr, SEASON, stamp=STAMP)
    html = client.get("/retro").text

    assert "1 archived run kept" in html
    assert "2098-02-04 10:15 UTC" in html          # when it ran
    assert "2 weeks" in html                       # how much it holds
    assert "1:01:01" in html                       # wall time
    assert "0.500" in html                         # headline relWIS
    assert f'href="/retro/{SEASON}?archive={STAMP}"' in html
    assert f'action="/retro/{SEASON}/archive/{STAMP}/delete"' in html
    assert "data-del-archive" in html
    assert "FluBNFConfirm" in html                 # the shared confirmation


def test_archived_run_loads_through_the_playback_api(tmp_path, monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    truth = _synthetic_data(monkeypatch, tmp_path)
    _season_tree(rr, SEASON, truth=truth)
    retro.archive_run(rr, SEASON, stamp=STAMP)

    # the live season is empty now, so a live request 404s ...
    assert client.get(f"/api/retro/{SEASON}/playback/{W1}").status_code == 404
    # ... while the archived run replays exactly as a live one does
    r = client.get(f"/api/retro/{SEASON}/playback/{W1}?archive={STAMP}")
    assert r.status_code == 200
    pl = r.json()
    assert pl["asof"] == W1
    assert pl["locations"] == ["Ohio", "Utah"]
    assert set(pl["models"]) == {"pf", "analogue", "ensemble"}
    assert pl["models"]["pf"]["Ohio"]["1"]["0.5"] == pytest.approx(101.0)
    # and the cache lands inside the ARCHIVE, never back in the live root
    assert (rr / f"{SEASON}__archived_{STAMP}" / "playback_cache"
            / f"{W1}.json").is_file()
    assert not (rr / SEASON / "playback_cache" / f"{W1}.json").exists()


def test_archived_run_builds_a_season_report_labelled_as_archived(
        tmp_path, monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    truth = _synthetic_data(monkeypatch, tmp_path)
    _season_tree(rr, SEASON, truth=truth)
    retro.archive_run(rr, SEASON, stamp=STAMP)
    arch = rr / f"{SEASON}__archived_{STAMP}"

    r = client.get(f"/api/retro/{SEASON}/report_path?archive={STAMP}")
    assert r.status_code == 200
    p = Path(r.json()["path"])
    assert p.parent == arch                      # built inside the archive
    html = p.read_text()
    assert "Archived run 2098-02-04 10:15 UTC" in html
    assert W1 in html and W2 in html             # both weeks embedded

    d = client.get(f"/retro/{SEASON}/report?archive={STAMP}")
    assert d.status_code == 200
    assert "attachment" in d.headers["content-disposition"]


def test_archived_season_page_carries_the_identifier_through_every_url(
        tmp_path, monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    truth = _synthetic_data(monkeypatch, tmp_path)
    _season_tree(rr, SEASON, truth=truth)
    retro.archive_run(rr, SEASON, stamp=STAMP)

    html = client.get(f"/retro/{SEASON}?archive={STAMP}").text
    assert "Archived run" in html
    assert f'href="/retro/{SEASON}/report?archive={STAMP}" download' in html
    assert f'data-archive="{STAMP}"' in html
    assert f'const ARCHIVE = "{STAMP}";' in html
    # the player's two fetches both append it, and neither is left bare
    assert "'/playback/' + encodeURIComponent(w)\n" in html
    assert "(AQ ? '?' + AQ : '')" in html
    assert "(AQ ? '&' + AQ : '')" in html
    # per-state table and the season report link are present as on a live page
    assert "Per-state scores" in html
    assert "Season player" in html


def test_playback_and_report_refuse_an_unverifiable_archive_identifier(
        tmp_path, monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    _synthetic_data(monkeypatch, tmp_path)
    _season_tree(rr, SEASON, truth=_truth_map()[0])
    for url in (f"/api/retro/{SEASON}/playback/{W1}?archive=../../etc",
                f"/retro/{SEASON}/report?archive=nope",
                f"/api/retro/{SEASON}/report_path?archive=nope"):
        assert client.get(url).status_code == 404, url
    r = client.get(f"/retro/{SEASON}?archive=nope", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/retro"


def test_a_deleted_archive_stops_resolving_without_touching_the_live_season(
        tmp_path, monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    _synthetic_data(monkeypatch, tmp_path)
    truth = _truth_map()[0]
    _season_tree(rr, SEASON, truth=truth)
    retro.archive_run(rr, SEASON, stamp=STAMP)
    live = _season_tree(rr, SEASON, truth=truth)

    client.post(f"/retro/{SEASON}/archive/{STAMP}/delete",
                data={"confirm": SEASON}, follow_redirects=False)
    r = client.get(f"/api/retro/{SEASON}/playback/{W1}?archive={STAMP}")
    assert r.status_code == 404
    # the live season still serves its own weeks
    assert client.get(f"/api/retro/{SEASON}/playback/{W1}").status_code == 200
    assert (live / "weeks" / W1 / "samples.json").is_file()
