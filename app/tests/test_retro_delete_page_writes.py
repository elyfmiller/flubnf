"""A page's requests write nothing into a run a delete or a move holds
(review 6 of #93, finding 1; the independent check of pass 6 found the
same: a delete could fail half way and still say "Nothing else changed").

The warm's own card write checked its stop, but a season page's request
did not: a /mapswap for a week with no cached cards, asked while Storage
deleted the season, worked the week out for a second and then wrote
playback_cache/map_cards/<week>.json into the tree the delete had half
removed. The delete's last step then failed on the folder, and the user
read that the run could not be deleted, with its weeks already gone.

Now every cache write into a season tree goes through
retro_prep._writing_into: nothing is written into a marked tree, and a
write under way holds off the mark until it ends. The page's APIs
(playback, mapswap, the season report) answer 503 with Retry-After for a
marked tree, and the season page's player keeps that answer for no week:
a refused delete leaves the run where it was, and a moved run's page asks
at its own address, so a later visit still gets the week.

Pass 7's independent check found three more (all here): the national
aggregate's two caches (us_aggregate.json, us_quantiles/<week>.json) were
written into a marked tree by a results page that had passed its checks
before the delete began, so the delete failed half way or the deleted
season folder came back; a report whose build met the mark answered a
bare 500; and a week with no published data kept an empty placeholder
when the stored week it is drawn from had answered "ask later".
"""
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient                  # noqa: E402

from app.core import playback, report_season, retro         # noqa: E402
from app.core import retro_store                             # noqa: E402
from app.ui import retro_prep as RP                          # noqa: E402
from app.ui import server as srv                             # noqa: E402
from app.ui import season_export                             # noqa: E402
from test_retro_archive import (SEASON, STAMP, W1, W2,       # noqa: E402
                                _roots, _season_tree)
from test_retro_delete_warm import _flash, world             # noqa: E402,F401

client = TestClient(srv.app)
REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "app" / "ui" / "templates" / "retro_season.html"
BUSY = "the run is being deleted or moved"


def _files(root: Path) -> list:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def _q23(center):
    from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
    return {str(float(L)): center + 10.0 * (float(L) - 0.5) for L in QL}


def _cards_week(root: Path, wk: str) -> None:
    """One stored week whose map has cards: the filter's draws with the
    anchor under "0", the Groundhog's grids under "1".."4" (as
    test_categorical's)."""
    wd = root / "weeks" / wk
    wd.mkdir(parents=True, exist_ok=True)
    pf = {"Ohio": {"0": [100.0] * 5,
                   **{str(h): [100.0 + 40.0 * h + d for d in (-1, 0, 1)]
                      for h in range(1, 5)}}}
    an = {"Ohio": {str(h): _q23(100.0 - 30.0 * h) for h in range(1, 5)}}
    (wd / "samples.json").write_text(json.dumps(
        {"asof": wk, "pf": pf, "analogue": an}))


def _card_file(root: Path, wk: str) -> Path:
    return root / "playback_cache" / "map_cards" / f"{wk}.json"


# ------------------------------------------------- the reviewer's scenario

def test_a_map_asked_for_while_storage_deletes_the_season_lets_it_end(world):
    """The request reads the week's samples (half a second here) while
    Storage marks the tree and removes playback_cache first; its card
    write comes in the middle of the delete and is skipped, so the
    delete removes the whole tree and says so."""
    root = _season_tree(world["rr"], SEASON)
    world["reading"].clear()
    got = {}

    def ask():
        got["r"] = client.get(f"/api/retro/{SEASON}/mapswap/{W2}")
    t = threading.Thread(target=ask, daemon=True)
    t.start()
    world["threads"].append(t)
    assert world["reading"].wait(5), "the map request did not start"
    r = client.post("/storage/delete", data={
        "kind": "retro-season", "ident": SEASON, "confirm": SEASON},
        follow_redirects=False)
    t.join(10)
    assert r.status_code == 303
    assert "Deleted the retrospective season" in _flash(), _flash()
    assert not root.exists(), _files(root)        # no stub left behind
    assert got["r"].status_code == 200


# ----------------------------------------------- the APIs: "ask later"

