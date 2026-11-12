"""Experiments on this console (app/ui/routes/sandbox.py's experiments
section, templates/sandbox_experiment.html and the gallery's Experiments
card): the four choices and nothing else; Start claiming the engine,
replaying, and releasing it the moment the replay returns, the summary
then scored off the engine as the folder's one job, and a worker that
fails saying so and letting go; each refusal with its code; the claim
refusing every other run; Stop, Resume and a complete experiment; the
compare page read from summary.json only, in the words of each state; its
JSON; Delete; and the guard modal's words. In a student's folder on the
runner computer: Start queues (no claim, no thread, no guard), Stop takes
it out of the queue, the badge, the line and the Queued card read the
queue, the page never rescores, and the runner's refusal is said; the
runner computer's own console waits while the runner replays.

The replay's weeks, the engine and the hub are faked as
test_experiments.py and test_experiment_summary.py fake them: no PyBNF,
no BNG2.pl, no hub clone. Every thread a start begins is joined.

golden/experiment_pages.json holds the gallery and three experiment
pages as a console off the runner renders them, from fixed fixtures. It
was captured from origin/dev 24ac926, before the runner's branches came
to the routes and templates; regenerate only for a deliberate change to
those pages, and review its diff:

    python app/tests/test_sandbox_experiments.py --write-golden
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

#: the default role's pages (the golden test's)
GOLDEN = Path(__file__).resolve().parent / "golden" / "experiment_pages.json"

if __name__ == "__main__":
    # the golden regeneration: pytest renders the pages with the suite's
    # fixtures (conftest keeps the state and the hub out of the checkout),
    # and this file's own imports happen only in that run
    import tempfile

    import pytest
    if sys.argv[1:] != ["--write-golden"]:
        sys.exit(__doc__)
    with tempfile.TemporaryDirectory(prefix="flubnf-golden-") as _d:
        pytest.main(["-q", "-p", "no:cacheprovider", f"--basetemp={_d}/t",
                     f"{__file__}::test_the_default_role_pages_are_as_on_"
                     "24ac926"])
    _pages = getattr(sys.modules.get("test_sandbox_experiments"), "PAGES",
                     None)
    if not _pages:
        sys.exit("The pages were not rendered: see pytest's words above.")
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps({
        "_about": ("the gallery and three experiment pages (<main> only) "
                   "as a console off the runner renders them from "
                   "test_sandbox_experiments.py's fixed fixtures; captured "
                   "at origin/dev 24ac926, before the runner's branches. "
                   "Regenerate only for a deliberate change: python "
                   "app/tests/test_sandbox_experiments.py --write-golden"),
        "pages": _pages}, indent=1, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    print(f"wrote {GOLDEN}")
    sys.exit(0)

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import experiments as X                    # noqa: E402
from app.core import library as L                        # noqa: E402
from app.core import retro                               # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core import runner                              # noqa: E402
from app.core import scoring                             # noqa: E402
from app.core.engines import pf                          # noqa: E402
from app.ui import pipeline as ui_pipeline               # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons     # noqa: E402
from app.ui import server as srv                         # noqa: E402
from app.ui import shared as ui_shared                   # noqa: E402
from app.ui import state as ui_state                     # noqa: E402
from app.ui import versions as ui_versions               # noqa: E402
from app.ui.routes import sandbox as ui_sandbox          # noqa: E402
from flubnf.vintages import sha256_of                    # noqa: E402
from test_experiment_summary import (S1, _age, _experiment, _q,  # noqa: E402
                                     _shipped_root, _snapshot, _store)
from test_experiments import (SMOKE_FP, SMOKE_WEEKS, _register,  # noqa: E402
                              _replay,
                              _sidecar, _weeks_run, season, truth)  # noqa: F401
from test_fewer_marks import marks                       # noqa: E402
from test_runner_folders import student, students        # noqa: E402,F401
from test_runner_queue import state as runner_state      # noqa: E402

client = TestClient(srv.app)
FORM = {"model": "sihrs", "season": "2024-25"}
SMOKE = "sihrs_2024-25_smoke_oracle"
PAGE = f"/sandbox/experiments/{SMOKE}"
JSON = {"accept": "application/json"}
#: the hand-written summary's experiment (test_experiment_summary's)
BETA = "beta2-v3_2024-25_smoke"


class _Guard:
    """The sleep guard a start holds (pipeline._sleep_guard faked)."""

    def __init__(self):
        self.ended = False

    def terminate(self):
        self.ended = True


def _join() -> None:
    """Every experiment thread this console started, ended (a worker
    starts its scoring thread as it ends, so until none is left)."""
    while True:
        alive = [t for t in threading.enumerate()
                 if t.name.startswith("experiment-")]
        if not alive:
            return
        for t in alive:
            t.join(60)
            assert not t.is_alive(), t.name


def cost_pinned(monkeypatch) -> None:
    """The Size choices' times (routes/sandbox.py _size_words) the same on
    any computer, on either engine and after a refit of the cost model:
    30 s a fit on the private engine (2.4 times it on the public one), 8
    runners, a first estimate 1 to 4 times the model, no recorded pace."""
    monkeypatch.setattr(pf, "cell_seconds", lambda cell, engine=None: 30.0 * (
        2.4 if (engine or ("public" if pf._public() else "private"))
        == "public" else 1.0))
    monkeypatch.setattr(pf, "DEFAULT_SHARD_WIDTH", 8)
    monkeypatch.setattr(sb, "ETA_FIRST_SPAN", (1.0, 4.0))
    monkeypatch.setattr(ui_retro_seasons, "_own_cost_ratio",
                        lambda: (None, 0))


@pytest.fixture
def world(season, truth, pf_engine_ready, monkeypatch):
    """test_experiments.season's 2024-25 calendar with the console's
    replay roots there (RETRO_ROOT), the synthetic truth to score against,
    the particle-filter engine, the hub's tables the card needs, the sleep
    guard recorded, a view that waits for its scoring, no season claim and
    no notice left over (another module's, restored after), and the cost
    model fixed (cost_pinned). The guards started, a list."""
    cost_pinned(monkeypatch)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", season)
    # the routes read the claims by name: emptied in place, not rebound
    seasons = dict(ui_retro_seasons._retro_status)
    ui_retro_seasons._retro_status.clear()
    monkeypatch.setattr(sb, "locations",
                        lambda: [{"name": "Alabama", "fips": "01"}])
    monkeypatch.setattr(sb, "vintages", lambda: ["2025-01-11"])
    guards = []

    def guard():
        guards.append(_Guard())
        return guards[-1]
    monkeypatch.setattr(ui_pipeline, "_sleep_guard", guard)
    monkeypatch.setattr(ui_sandbox, "_SCORE_GRACE_S", 60.0)
    _no_flash()
    try:
        yield guards
        _join()
    finally:
        ui_retro_seasons._retro_status.clear()
        ui_retro_seasons._retro_status.update(seasons)


def _no_flash() -> None:
    for k in ("flash", "flash_kind", "flash_detail"):
        ui_state._status.pop(k, None)


def _flash() -> str:
    return ui_state._status.get("flash") or ""


def _start(c=client, **form):
    """POST the Experiments form (FORM, then `form`); its 303."""
    r = c.post("/sandbox/experiments", data={**FORM, **form},
               follow_redirects=False)
    assert r.status_code == 303, r.text[:300]
    return r


def _claim() -> dict | None:
    return ui_state._sandbox_status.get("experiment")


def _blocked(monkeypatch, name: str):
    """experiments.<name> held until the returned gate is set; `entered`
    is set once it is called. Calls go on to the real function."""
    gate, entered, calls = threading.Event(), threading.Event(), []
    real = getattr(X, name)

    def held(*a, **k):
        calls.append(a)
        entered.set()
        assert gate.wait(60)
        return real(*a, **k)
    monkeypatch.setattr(X, name, held)
    return gate, entered, calls


def world_root() -> Path:
    """The replay roots of the world fixture (RETRO_ROOT)."""
    return ui_retro_seasons.RETRO_ROOT


def _form(html: str) -> str:
    return html.split('<form method="post" action="/sandbox/experiments">',
                      1)[1].split("</form>", 1)[0]


def _options(html: str, select_id: str) -> list:
    sel = html.split(f'id="{select_id}"', 1)[1].split("</select>", 1)[0]
    return re.findall(r"<option([^>]*)>([^<]*)</option>", sel)


# ------------------------------------------------- the gallery's card

def _sums(wis, log_wis, n=100, s=(80.0, 19.0)):
    """A summary group over n cells: the baseline's sums 100 and 20, this
    model's coverage 48, 79 and 96% and the shipped side's 40, 70, 90%."""
    def cov(*pct):
        return dict(zip(("cov50", "cov80", "cov95"),
                        (round(p * n / 100) for p in pct)))
    return {"n": n, "base_wis": 100.0, "base_log_wis": 20.0,
            "model": {"wis": wis, "log_wis": log_wis, **cov(48, 79, 96)},
            **({"shipped": {"wis": s[0], "log_wis": s[1], **cov(40, 70, 90)}}
               if s else {})}


def test_the_gallery_offers_the_four_choices_only(world, monkeypatch):
    monkeypatch.setattr(retro, "available_seasons",
                        lambda: ["2023-24", "2024-25", "2025-26"])
    _replay(world_root() / "2024-25", weeks=SMOKE_WEEKS)
    _replay(world_root() / "2025-26", engine="analogue", season="2025-26")
    # registered in another order than listed: beta is the newest
    stamp = {}
    monkeypatch.setattr(sb, "_stamp", lambda: stamp["utc"])
    for name, utc in (("beta", "2026-10-30T12:00:02Z"),
                      ("gamma", "2026-10-30T12:00:01Z"),
                      ("old", "2026-10-30T12:00:03Z")):
        stamp["utc"] = utc
        _register(name)
    # a version edited after Register is listed, and cannot be picked
    bngl = L.root() / "old" / "1" / "model.bngl"
    bngl.write_text(bngl.read_text(encoding="utf-8") + "# edited\n",
                    encoding="utf-8", newline="\n")
    # one experiment, scored: its row
    folder = _experiment({w: _q(10.0) for w in SMOKE_WEEKS})
    X.write_summary(folder, {"overall": _sums(75.0, 18.0)})
    scored = (folder / X.SUMMARY).read_bytes()
    html = client.get("/sandbox").text
    # the list reads the figures as last scored: no job, nothing written
    assert ui_sandbox._experiment_scores == {}
    assert (folder / X.SUMMARY).read_bytes() == scored
    form = _form(html)
    assert set(re.findall(r'name="([^"]+)"', form)) == {
        "model", "season", "size", "oracle"}
    models = _options(html, "sbexp-model")
    assert [re.search(r'value="([^"]+)"', a).group(1) for a, _t in models] == [
        "sihrs", "sihrs-2strain", "sihrs-natg", "beta@1", "gamma@1", "old@1"]
    oracle = {re.search(r'value="([^"]+)"', a).group(1):
              re.search(r'data-oracle="(\d)"', a).group(1)
              for a, _t in models}
    assert oracle == {"sihrs": "1", "sihrs-2strain": "0", "sihrs-natg": "0",
                      "beta@1": "0", "gamma@1": "0", "old@1": "0"}
    # the shipped ones say what they are; on the private engine all three
    # can be picked
    assert [(t, " disabled" in a) for a, t in models[:3]] == [
        ("sihrs · the Oracle SIHRS, as shipped", False),
        ("sihrs-2strain · influenza A and B (research)", False),
        ("sihrs-natg · with a national-growth factor (research)", False)]
    old = [(a, t) for a, t in models if 'value="old@1"' in a][0]
    assert " disabled" in old[0] and old[1] == "old@1 · changed since Register"
    gamma = [(a, t) for a, t in models if 'value="gamma@1"' in a][0]
    assert gamma[1] == f"gamma@1 · {L.resolve('gamma@1')['fingerprint'][:8]}"
    # the newest intact registration is preselected, its Oracle step off
    assert [t.split(" ·")[0] for a, t in models if "selected" in a] == [
        "beta@1"]
    assert '<optgroup label="Shipped">' in form
    assert '<optgroup label="Registered">' in form
    # each season says whether a shipped replay is here to compare with
    # (2025-26's is the Groundhog alone); its value is the bare name
    seasons = _options(html, "sbexp-season")
    assert [t for _a, t in seasons] == [
        "2025-26 · nothing to compare with", "2024-25 · shipped replay here",
        "2023-24 · nothing to compare with"]
    assert [re.search(r'value="([^"]+)"', a).group(1)
            for a, _t in seasons] == ["2025-26", "2024-25", "2023-24"]
    assert [t for a, t in seasons if "selected" in a] == [
        "2024-25 · shipped replay here"]
    # each size says how long it takes (cost_pinned: 30 s a fit, 8
    # runners, 1 to 4 times the model before a recorded pace)
    sizes = _options(html, "sbexp-size")
    assert [re.search(r'value="(\w+)"', a).group(1) for a, _t in sizes] == [
        "smoke", "pilot", "full"]
    assert [t for a, t in sizes if "selected" in a] == [
        "smoke: 2 locations, 2 weeks (about 1 to 4 min)"]
    assert [t for _a, t in sizes][1:] == [
        "pilot: 10 locations, every other week (about 14 to 56 min)",
        "full: every location and week, as shipped (about 5.0 to 20.0 h)"]
    assert _options(html, "sbexp-oracle") == [
        (' value="on"', "on"),
        (' value="off" selected', "off (the Liu-West filter alone)")]
    assert form.count("<button") == 1
    assert '<button class="gold" data-guard="sandbox-run">Start</button>' in form
    # no "?" beside the card's heading or its fields (the card alone: the
    # season fixture's BNG2.pl fake answers git too, so the page above it
    # says an update was pulled)
    card = html[html.index('<h2 id="h-sb-exp">'):
                html.index("window.SANDBOX_RES")]
    assert marks(card) == []
    # the list: three columns, the figures as last scored
    table = html.split('<thead><tr><th>experiment</th>', 1)[1].split(
        "</table>", 1)[0]
    assert table.startswith("<th>status</th><th>relWIS</th></tr></thead>")
    assert f'<a href="/sandbox/experiments/{BETA}">{BETA}</a>' in table
    assert ('<span class="relwis ok">0.750</span> (shipped 0.800)') in table
    assert "done" in table
    # the JS sets the Oracle step from the chosen model
    js = (Path(ui_sandbox.__file__).parents[1] / "static" / "sandbox.js"
          ).read_text(encoding="utf-8")
    assert ("xo.value = o.getAttribute('data-oracle') === '1' ? 'on' : "
            "'off';") in js
    # and an experiment's page polls its JSON, reloading once it is idle
    # or gone (the 404), or its status is not the one it was drawn with
    # (the badge follows starting, running, stopping)
    for line in ("fetch('/api/sandbox/experiments/' + encodeURIComponent("
                 "sbx.getAttribute('data-id')))",
                 "if (!d || !d.status || (!d.live && !(d.scoring && "
                 "d.scoring.pending))",
                 "|| d.status.status !== sbx.getAttribute('data-status')) {",
                 "root.FluBNFUI.setProgress(bar, st.weeks_done, "
                 "st.weeks_total || 1,",
                 "if (xl) xl.textContent = st.line;"):
        assert line in js, line
    # a list that cannot be read: said, and the page still shows
    with monkeypatch.context() as m:
        def gone():
            raise OSError("the disk is gone")
        m.setattr(X, "list_experiments", gone)
        r = client.get("/sandbox")
    assert r.status_code == 200
    assert "Experiments could not be listed: the disk is gone" in r.text
    assert 'uk-alert--error" id="flash"' in r.text
    assert 'id="h-sb-exp"' in r.text and "<table class=\"kv\"><thead><tr>" \
        "<th>experiment</th>" not in r.text


def test_without_a_hub_the_card_says_so_in_one_line(world, monkeypatch):
    monkeypatch.setattr(sb, "locations", lambda: [])
    html = client.get("/sandbox").text
    # the card is the gallery's last
    card = html.split('id="h-sb-exp"', 1)[1].split("window.SANDBOX_RES", 1)[0]
    assert ("<p class=\"hint\">Experiments replay the FluSight hub's "
            "seasons: update data on the Data tab first.</p>") in card
    assert card.count("<p") == 1 and "<table" not in card
    assert 'action="/sandbox/experiments"' not in html


# ------------------------------------------------- start, and the claim

def test_start_claims_runs_and_releases(world, monkeypatch):
    guards = world
    _replay(world_root() / "2024-25", weeks=SMOKE_WEEKS)
    calls = _weeks_run(monkeypatch, _sidecar)
    gate, entered = threading.Event(), threading.Event()
    real = X.replay

    def held(settings, *, retro_root, cancelled=None):
        entered.set()
        assert gate.wait(60)
        out = real(settings, retro_root=retro_root, cancelled=cancelled)
        retro.request_stop(X.root() / SMOKE)       # a Stop that came late
        return out
    monkeypatch.setattr(X, "replay", held)
    # the segment end's job is handed the build that runs (a text, "" where
    # this checkout answers no git), never None (a view's: kept as it was)
    builds, real_job = [], ui_sandbox._score_job

    def job(eid, why, build):
        builds.append(build)
        return real_job(eid, why, build)
    monkeypatch.setattr(ui_sandbox, "_score_job", job)
    r = _start()
    assert r.headers["location"] == PAGE
    assert _flash() == ("Started sihrs_2024-25_smoke_oracle: 2 weeks of "
                        "2024-25, 2 locations.")
    assert ui_state._status.get("flash_kind") == "ok"
    assert ui_state._status.get("flash_detail") == (
        "Compared with the shipped replay of 2024-25 (the Oracle SIHRS) on "
        "the cells both score.")
    assert entered.wait(60)
    # while it replays: the claim, /api/busy and the sleep guard are held
    assert _claim()["id"] == SMOKE and _claim()["cancel"] is False
    assert client.get("/api/busy").json()["experiment"] == SMOKE
    assert ui_shared._sandbox_live_reason() == f"experiment {SMOKE} is replaying"
    assert ui_shared._sandbox_live() == ""          # never a "sandbox fit"
    assert len(guards) == 1 and guards[0].ended is False
    gate.set()
    _join()
    assert [c["asof"] for c in calls] == SMOKE_WEEKS
    assert _claim() is None and guards[0].ended is True
    folder = X.root() / SMOKE
    assert not retro.stop_path(folder).exists()
    assert not retro.pause_path(folder).exists()
    job = ui_sandbox._experiment_scores[SMOKE]
    assert (job["why"], job["error"], job["done"].is_set()) == (
        "the segment ended", "", True)
    summary = X.read_summary(folder / X.SUMMARY)
    assert builds == [ui_versions.RUNNING_SHA]
    assert isinstance(builds[0], str)
    assert summary["ran"]["flubnf_build"] == ui_versions.RUNNING_SHA
    assert summary["complete"] is True and summary["shipped"]["member"] == "pf"


def test_a_worker_that_fails_says_so_and_lets_go(world, monkeypatch):
    from app.core.problem_codes import Refusal, finding
    guards = world
    _weeks_run(monkeypatch, _sidecar)
    folder = X.root() / SMOKE
    cases = [
        (retro.ResumeMismatch("its record names another season\nmore words"),
         "warn", f"{SMOKE} was not resumed: its record names another season",
         "Delete the experiment on its page to replay it here."),
        (Refusal(finding("MODEL_CHANGED", "sihrs is 0123abcd now")), "warn",
         f"{SMOKE} did not run: sihrs is 0123abcd now (MODEL_CHANGED).", ""),
        (RuntimeError("boom"), "error", f"{SMOKE} did not run: boom", ""),
    ]
    for exc, kind, said, detail in cases:
        gate, entered = threading.Event(), threading.Event()

        def fail(settings, *, retro_root, cancelled=None, exc=exc):
            # the folder made and its flags left, then the failure
            folder.mkdir(parents=True, exist_ok=True)
            retro.request_stop(folder)
            retro.request_pause(folder)
            entered.set()
            assert gate.wait(60)
            raise exc
        monkeypatch.setattr(X, "replay", fail)
        _start()
        assert entered.wait(60)
        _no_flash()
        gate.set()
        _join()
        assert _flash() == said, (said, _flash())
        assert ui_state._status.get("flash_kind") == kind
        assert (ui_state._status.get("flash_detail") or "") == detail
        assert _claim() is None and guards[-1].ended is True
        assert not retro.stop_path(folder).exists()
        assert not retro.pause_path(folder).exists()
        assert SMOKE not in ui_sandbox._experiment_scores   # nothing stored
    assert len(guards) == len(cases)


def test_a_start_with_findings_says_them(world, monkeypatch):
    # no shipped replay here, and a model without {{GAMMA}} with the step on
    _weeks_run(monkeypatch, _sidecar)
    ref = _register("fixed", lambda t: t.replace("{{GAMMA}}", "2.1875"))
    eid = "fixed-v1_2024-25_smoke_oracle"
    r = _start(model=ref, oracle="on")
    assert r.headers["location"] == f"/sandbox/experiments/{eid}"
    assert _flash() == f"Started {eid}; nothing to compare it with."
    assert ui_state._status.get("flash_kind") == "warn"
    assert ui_state._status.get("flash_detail") == (
        f"Worth a look: {ref} lacks {{{{GAMMA}}}}, and the Oracle step assumes "
        "a removal rate of 7/3.2 per week (GAMMA_ASSUMED) no shipped replay "
        "of 2024-25 here holds the Oracle SIHRS on the shipped settings: the "
        "summary will have no shipped side (NO_REFERENCE)")
    _join()
    _no_flash()
    got = client.post("/sandbox/experiments", data={"model": ref,
                                                    "season": "2024-25"},
                      headers=JSON).json()
    assert (got["ok"], got["id"], got["started"]) == (
        True, "fixed-v1_2024-25_smoke", True)
    assert got["text"] == ("Started fixed-v1_2024-25_smoke; nothing to "
                           "compare it with.")
    assert got["codes"] == [{
        "code": "NO_REFERENCE", "tier": "warning",
        "text": "no shipped replay of 2024-25 here holds the Liu-West filter "
        "on the shipped settings: the summary will have no shipped side"}]
    assert got["plan"]["reference"] is None
    _join()
    assert _flash() == ""


def test_the_engine_is_free_while_the_summary_is_scored(world, monkeypatch):
    _weeks_run(monkeypatch, _sidecar)
    gate, entered, calls = _blocked(monkeypatch, "score")
    _start()
    for t in threading.enumerate():
        if t.name == f"experiment-{SMOKE}":
            t.join(60)
    assert entered.wait(60)
    job = ui_sandbox._experiment_scores[SMOKE]
    assert not job["done"].is_set()
    assert client.get("/api/busy").json()["experiment"] is None
    assert ui_shared._sandbox_live_reason() == ""
    # a view joins the job: no second scoring
    monkeypatch.setattr(ui_sandbox, "_SCORE_GRACE_S", 0.05)
    html = client.get(PAGE).text
    assert "Scoring: the segment ended…" in html
    assert 'data-poll="1"' in html
    assert ui_sandbox._experiment_scores[SMOKE] is job and len(calls) == 1
    assert client.get(f"/api{PAGE}").json()["scoring"] == {
        "pending": True, "why": "the segment ended", "error": ""}
    gate.set()
    _join()
    assert len(calls) == 1


def test_start_answers_json_when_asked(world, monkeypatch):
    _replay(world_root() / "2024-25", weeks=SMOKE_WEEKS)
    _weeks_run(monkeypatch, _sidecar)
    r = client.post("/sandbox/experiments", data=FORM, headers=JSON)
    assert r.status_code == 200
    got = r.json()
    assert set(got) == {"ok", "id", "url", "started", "resumed", "complete",
                        "text", "codes", "plan"}
    assert (got["ok"], got["id"], got["url"], got["started"], got["resumed"],
            got["complete"], got["codes"]) == (
        True, SMOKE, PAGE, True, False, False, [])
    assert got["text"] == ("Started sihrs_2024-25_smoke_oracle: 2 weeks of "
                           "2024-25, 2 locations.")
    plan = got["plan"]
    assert set(plan) == {"model", "model_fingerprint", "experiment", "season",
                         "size", "oracle", "locations", "weeks", "replicates",
                         "particles", "reference"}
    assert (plan["model"], plan["season"], plan["size"], plan["oracle"],
            plan["locations"], plan["weeks"], plan["replicates"],
            plan["particles"]) == ("sihrs", "2024-25", "smoke", True,
                                   ["California", "Vermont"], SMOKE_WEEKS, 1,
                                   10_000)
    assert len(plan["experiment"]) == len(plan["model_fingerprint"]) == 64
    assert plan["reference"] == {"member": "pf",
                                 "root": str(world_root() / "2024-25"),
                                 "started_utc": "2026-09-21T14:13:20Z"}
    _join()
    assert _flash() == ""                       # no JSON answer flashes
    got = client.post("/sandbox/experiments", data=FORM, headers=JSON).json()
    assert got == {"ok": True, "id": SMOKE, "url": PAGE, "started": False,
                   "resumed": False, "complete": True, "codes": [],
                   "text": f"{SMOKE} is complete: every week is stored, "
                   "nothing to fit."}
    monkeypatch.setitem(ui_state._status, "running", "all:20990101-000000")
    got = client.post("/sandbox/experiments", data={**FORM, "size": "pilot"},
                      headers=JSON).json()
    assert got == {"ok": False, "id": "sihrs_2024-25_pilot_oracle",
                   "url": None, "started": False,
                   "text": "Not started: a console run is in progress: one "
                   "run at a time (MACHINE).",
                   "codes": [{"code": "MACHINE", "tier": "machine",
                              "text": "a console run is in progress: one run "
                              "at a time"}]}
    got = client.post("/sandbox/experiments", data={"model": "beta"},
                      headers=JSON).json()
    assert (got["ok"], got["id"], got["url"]) == (False, None, None)
    assert [c["code"] for c in got["codes"]] == ["FIELD_MISSING", "MODEL_REF"]
    assert _flash() == "" and _claim() is None


# --------------------------------------------------------------- refusals

def _refused(code: str, c=client, **form) -> str:
    """A start refused: back to the gallery, no claim, its notice."""
    _no_flash()
    r = _start(c, **form)
    assert r.headers["location"] == "/sandbox", _flash()
    said = _flash()
    assert said.startswith("Not started: ") and f"({code})." in said, said
    assert ui_state._status.get("flash_kind") == "warn"
    return said


def test_each_refusal_carries_its_code_and_leaves_no_claim(world,
                                                          monkeypatch):
    from flubnf import bank
    calls = _weeks_run(monkeypatch)
    assert "'particles' is not an experiment field" in _refused(
        "FIELD_UNKNOWN", particles="200")
    assert 'oracle is "yes"; it is true or false' in _refused(
        "FIELD_TYPE", oracle="yes")
    assert 'size is ["smoke", "pilot"]' in _refused(
        "FIELD_TYPE", size=["smoke", "pilot"])
    _refused("SIZE_UNKNOWN", size="huge")
    _refused("MODEL_REF", model="beta")
    _refused("MODEL_NOT_FOUND", model="beta@9")
    _refused("SEASON_NO_WEEKS", season="1999-00")
    assert _claim() is None and not X.root().exists()
    # every other run holds the engine: MACHINE, about this computer
    busy = [
        (ui_state._status, "running", "all:20990101-000000",
         "a console run is in progress"),
        (ui_state._status, "running", "dataset-replay:20990101T000000Z",
         "a console run is in progress"),
        (ui_retro_seasons._retro_status, "2098-99", "running",
         "a retrospective replay is running (2098-99)"),
        (ui_state._sandbox_status, "running", "20990101-000000_mine",
         "sandbox run 20990101-000000_mine is still fitting"),
        (ui_state._sandbox_status, "claim", "mine",
         "a sandbox run of mine is being prepared"),
    ]
    for store, key, value, why in busy:
        with monkeypatch.context() as m:
            m.setitem(store, key, value)
            said = _refused("MACHINE", size="pilot", oracle="off")
            assert said == f"Not started: {why}: one run at a time (MACHINE).", said
            assert _claim() is None
    other = {"id": "beta-v1_2024-25_smoke", "settings": {}, "cancel": False}
    with monkeypatch.context() as m:
        m.setitem(ui_state._sandbox_status, "experiment", other)
        assert "experiment beta-v1_2024-25_smoke is replaying: one run at a " \
               "time" in _refused("MACHINE")
        assert _claim() is other
    with monkeypatch.context() as m:
        m.setattr(ui_pipeline, "_pf_engine_state", lambda: "absent")
        assert ("an experiment needs the particle-filter engine, which is "
                "not installed on this machine") in _refused("MACHINE")
    with monkeypatch.context() as m:
        def no_bank(stream):
            raise FileNotFoundError(f"no {stream} bank")
        m.setattr(bank, "read", no_bank)
        assert "no flusurv bank" in _refused("MACHINE")
    assert _claim() is None and calls == []
    assert not X.root().exists()
    # on and off read in any case (MACHINE: the settings were read), and a
    # file where a word goes is FIELD_TYPE
    with monkeypatch.context() as m:
        m.setitem(ui_state._status, "running", "all:20990101-000000")
        for word, eid in (("ON", SMOKE), ("False", "sihrs_2024-25_smoke")):
            got = client.post("/sandbox/experiments",
                              data={**FORM, "oracle": word},
                              headers=JSON).json()
            assert (got["id"], [c["code"] for c in got["codes"]]) == (
                eid, ["MACHINE"]), word
    _no_flash()
    r = client.post("/sandbox/experiments", data={"season": "2024-25"},
                    files={"model": ("m.txt", b"sihrs", "text/plain")},
                    follow_redirects=False)
    assert r.headers["location"] == "/sandbox"
    assert _flash() == ("Not started: model is null; it is text in quotes "
                        "(FIELD_TYPE).")
    assert _claim() is None and not X.root().exists()
    # the refused form comes back as posted, once
    with monkeypatch.context() as m:
        m.setitem(ui_state._status, "running", "all:20990101-000000")
        _refused("MACHINE", size="pilot", oracle="off")
    html = client.get("/sandbox").text
    assert [t for a, t in _options(html, "sbexp-size") if "selected" in a] == [
        "pilot: 10 locations, every other week (about 14 to 56 min)"]
    assert (' value="off" selected', "off (the Liu-West filter alone)") in \
        _options(html, "sbexp-oracle")
    html = client.get("/sandbox").text
    assert [t for a, t in _options(html, "sbexp-size") if "selected" in a] == [
        "smoke: 2 locations, 2 weeks (about 1 to 4 min)"]
    # another experiment's record in the folder: EXPERIMENT_CHANGED, and
    # the record stays as it was
    folder = X.root() / SMOKE
    retro.write_meta(folder, {"settings": {"experiment": "0" * 64}})
    before = _snapshot(X.root())
    assert "delete its folder to run it again" in _refused(
        "EXPERIMENT_CHANGED")
    assert _snapshot(X.root()) == before and _claim() is None


def test_a_start_of_a_replay_under_way_in_another_process_is_refused(
        world, monkeypatch):
    calls = _weeks_run(monkeypatch)
    # a terminal's start of the same experiment: its record under way, its
    # worker another live process
    folder = X.root() / SMOKE
    retro.write_meta(folder, {"status": "running",
                              "heartbeat_utc": time.time(),
                              "pid": os.getppid(),
                              "settings": {"experiment": SMOKE_FP}})
    before = _snapshot(X.root())
    said = _refused("MACHINE")
    assert said == (f"Not started: {SMOKE} is replaying in another process; "
                    "stop it first (MACHINE).")
    got = client.post("/sandbox/experiments", data=FORM, headers=JSON).json()
    assert got == {"ok": False, "id": SMOKE, "url": None, "started": False,
                   "text": said, "codes": [{
                       "code": "MACHINE", "tier": "machine",
                       "text": f"{SMOKE} is replaying in another process; "
                               "stop it first"}]}
    assert _claim() is None and calls == []
    assert _snapshot(X.root()) == before


def test_an_experiment_holds_the_engine_against_every_other_run(
        world, monkeypatch, tmp_path):
    import app.core.runs as runs_mod
    from app.core import data as core_data
    from app.core import datasets as D
    from app.ui import datasets_ui as DU
    from test_dataset_engines import grouped_bytes
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path / "state")
    # /run's vintage, as test_busy_guard's refusal finds one
    monkeypatch.setattr(core_data, "vintage_path", lambda d: tmp_path)
    sb.add_example("kinetics_example")
    r = client.post("/data/datasets",
                    files={"file": ("kids.csv", grouped_bytes(), "text/csv")},
                    data={"name": "Kids", "kind": "count"},
                    follow_redirects=False)
    ds = D.get(r.headers["location"].split("source=")[1].split("#")[0])
    started = []
    monkeypatch.setattr(ui_pipeline, "_run_all",
                        lambda spec: started.append(spec))
    monkeypatch.setattr(DU, "run_worker", lambda spec: started.append(spec))
    monkeypatch.setattr(DU, "replay_worker", lambda *a, **k: started.append(a))
    monkeypatch.setitem(ui_state._sandbox_status, "experiment",
                        {"id": SMOKE, "settings": X.read(FORM),
                         "cancel": False})
    why = f"experiment {SMOKE} is replaying"
    posts = [("/run", {"forecast_date": "2098-01-04", "locations": ["Ohio"]}),
             ("/retro/run", {"season": "2098-99"}),
             ("/sandbox/models/kinetics_example/run", {}),
             ("/run/dataset", {"dataset": ds.id,
                               "forecast_date": ds.forecast_dates()[-1],
                               "locations": "all", "engine": "analogue"}),
             ("/retro/dataset/run", {"dataset": ds.id})]
    form_before = dict(ui_state._last_form)
    # what another test left in the season claims stays as it was
    seasons_before = dict(ui_retro_seasons._retro_status)
    try:
        for url, data in posts:
            _no_flash()
            r = client.post(url, data=data, follow_redirects=False)
            assert r.status_code == 303, url
            assert why in _flash(), (url, _flash())
            assert "sandbox fit" not in _flash(), url
    finally:
        ui_state._last_form.clear()
        ui_state._last_form.update(form_before)
    assert not started and not ui_state._status.get("running")
    assert not ui_state._sandbox_status.get("running")
    assert ui_retro_seasons._retro_status == seasons_before


# ------------------------------------------------------ stop and resume

def _week_gate(monkeypatch):
    """retro.run_week faked (_weeks_run): the first week it fits waits on
    the returned gate, its folder written; `inside` is set once it
    waits."""
    gate, inside = threading.Event(), threading.Event()

    def after(root, asof):
        _sidecar(root, asof)
        if not inside.is_set():
            inside.set()
            assert gate.wait(60)
    return gate, inside, _weeks_run(monkeypatch, after)


def test_stop_cancels_and_flags_only_the_experiment(world, monkeypatch,
                                                    tmp_path):
    folder = X.root() / SMOKE
    rr = world_root()
    rr_before = _snapshot(rr) if rr.exists() else None
    # the page's Stop: STOP in the folder and the claim's cancel
    gate, inside, calls = _week_gate(monkeypatch)
    _start()
    assert inside.wait(60)
    _no_flash()
    r = client.post("/sandbox/stop", data={"experiment": SMOKE},
                    follow_redirects=False)
    assert r.headers["location"] == PAGE
    assert _flash() == (f"Stopping {SMOKE} after the fits in flight; "
                        "finished weeks are kept.")
    assert retro.stop_path(folder).exists() and _claim()["cancel"] is True
    gate.set()
    _join()
    assert [c["asof"] for c in calls] == SMOKE_WEEKS[:1]
    assert X.status(folder)["status"] == "stopped"
    assert not retro.stop_path(folder).exists() and _claim() is None
    # the guard modal's Stop, posted with no body (Resume fits the second
    # week): it stops, and says nothing
    gate, inside, calls = _week_gate(monkeypatch)
    _start()
    assert inside.wait(60)
    _no_flash()
    r = client.post("/sandbox/stop", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/sandbox"
    assert _flash() == ""
    assert retro.stop_path(folder).exists() and _claim()["cancel"] is True
    gate.set()
    _join()
    assert [c["asof"] for c in calls] == SMOKE_WEEKS[1:]
    assert not retro.stop_path(folder).exists() and _claim() is None
    # a Stop during the preflight: nothing starts
    shutil.rmtree(folder)
    pgate, pentered, _pc = _blocked(monkeypatch, "preflight")
    calls = _weeks_run(monkeypatch)
    out = {}
    t = threading.Thread(target=lambda: out.update(r=_start(TestClient(srv.app))))
    t.start()
    assert pentered.wait(60)
    assert _claim()["id"] == SMOKE
    client.post("/sandbox/stop", data={"experiment": SMOKE},
                follow_redirects=False)
    pgate.set()
    t.join(60)
    assert not t.is_alive()
    assert out["r"].headers["location"] == "/sandbox"
    assert f"{SMOKE} was stopped before it started." in _flash()
    assert _claim() is None and calls == []
    assert not [x for x in threading.enumerate()
                if x.name == f"experiment-{SMOKE}"]
    # a folder another process replays (a fresh heartbeat, a live pid not
    # this one's: a child that waits on its stdin): its STOP is written
    other = X.root() / "sihrs_2024-25_pilot_oracle"
    other.mkdir(parents=True)
    L.write_json(other / X.SETTINGS, {"model": "sihrs", "season": "2024-25",
                                      "size": "pilot"})
    child = subprocess.Popen([sys.executable, "-c",
                              "import sys; sys.stdin.read()"],
                             stdin=subprocess.PIPE)
    try:
        now = time.time()
        retro.write_meta(other, {"status": "running", "heartbeat_utc": now,
                                 "pid": child.pid, "started_utc": now,
                                 "settings": {"experiment": "e" * 64,
                                              "weeks": SMOKE_WEEKS}})
        assert X.status(other)["status"] == "running"
        _no_flash()
        r = client.post("/sandbox/stop", data={"experiment": other.name},
                        follow_redirects=False)
        stopping = X.status(other)["status"]
        # pressed again while it stops: the same words, in JSON when asked
        again = client.post("/sandbox/stop", data={"experiment": other.name},
                            headers=JSON).json()
    finally:
        child.stdin.close()
        child.wait(60)
    assert r.headers["location"] == f"/sandbox/experiments/{other.name}"
    assert retro.stop_path(other).exists()
    assert _flash().startswith(f"Stopping {other.name} after")
    assert stopping == "stopping"
    assert again == {"ok": True, "id": other.name,
                     "text": f"Stopping {other.name} after the fits in "
                     "flight; finished weeks are kept."}
    # nothing to stop
    _no_flash()
    r = client.post("/sandbox/stop", data={"experiment": SMOKE},
                    headers=JSON)
    assert r.json() == {"ok": False, "id": SMOKE,
                        "text": f"Nothing to stop: {SMOKE} is not replaying."}
    # a Stop that names an experiment never reaches a Sandbox fit, live or
    # being prepared: that is the guard modal's Stop, posted with no body
    stopped = []
    monkeypatch.setattr(sb, "run_dir", lambda run_id: run_id)
    monkeypatch.setattr(sb, "stop", stopped.append)
    for key, value in (("running", "20990101-000000_mine"), ("claim", "mine")):
        with monkeypatch.context() as m:
            m.setitem(ui_state._sandbox_status, key, value)
            got = client.post("/sandbox/stop", data={"experiment": SMOKE},
                              headers=JSON).json()
            assert got["ok"] is False and stopped == [], key
            assert ui_state._sandbox_status["cancel"] is False, key
    with monkeypatch.context() as m:
        m.setitem(ui_state._sandbox_status, "running", "20990101-000000_mine")
        client.post("/sandbox/stop", follow_redirects=False)
    assert stopped == ["20990101-000000_mine"]
    # the Retrospective's Stop never reaches an experiment
    retro.clear_flags(other)
    before = _snapshot(X.root())
    client.post("/retro/stop", follow_redirects=False)
    assert _snapshot(X.root()) == before
    assert (_snapshot(rr) if rr.exists() else None) == rr_before


def test_start_again_resumes_and_a_complete_one_fits_nothing(world,
                                                            monkeypatch):
    _replay(world_root() / "2024-25", weeks=SMOKE_WEEKS)

    def stop(root, asof):
        _sidecar(root, asof)
        retro.request_stop(root)
    _weeks_run(monkeypatch, stop)
    _start()
    _join()
    folder = X.root() / SMOKE
    assert X.status(folder)["weeks_done"] == 1
    calls = _weeks_run(monkeypatch, _sidecar)
    _no_flash()
    r = _start()
    assert r.headers["location"] == PAGE
    assert _flash() == f"Resumed {SMOKE}: 1 of 2 weeks were stored already."
    _join()
    assert [c["asof"] for c in calls] == SMOKE_WEEKS[1:]
    assert X.status(folder)["complete"] is True
    calls = _weeks_run(monkeypatch)
    _no_flash()
    r = _start()
    assert r.headers["location"] == PAGE
    assert _flash() == (f"{SMOKE} is complete: every week is stored, nothing "
                        "to fit.")
    assert ui_state._status.get("flash_kind") == "info"
    assert _claim() is None and calls == []
    assert not [t for t in threading.enumerate()
                if t.name == f"experiment-{SMOKE}"]


def test_a_resume_waits_for_the_folders_scoring(world, monkeypatch):
    def stop(root, asof):
        _sidecar(root, asof)
        retro.request_stop(root)
    _weeks_run(monkeypatch, stop)
    _start()
    _join()
    # the summary goes stale, and a view starts its rescore
    (X.root() / SMOKE / X.SUMMARY).unlink()
    sgate, sentered, scalls = _blocked(monkeypatch, "score")
    monkeypatch.setattr(ui_sandbox, "_SCORE_GRACE_S", 0.05)
    assert "Scoring: not scored yet…" in client.get(PAGE).text
    assert sentered.wait(60)
    # Resume: claimed at once, but the replay waits for that scoring
    rgate, rentered, _rc = _blocked(monkeypatch, "replay")
    rgate.set()
    _weeks_run(monkeypatch, _sidecar)
    _start()
    assert _claim()["id"] == SMOKE
    assert not rentered.wait(0.3)
    sgate.set()
    assert rentered.wait(60)
    _join()
    assert X.status(X.root() / SMOKE)["complete"] is True
    assert len(scalls) == 2             # the view's, then the segment end's


def test_the_experiment_never_writes_the_shipped_tree_end_to_end(
        world, monkeypatch):
    locs = list(X.SMOKE_LOCATIONS)
    root = _shipped_root(world_root(),
                         pf={w: _q(12.0, locs) for w in SMOKE_WEEKS},
                         null={w: _q(11.0, locs) for w in SMOKE_WEEKS})
    _age(root)
    before = _snapshot(root)
    _weeks_run(monkeypatch, _sidecar)
    _start()
    _join()
    summary = X.read_summary(X.root() / SMOKE / X.SUMMARY)
    assert summary["shipped"]["root"] == str(root)
    assert summary["cells"]["compared"] == 2 * 2 * 4
    assert _snapshot(root) == before
    # and a view's rescore reads it the same way
    os.utime(X.root() / SMOKE / X.SUMMARY, (1.0, 1.0))
    assert X.stale(X.root() / SMOKE)
    client.get(PAGE)
    _join()
    assert _snapshot(root) == before


# ------------------------------------------------------- the compare page

def _hand_written(monkeypatch, target, *, overall=None, **over) -> Path:
    """BETA's folder with two stored weeks, a shipped replay of 2024-25
    (the Liu-West filter) both older than a hand-written summary.json
    whose truth hash and times hold, so stale() says nothing."""
    folder = _experiment({w: _q(10.0) for w in SMOKE_WEEKS})
    root = _shipped_root(world_root(), null={w: _q(12.0) for w in SMOKE_WEEKS})
    _age(folder, root)
    groups = {"by_location": {"Alaska": _sums(30.0, 6.0, n=40),
                              "Texas": _sums(25.0, 6.0, n=40),
                              "Vermont": _sums(20.0, 6.0, n=20)},
              "by_week": {SMOKE_WEEKS[0]: _sums(40.0, 9.0, n=50),
                          SMOKE_WEEKS[1]: _sums(35.0, 9.0, n=50)},
              "by_horizon": {str(h): _sums(18.75, 4.5, n=25)
                             for h in range(4)}}
    summary = {
        "complete": True, "id": BETA, "experiment": "e" * 64,
        "model": "beta2@3", "model_fingerprint": "m" * 64,
        "season": "2024-25", "size": "smoke", "oracle": False,
        "ran": {"locations": ["Alaska", "Texas", "Vermont"],
                "weeks": SMOKE_WEEKS, "replicates": 1, "particles": 10_000,
                "failed_fits": 0, "seconds": 3725.0,
                "started_utc": "2026-11-04T14:59:51Z",
                "finished_utc": "2026-11-04T16:01:56Z",
                "disk_bytes": 3_481_920, "engine_build": {},
                "flubnf_build": "53f1acf"},
        "shipped": {"member": "pf_filter", "root": str(root),
                    "started_utc": X._utc(S1), "replicates": 3,
                    "particles": 10_000, "engine_build": {}},
        "scored": {"utc": "2026-11-04T16:02:05Z", "truth": "settled",
                   "truth_sha256": sha256_of(target),
                   "scores_v": retro.SCORES_V},
        "cells": {"compared": 100, "model_only": 0, "shipped_only": 4},
        "overall": overall or _sums(75.0, 18.0), **groups, "us": None,
        "failures": []}
    summary.update(over)
    X.write_summary(folder, summary)
    return folder


def _no_scoring(monkeypatch):
    def never(*a, **k):
        raise AssertionError("the page scored")
    monkeypatch.setattr(scoring, "score_quantiles", never)
    monkeypatch.setattr(scoring, "load_truth", never)


def test_the_compare_page_reads_summary_json_only(world, truth, monkeypatch):
    folder = _hand_written(monkeypatch, truth)
    assert X.stale(folder) == ""
    _no_scoring(monkeypatch)
    html = client.get(f"/sandbox/experiments/{BETA}").text
    head = html.split('id="h-sbx-scores"', 1)[1]
    table = head.split("<table", 1)[1].split("</table>", 1)[0]
    rows = re.findall(r"<tr><th scope=\"row\">([^<]*)</th>(.*?)</tr>", table)
    assert [n for n, _c in rows] == ["beta2@3",
                                     "Shipped: Liu-West filter alone",
                                     "beta2@3 vs shipped"]
    model, shipped, vs = (c for _n, c in rows)
    assert '<span class="relwis ok">0.750</span>' in model
    assert '<span class="relwis ok">0.900</span>' in model     # 18 / 20
    assert re.findall(r'<td class="num cov-(\w+)">(\d+%)</td>', model) == [
        ("ok", "48%"), ("ok", "79%"), ("ok", "96%")]
    assert '<span class="relwis ok">0.800</span>' in shipped
    assert f'<span class="relwis ok">{75 / 80:.3f}</span>' in vs
    assert f'<span class="relwis ok">{18 / 19:.3f}</span>' in vs
    assert vs.count("<td class=\"num\">—</td>") == 3
    assert ('<p class="hint">100 cells compared; left out: 4 only the '
            'shipped replay scored, 0 only this model scored. This model ran '
            '1 replicate, the shipped replay 3.</p>') in html
    for fold, n, head_word in (("sbx-loc", 3, "Location"),
                               ("sbx-week", 2, "As of"),
                               ("sbx-hz", 4, "Horizon")):
        part = html.split(f'id="{fold}"', 1)[1].split("</details>", 1)[0]
        assert f"({n})</span>" in part
        assert part.count('colspan="2"') == 2
        assert f'<th rowspan="2" scope="col">{head_word}</th>' in part
        assert part.split("</thead>", 1)[0].count('<th class="num">') == 4
        assert part.count("<tr><td>") == n
    loc = html.split('id="sbx-loc"', 1)[1].split("</details>", 1)[0]
    assert "<tr><td>Alaska</td><td class=\"num\">0.300</td>" in loc  # 30/100
    ran = html.split('id="sbx-ran"', 1)[1].split("</details>", 1)[0]
    assert ran.count('<div class="uk-stat">') == 9
    for said in ("eeeeeeee", "3: Alaska, Texas, Vermont",
                 "2, 2024-12-28 to 2025-01-11",
                 "1 replicate of 10,000 particles a location-week",
                 "1:02:05 active, 2026-11-04 14:59:51 to 2026-11-04 16:01:56 "
                 "UTC", "3.3 MB", "engine not recorded · FluBNF 53f1acf",
                 f"the shipped replay of 2024-25 started "
                 f"{X._utc(S1).replace('T', ' ')[:-1]} UTC "
                 f"({world_root() / '2024-25'}): the Liu-West filter alone, "
                 "3 replicates of 10,000 particles",
                 f"2026-11-04 16:02:05 UTC against settled truth "
                 f"({sha256_of(truth)[:8]}), cell rule version "
                 f"{retro.SCORES_V}"):
        assert said in ran, said
    assert 'id="sbx-fail"' not in html and "Nothing to compare" not in html
    # the file is what the page shows
    _hand_written_again(folder, overall=_sums(50.0, 18.0))
    assert X.stale(folder) == ""
    html = client.get(f"/sandbox/experiments/{BETA}").text
    assert '<span class="relwis ok">0.500</span>' in html
    api = client.get(f"/api/sandbox/experiments/{BETA}").json()
    assert api["summary"] == json.loads(
        (folder / X.SUMMARY).read_text(encoding="utf-8"))
    assert api["figures"]["overall"]["model"]["rel"] == 0.5
    assert api["figures"]["us"] is None and api["problem"] == ""
    assert (api["live"], api["claimed"]) == (False, False)
    assert api["settings"] == {"model": "beta2@3", "season": "2024-25",
                               "size": "smoke", "oracle": False}


def _hand_written_again(folder: Path, **over) -> None:
    obj = json.loads((folder / X.SUMMARY).read_text(encoding="utf-8"))
    obj.update(over)
    X.write_summary(folder, obj)


def _record(folder: Path, status: str, **more) -> None:
    """BETA's run record, rewritten with another status."""
    meta = retro.read_meta(folder)
    retro.write_meta(folder, {**meta, "status": status, **more})


def test_the_page_words(world, truth, monkeypatch):
    url = f"/sandbox/experiments/{BETA}"
    folder = _hand_written(monkeypatch, truth)
    # the state, one alert, with Resume
    shutil.rmtree(folder / "weeks" / SMOKE_WEEKS[1])
    monkeypatch.setattr(X, "stale", lambda folder: "")
    resume = ('<input type="hidden" name="model" value="beta2@3"><input '
              'type="hidden" name="season" value="2024-25"><input '
              'type="hidden" name="size" value="smoke"><input type="hidden" '
              'name="oracle" value="off"><button class="gold" '
              'data-guard="sandbox-run">Resume</button>')
    cases = [
        ({"status": "stopped"}, "warn", "Stopped after 1 of 2 weeks.",
         "Finished weeks and fits are kept; Resume goes on from them."),
        ({"status": "stopped",
          "stop_reason": "the engine build changed since the week before"},
         "warn", "Stopped after 1 of 2 weeks.",
         "the engine build changed since the week before"),
        ({"status": "running", "heartbeat_utc": 1.0}, "warn",
         "Interrupted after 1 of 2 weeks.",
         "The console closed while it replayed. Finished weeks are kept; "
         "Resume goes on from them."),
        ({"status": "done"}, "warn", "Done, with 1 of 2 weeks stored.",
         "The others failed (see the failed fits below); Resume tries them "
         "again."),
        ({"status": "error: all 2 PF fits failed (first: x); the week is "
          "not stored"}, "error", "Every week failed.",
         "all 2 PF fits failed (first: x); the week is not stored. Resume "
         "tries them again once that is fixed."),
    ]
    for more, kind, title, text in cases:
        _record(folder, **more)
        html = client.get(url).text
        alert = html.split('id="sbx-state"', 1)[1].split("</div>", 1)[0]
        assert html.count('id="sbx-state"') == 1
        assert f'class="uk-alert uk-alert--{kind}"' in html.split(
            'id="sbx-state"', 1)[0].rsplit("<div", 1)[1]
        assert f"<strong>{title}</strong> {text}" in alert, (title, alert)
        assert resume in alert
        assert "Delete experiment" in html
    # complete and done: no state alert
    _record(folder, "done")
    shutil.copytree(folder / "weeks" / SMOKE_WEEKS[0],
                    folder / "weeks" / SMOKE_WEEKS[1])
    html = client.get(url).text
    assert 'id="sbx-state"' not in html and "uk-badge--ok" in html
    # no run record: Start
    retro.meta_path(folder).unlink()
    html = client.get(url).text
    alert = html.split('id="sbx-state"', 1)[1].split("</div>", 1)[0]
    assert "<strong>Not started yet.</strong>" in alert
    assert 'data-guard="sandbox-run">Start</button>' in alert
    # nothing to compare with, and the US not compared on a full
    _record(folder, "done")
    _hand_written_again(folder, shipped=None)
    html = client.get(url).text.replace("&#39;", "'")
    assert ("<strong>Nothing to compare with.</strong> No shipped replay of "
            "2024-25 here holds the Liu-West filter alone on the shipped "
            "settings, so these figures are this model's against the "
            "FluSight baseline only.") in html
    assert "<h2 id=\"h-sbx-scores\">Scores</h2>" in html
    assert '<p class="hint">100 cells scored.</p>' in html
    _hand_written_again(folder, shipped={
        "member": "pf", "root": str(world_root() / "2024-25"),
        "started_utc": X._utc(S1), "replicates": 3, "particles": 10_000,
        "engine_build": {}}, size="full",
        ran={**json.loads((folder / X.SUMMARY).read_text(
            encoding="utf-8"))["ran"], "locations": ["Alaska", "US"]})
    html = client.get(url).text
    assert ('<p class="hint">US national: not compared. The shipped '
            "replay's US forecast for these weeks is not of the same kind as "
            "this one's: it was stored before addendum A3 (2026-10-01).</p>"
            ) in html
    assert "<h2 id=\"h-sbx-scores\">Against the shipped replay</h2>" in html
    # a US group compared: the second tbody
    _hand_written_again(folder, us=_sums(5.0, 1.0, n=8))
    html = client.get(url).text
    assert '<th colspan="6" scope="rowgroup">US national</th>' in html
    assert "US national: not compared" not in html
    # the failed fits
    _hand_written_again(folder, ran={**json.loads((folder / X.SUMMARY)
                                                  .read_text("utf-8"))["ran"],
                                     "failed_fits": 4},
                        failures=[{"week": SMOKE_WEEKS[0], "text": "boom"},
                                  {"week": SMOKE_WEEKS[1],
                                   "location": "Texas", "text": "gone"},
                                  {"week": SMOKE_WEEKS[1],
                                   "location": "Vermont", "replicate": 0,
                                   "text": "FAIL: x"}])
    html = client.get(url).text
    fails = html.split('id="sbx-fail"', 1)[1].split("</details>", 1)[0]
    assert "4 fits had no forecast" in fails
    assert (f"<tr><td>{SMOKE_WEEKS[0]}</td><td>the whole week</td><td "
            'class="num"></td><td>boom</td></tr>') in fails
    assert (f"<tr><td>{SMOKE_WEEKS[1]}</td><td>Texas</td><td class=\"num\">"
            "</td><td>gone</td></tr>") in fails
    assert (f"<tr><td>{SMOKE_WEEKS[1]}</td><td>Vermont</td><td "
            'class="num">0</td><td>FAIL: x</td></tr>') in fails
    # a newer FluBNF's summary: never overwritten, and said
    raw = json.loads((folder / X.SUMMARY).read_text(encoding="utf-8"))
    (folder / X.SUMMARY).write_text(json.dumps({**raw, "format_version": 2}),
                                    encoding="utf-8", newline="\n")
    html = client.get(url).text
    assert ("summary.json was written by a newer FluBNF (format_version 2); "
            "this one reads 1 only.") in html
    assert 'id="h-sbx-scores"' not in html
    # scoring: pending, then failed
    (folder / X.SUMMARY).unlink()
    monkeypatch.setattr(X, "stale", lambda folder: "not scored yet")
    gate, entered, _c = _blocked(monkeypatch, "score")
    monkeypatch.setattr(ui_sandbox, "_SCORE_GRACE_S", 0.05)
    html = client.get(url).text
    assert ('class="uk-alert uk-alert--info" id="sbx-scoring" role="status">'
            in html)
    assert "Scoring: not scored yet…" in html and 'data-poll="1"' in html
    assert "Delete experiment" not in html
    gate.set()
    _join()

    def boom(folder, **kw):
        raise RuntimeError("no FluSight-baseline here")
    monkeypatch.setattr(X, "score", boom)
    monkeypatch.setattr(ui_sandbox, "_SCORE_GRACE_S", 60.0)
    html = client.get(url).text
    assert "Not scored: no FluSight-baseline here" in html
    assert 'class="uk-alert uk-alert--error" id="sbx-scoring"' in html
    _join()
    # no week stored
    shutil.rmtree(folder / "weeks")
    monkeypatch.setattr(X, "stale", lambda folder: "")
    html = client.get(url).text
    assert 'id="sbx-none"' in html and "No week stored yet" in html


def test_the_page_says_a_comparison_across_engines(world, truth,
                                                   monkeypatch):
    url = f"/sandbox/experiments/{BETA}"
    folder = _hand_written(monkeypatch, truth)
    monkeypatch.setattr(X, "stale", lambda folder, **k: "")
    _no_scoring(monkeypatch)
    raw = json.loads((folder / X.SUMMARY).read_text(encoding="utf-8"))
    ran, shipped = raw["ran"], raw["shipped"]
    public = {"branch": "lanl/PyBNF", "commit": "8410f794", "dirty": False,
              "source": "wheel", "engine": "public"}
    said = ("Compared across engines: this experiment ran on the {} engine, "
            "the shipped replay on the {} one.")
    # both on the private engine (no engine recorded): nothing more
    assert "across engines" not in client.get(url).text
    _hand_written_again(folder, ran={**ran, "engine_build": public})
    html = client.get(url).text
    # one line, under the comparison's own
    assert ("the shipped replay 3.</p>\n <p class=\"hint\">"
            + said.format("public", "private") + "</p>") in html
    assert html.count("across engines") == 1
    _hand_written_again(folder, ran=ran,
                        shipped={**shipped, "engine_build": public})
    assert said.format("private", "public") in client.get(url).text
    _hand_written_again(folder, ran={**ran, "engine_build": public})
    assert "across engines" not in client.get(url).text
    # nothing compared, nothing to say
    _hand_written_again(folder, shipped=None)
    assert "across engines" not in client.get(url).text


def test_the_page_opens_while_the_claim_has_no_folder_yet(world):
    ui_state._sandbox_status["experiment"] = {
        "id": SMOKE, "settings": X.read(FORM), "cancel": False}
    r = client.get(PAGE)
    assert r.status_code == 200
    html = r.text
    assert '<p class="runstat" id="sbx-line" aria-live="polite">Starting…</p>' \
        in html
    assert "uk-badge--pending" in html and ">starting<" in html
    meta = html.split('<ul class="uk-meta">', 1)[1].split("</ul>", 1)[0]
    assert re.findall(r"<li>([^<]*)</li>", meta) == [
        "sihrs", "2024-25", "smoke", "Oracle step on"]
    assert 'data-poll="1"' in html and "Delete experiment" not in html
    # the running card says where it is: no "No week stored yet" beside it
    assert 'data-status=""' in html and 'id="sbx-none"' not in html
    assert 'name="experiment" value="sihrs_2024-25_smoke_oracle"' in html
    api = client.get(f"/api{PAGE}").json()
    assert (api["live"], api["claimed"], api["status"]["line"]) == (
        True, True, "Starting…")
    assert not X.root().exists()


def _st(status: str, **more) -> dict:
    """A replay's state as experiments.status gives it: 2 of 5 weeks
    stored, 21:50 so far."""
    return {"status": status, "error": "", "stop_reason": "",
            "weeks_total": 5, "weeks_done": 2, "complete": False,
            "week": None, "fits_done": 0, "fits_total": 0,
            "elapsed_s": 1310.4, "eta_s": None, "started_utc": None,
            "finished_utc": None, **more}


def test_the_running_line_and_the_badge_of_each_state():
    line, badge = ui_sandbox._experiment_line, ui_sandbox._experiment_badge
    running = _st("running", week="2024-12-14", fits_done=4, fits_total=10)
    assert line(running, True) == "2024-12-14: 4 of 10 fits · 21:50 so far"
    assert line({**running, "eta_s": 2100.0}, False) == (
        "2024-12-14: 4 of 10 fits · 21:50 so far · about 35:00 left")
    assert line(_st("stopping"), True) == ("Stopping after the fits in "
                                           "flight · 21:50 so far")
    assert line(_st("paused"), False) == "Paused · 21:50 so far"
    # claimed, the record not under way yet (a first start, or a resume)
    for state in ("", "stopped"):
        assert line(_st(state), True) == "Starting…", state
    for state in ("", "stopped", "interrupted", "done", "error"):
        assert line(_st(state), False) == "", state
    whole = {"complete": True, "weeks_done": 5}
    for st, claimed, want in (
            (_st(""), True, ("pending", "starting")),
            (_st("done", **whole), True, ("pending", "starting")),
            (running, True, ("pending", "running")),
            (_st("stopping"), False, ("pending", "stopping")),
            (_st("paused"), False, ("warn", "paused")),
            (_st("stopped"), False, ("warn", "stopped · 2 of 5 weeks")),
            (_st("stopped", **whole), False, ("warn", "stopped")),
            (_st("interrupted"), False, ("warn", "interrupted · 2 of 5 weeks")),
            (_st("done", **whole), False, ("ok", "done")),
            (_st("done"), False, ("warn", "done · 2 of 5 weeks")),
            (_st("error", error="x"), False, ("error", "error")),
            (_st(""), False, ("neutral", "not started"))):
        assert badge(st, claimed) == want, (st["status"], claimed)


def test_a_stale_summary_is_rescored_once_and_never_while_live(world,
                                                             monkeypatch):
    folder = _experiment({w: _q(10.0) for w in SMOKE_WEEKS})
    assert X.stale(folder) == "not scored yet"
    gate, entered, calls = _blocked(monkeypatch, "score")
    monkeypatch.setattr(ui_sandbox, "_SCORE_GRACE_S", 0.05)
    url = f"/sandbox/experiments/{BETA}"
    client.get(url)
    assert entered.wait(60)
    job = ui_sandbox._experiment_scores[BETA]
    client.get(url)
    client.get(f"/api{url}")
    assert ui_sandbox._experiment_scores[BETA] is job and len(calls) == 1
    gate.set()
    _join()
    (folder / X.SUMMARY).unlink()
    # while this console replays it, or while its files say it replays
    ui_state._sandbox_status["experiment"] = {
        "id": BETA, "settings": X.read(folder / X.SETTINGS), "cancel": False}
    html = client.get(url).text
    assert ui_sandbox._experiment_scores[BETA] is job and len(calls) == 1
    assert "<h2>Running</h2>" in html
    ui_state._sandbox_status["experiment"] = None
    now = time.time()
    _record(folder, "running", heartbeat_utc=now, pid=os.getpid())
    client.get(url)
    assert ui_sandbox._experiment_scores[BETA] is job and len(calls) == 1
    _record(folder, "done")
    client.get(url)
    _join()
    assert len(calls) == 2 and (folder / X.SUMMARY).is_file()


def test_delete_needs_the_id_and_refuses_while_live_or_scored(world,
                                                             monkeypatch):
    folder = _experiment({w: _q(10.0) for w in SMOKE_WEEKS})
    url = f"/sandbox/experiments/{BETA}/delete"
    monkeypatch.setattr(X, "stale", lambda folder: "")
    r = client.post(url, follow_redirects=False)
    assert r.headers["location"] == f"/sandbox/experiments/{BETA}"
    assert _flash() == ("Not deleted: the confirmation did not name the "
                        "experiment.")
    _no_flash()
    ui_state._sandbox_status["experiment"] = {
        "id": BETA, "settings": X.read(folder / X.SETTINGS), "cancel": False}
    client.post(url, data={"confirm": BETA}, follow_redirects=False)
    assert _flash() == f"Not deleted: {BETA} is replaying; stop it first"
    ui_state._sandbox_status["experiment"] = None
    gate, entered, _c = _blocked(monkeypatch, "score")
    monkeypatch.setattr(X, "stale", lambda folder: "not scored yet")
    monkeypatch.setattr(ui_sandbox, "_SCORE_GRACE_S", 0.05)
    client.get(f"/sandbox/experiments/{BETA}")
    assert entered.wait(60)
    got = client.post(url, data={"confirm": BETA}, headers=JSON).json()
    assert got == {"ok": False, "id": BETA, "codes": [],
                   "text": f"Not deleted: {BETA} is being scored; delete it "
                   "once that is done"}
    gate.set()
    _join()
    assert folder.is_dir()
    monkeypatch.setattr(X, "stale", lambda folder: "")
    n = retro.dir_size(folder)
    _no_flash()
    r = client.post(url, data={"confirm": BETA}, follow_redirects=False)
    assert r.headers["location"] == "/sandbox"
    assert _flash() == f"Deleted {BETA}; {retro.human_bytes(n)} freed."
    assert not folder.exists() and X.root().is_dir()
    # in JSON, with the bytes freed
    folder = _experiment({w: _q(10.0) for w in SMOKE_WEEKS})
    n = retro.dir_size(folder)
    _no_flash()
    got = client.post(url, data={"confirm": BETA}, headers=JSON).json()
    assert got == {"ok": True, "id": BETA, "freed": n,
                   "text": f"Deleted {BETA}; {retro.human_bytes(n)} freed."}
    assert not folder.exists() and _flash() == ""
    # an unknown id
    r = client.get("/api/sandbox/experiments/nope")
    assert r.status_code == 404
    assert r.json() == {"error": "no experiment is named 'nope'"}
    _no_flash()
    r = client.get(f"/sandbox/experiments/{BETA}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/sandbox"
    assert _flash() == f"Not opened: no experiment is named '{BETA}'."


# ------------------------------------------------- the guard modal, marks

def test_the_guard_modal_names_an_experiment(tmp_path):
    html = client.get("/data").text
    funcs = html[html.index("function retroConflict(b)"):
                 html.index("function conflictFor(kind,b)")]
    exp = funcs[funcs.index("function experimentConflict(b)"):
                funcs.index("function sandboxConflict(b)")]
    for word in ("retrospective", "console", "no results"):
        assert word not in exp
    rules = html[html.index("function conflictFor(kind,b)"):]
    rules = rules[:rules.index("function proceed(el)")]
    for kind in ("console-run", "retro-run", "sandbox-run"):
        rule = rules.split(f"kind==='{kind}'", 1)[1].split("if(kind", 1)[0]
        assert "experimentConflict(b)||sandboxConflict(b)" in "".join(
            rule.split()), kind
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        pytest.skip("node not available")
    drv = tmp_path / "guard.js"
    drv.write_text(funcs + "\nvar c = experimentConflict({experiment: '"
                   + SMOKE + "'});\nconsole.log(JSON.stringify([c.label, "
                   "c.hint, c.stop, c.done({experiment: null}), "
                   "c.done({experiment: 'x'}), experimentConflict({})]));\n",
                   encoding="utf-8", newline="\n")
    out = subprocess.run([node, str(drv)], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    label, hint, stop, done, busy, none = json.loads(out.stdout)
    assert label == f"experiment ({SMOKE})"
    assert hint == ("An experiment stopped now keeps its finished weeks; "
                    "Resume on its page goes on from them.")
    assert stop == "/sandbox/stop"
    assert (done, busy, none) == (True, False, None)


def test_one_question_mark_on_the_page(world, truth, monkeypatch):
    _hand_written(monkeypatch, truth, failures=[
        {"week": SMOKE_WEEKS[0], "text": "boom"}], us=_sums(5.0, 1.0, n=8))
    html = client.get(f"/sandbox/experiments/{BETA}").text
    assert 'id="sbx-fail"' in html and "US national" in html
    # the page's own content (the season fixture's BNG2.pl fake answers
    # git too, so base.html's banner says an update was pulled)
    assert marks(html.split('<div id="sbx"', 1)[1]) == ["tip-sbx-scores"]


# ------------------------------------- the default role, as on 24ac926

#: the pages the golden test rendered (read by its --write-golden)
PAGES: dict = {}


def _golden_world(monkeypatch) -> dict:
    """The default role's fixed world, nothing in it a time or a path
    of this run: one registered model (its working copy gone, so no file
    time shows), a shipped replay of 2024-25 to compare with, and three
    experiments at fixed times: BETA done and scored (a hand-written
    summary), the shipped smoke stopped after one of its two weeks, and a
    pilot never started. {page name: its URL}."""
    from app.ui.templating import templates
    monkeypatch.setitem(templates.env.globals, "restart_needed",
                        lambda: False)
    monkeypatch.setattr(sb, "_stamp", lambda: "2026-10-30T12:00:02Z")
    _register("beta")
    shutil.rmtree(sb.MODELS / "beta")
    _shipped_root(world_root(), null={w: _q(12.0) for w in SMOKE_WEEKS})
    beta = _experiment({w: _q(10.0) for w in SMOKE_WEEKS})
    retro.write_meta(beta, {**retro.read_meta(beta), "started_utc": S1 + 300,
                            "finished_utc": S1 + 400})
    X.write_summary(beta, {
        "complete": True, "id": BETA, "experiment": "e" * 64,
        "model": "beta2@3", "model_fingerprint": "m" * 64,
        "season": "2024-25", "size": "smoke", "oracle": False,
        "ran": {"locations": ["Alaska", "Texas", "Vermont"],
                "weeks": SMOKE_WEEKS, "replicates": 1, "particles": 10_000,
                "failed_fits": 1, "seconds": 3725.0,
                "started_utc": "2026-11-04T14:59:51Z",
                "finished_utc": "2026-11-04T16:01:56Z",
                "disk_bytes": 3_481_920, "engine_build": {},
                "flubnf_build": "53f1acf"},
        "shipped": {"member": "pf_filter", "root": "app/state/retro/2024-25",
                    "started_utc": "2026-09-23T19:58:19Z", "replicates": 3,
                    "particles": 10_000, "engine_build": {}},
        "scored": {"utc": "2026-11-04T16:02:05Z", "truth": "settled",
                   "truth_sha256": "a" * 64, "scores_v": 2},
        "cells": {"compared": 100, "model_only": 0, "shipped_only": 4},
        "overall": _sums(75.0, 18.0),
        "by_location": {"Alaska": _sums(30.0, 6.0, n=40),
                        "Texas": _sums(25.0, 6.0, n=40),
                        "Vermont": _sums(20.0, 6.0, n=20)},
        "by_week": {SMOKE_WEEKS[0]: _sums(40.0, 9.0, n=50),
                    SMOKE_WEEKS[1]: _sums(35.0, 9.0, n=50)},
        "by_horizon": {str(h): _sums(18.75, 4.5, n=25) for h in range(4)},
        "us": None,
        "failures": [{"week": SMOKE_WEEKS[1], "location": "Texas",
                      "replicate": 0, "text": "the fit stopped"}]})
    smoke = X.root() / SMOKE
    smoke.mkdir(parents=True)
    L.write_json(smoke / X.SETTINGS, json.loads(X.settings_text(FORM)))
    retro.write_meta(smoke, {
        "status": "stopped", "started_utc": S1 + 200,
        "finished_utc": S1 + 250, "elapsed_s": 50.0,
        "settings": {"experiment": "f" * 64, "model_fingerprint": "s" * 64,
                     "model": "sihrs", "weeks": SMOKE_WEEKS,
                     "locations": ["California", "Vermont"],
                     "replicates": 1, "particles": 10_000}})
    _store(smoke, SMOKE_WEEKS[0], {"pf": _q(10.0)})
    pilot = {"model": "sihrs-natg", "season": "2024-25", "size": "pilot"}
    idle = X.root() / X.experiment_id(pilot)
    idle.mkdir()
    L.write_json(idle / X.SETTINGS, json.loads(X.settings_text(pilot)))
    os.utime(idle / X.SETTINGS, (S1, S1))
    monkeypatch.setattr(X, "stale", lambda folder, **k: "")
    _no_scoring(monkeypatch)
    return {"gallery": "/sandbox",
            "compare": f"/sandbox/experiments/{BETA}",
            "stopped": PAGE,
            "not_started": f"/sandbox/experiments/{idle.name}"}


def _main(html: str) -> str:
    """A page's <main>: what the routes and the page's own template draw
    (base.html's head, menus and footer around it are not theirs)."""
    return re.search(r'<main id="main".*?</main>', html, re.S).group(0)


def test_the_default_role_pages_are_as_on_24ac926(world, truth, tmp_path,
                                                  monkeypatch):
    urls = _golden_world(monkeypatch)
    pages = {}
    for name, url in urls.items():
        r = client.get(url, follow_redirects=False)
        assert r.status_code == 200, (url, r.status_code)
        pages[name] = _main(r.text)
        assert str(tmp_path) not in pages[name], name
    PAGES.update(pages)
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))["pages"]
    assert sorted(pages) == sorted(want)
    for name in want:
        assert pages[name] == want[name], name
    # not vacuous: each page is the one meant
    assert 'id="h-sb-exp"' in pages["gallery"]
    assert pages["gallery"].count('<a href="/sandbox/experiments/') == 3
    assert '<span class="relwis ok">0.750</span>' in pages["compare"]
    assert 'id="sbx-fail"' in pages["compare"]
    assert "Stopped after 1 of 2 weeks." in pages["stopped"]
    assert 'data-guard="sandbox-run">Resume</button>' in pages["stopped"]
    assert "Not started yet." in pages["not_started"]


# ---------------------------- in a student's folder on the runner computer

GiB = runner.GiB
#: a pid no process has (above every pid_max)
DEAD = 2_147_483_646
#: a refusal the runner records at dispatch
LINKED = (f"experiments/{SMOKE}/weeks/2024-12-28 is a link, and the runner "
          "follows no link in a student folder (MACHINE)")


@pytest.fixture
def alice(world, students, monkeypatch) -> Path:
    """This console is alice's on the runner computer (the students' Mac
    Studio): its Sandbox her folder under STUDENTS, the runner running
    with the world's replay roots as its retro root, room on the disk,
    and the Mac Studio's shard width. Her Sandbox folder."""
    top = student(students, "alice")
    monkeypatch.setattr(sb, "SANDBOX", top)
    monkeypatch.setattr(sb, "MODELS", top / "models")
    monkeypatch.setattr(sb, "RUNS", top / "runs")
    monkeypatch.setattr(runner, "_free", lambda: 500 * GiB)
    monkeypatch.setattr(pf, "DEFAULT_SHARD_WIDTH", 16)
    runner_state(students, retro_root=str(world_root()))
    return top


def _no_console_run(monkeypatch) -> None:
    """This console replays, preflights and claims the engine never."""
    def never(*a, **k):
        raise AssertionError("this console ran the experiment")
    for name in ("replay", "run", "preflight"):
        monkeypatch.setattr(X, name, never)
    monkeypatch.setattr(ui_pipeline, "_pf_engine_state", never)


def _detail() -> str:
    return ui_state._status.get("flash_detail") or ""


def _line(html: str) -> str:
    return re.search(r'<p class="runstat" id="sbx-line" aria-live="polite">'
                     r"([^<]*)</p>", html).group(1)


def _title_badge(html: str) -> tuple:
    head = html.split('id="h-sbx-title"', 1)[1].split("</div>", 1)[0]
    return (re.search(r'data-state="(\w+)"', head).group(1),
            re.search(r'<span class="uk-badge-t">([^<]*)</span>', head
                      ).group(1))


def test_in_a_runner_folder_start_queues_and_claims_nothing(alice,
                                                            monkeypatch):
    _replay(world_root() / "2024-25", weeks=SMOKE_WEEKS)
    _no_console_run(monkeypatch)
    # Start carries no guard: the modal would offer to stop her own fit
    form = _form(client.get("/sandbox").text)
    assert form.count("<button") == 1 and "data-guard" not in form
    assert '<button class="gold">Start</button>' in form
    r = _start()
    assert r.headers["location"] == PAGE
    est = runner.estimate(FORM, weeks=SMOKE_WEEKS)
    runs = sb.eta_words(est["seconds"], est["seconds"])
    peak, keep = (retro.human_bytes(est[k])
                  for k in ("peak_bytes", "keep_bytes"))
    assert _flash() == f"Queued {SMOKE}: 1st in line on the runner."
    assert ui_state._status.get("flash_kind") == "ok"
    assert _detail() == (
        f"It runs {runs} once it starts (a first estimate: no smoke has "
        "finished on this computer yet). It starts within a minute. While it "
        f"runs it needs about {peak} of disk and keeps about {keep}. "
        "Compared with the shipped replay of 2024-25 (the Oracle SIHRS) on "
        "the cells both score. FluBNF keeps 20.0 GB free on this disk; "
        "500.0 GB is free now.")
    # the settings and the flag, nothing else; no claim, no thread
    f = alice / "experiments" / SMOKE
    assert sorted(p.name for p in f.iterdir()) == [X.QUEUED, X.SETTINGS]
    assert _claim() is None and not [t for t in threading.enumerate()
                                     if t.name.startswith("experiment-")]
    assert client.get("/api/busy").json()["experiment"] is None
    # the page: live (it polls on), the Queued card, the line, Stop
    html = client.get(PAGE).text
    assert 'data-poll="1"' in html and "<h2>Queued</h2>" in html
    line = (f"Queued · 1st in line · starts within a minute · runs {runs} · "
            f"needs about {peak} of disk")
    assert _line(html) == line
    assert _title_badge(html) == ("pending", "queued · 1st in line")
    assert ('<input type="hidden" name="experiment" value="' + SMOKE
            + '"><button class="quiet">Stop</button>') in html
    assert "Delete experiment" not in html and 'id="sbx-state"' not in html
    api = client.get(f"/api/sandbox/experiments/{SMOKE}").json()
    assert (api["live"], api["claimed"], api["status"]["line"]) == (
        True, False, line)
    assert api["queued"] == {
        "position": 1, "wait_s": 0.0, "seconds": est["seconds"],
        "measured": False, "peak_bytes": est["peak_bytes"],
        "keep_bytes": est["keep_bytes"], "why": "", "runner": True}
    assert api["status"]["queued"] is True
    row = client.get("/sandbox").text.split(f'href="{PAGE}"', 1)[1]
    assert '<span class="uk-badge-t">queued · 1st in line</span>' in row.split(
        "</tr>", 1)[0]
    # JSON: Start's keys, started false, and where it stands: "queued" as
    # the experiment's JSON gives it
    got = client.post("/sandbox/experiments", data=FORM, headers=JSON).json()
    assert set(got) == {"ok", "id", "url", "started", "resumed", "complete",
                        "text", "codes", "queued"}
    assert (got["ok"], got["id"], got["url"], got["started"],
            got["complete"], got["codes"]) == (True, SMOKE, PAGE, False,
                                               False, [])
    assert got["text"] == f"{SMOKE} is already queued: 1st in line."
    assert got["queued"] == api["queued"]
    off = "sihrs_2024-25_smoke"
    got = client.post("/sandbox/experiments", data={**FORM, "oracle": "off"},
                      headers=JSON).json()
    assert set(got) == {"ok", "id", "url", "started", "resumed", "complete",
                        "text", "codes", "queued", "plan"}
    assert (got["ok"], got["id"], got["started"]) == (True, off, False)
    est = runner.estimate({**FORM, "oracle": False}, weeks=SMOKE_WEEKS)
    assert got["queued"] == {
        "position": 1, "wait_s": 0.0, "seconds": est["seconds"],
        "measured": False, "peak_bytes": est["peak_bytes"],
        "keep_bytes": est["keep_bytes"], "why": "", "runner": True}
    plan = got["plan"]
    assert set(plan) == {"model", "model_fingerprint", "experiment", "season",
                         "size", "oracle", "locations", "weeks", "replicates",
                         "particles", "reference"}
    assert (plan["model"], plan["season"], plan["size"], plan["oracle"],
            plan["weeks"]) == ("sihrs", "2024-25", "smoke", False,
                               SMOKE_WEEKS)
    assert plan["reference"]["member"] == "pf_filter"
    assert (alice / "experiments" / off / X.QUEUED).is_file()
    assert _flash() == "" and _claim() is None


def _stopped(top: Path) -> Path:
    """The smoke in a Sandbox folder, stopped after its first week."""
    f = top / "experiments" / SMOKE
    f.mkdir(parents=True, exist_ok=True)
    L.write_json(f / X.SETTINGS, json.loads(X.settings_text(FORM)))
    retro.write_meta(f, {"status": "stopped", "started_utc": S1,
                         "settings": {"experiment": SMOKE_FP,
                                      "weeks": SMOKE_WEEKS}})
    _store(f, SMOKE_WEEKS[0], {"pf": _q(10.0)})
    return f


def test_in_a_runner_folder_resume_queues_without_the_guard(alice,
                                                            monkeypatch):
    _replay(world_root() / "2024-25", weeks=SMOKE_WEEKS)
    _no_console_run(monkeypatch)
    f = _stopped(alice)
    html = client.get(PAGE).text
    alert = html.split('id="sbx-state"', 1)[1].split("</div>", 1)[0]
    assert "Stopped after 1 of 2 weeks." in alert
    assert '<button class="gold">Resume</button>' in alert
    assert "data-guard" not in _main(html)
    _start()
    assert _flash() == f"Queued {SMOKE}: 1st in line on the runner."
    assert (f / X.QUEUED).is_file() and _claim() is None
    # the estimate counts the week left only
    est = runner.estimate(FORM, weeks=SMOKE_WEEKS, done=SMOKE_WEEKS[:1])
    assert est["weeks"] == 1
    assert _detail().startswith(
        f"It runs {sb.eta_words(est['seconds'], est['seconds'])} once it "
        "starts")


def test_in_a_runner_folder_stop_dequeues_or_stops(alice):
    f = alice / "experiments" / SMOKE
    _start()
    _no_flash()
    r = client.post("/sandbox/stop", data={"experiment": SMOKE},
                    follow_redirects=False)
    assert r.headers["location"] == PAGE
    assert _flash() == f"Took {SMOKE} out of the queue; nothing was fitted."
    assert ui_state._status.get("flash_kind") == "ok"
    assert not (f / X.QUEUED).exists() and (f / X.SETTINGS).is_file()
    got = client.post("/sandbox/stop", data={"experiment": SMOKE},
                      headers=JSON).json()
    assert got == {"ok": False, "id": SMOKE,
                   "text": f"Nothing to stop: {SMOKE} is not replaying."}
    # replaying on the runner (its record under way in another process)
    now = time.time()
    retro.write_meta(f, {"status": "running", "pid": os.getpid(),
                         "heartbeat_utc": now, "segment_start_utc": now,
                         "settings": {"experiment": "e" * 64,
                                      "weeks": SMOKE_WEEKS}})
    got = client.post("/sandbox/stop", data={"experiment": SMOKE},
                      headers=JSON).json()
    assert got == {"ok": True, "id": SMOKE,
                   "text": f"Stopping {SMOKE} after the fits in flight; "
                   "finished weeks are kept."}
    assert retro.stop_path(f).exists() and _claim() is None
    # an id with no folder: nothing written anywhere
    r = client.post("/sandbox/stop", data={"experiment": "x_2024-25_smoke"},
                    follow_redirects=False)
    assert r.headers["location"] == "/sandbox"
    assert not (alice / "experiments" / "x_2024-25_smoke").exists()


def test_the_queue_line_and_badge():
    line, badge = ui_sandbox._experiment_line, ui_sandbox._experiment_badge
    q = {"position": 2, "wait_s": 3900.0, "seconds": 632.0,
         "measured": False, "peak_bytes": 182_200_000,
         "keep_bytes": 9_960_000, "why": "", "runner": True}
    said = ("Queued · 2nd in line · starts in about 1:05:00 · runs about "
            "10:32 · needs about 173.8 MB of disk")
    assert line(_st(""), False, q) == said
    assert badge(_st(""), False, q) == ("pending", "queued · 2nd in line")
    why = ("waiting: a replay is running on this computer (the shipped "
           "replay of 2024-25)")
    assert line(_st("stopped"), False, {**q, "why": why}) == said + " · " + why
    assert line(_st(""), False, {**q, "position": 1, "wait_s": 20.0}) == (
        "Queued · 1st in line · starts within a minute · runs about 10:32 · "
        "needs about 173.8 MB of disk")
    # an estimate not worked out leaves its parts out
    assert line(_st(""), False, {**q, "seconds": 0.0, "peak_bytes": 0}) == (
        "Queued · 2nd in line · starts in about 1:05:00")
    down = {**q, "runner": False}
    assert line(_st(""), False, down) == (
        "Queued · 2nd in line · the runner is not running · runs about "
        "10:32 · needs about 173.8 MB of disk")
    assert badge(_st("stopped"), False, down) == (
        "warn", "queued · runner not running")
    # the runner's job, its record not under way yet
    for state in ("", "stopped"):
        assert line(_st(state), "runner") == "Starting on the runner…"
        assert badge(_st(state), "runner") == ("pending", "starting")
    running = _st("running", week="2024-12-14", fits_done=4, fits_total=10)
    assert line(running, "runner") == "2024-12-14: 4 of 10 fits · 21:50 so far"
    assert badge(running, "runner") == ("pending", "running")
    # refused by the runner, over the state it was left in
    for state in ("", "stopped", "done"):
        assert badge(_st(state), False, None, LINKED) == (
            "warn", "refused by the runner")
    assert badge(_st("stopped"), False, None, "") == (
        "warn", "stopped · 2 of 5 weeks")


def test_in_a_runner_folder_the_page_reads_the_runner(alice, students,
                                                      truth, monkeypatch):
    _no_console_run(monkeypatch)
    rr = str(world_root())
    f = alice / "experiments" / SMOKE
    f.mkdir()
    L.write_json(f / X.SETTINGS, json.loads(X.settings_text(FORM)))
    old = time.time() - 60
    os.utime(f / X.SETTINGS, (old, old))
    # starting: the runner's job names it, QUEUED claimed, no record yet
    job = {"kind": "run", "folder": "alice", "id": SMOKE, "size": "smoke",
           "pid": os.getpid(), "started_utc": runner._utc(time.time()),
           "keep_bytes": 0}
    runner_state(students, retro_root=rr, job=job)
    html = client.get(PAGE).text
    assert 'data-poll="1"' in html and "<h2>Running</h2>" in html
    assert _line(html) == "Starting on the runner…"
    assert _title_badge(html) == ("pending", "starting")
    assert "Delete experiment" not in html
    got = client.post(f"{PAGE}/delete", data={"confirm": SMOKE},
                      headers=JSON).json()
    assert got == {"ok": False, "id": SMOKE, "codes": [],
                   "text": f"Not deleted: {SMOKE} is replaying; stop it "
                   "first"}
    assert f.is_dir()
    # a runner that is not running names no job: the page is idle
    runner_state(students, retro_root=rr, job=job, pid=DEAD)
    html = client.get(PAGE).text
    assert 'data-poll="0"' in html and 'id="sbx-line"' not in html
    assert _title_badge(html) == ("neutral", "not started")
    alert = html.split('id="sbx-state"', 1)[1].split("</div>", 1)[0]
    assert "Not started yet." in alert
    assert '<button class="gold">Start</button>' in alert
    # refused at dispatch: said, with Start (Resume once a week is stored)
    runner_state(students, retro_root=rr, recent=[{
        "folder": "alice", "id": SMOKE, "size": "smoke", "kind": "run",
        "utc": runner._utc(old + 30), "outcome": "refused", "text": LINKED,
        "seconds": 0.0, "weeks": 0}])
    html = client.get(PAGE).text
    assert 'data-poll="0"' in html
    assert _title_badge(html) == ("warn", "refused by the runner")
    alert = html.split('id="sbx-state"', 1)[1].split("</div>", 1)[0]
    assert html.count('id="sbx-state"') == 1
    assert 'class="uk-alert uk-alert--warn"' in html.split(
        'id="sbx-state"', 1)[0].rsplit("<div", 1)[1]
    assert f"The runner did not run it: {LINKED}." in alert
    assert '<button class="gold">Start</button>' in alert
    row = client.get("/sandbox").text.split(f'href="{PAGE}"', 1)[1]
    assert ('<span class="uk-badge-t">refused by the runner</span>'
            in row.split("</tr>", 1)[0])
    retro.write_meta(f, {"status": "stopped", "started_utc": old,
                         "settings": {"experiment": SMOKE_FP,
                                      "weeks": SMOKE_WEEKS}})
    _store(f, SMOKE_WEEKS[0], {"pf": _q(10.0)})
    os.utime(f / X.SETTINGS, (old, old))
    alert = client.get(PAGE).text.split('id="sbx-state"', 1)[1].split(
        "</div>", 1)[0]
    assert f"The runner did not run it: {LINKED}." in alert
    assert '<button class="gold">Resume</button>' in alert
    # queued again (its settings written anew): the refusal is behind it
    _start()
    html = client.get(PAGE).text
    assert "The runner did not run it" not in html
    assert _title_badge(html) == ("pending", "queued · 1st in line")
    # an interrupted replay says the runner's reason when it gave one
    os.unlink(f / X.QUEUED)
    retro.write_meta(f, {"status": "running", "pid": DEAD,
                         "heartbeat_utc": 1.0, "started_utc": old,
                         "stop_reason": "The runner stopped while it "
                         "replayed; it was queued again.",
                         "settings": {"experiment": SMOKE_FP,
                                      "weeks": SMOKE_WEEKS}})
    alert = client.get(PAGE).text.split('id="sbx-state"', 1)[1].split(
        "</div>", 1)[0]
    assert ("<strong>Interrupted after 1 of 2 weeks.</strong> The runner "
            "stopped while it replayed; it was queued again.") in alert


def test_in_a_runner_folder_nothing_is_scored_on_view(alice, truth,
                                                      monkeypatch):
    folder = _hand_written(monkeypatch, truth)
    truth.write_text(truth.read_text(encoding="utf-8") + "\n",
                     encoding="utf-8", newline="\n")
    # off the runner, a view would score it again
    assert X.stale(folder) == "the truth data changed"

    def never(*a, **k):
        raise AssertionError("scored on view")
    monkeypatch.setattr(X, "score", never)
    before = (folder / X.SUMMARY).read_bytes()
    url = f"/sandbox/experiments/{BETA}"
    html = client.get(url).text
    api = client.get(f"/api/sandbox/experiments/{BETA}").json()
    client.get("/sandbox")
    assert ui_sandbox._experiment_scores == {}
    assert api["scoring"] == {"pending": False, "why": "", "error": ""}
    assert (api["live"], api["queued"]) == (False, None)
    assert 'data-poll="0"' in html and 'id="sbx-scoring"' not in html
    assert (folder / X.SUMMARY).read_bytes() == before
    assert not [t for t in threading.enumerate()
                if t.name.startswith("experiment-")]


def test_in_a_runner_folder_a_refusal_is_not_queued(alice, monkeypatch):
    _no_console_run(monkeypatch)
    # the floor: the detail is the runner's sentence, with no code
    monkeypatch.setattr(runner, "_free", lambda: 20 * GiB)
    r = _start()
    assert r.headers["location"] == "/sandbox"
    est = runner.estimate(FORM, weeks=SMOKE_WEEKS)
    left = retro.human_bytes(20 * GiB - est["peak_bytes"])
    words = (f"{SMOKE} needs about {retro.human_bytes(est['peak_bytes'])} of "
             f"disk while it runs, which would leave {left} free; FluBNF "
             "keeps 20.0 GB free on this disk")
    assert _flash() == f"Not queued: {words} (MACHINE)."
    assert ui_state._status.get("flash_kind") == "warn"
    assert _detail() == ("The experiments queued ahead of it keep 0 B. "
                         "Delete experiments you no longer need, or ask Ely "
                         "to free space.")
    assert not (alice / "experiments" / SMOKE).exists()
    got = client.post("/sandbox/experiments", data=FORM, headers=JSON).json()
    assert (got["ok"], got["id"], got["url"], got["started"],
            got["queued"]) == (False, SMOKE, None, False, None)
    assert got["text"] == f"Not queued: {words} (MACHINE)."
    assert [c["code"] for c in got["codes"]] == ["MACHINE", "MACHINE"]
    # the model's refusal, its code said; the form comes back as posted
    monkeypatch.setattr(runner, "_free", lambda: 500 * GiB)
    _no_flash()
    _start(model="beta@9", size="pilot")
    assert _flash().startswith("Not queued: ")
    assert _flash().endswith("(MODEL_NOT_FOUND).")
    html = client.get("/sandbox").text
    # no time on the size: this runner.json names no engine (an older
    # runner's), so the runner's figure cannot be worked out here
    assert [t for a, t in _options(html, "sbexp-size") if "selected" in a] == [
        "pilot: 10 locations, every other week"]
    assert sorted(p.name for p in (alice / "experiments").iterdir()) == []
    assert _claim() is None


def test_the_runner_computers_own_console_waits_for_the_runner(
        world, students, monkeypatch):
    _replay(world_root() / "2024-25", weeks=SMOKE_WEEKS)
    job = {"kind": "run", "folder": "alice", "id": "beta2-v3_2024-25_pilot",
           "size": "pilot", "pid": 4242, "keep_bytes": 0}
    runner_state(students, job=job)
    said = ("the runner on this computer is replaying alice's "
            "beta2-v3_2024-25_pilot: one replay at a time")
    got = client.post("/sandbox/experiments", data=FORM, headers=JSON).json()
    assert got == {"ok": False, "id": SMOKE, "url": None, "started": False,
                   "text": f"Not started: {said} (MACHINE).",
                   "codes": [{"code": "MACHINE", "tier": "machine",
                              "text": said}]}
    assert _claim() is None and not (X.root() / SMOKE).exists()
    # its own pages are step 4's: Start holds the guard
    assert ('<button class="gold" data-guard="sandbox-run">Start</button>'
            in client.get("/sandbox").text)
    # a tidy holds nothing, nor does a runner that is not running
    runner_state(students, job={**job, "kind": "tidy"})
    assert runner.busy_words() == ""
    runner_state(students, job=job, pid=DEAD)
    calls = _weeks_run(monkeypatch, _sidecar)
    r = _start()
    assert r.headers["location"] == PAGE
    _join()
    assert [c["asof"] for c in calls] == SMOKE_WEEKS
    assert X.status(X.root() / SMOKE)["status"] == "done"
    assert _flash().startswith(f"Started {SMOKE}: ")
    ui_state._status.pop("flash", None)         # no notice left for the next
