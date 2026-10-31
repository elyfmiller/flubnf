"""Experiments on this console (app/ui/routes/sandbox.py's experiments
section, templates/sandbox_experiment.html and the gallery's Experiments
card): the four choices and nothing else; Start claiming the engine,
replaying, and releasing it the moment the replay returns, the summary
then scored off the engine as the folder's one job, and a worker that
fails saying so and letting go; each refusal with its code; the claim
refusing every other run; Stop, Resume and a complete experiment; the
compare page read from summary.json only, in the words of each state; its
JSON; Delete; and the guard modal's words.

The replay's weeks, the engine and the hub are faked as
test_experiments.py and test_experiment_summary.py fake them: no PyBNF,
no BNG2.pl, no hub clone. Every thread a start begins is joined.
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

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import experiments as X                    # noqa: E402
from app.core import library as L                        # noqa: E402
from app.core import retro                               # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core import scoring                             # noqa: E402
from app.ui import pipeline as ui_pipeline               # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons     # noqa: E402
from app.ui import server as srv                         # noqa: E402
from app.ui import shared as ui_shared                   # noqa: E402
from app.ui import state as ui_state                     # noqa: E402
from app.ui import versions as ui_versions               # noqa: E402
from app.ui.routes import sandbox as ui_sandbox          # noqa: E402
from flubnf.vintages import sha256_of                    # noqa: E402
from test_experiment_summary import (S1, _age, _experiment, _q,  # noqa: E402
                                     _shipped_root, _snapshot)
from test_experiments import (SMOKE_WEEKS, _register, _replay,  # noqa: E402
                              _sidecar, _weeks_run, season, truth)  # noqa: F401
from test_fewer_marks import marks                       # noqa: E402

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


@pytest.fixture
def world(season, truth, pf_engine_ready, monkeypatch):
    """test_experiments.season's 2024-25 calendar with the console's
    replay roots there (RETRO_ROOT), the synthetic truth to score against,
    the particle-filter engine, the hub's tables the card needs, the sleep
    guard recorded, a view that waits for its scoring, no season claim and
    no notice left over (another module's, restored after). The guards
    started, a list."""
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
    old = [(a, t) for a, t in models if 'value="old@1"' in a][0]
    assert " disabled" in old[0] and old[1] == "old@1 · changed since Register"
    gamma = [(a, t) for a, t in models if 'value="gamma@1"' in a][0]
    assert gamma[1] == f"gamma@1 · {L.resolve('gamma@1')['fingerprint'][:8]}"
    # the newest intact registration is preselected, its Oracle step off
    assert [t.split(" ·")[0] for a, t in models if "selected" in a] == [
        "beta@1"]
    assert '<optgroup label="Shipped">' in form
    assert '<optgroup label="Registered">' in form
    seasons = _options(html, "sbexp-season")
    assert [t for _a, t in seasons] == ["2025-26", "2024-25", "2023-24"]
    assert [t for a, t in seasons if "selected" in a] == ["2024-25"]
    sizes = _options(html, "sbexp-size")
    assert [re.search(r'value="(\w+)"', a).group(1) for a, _t in sizes] == [
        "smoke", "pilot", "full"]
    assert [t for a, t in sizes if "selected" in a] == [
        "smoke: 2 locations, 2 weeks (minutes)"]
    assert _options(html, "sbexp-oracle") == [(' value="on"', "on"),
                                              (' value="off" selected', "off")]
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
        "pilot: 10 locations, every other week (under an hour)"]
    assert (' value="off" selected', "off") in _options(html, "sbexp-oracle")
    html = client.get("/sandbox").text
    assert [t for a, t in _options(html, "sbexp-size") if "selected" in a] == [
        "smoke: 2 locations, 2 weeks (minutes)"]
    # another experiment's record in the folder: EXPERIMENT_CHANGED, and
    # the record stays as it was
    folder = X.root() / SMOKE
    retro.write_meta(folder, {"settings": {"experiment": "0" * 64}})
    before = _snapshot(X.root())
    assert "delete its folder to run it again" in _refused(
        "EXPERIMENT_CHANGED")
    assert _snapshot(X.root()) == before and _claim() is None


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