def _apis():
    return [
        ("get", f"/api/retro/{SEASON}/playback/{W1}", True),
        ("get", f"/api/retro/{SEASON}/mapswap/{W1}", True),
        ("post", f"/api/retro/{SEASON}/report_job", True),
        ("get", f"/api/retro/{SEASON}/report_path", True),
        # the download is a page of the console, not a script's answer
        ("get", f"/retro/{SEASON}/report", False),
    ]


@pytest.mark.parametrize("method,url,api", _apis(),
                         ids=["playback", "mapswap", "report_job",
                              "report_path", "report"])
def test_the_page_apis_answer_ask_later_while_a_delete_holds_the_run(
        tmp_path, monkeypatch, method, url, api):
    rr = _roots(tmp_path, monkeypatch)
    root = _season_tree(rr, SEASON)
    before = _files(root)
    with RP._removing(root) as busy:
        assert busy == ""
        r = getattr(client, method)(url)
    assert r.status_code == 503, r.text[:300]
    assert BUSY in r.text
    if api:
        assert r.headers.get("Retry-After"), dict(r.headers)
        assert r.text == (f"{SEASON}: {BUSY}, so "
                          + ("week 2098-01-03 is not shown" if "playback"
                             in url else "its map for 2098-01-03 is not "
                             "shown" if "mapswap" in url
                             else "its season report is not built")
                          + " while it is.")
    assert _files(root) == before


def test_an_unknown_week_is_still_a_404_kept_by_the_player(tmp_path,
                                                         monkeypatch):
    """Only the mark answers "ask later": a week that is not stored is a
    404 without Retry-After, as before."""
    rr = _roots(tmp_path, monkeypatch)
    _season_tree(rr, SEASON)
    r = client.get(f"/api/retro/{SEASON}/mapswap/2098-02-28")
    assert r.status_code == 404
    assert "Retry-After" not in r.headers


