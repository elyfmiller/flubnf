"""Storage reclaim: intermediates versus load-bearing files, as enforced.

The rules under test (app/core/reclaim.py and the /storage/reclaim routes):

  * reclaim deletes ONLY fit intermediates of COMPLETED weeks and runs --
    per-cell trees, runner scripts, shard lists, prep manifests, done
    markers, .prog files -- and compresses stored samples losslessly with
    their mtimes preserved;
  * every load-bearing file survives byte-identical: samples records,
    scores.json, run_meta.json, playback caches, report HTML, submission
    CSVs, a workroot's assembled results; the STRONG test builds a full
    fixture tree, hashes every file, runs the whole reclaim, and asserts
    survival file by file;
  * the sealed validation record and the hub clone are untouched to the
    byte and to the mtime, no matter how the reclaim is invoked;
  * an INCOMPLETE week or run keeps every checkpoint (resumability is the
    contract the checkpoints exist for), and busy seasons and the live
    workroot are skipped;
  * a compressed season still scores, plays back, and exports identically
    to the uncompressed one;
  * automatic hygiene: run_week prunes the week it just assembled, and
    finalize_season sweeps the season;
  * the storage panel's reclaim control reports by category first (dry
    run), performs only behind the count-stamped confirmation, and
    refuses a stale one.
"""
import gzip
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient                    # noqa: E402

import app.core.runs as runs_mod                             # noqa: E402
from app.core import playback, reclaim, retro, scoring       # noqa: E402
from app.core.runs import run_display, run_id_time           # noqa: E402
from app.ui import server as srv                             # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL        # noqa: E402

client = TestClient(srv.app)

SEASON, BUSY, RESEARCH = "2098-99", "2097-98", "2096-97"
W1, W2, W3 = "2098-01-03", "2098-01-10", "2098-01-17"
N2F = {"Ohio": "39", "Utah": "49"}
WEIGHTS = {"pf": 0.5, "analogue": 0.5}


# ------------------------------------------------------------------ builders

def _intermediates(wd: Path) -> None:
    """The full fit machinery a week (or workroot) accumulates."""
    cell = wd / "Ohio_r0"
    (cell / "out" / "Results").mkdir(parents=True)
    (cell / "m.bngl").write_text("model")
    (cell / "m.net").write_text("netgen scratch")
    (cell / "m_flu.cdat").write_text("0 1 2")
    (cell / "out" / "Results" / "traj_noise.txt").write_text("1 2 3\n" * 50)
    (cell / "out" / "pf_state.npz").write_bytes(b"\x00" * 256)
    (wd / "cells.json").write_text('[{"key": "Ohio_r0"}]')
    (wd / "cells_0.json").write_text("[]")
    (wd / "runner_0.py").write_text("# runner")
    (wd / "prep.json").write_text("{}")
    (wd / "HALT").write_text("")
    (wd / "cells_done").mkdir()
    (wd / "cells_done" / "Ohio_r0.json").write_text('{"status": "ok"}')


def _payload(asof: str) -> dict:
    pf = {loc: {str(h): [10.0 + h, 11.0 + h, 12.0 + h] for h in range(5)}
          for loc in N2F}
    an = {loc: {str(h): {str(L): 10.0 + h + L for L in QL}
                for h in range(1, 5)} for loc in N2F}
    return {"asof": asof, "pf": pf, "analogue": an}


def _mk_week(root: Path, asof: str, complete=True, gz=False,
             with_intermediates=True) -> Path:
    wd = root / "weeks" / asof
    wd.mkdir(parents=True, exist_ok=True)
    if with_intermediates:
        _intermediates(wd)
    if complete:
        if gz:
            retro.write_week_samples(wd, _payload(asof))
        else:
            (wd / "samples.json").write_text(json.dumps(_payload(asof)))
    return wd


