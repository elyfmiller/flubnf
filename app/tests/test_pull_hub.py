"""Update data against a faked git (app.core.data.pull_hub and
check_freshness), and the Data tab's background posts.

The laptop case: the hub clone's fetch setting mapped origin's main onto
the local branch, so a fetch moved HEAD and then failed to fast-forward
the working tree ("fatal: Cannot fast-forward your working tree"). The
console showed the transcript's first 200 characters (the warning, not
the fatal line) and then "up to date with origin", because the refs were
equal while last week's file sat on disk.

The November 2026 case: the hub clone is a partial clone, so the
fast-forward fetched each file it wrote from GitHub as it went, this
week's target-data/time-series.csv (93 MB) at some tens of kB/s, and its
closing diffstat then fetched every changed file of the whole hub. The
merge hit its timeout, the kill left .git/index.lock, which failed every
later update, and git's own fetch processes kept running.
"""
import os
import subprocess
import sys
import time
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
    monkeypatch.setattr(data, "_run", g)            # _git's commands
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
    assert ["merge", "--ff-only", "--no-stat", "FETCH_HEAD"] in g.calls


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


def test_a_timed_out_step_is_said_in_words(hub, monkeypatch):
    def merge(a):
        raise subprocess.TimeoutExpired(a, 300)
    _fake(monkeypatch, hub, merge=merge)
    assert data.pull_hub() == (
        False, "git merge was stopped after 5 minutes (GitHub sent the "
               "hub's files too slowly); try again")

    def config(a):
        raise subprocess.TimeoutExpired(a, 60)
    _fake(monkeypatch, hub, config=config)
    assert data.pull_hub() == (
        False, "git config was stopped after 60 seconds; try again")


def test_one_update_at_a_time(hub, monkeypatch):
    g = _fake(monkeypatch, hub)
    assert data._PULLING.acquire(blocking=False)
    try:
        assert data.pull_hub() == (
            False, "another update of the hub clone is running; try again "
                   "when it ends")
        assert g.calls == []
    finally:
        data._PULLING.release()


def test_a_locked_clone_names_the_lock_to_delete(hub, monkeypatch):
    lock = str(hub / ".git" / "index.lock")
    _fake(monkeypatch, hub, merge=_R(128, "", (
        f"fatal: Unable to create '{lock}': File exists.\n\n"
        "Another git process seems to be running in this repository, e.g.\n"
        "an editor opened by 'git commit'. Please make sure all processes\n"
        "are terminated then try again. If it still fails, a git process\n"
        "may have crashed in this repository earlier:\n"
        "remove the file manually to continue.\n")))
    assert data.pull_hub() == (
        False, f"the hub clone is locked by {lock}: if no git command is "
               "running on it, delete that file and try again")


def test_the_unread_files_are_left_out_before_the_fetch(hub, monkeypatch):
    g = _fake(monkeypatch, hub, merge=_R(0, "Fast-forward\n"))
    seen = []
    monkeypatch.setattr(data, "_skip_unread_files", lambda: seen.append(
        list(g.subs())) or "hub clone repaired to leave out x")
    assert data.pull_hub() == (True, "Fast-forward · hub clone repaired to "
                                     "leave out x")
    assert seen and "fetch" not in seen[0] and "fetch" in g.subs()


def _sparse_hub(tmp_path, *dirs, cone=True):
    """A clone of a hub-shaped repository, sparse on dirs."""
    src, hub = tmp_path / "src", tmp_path / "hub"
    files = ("README.md", "target-data/time-series.csv",
             "target-data/target-hospital-admissions.csv",
             "model-output/README.md", "model-output/FluSight-baseline/a.csv",
             "model-output/other-team/b.csv", "src/x.R", "b c/z.csv")
    for f in files:
        (src / f).parent.mkdir(parents=True, exist_ok=True)
        (src / f).write_text(f + "\n")
    for a in (["init", "-q"], ["add", "."],
              ["-c", "user.name=t", "-c", "user.email=t@example.com",
               "commit", "-q", "-m", "a"]):
        subprocess.run(["git", "-C", str(src), *a], check=True)
    subprocess.run(["git", "clone", "-q", "--sparse", str(src), str(hub)],
                   check=True)
    subprocess.run(["git", "-C", str(hub), "sparse-checkout", "set",
                    "--cone" if cone else "--no-cone", *dirs], check=True)
    return hub


def _on_disk(hub) -> set:
    return {p.relative_to(hub).as_posix() for p in hub.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(hub).parts}


def test_a_cone_clone_keeps_its_files_but_the_unread_one(tmp_path,
                                                         monkeypatch):
    hub = _sparse_hub(tmp_path, "target-data", "model-output/FluSight-baseline",
                      "src", "b c")
    monkeypatch.setattr(data, "HUB", hub)
    before = _on_disk(hub)
    assert {"target-data/time-series.csv", "b c/z.csv"} <= before
    assert data._skip_unread_files() == (
        "hub clone repaired to leave out target-data/time-series.csv, which "
        "FluBNF does not read")
    # the same files as the cone gave, less the one
    assert _on_disk(hub) == before - {"target-data/time-series.csv"}
    # and it holds: a second call has nothing to do, a reapply keeps it out
    assert data._skip_unread_files() is None
    subprocess.run(["git", "-C", str(hub), "sparse-checkout", "reapply"],
                   check=True)
    assert "target-data/time-series.csv" not in _on_disk(hub)


