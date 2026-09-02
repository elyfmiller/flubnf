"""Server-side hardening from the 2026-09-01 final pass review.

Four behaviors pinned here:

  1. the engine busy check and its claim are atomic under one module lock
     (srv._engine_lock), so two overlapping submits cannot both start
     full engine runs -- the race was reproduced with exactly the
     threaded TestClient shape these tests use;
  2. state-changing requests must arrive under a localhost Host header
     and, when the browser attaches one, a localhost Origin: a foreign
     page's form-POST and a DNS-rebound hostname get 403, while
     curl-style no-Origin posts, same-origin posts, and every GET pass;
  3. /data/pull refuses server-side while a run is reading hub files
     (the client button guard alone was bypassed by a second tab), and a
     failed git pull is reported as a failure instead of a status line;
  4. strings that reach | safe HTML and inline scripts are hardened:
     _script_json emits "<" as \\u003c, and the season map's
     scoring-failed fragment escapes the raw error text.
"""
import threading
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                       # noqa: E402
from fastapi.testclient import TestClient           # noqa: E402

from app.ui import server as srv                    # noqa: E402

client = TestClient(srv.app)
#: a client whose default authority is the loopback address the console
#: actually binds, for the same-origin acceptance cases
local_client = TestClient(srv.app, base_url="http://127.0.0.1:8710")

SEASON = "2098-99"


@pytest.fixture(autouse=True)
def _isolated_status():
    """Snapshot and restore the module-level status stores around each test
    so mocked busy states and claims never leak between tests."""
    status_before = dict(srv._status)
    retro_before = dict(srv._retro_status)
    stop_before = set(srv._retro_stop)
    claim_before = dict(srv._retro_claim_at)
    form_before = dict(srv._last_form)
    yield
    srv._status.clear(); srv._status.update(status_before)
    srv._retro_status.clear(); srv._retro_status.update(retro_before)
    srv._retro_stop.clear(); srv._retro_stop.update(stop_before)
    srv._retro_claim_at.clear(); srv._retro_claim_at.update(claim_before)
    srv._last_form.clear(); srv._last_form.update(form_before)


# ------------------------------------------- 1. atomic check-and-claim