def _mk_season(root: Path) -> None:
    _mk_week(root, W1, complete=True, gz=False)
    _mk_week(root, W2, complete=True, gz=True)
    _mk_week(root, W3, complete=False)          # interrupted: checkpoints stay
    (root / "scores.json").write_text('{"model": {"0": "pf"}}')
    (root / "run_meta.json").write_text('{"season": "x"}')
    (root / "playback_cache").mkdir(exist_ok=True)
    (root / "playback_cache" / f"{W1}.json").write_text("{}")
    (root / f"{SEASON}-FluBNF-season-report.html").write_text("<p>r</p>")


def _mk_workroot(base: Path, name: str, complete=True) -> Path:
    w = base / name
    w.mkdir(parents=True)
    _intermediates(w)
    (w / "pf_runner.py").write_text("# console runner")
    (w / "pf_status.json.prog").write_text("{}")
    (w / "pf_status.json").write_text("{}")
    if complete:
        (w / "results.json").write_text('{"models": {}}')
        (w / "scores_pf.json").write_text("{}")
        (w / "report.html").write_text("<p>weekly</p>")
        sub = w / "submission" / "NAU-PF-SIHRS"
        sub.mkdir(parents=True)
        (sub / "2098-01-03-NAU-PF-SIHRS.csv").write_text("a,b\n1,2\n")
    return w


