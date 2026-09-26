"""Update data against a faked git (app.core.data.pull_hub and
check_freshness), and the Data tab's background posts.

The laptop case: the hub clone's fetch setting mapped origin's main onto
the local branch, so a fetch moved HEAD and then failed to fast-forward
the working tree ("fatal: Cannot fast-forward your working tree"). The
console showed the transcript's first 200 characters (the warning, not
the fatal line) and then "up to date with origin", because the refs were
equal while last week's file sat on disk.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import pytest                                       # noqa: E402
from fastapi.testclient import TestClient           # noqa: E402

from app.core import data                           # noqa: E402
from app.ui import server as srv                    # noqa: E402
from app.ui import state as ui_state                # noqa: E402

client = TestClient(srv.app)


class _R:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


class FakeGit:
    """subprocess.run for git in the hub clone: answers per subcommand
    (the first argument after `git -C <hub>` or `git`), records every
    call. `answers` maps a subcommand to an _R or a callable(args) -> _R;
    anything else succeeds silently."""

    def __init__(self, hub, **answers):
        self.hub, self.answers, self.calls = hub, answers, []

    def __call__(self, args, **kw):
        args = list(args)
        sub = args[3] if args[1:3] == ["-C", str(self.hub)] else args[1]
        self.calls.append([sub] + args[args.index(sub) + 1:])
        if sub == "rev-parse" and "--show-toplevel" in args:
            return _R(0, str(self.hub) + "\n")
        a = self.answers.get(sub)
        if callable(a):
            return a(args)
        return a if a is not None else _R()

    def subs(self):
        return [c[0] for c in self.calls]


@pytest.fixture
def hub(tmp_path, monkeypatch):
    h = tmp_path / "hub"
    for sub in ("model-output/FluSight-baseline",
                "model-output/FluSight-ensemble"):
        (h / sub).mkdir(parents=True)
    monkeypatch.setattr(data, "HUB", h)
    return h


def _fake(monkeypatch, hub, **answers):
    g = FakeGit(hub, **answers)
    monkeypatch.setattr(data.subprocess, "run", g)
    return g


# ------------------------------------------------------------- pull_hub

def test_a_warning_only_fetch_is_a_success(hub, monkeypatch):
    g = _fake(monkeypatch, hub,
              fetch=_R(0, "", "From https://example/hub\n * branch main "
                              "-> FETCH_HEAD\nwarning: something odd\n"),
              merge=_R(0, "Updating b758798..1c8e114\nFast-forward\n "
                          "2 files changed\n"))
    ok, msg = data.pull_hub()
    assert ok is True
    assert msg == "2 files changed"                 # git's last line
    # fetch then fast-forward merge, never `git pull`
    assert "pull" not in g.subs()
    assert g.subs().index("fetch") < g.subs().index("merge")
    assert ["merge", "--ff-only", "FETCH_HEAD"] in g.calls


def test_a_fatal_fast_forward_is_reported_by_its_last_line(hub, monkeypatch):
    transcript = ("From https://github.com/cdcepi/FluSight-forecast-hub\n"
                  " * branch            main       -> FETCH_HEAD\n"
                  "warning: fetch updated the current branch head.\n"
                  "fast-forwarding your working tree from\n"
                  "commit b758798...\n"
                  "fatal: Cannot fast-forward your working tree.\n")
    _fake(monkeypatch, hub, fetch=_R(1, "", transcript))
    ok, msg = data.pull_hub()
    assert ok is False
    assert msg == "fatal: Cannot fast-forward your working tree."
    # the same for a merge that cannot fast-forward
    _fake(monkeypatch, hub,
          merge=_R(128, "", "fatal: Not possible to fast-forward, aborting.\n"))
    ok, msg = data.pull_hub()
    assert ok is False
    assert msg == "fatal: Not possible to fast-forward, aborting."


def test_a_refspec_into_refs_heads_is_repaired_before_fetching(hub, monkeypatch):
    g = _fake(monkeypatch, hub,
              config=lambda a: (_R(0, "+refs/heads/main:refs/heads/main\n")
                                if "--get-all" in a else _R()),
              merge=_R(0, "Already up to date.\n"))
    ok, msg = data.pull_hub()
    assert ok is True
    assert msg == "Already up to date. · hub clone's fetch setting repaired"
    subs = g.subs()
    assert ["config", "--unset-all", "remote.origin.fetch"] in g.calls
    assert ["config", "--add", "remote.origin.fetch", data.GOOD_REFSPEC] in g.calls
    assert subs.index("config") < subs.index("fetch")
    # a healthy setting is left alone and not mentioned
    g = _fake(monkeypatch, hub,
              config=lambda a: (_R(0, data.GOOD_REFSPEC + "\n")
                                if "--get-all" in a else _R()),
              merge=_R(0, "Already up to date.\n"))
    assert data.pull_hub() == (True, "Already up to date.")
    assert not any(c[:2] == ["config", "--add"] for c in g.calls)


def test_a_stale_working_tree_is_restored_to_head(hub, monkeypatch):
    # HEAD already equals FETCH_HEAD but the files on disk differ from it
    g = _fake(monkeypatch, hub,
              merge=_R(0, "Already up to date.\n"),
              diff=_R(1),
              config=lambda a: (_R(0, "true\n") if "core.sparseCheckout" in a
                                else _R()))
    ok, msg = data.pull_hub()
    assert ok is True
    assert msg == ("Already up to date. · hub files restored to match the "
                   "clone")
    assert ["diff", "--quiet", "HEAD"] in g.calls
    assert ["checkout", "--", "."] in g.calls
    assert ["sparse-checkout", "reapply"] in g.calls    # a sparse clone
    # a plain clone: no reapply; a clean tree: nothing touched
    g = _fake(monkeypatch, hub, merge=_R(0, "Already up to date.\n"),
              diff=_R(1))
    data.pull_hub()
    assert ["checkout", "--", "."] in g.calls
    assert "sparse-checkout" not in g.subs()
    g = _fake(monkeypatch, hub, merge=_R(0, "Already up to date.\n"))
    assert data.pull_hub() == (True, "Already up to date.")
    assert "checkout" not in g.subs()


# ------------------------------------------------------- check_freshness

def _freshness_git(hub, monkeypatch, *, behind="0", want="aaaa", have="aaaa",
                   remote_csv="date,location,value\n2026-07-04,US,1\n"):
    return _fake(
        monkeypatch, hub,
        **{"rev-list": _R(0, behind + "\n"),
           "ls-tree": _R(0, ""),
           "show": _R(0, remote_csv),
           "rev-parse": _R(0, want + "\n"),
           "hash-object": _R(0, have + "\n")})


def test_up_to_date_needs_the_file_on_disk_to_be_origins(hub, monkeypatch):
    monkeypatch.setattr(data, "vintages", lambda: [])
    monkeypatch.setattr(data, "live_newest_week", lambda: "2026-07-04")
    _freshness_git(hub, monkeypatch)
    f = data.check_freshness()
    assert f.is_fresh and f.detail == "up to date with origin"
    assert f.pill() == ("ok", "up to date")
    # equal refs, a different blob on disk: not fresh
    _freshness_git(hub, monkeypatch, have="bbbb")
    f = data.check_freshness()
    assert f.is_fresh is False and f.tree_stale
    assert "not origin's" in f.detail and f.pill() == ("warn", "stale files")
    # origin's file holds a newer week: weeks behind
    monkeypatch.setattr(data, "live_newest_week", lambda: "2026-06-20")
    _freshness_git(hub, monkeypatch, have="bbbb")
    f = data.check_freshness()
    assert f.is_fresh is False
    assert f.pill() == ("warn", "2 weeks behind")
    assert f.detail.startswith("new data through 2026-07-04 upstream")


def test_offline_is_never_fresh(hub, monkeypatch):
    monkeypatch.setattr(data, "vintages", lambda: [])
    _fake(monkeypatch, hub, fetch=_R(128, "", "fatal: unable to access\n"))
    f = data.check_freshness()
    assert f.is_fresh is False
    assert f.pill() == ("bad", "offline")
    assert f.detail == "fetch failed: fatal: unable to access"


# ---------------------------------------------- the Data tab's background posts

def test_the_buttons_answer_json_when_asked(hub, monkeypatch):
    monkeypatch.setattr(data, "pull_hub", lambda: (True, "Already up to date."))
    monkeypatch.setattr(data, "vintages", lambda: [])
    monkeypatch.setattr(data, "newest_week", lambda: "2026-07-04")
    ui_state._status.update({"running": None, "phase": "", "run_label": ""})
    ui_state._status.pop("flash", None)
    r = client.post("/data/pull", headers={"Accept": "application/json"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["message"].startswith("Up to date · data through 2026-07-04")
    # the notice is kept for the reload the script makes
    assert ui_state._status.get("flash") == body["message"]
    # a failure: ok false, the git line, still 200 (the script reads it)
    monkeypatch.setattr(data, "pull_hub", lambda: (False, "fatal: no network"))
    r = client.post("/data/pull", headers={"Accept": "application/json"})
    assert r.json()["ok"] is False
    assert "fatal: no network" in r.json()["message"]
    # a plain post still redirects
    r = client.post("/data/pull", follow_redirects=False)
    assert r.status_code == 303
    # the freshness check: pill class, words and the detail line
    monkeypatch.setattr(data, "check_freshness", lambda: data.Freshness(
        None, None, 0, True, "up to date with origin"))
    r = client.post("/freshness", headers={"Accept": "application/json"})
    assert r.json() == {"ok": True, "fresh": True, "pill": "ok",
                        "words": "up to date", "detail": "up to date with origin"}
    r = client.post("/freshness")
    assert r.status_code == 200
    assert '<span class="pill ok" id="hub-pill">up to date</span>' in r.text


def test_the_page_carries_the_progress_bar_and_the_script(hub, monkeypatch):
    monkeypatch.setattr(data, "vintages", lambda: [])
    html = client.get("/data").text
    assert 'id="hub-progress" hidden' in html
    assert 'class="runbar busy" role="progressbar"' in html
    assert 'id="hub-status" role="status" aria-live="polite"' in html
    assert "headers:{'Accept':'application/json'}" in html
    # the forms still post on their own without script
    assert '<form method="post" action="/data/pull">' in html
    assert '<form method="post" action="/freshness">' in html