def test_a_refused_delete_leaves_the_week_to_be_asked_again(tmp_path,
                                                           monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    root = rr / SEASON
    _cards_week(root, W1)
    url = f"/api/retro/{SEASON}/mapswap/{W1}"
    with RP._removing(root):
        assert client.get(url).status_code == 503
        assert not _card_file(root, W1).exists()
    # the delete refused and lifted its mark: the same address answers
    r = client.get(url)
    assert r.status_code == 200
    assert set(r.json()["models"]) == {"pf", "analogue"}
    assert _card_file(root, W1).is_file()


def test_a_moved_run_s_page_gets_its_cards(tmp_path, monkeypatch):
    """Start's archive moves the run aside under the mark: asked during
    the move, the live address answers "ask later" and writes nothing;
    the moved run's page then gets every card at its own address."""
    rr = _roots(tmp_path, monkeypatch)
    root = rr / SEASON
    _cards_week(root, W1)
    with RP._removing(root):
        r = client.get(f"/api/retro/{SEASON}/mapswap/{W1}")
        assert r.status_code == 503 and r.headers.get("Retry-After")
        moved = retro.archive_run(rr, SEASON, STAMP)
    assert not root.exists()
    assert not _card_file(moved, W1).exists()
    r = client.get(f"/api/retro/{SEASON}/mapswap/{W1}?archive={STAMP}")
    assert r.status_code == 200
    d = r.json()
    assert set(d["models"]) == {"pf", "analogue"}
    assert d["models"]["pf"]["states"]["39"]["f"] != \
        d["models"]["analogue"]["states"]["39"]["f"]
    assert _card_file(moved, W1).is_file()
    # the live address now has no run: a plain 404, kept by the player
    r = client.get(f"/api/retro/{SEASON}/mapswap/{W1}")
    assert r.status_code == 404 and "Retry-After" not in r.headers


# ------------------------------------------------ every cache writer

def test_no_map_card_is_written_into_a_marked_tree(tmp_path):
    root = tmp_path / SEASON
    _cards_week(root, W1)
    with RP._removing(root):
        by_model = RP._week_map_cards_by_model(root, W1)
    assert set(by_model) == {"pf", "analogue"}    # the request is answered
    assert not (root / "playback_cache").exists()
    RP._week_map_cards_by_model(root, W1)
    assert _card_file(root, W1).is_file()


def test_no_player_week_file_is_written_into_a_marked_tree(tmp_path):
    root = tmp_path / SEASON
    root.mkdir()
    cf = root / "playback_cache" / f"{W1}.json"
    with RP._removing(root):
        playback._write_cache(cf, {"_v": 1})
    assert not (root / "playback_cache").exists()
    playback._write_cache(cf, {"_v": 1})
    assert json.loads(cf.read_text()) == {"_v": 1}


def test_a_player_week_file_never_makes_a_deleted_tree_again(tmp_path):
    root = tmp_path / SEASON                       # deleted meanwhile
    playback._write_cache(root / "playback_cache" / "stats_cells.json",
                          {"weeks": {}})
    assert not root.exists()


def test_no_quantiles_file_is_written_into_a_marked_tree(tmp_path):
    root = tmp_path / SEASON
    wd = root / "weeks" / W1
    wd.mkdir(parents=True)
    (wd / "samples.json").write_text(json.dumps({"asof": W1, "pf": {}}))
    with RP._removing(root):
        assert retro_store.week_member_quantiles(root, W1) == {"pf": {}}
    assert not (wd / retro_store.QUANTILES_NAME).exists()
    retro_store.week_member_quantiles(root, W1)
    assert (wd / retro_store.QUANTILES_NAME).is_file()


def test_no_season_report_is_written_into_a_marked_tree(tmp_path,
                                                       monkeypatch):
    """A build that was under way when the delete began writes no file
    into the tree; the job says why."""
    root = tmp_path / SEASON
    (root / "weeks" / W1).mkdir(parents=True)
    (root / "weeks" / W1 / "samples.json").write_text(
        json.dumps({"asof": W1, "pf": {}}))
    monkeypatch.setattr(season_export, "render_season_report",
                        lambda *a, **k: "<html></html>")
    before = _files(root)
    with RP._removing(root):
        with pytest.raises(RuntimeError) as e:
            report_season.build_season_report(root, SEASON)
    assert str(e.value) == (f"{SEASON}: the run is being deleted or moved, "
                            "so its season report was not written.")
    assert _files(root) == before
    out = report_season.build_season_report(root, SEASON)
    assert out.is_file() and out.parent == root


# ------------------------------- the national aggregate (pass 7's skeptics)

def _levels() -> list:
    from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
    return [float(L) for L in QL]


def _us_week_file(root: Path, wk: str) -> Path:
    return root / "playback_cache" / retro.US_QUANTILES_DIRNAME / f"{wk}.json"


AGG_BUSY = ("the run is being deleted or moved, so its national aggregate "
            "was not built")


def test_no_national_week_file_is_written_into_a_marked_tree(tmp_path):
    """A week's national quantile sets are given and not cached while a
    delete or a move holds the tree; no folder is made for it."""
    root = tmp_path / SEASON
    _cards_week(root, W1)
    sp = root / "weeks" / W1 / "samples.json"
    with RP._removing(root):
        asof, pf_nat, an_nat = retro._national_week(root, sp, _levels())
    assert asof == W1 and pf_nat and an_nat       # the request is answered
    assert not (root / "playback_cache").exists()
    retro._national_week(root, sp, _levels())
    assert _us_week_file(root, W1).is_file()


def test_no_national_aggregate_is_written_into_a_marked_tree(tmp_path,
                                                            monkeypatch):
    """Nothing is written, and no figure is given for weeks that were
    going while it was worked out: the US row says why in plain words."""
    from app.core import scoring
    from app.core import us_national as usn
    monkeypatch.setattr(scoring, "load_truth", lambda: ({}, {}))
    root = tmp_path / SEASON
    _cards_week(root, W1)
    _cards_week(root, W2)
    with RP._removing(root):
        with pytest.raises(retro_store.TreeBusy) as e:
            retro.national_aggregate(root)
        assert str(e.value) == AGG_BUSY
        assert usn.aggregate_row(root) == (None, AGG_BUSY)
    assert not (root / "playback_cache").exists()
    # the mark lifted (a refused delete): built and cached as before
    assert retro.national_aggregate(root)["weeks"] == 2
    assert (root / "playback_cache" / "us_aggregate.json").is_file()
    assert _us_week_file(root, W2).is_file()


def test_the_national_aggregate_never_makes_a_deleted_tree_again(
        tmp_path, monkeypatch):
    """A delete that ended between the last week read and the aggregate's
    write: the season folder does not come back."""
    from app.core import scoring
    monkeypatch.setattr(scoring, "load_truth", lambda: ({}, {}))
    root = tmp_path / SEASON
    _cards_week(root, W1)
    orig = retro._national_week

    def read_then_deleted(r, sp, levels):
        out = orig(r, sp, levels)
        shutil.rmtree(root)                   # the delete ends meanwhile
        return out
    monkeypatch.setattr(retro, "_national_week", read_then_deleted)
    assert retro.national_aggregate(root)["weeks"] == 1
    assert not root.exists()


def test_a_results_page_open_while_storage_deletes_the_season_lets_it_end(
        world, monkeypatch):
    """The skeptic's scenario: the page passed its checks before the
    delete began, and reached the national aggregate once the delete had
    removed playback_cache and the first week. The aggregate, worked out
    from the weeks left, writes nothing into the tree (before, its week
    files and us_aggregate.json made playback_cache again and the delete
    failed on the folder, "Could not delete", with every week gone)."""
    from app.core import scoring
    from app.ui import retro_prep
    W3 = "2098-01-17"
    root = _season_tree(world["rr"], SEASON, weeks=(W1, W2, W3))
    monkeypatch.setattr(retro_prep, "_results_pending", lambda r: "")
    monkeypatch.setattr(scoring, "load_truth", lambda: ({}, {}))
    at_aggregate, week_gone, page_done = (threading.Event(),
                                          threading.Event(),
                                          threading.Event())
    orig = retro.national_aggregate

    def aggregate(r):
        at_aggregate.set()
        assert week_gone.wait(20)
        return orig(r)
    monkeypatch.setattr(retro, "national_aggregate", aggregate)

    def delete(p):
        """rmtree's walk: one listing, playback_cache first, then weeks/
        week by week (the page ends after the first), the folder last."""
        p = Path(p)
        for q in sorted(p.iterdir(), key=lambda q: (
                q.name != "playback_cache", q.name != "weeks", q.name)):
            if q.name == "weeks":
                for wd in sorted(q.iterdir()):
                    shutil.rmtree(wd)
                    if not week_gone.is_set():
                        week_gone.set()
                        page_done.wait(30)
                q.rmdir()
            elif q.is_dir():
                shutil.rmtree(q)
            else:
                q.unlink()
        p.rmdir()
    monkeypatch.setattr(retro, "delete_tree", delete)
    got = {}

    def page():
        try:
            got["r"] = client.get(f"/retro/{SEASON}")
        finally:
            page_done.set()
    t = threading.Thread(target=page, daemon=True)
    t.start()
    world["threads"].append(t)
    assert at_aggregate.wait(30), "the page did not reach the aggregate"
    r = client.post("/storage/delete", data={
        "kind": "retro-season", "ident": SEASON, "confirm": SEASON},
        follow_redirects=False)
    t.join(30)
    assert r.status_code == 303
    assert "Deleted the retrospective season" in _flash(), _flash()
    assert not root.exists(), _files(root)        # no stub left behind
    assert got["r"].status_code == 200


# --------------------------- the season report, when the mark comes mid-build

#: a 500 is answered, not raised, so a test sees what the browser sees
loose = TestClient(srv.app, raise_server_exceptions=False)


@pytest.mark.parametrize("url,api", [
    (f"/api/retro/{SEASON}/report_path", True),
    (f"/retro/{SEASON}/report", False)], ids=["report_path", "report"])
def test_a_report_whose_build_meets_a_delete_answers_ask_later(
        tmp_path, monkeypatch, url, api):
    """The build passed the check before the delete began; its write is
    refused: the answer is the one a marked tree gets before the build
    (503 with Retry-After for the API, a page of the console for the
    download), never a bare 500."""
    rr = _roots(tmp_path, monkeypatch)
    root = _season_tree(rr, SEASON)
    rendering, go = threading.Event(), threading.Event()

    def slow_render(*a, **k):
        rendering.set()
        assert go.wait(10)
        return "<html></html>"
    monkeypatch.setattr(season_export, "render_season_report", slow_render)
    before = _files(root)
    got = {}
    t = threading.Thread(target=lambda: got.setdefault("r", loose.get(url)),
                         daemon=True)
    t.start()
    assert rendering.wait(10)
    with RP._removing(root) as busy:          # Storage's Delete, say
        assert busy == ""
        go.set()
        t.join(10)
    r = got["r"]
    assert r.status_code == 503, r.text[:300]
    assert BUSY in r.text
    if api:
        assert r.headers.get("Retry-After"), dict(r.headers)
        assert r.text == (f"{SEASON}: {BUSY}, so its season report is not "
                          "built while it is.")
    else:
        assert "Season report" in r.text and "Open the season" in r.text
    assert _files(root) == before


def test_the_report_job_meeting_a_delete_says_so_in_its_words(tmp_path,
                                                             monkeypatch):
    """The page's background build ends with the sentence, not a class
    name before it."""
    root = tmp_path / SEASON
    _cards_week(root, W1)
    rendering, go = threading.Event(), threading.Event()

    def slow_render(*a, **k):
        rendering.set()
        assert go.wait(10)
        return "<html></html>"
    monkeypatch.setattr(season_export, "render_season_report", slow_render)
    season_export.report_job(root, SEASON)
    assert rendering.wait(10)
    with RP._removing(root):
        go.set()
        t_end = time.monotonic() + 10
        while (season_export.job_status(root)["state"] == "running"
               and time.monotonic() < t_end):
            time.sleep(0.02)
    st = season_export.job_status(root)
    assert st["state"] == "error"
    assert st["error"] == (f"{SEASON}: {BUSY}, so its season report was not "
                           "written.")
    assert not report_season.report_path(root, SEASON).exists()


def test_a_write_under_way_holds_off_a_delete_s_mark(tmp_path):
    """No delete marks a tree and starts removing it under a file half
    written: the mark waits for the write to end."""
    root = tmp_path / SEASON
    root.mkdir()
    writing, release = threading.Event(), threading.Event()

    def write():
        with RP._writing_into(root) as ok:
            assert ok
            writing.set()
            release.wait(10)
    marked = threading.Event()

    def delete():
        with RP._removing(root):
            marked.set()
    tw = threading.Thread(target=write, daemon=True)
    tw.start()
    assert writing.wait(5)
    td = threading.Thread(target=delete, daemon=True)
    td.start()
    time.sleep(0.3)
    assert not marked.is_set() and not RP._being_removed(root)
    release.set()
    tw.join(5)
    td.join(5)
    assert marked.is_set()
    assert not RP._being_removed(root)          # lifted at the block's end


# ----------------------------------------- the player keeps "later" for no week

NODE = shutil.which("node")


def _player_slice() -> str:
    """The season page's payload and map fetches, as the template has
    them (no template expression inside)."""
    s = TEMPLATE.read_text(encoding="utf-8")
    js = s[s.index(" const PAY = {}, PPROM = {}, PERR = {};"):
           s.index(" // the cumulative chart's marker")]
    assert "function showMap(w)" in js
    assert "{{" not in js and "{%" not in js
    return js


_HARNESS = r"""
const RAF = [];
function requestAnimationFrame(f){ RAF.push(f); }
const window = {};
const FluBNFPlayer = {MODEL_NAMES: {}};
const SEASON = '2098-99', AQ = '';
const NOTES = {}, NO_DATA_NOTE = 'No data published';
function noData(w){ return NOTES[w] === NO_DATA_NOTE; }
function el(){ return {dataset: {}, hidden: true, textContent: '',
  attrs: {}, classList: {toggle(){}, remove(){}},
  setAttribute(k, v){ this.attrs[k] = v; }}; }
const path = el(); path.dataset.fips = '39'; path.dataset.abbr = 'OH';
const svg = {querySelectorAll: () => [path]};
const host = el(); host.querySelector = q => (q === 'svg#usmap' ? svg : null);
const noteT = el();
const note = el(); note.querySelector = () => noteT;
const document = {
  getElementById: id => ({'view-map': host, 'map-note': note})[id] || null,
  querySelector: () => null, addEventListener(){}};
// the answers, per address, in turn; every request is counted
const ANSWERS = {}, ASKED = {};
function answer(status, body, later){
  return {ok: status === 200, status,
          headers: {get: k => (later && k === 'Retry-After') ? '5' : null},
          text: () => Promise.resolve(typeof body === 'string' ? body
                                      : JSON.stringify(body)),
          json: () => Promise.resolve(body)};
}
function fetch(url){
  ASKED[url] = (ASKED[url] || 0) + 1;
  return Promise.resolve(ANSWERS[url].shift());
}
async function settle(){
  for(let i = 0; i < 20; i++){
    await new Promise(r => setTimeout(r, 0));
    RAF.splice(0).forEach(f => f());
  }
}
"""

_SCENARIO = r"""
const W = '2098-01-03', W2 = '2098-01-10', W3 = '2098-01-17';
const MAP = w => '/api/retro/2098-99/mapswap/' + w;
const PB = w => '/api/retro/2098-99/playback/' + w;
const SAY = '2098-99: the run is being deleted or moved, so its map for '
            + W + ' is not shown while it is.';
const cards = f => ({default: 'pf',
                     models: {pf: {states: {'39': {f: f, o: 1, h: 'Ohio'}}}}});
ANSWERS[MAP(W)] = [answer(503, SAY, true), answer(200, cards('#c00'))];
ANSWERS[MAP(W2)] = [answer(200, cards('#0c0'))];
ANSWERS[MAP(W3)] = [answer(404, 'no stored week ' + W3)];
ANSWERS[PB(W)] = [answer(503, 'busy', true), answer(200, {asof: W})];
ANSWERS[PB(W3)] = [answer(503, 'No observed data to score against.', false)];
(async () => {
  const out = {};
  // the map: "later" is said in the note and kept for no week
  showMap(W); await settle();
  out.note = note.hidden ? null : noteT.textContent;
  out.keptLater = (W in SWAP);
  showMap(W); await settle();                      // still on it: no ask
  out.askedOnce = ASKED[MAP(W)];
  showMap(W2); await settle();
  showMap(W); await settle();                      // back again: asks
  out.askedAgain = ASKED[MAP(W)];
  out.fill = path.attrs.fill || null;
  out.noteAfter = note.hidden;
  // a week that is not stored is kept, and never asked again
  showMap(W3); await settle(); showMap(W2); await settle();
  showMap(W3); await settle();
  out.notStoredAsked = ASKED[MAP(W3)];
  // the week's payload: "later" is not kept, and its words are shown
  out.pl1 = await ensurePayload(W);
  out.err1 = PERR[W];
  out.cached1 = (W in PAY);
  out.pl2 = await ensurePayload(W);
  out.pbAsked = ASKED[PB(W)];
  // any other failure is kept, as before
  await ensurePayload(W3); await ensurePayload(W3);
  out.otherAsked = ASKED[PB(W3)];
  out.otherKept = (W3 in PAY);
  console.log(JSON.stringify(out));
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
"""


@pytest.mark.skipif(not NODE, reason="node not available")
def test_the_player_asks_again_for_a_week_it_was_told_to_ask_later(
        tmp_path):
    drv = tmp_path / "player_later.js"
    drv.write_text(_HARNESS + _player_slice() + _SCENARIO, encoding="utf-8")
    out = subprocess.run([NODE, str(drv)], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got["note"] == ("2098-99: the run is being deleted or moved, so "
                           "its map for 2098-01-03 is not shown while it is.")
    assert got["keptLater"] is False
    assert got["askedOnce"] == 1
    assert got["askedAgain"] == 2
    assert got["fill"] == "#c00"                 # the week's cards, painted
    assert got["noteAfter"] is True
    assert got["notStoredAsked"] == 1
    assert got["pl1"] is None and got["err1"] == "busy"
    assert got["cached1"] is False
    assert got["pl2"] == {"asof": "2098-01-03"}
    assert got["pbAsked"] == 2
    assert got["otherAsked"] == 1 and got["otherKept"] is True


# --------------- the player's no-data week keeps no placeholder from "later"

PLAYER = REPO / "app" / "ui" / "static" / "player.js"


def _no_data_slice() -> str:
    """The season page's ensurePayload (the template's) with the player's
    noDataPayload and payloadFor (player.js's), as they are."""
    s = TEMPLATE.read_text(encoding="utf-8")
    ens = s[s.index(" const PAY = {}, PPROM = {}, PERR = {};"):
            s.index(" // ---- categorical map per week")]
    assert "{{" not in ens and "{%" not in ens
    pj = PLAYER.read_text(encoding="utf-8")
    ndp = pj[pj.index("function noDataPayload(src, week){"):
             pj.index("// ------------------------------------------------ "
                      "stats table")]
    pf = pj[pj.index("  function noteOf(w){"):
            pj.index("  function plotHeight(){")]
    assert "function payloadFor(w)" in pf
    return ens + ndp + pf


_NO_DATA_HARNESS = r"""
const window = {};
const SEASON = '2098-99', AQ = '';
const W1 = '2098-01-03', W2 = '2098-01-10', W3 = '2098-01-17',
      W4 = '2098-01-24';
const NO_DATA_NOTE = 'No data published';
const NOTES = {}; NOTES[W2] = NO_DATA_NOTE; NOTES[W4] = NO_DATA_NOTE;
function noData(w){ return NOTES[w] === NO_DATA_NOTE; }
const ANSWERS = {}, ASKED = {};
function answer(status, body, later){
  return {ok: status === 200, status,
          headers: {get: k => (later && k === 'Retry-After') ? '5' : null},
          text: () => Promise.resolve(typeof body === 'string' ? body
                                      : JSON.stringify(body))};
}
function fetch(url){
  ASKED[url] = (ASKED[url] || 0) + 1;
  return Promise.resolve(ANSWERS[url].shift());
}
const weeks = [W1, W2, W3, W4];
const cfg = {getPayload: ensurePayload, notes: NOTES,
             noDataNote: NO_DATA_NOTE};
let built = 0;
function buildControls(){ built++; }
"""

_NO_DATA_SCENARIO = r"""
const PB = w => '/api/retro/2098-99/playback/' + w;
const stored = w => ({asof: w, locations: ['Ohio'],
                      truth: {Ohio: [[w, 5]]}, stats: {}});
ANSWERS[PB(W1)] = [answer(503, 'busy', true), answer(200, stored(W1))];
ANSWERS[PB(W3)] = [answer(404, 'no stored week ' + W3)];
(async () => {
  const out = {};
  // W2's placeholder comes from W1, which is asked while "later"
  out.nd1 = await payloadFor(W2);
  out.nd2 = await payloadFor(W2);          // asked again, and served
  out.nd3 = await payloadFor(W2);          // kept now: no third ask
  out.asked = ASKED[PB(W1)];
  out.built = built;
  // W4's source answers a final 404: kept by ensurePayload, never refetched
  out.gone1 = await payloadFor(W4);
  out.gone2 = await payloadFor(W4);
  out.goneAsked = ASKED[PB(W3)];
  console.log(JSON.stringify(out));
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
"""


@pytest.mark.skipif(not NODE, reason="node not available")
def test_a_no_data_week_asks_again_when_its_source_said_ask_later(tmp_path):
    """A week with no published data is drawn from the nearest stored
    week. When that week's answer was "ask later", the no-data week keeps
    nothing either: the next request builds its placeholder (before, it
    stayed empty for the life of the page)."""
    drv = tmp_path / "player_no_data_later.js"
    drv.write_text(_NO_DATA_HARNESS + _no_data_slice() + _NO_DATA_SCENARIO,
                   encoding="utf-8")
    out = subprocess.run([NODE, str(drv)], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got["nd1"] is None
    assert got["nd2"]["asof"] == "2098-01-10"
    assert got["nd2"]["truth"] == {"Ohio": [["2098-01-03", 5]]}
    assert got["nd2"]["models"] == {}
    assert got["nd3"] == got["nd2"]
    assert got["asked"] == 2
    assert got["built"] == 1
    assert got["gone1"] is None and got["gone2"] is None
    assert got["goneAsked"] == 1