def test_a_clone_that_never_had_the_file_is_left_alone(tmp_path, monkeypatch):
    hub = _sparse_hub(tmp_path, "src")
    monkeypatch.setattr(data, "HUB", hub)
    assert data._skip_unread_files() is None
    cone = subprocess.run(["git", "-C", str(hub), "config", "--get",
                           "core.sparseCheckoutCone"], capture_output=True,
                          text=True).stdout.strip()
    assert cone == "true"


def test_a_non_cone_clone_gets_the_exclusion_added(tmp_path, monkeypatch):
    hub = _sparse_hub(tmp_path, "/*", "!/*/", "/target-data/", cone=False)
    monkeypatch.setattr(data, "HUB", hub)
    assert "target-data/time-series.csv" in _on_disk(hub)
    assert data._skip_unread_files() is not None
    assert _on_disk(hub) == {"README.md",
                             "target-data/target-hospital-admissions.csv"}
    assert data._skip_unread_files() is None


def test_a_full_clone_is_never_made_sparse(tmp_path, monkeypatch):
    src = _sparse_hub(tmp_path, "src").parent / "src"
    full = tmp_path / "full"
    subprocess.run(["git", "clone", "-q", str(src), str(full)], check=True)
    monkeypatch.setattr(data, "HUB", full)
    assert data._skip_unread_files() is None
    assert (full / "target-data" / "time-series.csv").is_file()


def _gone(pid: int) -> bool:
    end = time.monotonic() + 5
    while time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    os.kill(pid, 9)
    return False


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")
def test_a_killed_command_ends_whole_and_its_locks_go(tmp_path, monkeypatch):
    hub = tmp_path / "hub"
    subprocess.run(["git", "init", "-q", str(hub)], check=True)
    monkeypatch.setattr(data, "HUB", hub)
    monkeypatch.setattr(data, "KILL_GRACE_S", 1)
    pidfile = tmp_path / "grandchild.pid"
    # deaf to SIGTERM, so it takes SIGKILL, which git cannot clean up
    # after: takes the index lock and leaves a grandchild running, as the
    # merge's fetch of missing files does
    hang = (f"!trap '' TERM; touch .git/index.lock; sleep 60 & "
            f"echo $! > '{pidfile}'; wait")
    with pytest.raises(subprocess.TimeoutExpired) as e:
        data._git(["-c", f"alias.hang={hang}", "hang"], timeout=2)
    assert e.value.killed is True
    assert not (hub / ".git" / "index.lock").exists()
    assert _gone(int(pidfile.read_text())), "the grandchild outlived it"
    assert data._LIVE == set()


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")
def test_a_lock_not_left_by_a_killed_command_stays(tmp_path, monkeypatch):
    hub = tmp_path / "hub"
    subprocess.run(["git", "init", "-q", str(hub)], check=True)
    monkeypatch.setattr(data, "HUB", hub)
    # ended by SIGTERM: git itself removes its locks then, so a lock still
    # there is another command's
    with pytest.raises(subprocess.TimeoutExpired) as e:
        data._git(["-c", "alias.nap=!touch .git/index.lock; sleep 30",
                   "nap"], timeout=1)
    assert e.value.killed is False
    assert (hub / ".git" / "index.lock").exists()
    # and one there before the command is never this command's
    monkeypatch.setattr(data, "KILL_GRACE_S", 1)
    with pytest.raises(subprocess.TimeoutExpired) as e:
        data._git(["-c", "alias.deaf=!trap '' TERM; sleep 30", "deaf"],
                  timeout=1)
    assert e.value.killed is True
    assert (hub / ".git" / "index.lock").exists()


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
                        "words": "up to date", "detail": "up to date with origin",
                        "behind": False}
    r = client.post("/freshness")
    assert r.status_code == 200
    assert ('<span class="uk-badge uk-badge--ok" id="hub-pill" '
            'data-state="ok">') in r.text
    assert r.text.split('id="hub-pill"')[1].split("</span></span>")[0] \
        .endswith('<span class="uk-badge-t">up to date')
    # the check's own words in the "?" beside the badge
    assert 'id="tip-hub-detail">up to date with origin</span>' in r.text


def test_the_page_carries_the_progress_bar_and_the_script(hub, monkeypatch):
    monkeypatch.setattr(data, "vintages", lambda: [])
    html = client.get("/data").text
    assert 'id="hub-progress" hidden' in html
    # the kit's sliding bar, labelled with what runs; the status line
    # speaks it; a failure is an alert line
    assert '<div class="uk-progress uk-progress--busy" id="hub-bar">' in html
    assert 'role="progressbar" aria-labelledby="hub-bar-l"' in html
    assert 'id="hub-status" role="status" aria-live="polite"' in html
    assert "FluBNFUI.setBadge(pill,STATES[d.pill]||'neutral'" in html
    assert "err.innerHTML=ui.alert('error',msg)" in html
    assert "headers:{'Accept':'application/json'}" in html
    # the forms still post on their own without script
    assert '<form method="post" action="/data/pull">' in html
    assert '<form method="post" action="/freshness">' in html