def _two_threads(post):
    codes = []
    threads = [threading.Thread(target=lambda: codes.append(post()))
               for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return codes


def test_concurrent_run_posts_start_exactly_one_engine_run(tmp_path,
                                                           monkeypatch):
    """Two overlapping POST /run both read idle and both started full
    engine runs before the check and the claim shared a lock. The sleep
    below sits inside the check-to-claim window (via _known_seasons), so
    without the lock both threads pass the busy check during the overlap
    and started would be 2."""
    from app.core import data as data_real
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    # patch the REAL module, not srv.data_mod: the lazy proxy swaps the
    # server's data_mod global for app.core.data on first use, and the
    # import-time warm thread can perform that swap mid-test, dropping an
    # attribute patched onto the proxy instance
    monkeypatch.setattr(data_real, "vintage_path", lambda d: tmp_path)
    started = []
    monkeypatch.setattr(srv, "_run_all", lambda spec: started.append(spec))

    def slow_known():
        time.sleep(0.25)      # widen the race window deterministically
        return []

    monkeypatch.setattr(srv, "_known_seasons", slow_known)
    srv._retro_status.clear()
    srv._status.update({"running": None, "phase": "", "run_label": "",
                        "log": []})

    def post():
        return client.post("/run", data={"forecast_date": "2098-01-04",
                                         "locations": ["Ohio"]},
                           follow_redirects=False).status_code

    codes = _two_threads(post)
    assert codes == [303, 303]        # both answered; only one started
    assert len(started) == 1
    refusals = [l for l in srv._status["log"]
                if "already in progress" in l]
    assert len(refusals) == 1


def test_concurrent_retro_run_posts_claim_exactly_one_worker(tmp_path,
                                                             monkeypatch):
    """The same check-then-claim race in POST /retro/run: without the
    shared lock, two overlapping submits both passed every busy check and
    two season workers raced over the same tree."""
    from app.core import retro
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(retro, "available_seasons", lambda: [SEASON])
    workers = []
    monkeypatch.setattr(srv, "_retro_bg", lambda *a, **k: workers.append(a))

    def slow_known():
        time.sleep(0.25)      # inside the locked window, before the claim
        return [SEASON]

    monkeypatch.setattr(srv, "_known_seasons", slow_known)
    srv._retro_status.clear()
    srv._status.update({"running": None, "phase": "", "run_label": ""})

    def post():
        return client.post("/retro/run", data={"season": SEASON},
                           follow_redirects=False).status_code

    codes = _two_threads(post)
    assert codes == [303, 303]
    assert len(workers) == 1
    assert srv._retro_status[SEASON] == "running"
    assert "already replaying" in srv._status.get("flash", "")


# --------------------------------- 2. localhost Host and Origin guard

def test_cross_origin_form_post_is_refused():
    r = client.post("/run/stop", follow_redirects=False,
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert "Origin" in r.text


def test_opaque_null_origin_post_is_refused():
    # a sandboxed page's form-POST carries the literal Origin "null"; it
    # is not this console's page either
    r = client.post("/run/stop", follow_redirects=False,
                    headers={"Origin": "null"})
    assert r.status_code == 403


def test_same_origin_post_is_accepted():
    r = local_client.post("/run/stop", follow_redirects=False,
                          headers={"Origin": "http://127.0.0.1:8710"})
    assert r.status_code == 303


def test_no_origin_curl_style_post_is_accepted():
    # scripts and curl send no Origin at all; localhost Host suffices
    r = local_client.post("/run/stop", follow_redirects=False)
    assert r.status_code == 303


def test_evil_host_header_is_refused():
    # the DNS-rebinding shape: the request reaches loopback but names the
    # attacker's own hostname
    r = client.post("/run/stop", follow_redirects=False,
                    headers={"Host": "evil.example:8710"})
    assert r.status_code == 403
    assert "Host" in r.text


def test_bracketed_ipv6_and_localhost_hosts_are_accepted():
    for host in ("[::1]:8710", "localhost:9999", "127.0.0.1"):
        r = client.post("/run/stop", follow_redirects=False,
                        headers={"Host": host})
        assert r.status_code == 303, host


def test_gets_stay_open_whatever_the_headers():
    r = client.get("/api/busy", headers={"Origin": "https://evil.example",
                                         "Host": "evil.example"})
    assert r.status_code == 200


# ------------------------------------------- 3. /data/pull hardening

def test_data_pull_refused_while_a_run_reads_hub_files(monkeypatch):
    """The server-side mirror of the client data-pull guard: a POST from
    a second tab must not let git pull mutate the hub clone under a
    materializing run."""
    from app.core import data as data_real
    calls = []
    monkeypatch.setattr(data_real, "pull_hub",
                        lambda: calls.append(1) or (True, "pulled"))
    srv._status.update({"running": "all:20990101T000000-abc",
                        "run_label": "2099-01-02 · 1 state(s) + US",
                        "phase": "materializing models (BNG network "
                                 "generation)"})
    r = client.post("/data/pull", follow_redirects=False)
    assert r.status_code == 303
    assert calls == []
    flash = srv._status.get("flash", "")
    assert "reading the hub files" in flash
    assert "2099-01-02" in flash        # names what holds the engine


def test_data_pull_refused_during_the_starting_claim(monkeypatch):
    # "starting" is the claim window before the worker names its phase;
    # materializing is imminent, so the pull must wait
    from app.core import data as data_real
    monkeypatch.setattr(data_real, "pull_hub",
                        lambda: (_ for _ in ()).throw(AssertionError(
                            "pull must not run during a claim")))
    srv._status.update({"running": "starting", "run_label": "",
                        "phase": ""})
    r = client.post("/data/pull", follow_redirects=False)
    assert r.status_code == 303
    assert "reading the hub files" in srv._status.get("flash", "")


def test_data_pull_allowed_during_pure_fitting(monkeypatch):
    # the doctrine's other half: fitting reads no hub files, so the pull
    # proceeds exactly as when idle
    from app.core import data as data_real
    monkeypatch.setattr(data_real, "pull_hub",
                        lambda: (True, "Already up to date."))
    monkeypatch.setattr(data_real, "vintages", lambda: [])
    srv._status.update({"running": "all:20990101T000000-abc",
                        "run_label": "2099-01-02 · 1 state(s) + US",
                        "phase": "filtering 3 location(s) x 3 replicate(s)"})
    r = client.post("/data/pull", follow_redirects=False)
    assert r.status_code == 303
    assert "Already up to date." in srv._status.get("flash", "")


def test_data_pull_failure_is_flashed_as_a_failure(monkeypatch):
    """A fatal git error once returned as pull_hub's only output and the
    page flashed it like a status line; the exit code now decides."""
    from app.core import data as data_real
    monkeypatch.setattr(data_real, "pull_hub",
                        lambda: (False, "fatal: unable to access remote"))
    srv._status.update({"running": None, "phase": "", "run_label": ""})
    srv._status.pop("flash", None)
    r = client.post("/data/pull", follow_redirects=False)
    assert r.status_code == 303
    flash = srv._status.get("flash", "")
    assert "FAILED" in flash
    assert "fatal: unable to access remote" in flash
    assert "latest vintage" not in flash    # the success trimmings stay off


def test_pull_hub_returns_gits_own_verdict(monkeypatch):
    from app.core import data

    class _R:
        def __init__(self, rc, out, err):
            self.returncode, self.stdout, self.stderr = rc, out, err

    def failing_run(args, **kw):
        if "pull" in args:
            return _R(1, "", "fatal: could not read from remote\n")
        return _R(0, "", "")            # the sparse-checkout heal calls

    monkeypatch.setattr(data.subprocess, "run", failing_run)
    ok, msg = data.pull_hub()
    assert ok is False
    assert "fatal: could not read from remote" in msg

    def clean_run(args, **kw):
        return _R(0, "Already up to date.\n", "")

    monkeypatch.setattr(data.subprocess, "run", clean_run)
    assert data.pull_hub() == (True, "Already up to date.")


# ------------------------------------- 4. script and HTML hardening

def test_script_json_escapes_every_angle_bracket():
    import json
    payload = {"name": "</script><svg onload=alert(1)>"}
    blob = srv._script_json(payload)
    assert "<" not in blob
    assert "\\u003c/script" in blob
    assert json.loads(blob) == payload   # still the same JSON value


def test_scoring_failed_hint_escapes_the_error_text():
    frag = srv._scoring_failed_hint("<img src=x onerror=alert(1)> & boom")
    assert "<img" not in frag
    assert "&lt;img src=x onerror=alert(1)&gt; &amp; boom" in frag
    assert frag.startswith("<p class='hint'>Scoring failed: <code>")


def test_forecast_script_blob_cannot_close_its_script_element(monkeypatch):
    # the forecast page embeds the model-name map in an inline script the
    # template marks | safe; a name carrying markup must not escape it
    evil = "</script><script>alert(1)</script>"
    monkeypatch.setattr(srv, "_model_names",
                        lambda: {"pf": evil, "ensemble": "Ensemble"})
    html_text = client.get("/forecast").text
    assert evil not in html_text
    assert "\\u003c/script" in html_text