def _snapshot(root: Path) -> dict:
    """{relative path: (sha256, mtime_ns)} for every file under root.

    The key is as_posix(), not str(): every expectation below is written
    with forward slashes ("retro/2098-99/scores.json"), and str() of a
    relative WindowsPath is "retro\\2098-99\\scores.json", so on Windows
    every lookup missed and the test died on
    `KeyError: 'retro/2098-99/scores.json'` (run 33200477476). Nothing in
    app/core/reclaim.py builds a key like this -- it compares Path objects
    throughout -- so the separator only ever existed in this helper.
    """
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            st = p.stat()
            out[p.relative_to(root).as_posix()] = (
                hashlib.sha256(p.read_bytes()).hexdigest(), st.st_mtime_ns)
    return out


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A full storage world: managed seasons (one busy), an archived run,
    a research tree, workroots in every state, a sealed record, a hub."""
    retro_root = tmp_path / "retro"
    workroots = tmp_path / "workroots"
    seal = tmp_path / "retro_seal"
    hub = tmp_path / "hub"
    research = tmp_path / "retro_2s"
    # protection reads reclaim.APP_STATE and settings.HUB at call time
    monkeypatch.setattr(reclaim, "APP_STATE", tmp_path)
    import flubnf.settings as settings_mod
    monkeypatch.setattr(settings_mod, "HUB", hub)

    _mk_season(retro_root / SEASON)
    _mk_week(retro_root / f"{SEASON}__archived_20980204T101500Z", W1)
    _mk_week(retro_root / BUSY, W1)             # busy: must be skipped
    # the sealed record, complete WITH intermediates and plain samples:
    # nothing in it may move, compress, or vanish
    _mk_week(seal / SEASON, W1, complete=True, gz=False)
    (seal / SEASON / "scores.json").write_text("{}")
    (hub / "model-output").mkdir(parents=True)
    (hub / "model-output" / "f.csv").write_text("h")
    # research tree: compress-only; its stray sidecar must survive
    _mk_week(research / RESEARCH, W1, complete=True, gz=False,
             with_intermediates=False)
    (research / RESEARCH / "weeks" / W1 / "sidecar.txt").write_text("keep")
    _mk_workroot(workroots, "20980118T090000-aaaaaa", complete=True)
    _mk_workroot(workroots, "20980118T100000-bbbbbb", complete=False)
    live = _mk_workroot(workroots, "20980118T110000-cccccc", complete=True)
    return {"tmp": tmp_path, "retro_root": retro_root,
            "workroots": workroots, "seal": seal, "hub": hub,
            "research": research, "live": live.name}


def _run_world(world):
    return reclaim.execute(
        world["retro_root"], world["workroots"],
        research_roots=(world["research"],),
        skip_seasons={BUSY}, skip_workroots={world["live"]})


# ----------------------------------------- the strong load-bearing survival

def test_reclaim_preserves_every_load_bearing_file_and_the_seal(world):
    tmp = world["tmp"]
    before = _snapshot(tmp)
    payload_w1 = retro.read_week_samples(world["retro_root"] / SEASON, W1)
    out = _run_world(world)
    after = _snapshot(tmp)

    # the sealed record and the hub: every file byte-identical, mtime and
    # all -- including the seal's own intermediates and its PLAIN samples
    # (never compressed: its bytes are its evidence)
    for rel, sig in before.items():
        if rel.startswith(("retro_seal/", "hub/")):
            assert after.get(rel) == sig, rel

    # load-bearing files in the managed trees: byte-identical, in place
    keep = [f"retro/{SEASON}/scores.json",
            f"retro/{SEASON}/run_meta.json",
            f"retro/{SEASON}/playback_cache/{W1}.json",
            f"retro/{SEASON}/{SEASON}-FluBNF-season-report.html",
            "workroots/20980118T090000-aaaaaa/results.json",
            "workroots/20980118T090000-aaaaaa/scores_pf.json",
            "workroots/20980118T090000-aaaaaa/report.html",
            "workroots/20980118T090000-aaaaaa/pf_status.json",
            "workroots/20980118T090000-aaaaaa/cells.json",
            "workroots/20980118T090000-aaaaaa/submission/NAU-PF-SIHRS/"
            "2098-01-03-NAU-PF-SIHRS.csv",
            f"retro_2s/{RESEARCH}/weeks/{W1}/sidecar.txt"]
    for rel in keep:
        assert after.get(rel) == before[rel], rel

    # the samples records: the gz week untouched; the plain week now
    # compressed with IDENTICAL content and its mtime preserved
    w2 = f"retro/{SEASON}/weeks/{W2}/samples.json.gz"
    assert after[w2] == before[w2]
    w1_old = f"retro/{SEASON}/weeks/{W1}/samples.json"
    w1_new = f"retro/{SEASON}/weeks/{W1}/samples.json.gz"
    assert w1_old not in after and w1_new in after
    assert after[w1_new][1] == before[w1_old][1]          # mtime preserved
    assert retro.read_week_samples(world["retro_root"] / SEASON,
                                   W1) == payload_w1

    # completed weeks and the completed workroot lost their intermediates
    for rel in (f"retro/{SEASON}/weeks/{W1}/cells.json",
                f"retro/{SEASON}/weeks/{W1}/prep.json",
                f"retro/{SEASON}/weeks/{W1}/runner_0.py",
                f"retro/{SEASON}/weeks/{W1}/cells_done/Ohio_r0.json",
                f"retro/{SEASON}/weeks/{W1}/Ohio_r0/m.net",
                "workroots/20980118T090000-aaaaaa/Ohio_r0/m.bngl",
                "workroots/20980118T090000-aaaaaa/pf_runner.py",
                "workroots/20980118T090000-aaaaaa/pf_status.json.prog"):
        assert rel not in after, rel

    # the INCOMPLETE week keeps every checkpoint (resumability), the
    # incomplete workroot keeps its whole tree, the busy season and the
    # live workroot were skipped wholesale
    for rel, sig in before.items():
        if rel.startswith((f"retro/{SEASON}/weeks/{W3}/",
                           f"retro/{BUSY}/",
                           "workroots/20980118T100000-bbbbbb/",
                           "workroots/20980118T110000-cccccc/")):
            assert after.get(rel) == sig, rel

    assert out["weeks"] == 3 and out["workroots"] == 1
    # W1, the archived week, and the research week were all plain JSON
    assert out["compress_files"] == 3
    assert out["total"] > 0


def test_survey_is_a_true_dry_run_with_stable_counts(world):
    tmp = world["tmp"]
    before = _snapshot(tmp)
    plan = reclaim.survey(world["retro_root"], world["workroots"],
                          research_roots=(world["research"],),
                          skip_seasons={BUSY},
                          skip_workroots={world["live"]})
    assert _snapshot(tmp) == before            # measured, touched nothing
    assert plan["weeks"] == 3 and plan["workroots"] == 1
    assert plan["compress_files"] == 3
    assert 0 < plan["est_compress_saved"] < plan["compress_bytes"]
    assert plan["total_est"] == (plan["week_bytes"] + plan["workroot_bytes"]
                                 + plan["est_compress_saved"])
    # the perform step's stale-confirmation token
    assert reclaim.plan_counts(plan) == (plan["weeks"], plan["workroots"],
                                         plan["compress_files"])


def test_prune_refuses_incomplete_weeks_and_protected_trees(world):
    # an incomplete week has no intermediates BY DEFINITION
    wd = world["retro_root"] / SEASON / "weeks" / W3
    assert reclaim.week_intermediates(wd) == []
    assert reclaim.prune_week(wd) == 0
    # the seal is refused per entry AND per tree, even by direct call
    seal_week = world["seal"] / SEASON / "weeks" / W1
    before = _snapshot(world["seal"])
    assert reclaim.prune_week(seal_week) == 0
    assert reclaim.prune_season(world["seal"] / SEASON)["bytes"] == 0
    assert reclaim.compressible_files(world["seal"] / SEASON) == []
    assert reclaim.compress_tree(world["seal"] / SEASON)["files"] == 0
    assert _snapshot(world["seal"]) == before


# ------------------------------------ compressed == uncompressed, end to end

def _truth():
    t = {}
    for fips, base in (("39", 100.0), ("49", 50.0)):
        for k in range(-8, 8):
            d = pd.Timestamp(W1) + pd.Timedelta(days=7 * k)
            t[(fips, d)] = base + k
    for k in range(-8, 8):
        t[("US", pd.Timestamp(W1) + pd.Timedelta(days=7 * k))] = 150.0
    return t


def _mk_scoreable_tree(tmp_path) -> Path:
    """A season whose synthetic samples actually score (the results-prep
    fixture pattern): truth-anchored draws for two locations, two weeks."""
    root = tmp_path / SEASON
    truth = _truth()
    for asof in (W1, W2):
        wd = root / "weeks" / asof
        wd.mkdir(parents=True, exist_ok=True)
        pf, an = {}, {}
        for loc, fips in N2F.items():
            pf[loc] = {str(h): [truth[(fips, pd.Timestamp(asof)
                                       + pd.Timedelta(days=7 * h))] + d
                                for d in (-1.0, 0.0, 1.0)] for h in range(5)}
            an[loc] = {str(h): {str(L): truth[(fips, pd.Timestamp(asof)
                                               + pd.Timedelta(days=7 * h))]
                                + (L - 0.5) * 10 for L in QL}
                       for h in range(1, 5)}
        (wd / "samples.json").write_text(
            json.dumps({"asof": asof, "pf": pf, "analogue": an}))
        _intermediates(wd)
    return root


@pytest.fixture
def _stubbed(monkeypatch, tmp_path):
    truth = _truth()
    monkeypatch.setattr(scoring, "load_truth", lambda: (truth, dict(N2F)))
    monkeypatch.setattr(scoring, "_baseline_cells",
                        lambda asof, fips_set, tr: {(f, asof, h): 2.0
                                                    for f in fips_set
                                                    for h in range(4)})
    monkeypatch.setattr(playback, "load_truth", lambda: (truth, dict(N2F)))
    monkeypatch.setattr(playback, "_baseline_cells",
                        lambda asof, fips_set, tr: {(f, asof, h): 2.0
                                                    for f in fips_set
                                                    for h in range(4)})
    monkeypatch.setattr(playback, "HUB", tmp_path / "hub")
    return truth


def test_compressed_season_scores_plays_back_and_exports_identically(
        tmp_path, _stubbed, monkeypatch):
    from app.core import report_season
    monkeypatch.setattr(reclaim, "APP_STATE", tmp_path)
    import flubnf.settings as settings_mod
    monkeypatch.setattr(settings_mod, "HUB", tmp_path / "hub")
    root = _mk_scoreable_tree(tmp_path)

    df1 = retro.score_season(root, SEASON, ensemble_weights=WEIGHTS)
    tmpj = root / "scores.json.tmp"
    df1.to_json(tmpj)
    import os as _os
    _os.replace(tmpj, root / "scores.json")
    assert retro.scores_current(root)
    p1 = playback.build_week(root, SEASON, W2)
    n1 = retro.national_aggregate(root, ensemble_weights=WEIGHTS)
    export_key1 = report_season._newest_input(root)

    # migrate: prune the intermediates AND compress every stored week
    out = reclaim.execute(tmp_path / "nothing", tmp_path / "nothing",
                          research_roots=(tmp_path,))
    assert out["compress_files"] == 2
    assert not (root / "weeks" / W1 / "samples.json").is_file()
    assert (root / "weeks" / W1 / "samples.json.gz").is_file()

    # the export freshness key is unchanged (mtimes preserved): a season
    # report built before the migration is still the current export after
    export_key2 = report_season._newest_input(root)
    assert export_key1 == export_key2
    # scores.json currency is undisturbed for the same reason
    assert retro.scores_current(root)

    # scores: recomputed FRESH from the compressed store, cell-identical
    df2 = retro.score_season(root, SEASON, ensemble_weights=WEIGHTS)
    pd.testing.assert_frame_equal(
        df1.reset_index(drop=True), df2.reset_index(drop=True))

    # playback: force a full rebuild (no cache) and compare payloads
    import shutil as _sh
    _sh.rmtree(root / "playback_cache")
    p2 = playback.build_week(root, SEASON, W2)
    assert p1["models"] == p2["models"]
    assert p1["truth"] == p2["truth"]
    assert p1["stats"] == p2["stats"]

    # the national aggregate: recomputed fresh, same numbers
    n2 = retro.national_aggregate(root, ensemble_weights=WEIGHTS)
    for k in ("pf", "analogue", "ensemble"):
        assert n1[k] == pytest.approx(n2[k])


def test_week_done_and_run_week_read_the_compressed_form(tmp_path):
    root = tmp_path / SEASON
    wd = root / "weeks" / W1
    wd.mkdir(parents=True)
    retro.write_week_samples(wd, _payload(W1))
    assert retro.week_done(root, W1)
    assert retro.read_week_samples(root, W1)["asof"] == W1
    # run_week's completed-week early return reads the stored record and
    # dispatches nothing (no engines are stubbed: a dispatch would fail)
    out = retro.run_week(root, SEASON, W1, ["Ohio"])
    assert out == _payload(W1)


def test_compress_is_atomic_and_prefers_the_plain_form_when_both_exist(
        tmp_path):
    wd = tmp_path / "weeks" / W1
    wd.mkdir(parents=True)
    (wd / "samples.json").write_text(json.dumps({"asof": W1, "v": 1}))
    # an interrupted migration can leave BOTH: the plain file stays the
    # record until it is retired
    with gzip.open(wd / "samples.json.gz", "wt") as f:
        json.dump({"asof": W1, "v": 0}, f)
    assert retro.read_samples(retro.samples_file(wd))["v"] == 1
    gz = retro.compress_samples_file(wd / "samples.json")
    assert gz.name == "samples.json.gz"
    assert not (wd / "samples.json").exists()
    assert retro.read_samples(retro.samples_file(wd))["v"] == 1


# --------------------------------------------------------- automatic hygiene

def test_run_week_prunes_the_week_it_just_assembled(tmp_path, monkeypatch):
    """End to end with stubbed engines: the moment samples land, the week
    directory holds the samples record and nothing else."""
    root = tmp_path / SEASON
    wd = root / "weeks" / W1

    def fake_prepare(spec, w):
        cells = [{"key": "cell_0", "dir": str(Path(w) / "cell_0")}]
        (Path(w) / "cells.json").write_text(json.dumps(cells))
        return cells

    monkeypatch.setattr(retro.pf_engine, "prepare", fake_prepare)
    monkeypatch.setattr(retro.pf_engine, "collect",
                        lambda w: {"Ohio": {"0": [1.0]}})
    monkeypatch.setattr(retro.an_engine, "run",
                        lambda spec: {"Ohio": {"1": {0.5: 2.0}}})

    class Runner:
        def __init__(self, w, shard):
            self.w, self.shard, self.i = Path(w), list(shard), 0
        def poll(self):
            for c in self.shard[self.i:]:
                retro.mark_cell_done(self.w, c["key"])
                self.i += 1
            return 0
        def kill(self):
            pass

    monkeypatch.setattr(retro, "_launch_runners",
                        lambda w, shards, halt: [Runner(w, s)
                                                 for s in shards])
    monkeypatch.setattr(retro, "_sleep", lambda s: None)
    out = retro.run_week(root, SEASON, W1, ["Ohio"], width=1)
    assert out["pf"] == {"Ohio": {"0": [1.0]}}
    assert retro.week_done(root, W1)
    assert [p.name for p in wd.iterdir()] == ["samples.json.gz"]
    # and the stored record round-trips
    assert retro.read_week_samples(root, W1) == out


def test_finalize_season_sweeps_leftover_intermediates(tmp_path, _stubbed,
                                                       monkeypatch):
    monkeypatch.setattr(reclaim, "APP_STATE", tmp_path)
    import flubnf.settings as settings_mod
    monkeypatch.setattr(settings_mod, "HUB", tmp_path / "hub")
    root = _mk_scoreable_tree(tmp_path)          # weeks carry intermediates
    phases = []
    sec = retro.finalize_season(root, SEASON, ensemble_weights=WEIGHTS,
                                phase_cb=phases.append)
    assert "pruning intermediates" in phases
    assert "prune" in sec
    for asof in (W1, W2):
        wd = root / "weeks" / asof
        assert retro.samples_file(wd) is not None
        assert not (wd / "Ohio_r0").exists()
        assert not (wd / "prep.json").exists()


# ------------------------------------------------------- the storage routes

@pytest.fixture
def routed(world, monkeypatch):
    """Point the app at the fixture world."""
    monkeypatch.setattr(runs_mod, "APP_STATE", world["tmp"])
    monkeypatch.setattr(srv, "RETRO_ROOT", world["retro_root"])
    monkeypatch.setattr(srv, "RETRO_SEAL", world["seal"])
    monkeypatch.setattr(reclaim, "RESEARCH_ROOTS", (world["research"],))
    status_before = dict(srv._status)
    retro_before = dict(srv._retro_status)
    srv._status.update({"running": None, "workroot": None, "flash": ""})
    srv._retro_status.clear()
    srv._results_jobs.clear()
    srv._invalidate_scans()
    yield world
    srv._status.clear(); srv._status.update(status_before)
    srv._retro_status.clear(); srv._retro_status.update(retro_before)
    srv._results_jobs.clear()
    srv._invalidate_scans()


def test_reclaim_api_reports_categories_without_side_effects(routed):
    before = _snapshot(routed["tmp"])
    d = client.get("/api/storage/reclaim").json()
    assert _snapshot(routed["tmp"]) == before
    labels = [c["label"] for c in d["categories"]]
    assert "Completed-week fit intermediates" in labels
    assert "Completed-run workroot intermediates" in labels
    assert "Stored-sample compression (lossless gzip)" in labels
    assert d["total"] > 0 and d["total_h"]
    assert d["confirm"].count("/") == 2


def test_reclaim_post_refuses_a_stale_confirmation(routed):
    before = _snapshot(routed["tmp"])
    r = client.post("/storage/reclaim", data={"confirm": "9/9/9"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert _snapshot(routed["tmp"]) == before
    assert "Nothing was deleted" in srv._status.get("flash", "")


def test_reclaim_post_performs_and_names_what_it_freed(routed):
    d = client.get("/api/storage/reclaim").json()
    seal_before = _snapshot(routed["seal"])
    r = client.post("/storage/reclaim", data={"confirm": d["confirm"]},
                    follow_redirects=False)
    assert r.status_code == 303
    flash = srv._status.get("flash", "")
    assert "Reclaimed" in flash
    assert "sealed validation record and the hub clone were not touched" \
        in flash
    # it did the work: intermediates gone, samples compressed, seal intact
    season = routed["retro_root"] / SEASON
    assert not (season / "weeks" / W1 / "Ohio_r0").exists()
    assert (season / "weeks" / W1 / "samples.json.gz").is_file()
    assert _snapshot(routed["seal"]) == seal_before
    # a second dry run finds nothing left in the swept categories
    d2 = client.get("/api/storage/reclaim").json()
    assert d2["confirm"] == "0/0/0"


def test_reclaim_skips_busy_seasons_and_the_live_workroot(routed):
    srv._retro_status[SEASON] = "running"
    live = routed["live"]
    srv._status["running"] = f"all:{live}"
    srv._status["workroot"] = str(routed["workroots"] / live)
    d = client.get("/api/storage/reclaim").json()
    client.post("/storage/reclaim", data={"confirm": d["confirm"]},
                follow_redirects=False)
    # the busy season kept every intermediate; the live workroot too
    assert (routed["retro_root"] / SEASON / "weeks" / W1 / "Ohio_r0").is_dir()
    assert (routed["workroots"] / live / "Ohio_r0").is_dir()
    # the idle completed workroot was still swept
    assert not (routed["workroots"] / "20980118T090000-aaaaaa"
                / "Ohio_r0").exists()


# ------------------------------------------------------- readable run labels

def test_run_id_time_parses_the_workroot_stamp():
    assert run_id_time("20260821T163029-5dbec2") == "2026-08-21 16:30"
    assert run_id_time("smoke1s") == ""
    assert run_id_time("") == ""


def test_run_display_reads_the_ledger_row():
    spec = json.dumps({"engine": "all", "forecast_date": "2026-01-24",
                       "locations": ["Ohio", "Utah", "US"]})
    d = run_display("20260118T090000-aaaaaa", spec, created_utc=None)
    assert d["what"] == "Forecast for 2026-01-24"
    assert d["when"] == "2026-01-18 09:00"
    assert d["scope"] == "2 states plus US national: Ohio, Utah"
    assert d["recorded"]
    r = run_display("20260118T090000-aaaaaa",
                    json.dumps({"engine": "retro",
                                "forecast_date": "2025-11-01",
                                "locations": ["Ohio"]}))
    assert r["what"] == "Retrospective fit 2025-11-01"


def test_run_display_orphan_reads_as_unrecorded(routed):
    d = run_display("20980118T100000-bbbbbb", None)
    assert d == {"what": "Unrecorded run", "when": "2098-01-18 10:00",
                 "scope": "", "recorded": False}
    # and the storage panel renders it that way, id secondary
    html = client.get("/storage").text
    row = html.split('data-wid="20980118T100000-bbbbbb"', 1)[1] \
              .split("</div>", 1)[0]
    assert "Unrecorded run" in row
    assert "run 2098-01-18 10:00" in row
    assert "<code" in row and "20980118T100000-bbbbbb" in row


def test_protect_roots_env_keeps_a_research_arms_evidence(tmp_path, monkeypatch):
    """A pre-registered arm run OUTSIDE app/state (the kernel A/B of
    2026-09-03 lives in the lab archive) needs its per-cell evidence, the
    ESS files, parameter samples and cells.json, for the diagnostics it
    committed to; reclaim protects by path only, so without a way to name
    the arm every completed week was pruned to its samples file before the
    measurement could be made. FLUBNF_PROTECT_ROOTS names such roots, read
    at call time; the two built-in roots are unchanged."""
    from app.core import reclaim, retro
    arm = tmp_path / "arms" / "B" / "2023-24"
    wd = arm / "weeks" / "2023-09-23"
    wd.mkdir(parents=True)
    (wd / retro.SAMPLES_JSON).write_text("{}")
    (wd / "ess_0.txt").write_text("1000\n")
    monkeypatch.delenv("FLUBNF_PROTECT_ROOTS", raising=False)
    assert not reclaim.is_protected(wd)
    assert [p.name for p in reclaim.week_intermediates(wd)] == ["ess_0.txt"]
    monkeypatch.setenv("FLUBNF_PROTECT_ROOTS", f"/nonexistent/other:{arm}")
    assert reclaim.is_protected(wd)
    assert reclaim.week_intermediates(wd) == []
    assert reclaim.prune_week(wd) == 0
    assert (wd / "ess_0.txt").exists()
