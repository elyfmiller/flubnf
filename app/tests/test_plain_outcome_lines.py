"""Plain outcome lines first, operator detail in a closed, labelled fold
(review findings B7 and B8, compromise C3).

  * the Data tab's FluSight hub card says what a check found in plain
    words: "No new flu data since Nov 21: you are up to date" when the
    clone is level with the hub or the hub's new commits change nothing
    in the folders FluBNF reads (the sparse clone holds no team's
    forecasts), an info line naming what changed there (the FluSight
    ensemble's and baseline's forecasts) when they do, and "New flu
    data: the week ending Nov 28 is ready to update" when there is a new
    week. A failed check says why: no
    connection, or git's own reason when git refused the clone; with no
    hub folder, or commits that could not be counted, it says so too, so
    every check ends in a line. Check for new data comes first; Update
    data is the primary button only when there is new data. The commit
    count, origin and the check's own words sit in a closed "Hub clone
    details" fold under the line;
  * the kit's fold (tips.fold) is closed unless the page asks, labelled
    with what it holds, and with `remember` keeps each reader's open or
    closed choice in the browser (localStorage "fold:<id>"); it works
    without storage and without script. Its script and the hub card's
    are run here on the served page (JavaScriptCore, or node as on CI);
  * the same fold holds other operator detail: Home's component versions
    (the engine's commit) and the run page's software versions.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import data as data_mod                    # noqa: E402
from app.core import runs as runs_mod                    # noqa: E402
from app.core.runs import Ledger, RunSpec                # noqa: E402
from app.ui import server as srv                         # noqa: E402
from app.ui.routes import data as D                      # noqa: E402

import served_dom as SD                                  # noqa: E402
from test_pull_hub import _freshness_git, hub            # noqa: E402,F401
from test_ui_kit import render                           # noqa: E402

client = TestClient(srv.app)
F = data_mod.Freshness
TIPS_JS = Path(__file__).resolve().parents[1] / "ui" / "static" / "tips.js"
needs_js = pytest.mark.skipif(
    not SD.HAVE_JS, reason="no JavaScript engine (JavaScriptCore jsc or node)")

UP_TO_DATE = "No new flu data since Nov 21: you are up to date"
#: the comparators' folders in the sparse clone (data.COMPARATORS)
COMP_DIRS = tuple(sub for _name, sub in data_mod.COMPARATORS)
NEW_FORECASTS = ("No new flu data since Nov 21. The hub has new FluSight "
                 "baseline and ensemble forecasts; Update data brings them "
                 "in.")
NEW_WEEK = "New flu data: the week ending Nov 28 is ready to update"
OFFLINE = ("Could not reach the FluSight hub: check the internet connection "
           "and try again")


def _behind(n=46, week="2026-11-21", changed=COMP_DIRS, **kw):
    """A check that found the clone n commits behind origin and no new
    week in the hub's file (the review's case: 46 commits, no new data),
    the commits changing `changed` of the folders FluBNF reads (the
    round's ensemble and baseline by default; () for none of them)."""
    return F(week, week, n, False,
             f"{n} commits behind origin, no new week of data",
             local_live=week, remote_live=week, changed=changed, **kw)


# ----------------------------------------------------------- the words

@pytest.mark.parametrize("f, missing, want", [
    # no new week: up to date when level, or when the commits change none
    # of the folders FluBNF reads (other teams' forecasts, which the
    # sparse clone never holds); what they change there said by name,
    # but nothing that makes the pull the next step
    (_behind(), (), ("info", False, NEW_FORECASTS)),
    (_behind(changed=()), (), ("ok", False, UP_TO_DATE)),
    (F("2026-11-21", "2026-11-21", 0, True, "up to date with origin",
       local_live="2026-11-21", remote_live="2026-11-21"), (),
     ("ok", False, UP_TO_DATE)),
    (_behind(changed=("model-output/FluSight-ensemble",)), (),
     ("info", False, "No new flu data since Nov 21. The hub has new "
                     "FluSight ensemble forecasts; Update data brings them "
                     "in.")),
    (_behind(changed=("auxiliary-data",)), (),
     ("info", False, "No new flu data since Nov 21. The hub has updated "
                     "auxiliary data; Update data brings them in.")),
    (_behind(changed=("auxiliary-data", "target-data",
                      "model-output/FluSight-baseline")), (),
     ("info", False, "No new flu data since Nov 21. The hub has new "
                     "FluSight baseline forecasts, revised flu data and "
                     "updated auxiliary data; Update data brings them in.")),
    # git could not say what the commits change: no claim either way
    (_behind(changed=None), (),
     ("info", False, "No new flu data since Nov 21. The hub has changed "
                     "since your last update; Update data brings the "
                     "changes in.")),
    # the hub's file holds newer weeks: one, two, three, or a first pull
    (F(None, None, 3, False, "x", local_live="2026-11-21",
       remote_live="2026-11-28"), (), ("info", True, NEW_WEEK)),
    (F(None, None, 3, False, "x", local_live="2026-11-21",
       remote_live="2026-12-05"), (),
     ("info", True, "New flu data: the weeks ending Nov 28 and Dec 5 are "
                    "ready to update")),
    (F(None, None, 3, False, "x", local_live="2026-11-21",
       remote_live="2026-12-12"), (),
     ("info", True, "New flu data: the weeks ending Nov 28 to Dec 12 are "
                    "ready to update")),
    (F(None, None, 3, False, "x", local_live=None,
       remote_live="2026-11-28"), (),
     ("info", True, "New flu data: weeks through Nov 28 are ready to "
                    "update")),
    # across the new year
    (F(None, None, 1, False, "x", local_live="2026-12-26",
       remote_live="2027-01-02"), (),
     ("info", True, "New flu data: the week ending Jan 2 is ready to "
                    "update")),
    # a newer archived week (the live file level)
    (F("2026-11-14", "2026-11-21", 2, False, "x", local_live="2026-11-21",
       remote_live="2026-11-21"), (),
     ("info", True, "New flu data: the archived week ending Nov 21 is "
                    "ready to update")),
    # the file on disk is not the hub's
    (_behind(0, tree_stale=True), (),
     ("info", True, "Your copy of the flu data differs from the hub's: "
                    "Update data replaces it")),
    # commits whose file could not be read: no claim either way
    (F(None, None, 3, False, "x", local_live="2026-11-21"), (),
     ("info", True, "The hub has changed since your last update: Update "
                    "data brings the changes in")),
    # no new week, but the comparators a pull adds are missing
    (_behind(), ["baseline", "ensemble"],
     ("info", True, "No new flu data since Nov 21, but the hub's baseline "
                    "and ensemble forecasts are missing: Update data adds "
                    "them")),
    # offline: what to do, never git's words
    (F(None, None, None, False, "fetch failed: fatal: unable to access"), (),
     ("warn", False, OFFLINE)),
])
def test_the_outcome_in_plain_words(f, missing, want):
    o = D._hub_outcome(f, missing)
    assert (o["state"], o["new"], o["text"]) == want
    for word in ("commit", "origin", "clone", "vintage", "upstream"):
        assert word not in o["text"].lower(), word


def test_up_to_date_when_nothing_flubnf_reads_has_changed():
    level = _behind(0, changed=None)
    assert level.behind == 0
    for f, want in ((level, ("ok", UP_TO_DATE)),
                    (_behind(1, changed=()), ("ok", UP_TO_DATE)),
                    (_behind(46, changed=()), ("ok", UP_TO_DATE)),
                    (_behind(1), ("info", NEW_FORECASTS)),
                    (_behind(46), ("info", NEW_FORECASTS))):
        o = D._hub_outcome(f)
        assert (o["state"], o["text"]) == want
        # neither makes Update data the primary: no new week either way
        assert o["new"] is False and D._new_data(f) is False
    # no week to name: the same line without a date
    assert D._hub_outcome(_behind(0, week=None))["text"] == \
        "No new flu data: you are up to date"


@pytest.mark.parametrize("why", [
    "fatal: unable to access 'https://github.com/cdcepi/FluSight-forecast-"
    "hub/': Could not resolve host: github.com",
    "fatal: unable to access 'https://github.com/cdcepi/FluSight-forecast-"
    "hub/': Failed to connect to github.com port 443 after 75003 ms: "
    "Couldn't connect to server",
    "fatal: unable to access 'https://github.com/cdcepi/FluSight-forecast-"
    "hub/': SSL certificate problem: unable to get local issuer certificate",
    "fatal: unable to access 'https://github.com/cdcepi/FluSight-forecast-"
    "hub/': Recv failure: Connection reset by peer",
    "ssh: connect to host github.com port 22: Network is unreachable",
    "ssh: connect to host github.com port 22: Connection refused",
    "Command '['git', 'fetch', 'origin']' timed out after 60 seconds",
])
def test_a_fetch_that_found_no_network_says_check_the_connection(why):
    f = F(None, None, None, False, f"fetch failed: {why}")
    assert f.offline is True
    assert D._hub_outcome(f) == {"state": "warn", "new": False,
                                 "text": OFFLINE}
    assert f.pill() == ("bad", "offline")


@pytest.mark.parametrize("why, said", [
    ("fatal: detected dubious ownership in repository at '/Users/ssl/"
     "timed out/hub'",
     "detected dubious ownership in repository at '/Users/ssl/timed out/"
     "hub'"),
    ("fatal: not a git repository (or any of the parent directories): .git",
     "not a git repository (or any of the parent directories): .git"),
    ("fatal: refusing to fetch into branch 'refs/heads/main' checked out at "
     "'/data/hub'",
     "refusing to fetch into branch 'refs/heads/main' checked out at "
     "'/data/hub'"),
    ("[Errno 20] Not a directory: '/data/hub'",
     "Not a directory: '/data/hub'"),
    ("git exited 128", "git exited 128"),
])
def test_a_fetch_git_refused_says_why_not_check_the_connection(why, said):
    # a path's own words (ssl, timed out) are not a network failure
    f = F(None, None, None, False, f"fetch failed: {why}")
    assert f.offline is False
    assert D._hub_outcome(f) == {
        "state": "warn", "new": False,
        "text": f"Could not check the FluSight hub: {said}"}
    assert f.pill() == ("bad", "check failed")


def test_a_check_git_refused_keeps_its_reason(hub, monkeypatch):  # noqa: F811
    from test_pull_hub import _R, _fake
    monkeypatch.setattr(data_mod, "vintages", lambda: [])
    monkeypatch.setattr(data_mod, "live_newest_week", lambda: "2026-11-21")
    _fake(monkeypatch, hub, fetch=_R(128, "", (
        f"fatal: detected dubious ownership in repository at '{hub}'\n"
        "To add an exception for this directory, call:\n\n"
        f"\tgit config --global --add safe.directory {hub}\n")))
    f = data_mod.check_freshness()
    assert D._hub_outcome(f)["text"] == (
        "Could not check the FluSight hub: detected dubious ownership in "
        f"repository at '{hub}'")
    # offline still reads as offline
    _fake(monkeypatch, hub, fetch=_R(128, "", (
        "fatal: unable to access 'https://github.com/cdcepi/FluSight-"
        "forecast-hub/': Could not resolve host: github.com\n")))
    assert D._hub_outcome(data_mod.check_freshness())["text"] == OFFLINE


def test_a_file_at_the_hub_path_is_not_called_offline(
        tmp_path, monkeypatch, hub_check_real):
    # the folder test passes (something is there), then git cannot run in
    # it: the system's own reason, never the internet line
    spot = tmp_path / "hub"
    spot.write_text("not a folder", encoding="utf-8")
    monkeypatch.setattr(data_mod, "HUB", spot)
    monkeypatch.setattr(data_mod, "vintages", lambda: [])
    monkeypatch.setattr(data_mod, "live_newest_week", lambda: None)
    f = data_mod.check_freshness()
    assert f.detail.startswith("fetch failed: ")
    assert f.offline is False and f.pill() == ("bad", "check failed")
    o = D._hub_outcome(f)
    assert o["state"] == "warn" and o["new"] is False
    assert o["text"].startswith("Could not check the FluSight hub: ")
    assert "internet" not in o["text"] and "Errno" not in o["text"]


def test_before_a_check_no_outcome_and_every_check_ends_in_a_line(
        monkeypatch):
    from app.ui import templating
    monkeypatch.setattr(templating, "_platform", lambda: "linux")
    assert D._hub_outcome(None) is None
    # no hub folder: the card's own no-data sentence (its alert's words,
    # test_hub_setup), as plain text
    assert D._hub_outcome(F(None, None, None, False,
                            "no hub clone: there is no hub folder at /x")) \
        == {"state": "warn", "new": False,
            "text": ("No FluSight data: there is no hub folder at /x. To "
                     "fetch it, run ./setup.sh and relaunch the console.")}
    # nothing compared: the hub clone could not be read
    assert D._hub_outcome(F(None, None, None, False, "")) == {
        "state": "warn", "new": False, "text": "Could not read the hub clone"}
    # a week that is not a date: said, not dropped
    assert D._hub_outcome(F(None, None, 0, True, "up to date with origin",
                            local_live="soon", remote_live="soon")) == {
        "state": "warn", "new": False,
        "text": "Could not read the hub clone: a week in the flu data is "
                "not a date"}


def test_commits_alone_are_a_quiet_fact_in_the_fold():
    assert _behind(46).pill() == ("neutral", "46 commits behind")
    assert _behind(1).pill() == ("neutral", "1 commit behind")
    # a file on disk that is not origin's still asks for a look
    assert _behind(3, tree_stale=True).pill() == ("warn", "stale files")
    assert D._new_data(_behind(46)) is False


def test_the_checks_own_words_count_commits_properly(hub, monkeypatch):  # noqa: F811
    from test_pull_hub import _R
    monkeypatch.setattr(data_mod, "vintages", lambda: [])
    monkeypatch.setattr(data_mod, "live_newest_week", lambda: "2026-07-04")
    g = _freshness_git(hub, monkeypatch, behind="46")
    g.answers["diff"] = _R(0, "model-output/FluSight-ensemble/2026-07-05-"
                              "FluSight-ensemble.csv\n")
    f = data_mod.check_freshness()
    assert f.detail == "46 commits behind origin, no new week of data"
    assert D._hub_outcome(f)["text"] == (
        "No new flu data since Jul 4. The hub has new FluSight ensemble "
        "forecasts; Update data brings them in.")
    _freshness_git(hub, monkeypatch, behind="0")
    assert D._hub_outcome(data_mod.check_freshness())["text"] == (
        "No new flu data since Jul 4: you are up to date")
    _freshness_git(hub, monkeypatch, behind="1")
    assert data_mod.check_freshness().detail == \
        "1 commit behind origin, no new week of data"
    # origin's file unreadable: the count alone, no claim about weeks
    _freshness_git(hub, monkeypatch, behind="2", remote_csv="")
    assert data_mod.check_freshness().detail == "2 commits behind origin"


def test_the_check_asks_git_what_the_commits_change_in_the_read_folders(
        hub, monkeypatch):  # noqa: F811
    from flubnf.settings import HUB_DIRS
    from test_pull_hub import _R
    monkeypatch.setattr(data_mod, "vintages", lambda: [])
    monkeypatch.setattr(data_mod, "live_newest_week", lambda: "2026-07-04")
    ask = ["diff", "--name-only", "--no-renames", "HEAD", "origin/main",
           "--", *HUB_DIRS]
    # commits with no new week: git names the read folders' changed files
    g = _freshness_git(hub, monkeypatch, behind="46")
    g.answers["diff"] = _R(0, (
        "auxiliary-data/locations.csv\n"
        "model-output/FluSight-baseline/2026-07-05-FluSight-baseline.csv\n"
        "model-output/FluSight-ensemble/2026-07-05-FluSight-ensemble.csv\n"))
    f = data_mod.check_freshness()
    assert ask in g.calls
    assert f.changed == ("auxiliary-data", "model-output/FluSight-baseline",
                         "model-output/FluSight-ensemble")
    # only other folders changed (teams' forecasts): git lists nothing
    # under the read folders, and the clone is up to date for FluBNF; the
    # count stays in the fold
    g = _freshness_git(hub, monkeypatch, behind="46")
    f = data_mod.check_freshness()
    assert ask in g.calls and f.changed == ()
    assert D._hub_outcome(f) == {
        "state": "ok", "new": False,
        "text": "No new flu data since Jul 4: you are up to date"}
    assert f.pill() == ("neutral", "46 commits behind")
    # a file FluBNF leaves out of the clone (data.HUB_SKIPPED) is no news
    g = _freshness_git(hub, monkeypatch, behind="3")
    g.answers["diff"] = _R(0, "".join(p + "\n" for p in data_mod.HUB_SKIPPED))
    assert data_mod.check_freshness().changed == ()
    # git could not say: unknown, not "nothing changed"
    g = _freshness_git(hub, monkeypatch, behind="3")
    g.answers["diff"] = _R(128, "", "fatal: bad revision 'origin/main'\n")
    f = data_mod.check_freshness()
    assert f.changed is None
    assert D._hub_outcome(f)["text"] == (
        "No new flu data since Jul 4. The hub has changed since your last "
        "update; Update data brings the changes in.")

    def slow(args):
        raise data_mod.subprocess.TimeoutExpired(args, 30)
    g = _freshness_git(hub, monkeypatch, behind="3")
    g.answers["diff"] = slow
    f = data_mod.check_freshness()
    assert f.changed is None and f.detail.startswith("3 commits behind")
    # level, or a new week: nothing to ask
    for behind, local in (("0", "2026-07-04"), ("3", "2026-06-27")):
        monkeypatch.setattr(data_mod, "live_newest_week", lambda w=local: w)
        g = _freshness_git(hub, monkeypatch, behind=behind)
        f = data_mod.check_freshness()
        assert "diff" not in g.subs() and f.changed is None


def _commit(repo, files: dict, msg="c"):
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text, encoding="utf-8")
    for a in (["add", "-A"], ["-c", "user.name=t", "-c",
                              "user.email=t@example.com", "commit", "-q",
                              "-m", msg]):
        subprocess.run(["git", "-C", str(repo), *a], check=True,
                       capture_output=True)


def test_a_real_sparse_clone_is_up_to_date_until_a_read_folder_changes(
        tmp_path, monkeypatch):
    from flubnf.settings import HUB_DIRS
    src, hub = tmp_path / "src", tmp_path / "hub"
    src.mkdir()
    subprocess.run(["git", "-C", str(src), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(src), "symbolic-ref", "HEAD",
                    "refs/heads/main"], check=True)
    _commit(src, {data_mod.LIVE_TARGET: "date,location,value\n"
                                        "2026-11-21,US,1\n",
                  "auxiliary-data/locations.csv": "location\nUS\n",
                  "model-output/FluSight-baseline/a.csv": "a\n",
                  "model-output/FluSight-ensemble/a.csv": "a\n",
                  "model-output/team-a/a.csv": "a\n"})
    subprocess.run(["git", "clone", "-q", "--sparse", str(src), str(hub)],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(hub), "sparse-checkout", "set",
                    *HUB_DIRS], check=True, capture_output=True)
    monkeypatch.setattr(data_mod, "HUB", hub)
    monkeypatch.setattr(data_mod, "vintages", lambda: [])
    monkeypatch.setattr(data_mod, "live_newest_week", lambda: "2026-11-21")
    # two teams' rounds and the hub's time series (left out of the clone)
    _commit(src, {"model-output/team-a/b.csv": "b\n",
                  "model-output/team-b/b.csv": "b\n"})
    _commit(src, {data_mod.HUB_SKIPPED[0]: "x\n"})
    f = data_mod.check_freshness()
    assert (f.behind, f.changed) == (2, ())
    assert D._hub_outcome(f)["text"] == ("No new flu data since Nov 21: you "
                                         "are up to date")
    # the round's ensemble: said by name
    _commit(src, {"model-output/FluSight-ensemble/b.csv": "b\n"})
    f = data_mod.check_freshness()
    assert (f.behind, f.changed) == (3, ("model-output/FluSight-ensemble",))
    assert D._hub_outcome(f) == {
        "state": "info", "new": False,
        "text": ("No new flu data since Nov 21. The hub has new FluSight "
                 "ensemble forecasts; Update data brings them in.")}


def test_commits_that_cannot_be_counted_say_so_with_gits_reason(
        hub, monkeypatch):  # noqa: F811
    from test_pull_hub import _R
    monkeypatch.setattr(data_mod, "vintages", lambda: [])
    monkeypatch.setattr(data_mod, "live_newest_week", lambda: "2026-07-04")
    g = _freshness_git(hub, monkeypatch)
    g.answers["rev-list"] = _R(128, "", (
        "fatal: ambiguous argument 'HEAD..origin/main': unknown revision or "
        "path not in the working tree.\nUse '--' to separate paths from "
        "revisions, like this:\n'git <command> [<revision>...] -- "
        "[<file>...]'\n"))
    f = data_mod.check_freshness()
    assert f.behind is None and f.is_fresh is False
    # git's fatal line, not the usage hint after it
    assert f.detail == ("could not compare with origin: fatal: ambiguous "
                        "argument 'HEAD..origin/main': unknown revision or "
                        "path not in the working tree.")
    assert D._hub_outcome(f) == {
        "state": "warn", "new": False,
        "text": ("Could not read the hub clone: ambiguous argument "
                 "'HEAD..origin/main': unknown revision or path not in the "
                 "working tree")}
    # a newer week in origin's file is still news, count or no count
    monkeypatch.setattr(data_mod, "live_newest_week", lambda: "2026-06-27")
    f = data_mod.check_freshness()
    assert D._hub_outcome(f)["text"] == ("New flu data: the week ending "
                                         "Jul 4 is ready to update")


# ------------------------------------------------------- the hub card

def _card(monkeypatch, f) -> str:
    """The Data page as a plain (no-script) Check for new data answers
    with `f`, cut to the FluSight hub card."""
    monkeypatch.setattr(data_mod, "vintages", lambda: [])
    monkeypatch.setattr(data_mod, "live_newest_week",
                        lambda: getattr(f, "local_live", None) or "2026-11-21")
    if f is not None:
        monkeypatch.setattr(data_mod, "check_freshness", lambda: f)
        html = client.post("/freshness").text
    else:
        html = client.get("/data").text
    return html.split('class="card hubcard"', 1)[1] \
        .split('<div class="card dt-archive">', 1)[0]


def _fold(card: str) -> str:
    return card.split('id="hub-clone-fold"', 1)[1].split("</details>", 1)[0]


def _visible(html: str) -> str:
    """Text outside scripts and tags."""
    html = re.sub(r"<script>.*?</script>", "", html, flags=re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _line(card: str) -> str:
    return card.split('id="hub-outcome"', 1)[1].split("</div></div>", 1)[0]


def test_level_with_the_hub_says_up_to_date(hub, monkeypatch):  # noqa: F811
    line = _line(_card(monkeypatch, _behind(0)))
    assert '<div class="uk-alert uk-alert--ok" id="hub-outcome-line">' in line
    assert f'<span class="uk-alert-text">{UP_TO_DATE}</span>' in line


def test_no_new_week_names_the_new_forecasts_and_keeps_update_data_quiet(
        hub, monkeypatch):  # noqa: F811
    card = _card(monkeypatch, _behind())
    # the outcome in plain words, an info line, not "up to date" (the
    # status line speaks it, so the line has no role of its own)
    line = _line(card)
    assert '<div class="uk-alert uk-alert--info" id="hub-outcome-line">' in line
    assert f'<span class="uk-alert-text">{NEW_FORECASTS}</span>' in line
    assert "up to date" not in line
    assert "role=" not in line
    # Check for new data first and the primary; Update data quiet
    assert card.index('id="hub-check"') < card.index('id="hub-pull"')
    assert 'class="gold" id="hub-check"' in card
    assert 'class="quiet" id="hub-pull"' in card
    # then the outcome, then the closed fold labelled with what it holds
    assert card.index('id="hub-pull"') < card.index('id="hub-outcome"') \
        < card.index('id="hub-clone-fold"')
    assert ('<details class="uk-fold" id="hub-clone-fold" data-remember>'
            '<summary><span class="uk-fold-sum">Hub clone details</span>'
            '</summary>') in card
    # the commit count and origin live in the fold, and nowhere else on
    # the card
    fold = _fold(card)
    assert ('<span class="uk-badge uk-badge--neutral" id="hub-pill" '
            'data-state="neutral">') in fold
    assert '<span class="uk-badge-t">46 commits behind</span>' in fold
    assert ('<p class="hint" id="hub-detail">46 commits behind origin, no '
            'new week of data</p>') in fold
    outside = _visible(card.replace(card.split('<details class="uk-fold" '
                                               'id="hub-clone-fold"', 1)[1]
                                    .split("</details>", 1)[0], ""))
    for word in ("commit", "origin"):
        assert word not in outside.lower(), word
    # no warning mark for commits
    assert "uk-badge--warn" not in card and "uk-alert--warn" not in card


def test_a_new_week_makes_update_data_the_primary(hub, monkeypatch):  # noqa: F811
    card = _card(monkeypatch, F(None, None, 3, False, "x",
                                local_live="2026-11-21",
                                remote_live="2026-11-28"))
    assert '<div class="uk-alert uk-alert--info" id="hub-outcome-line">' in card
    assert f'<span class="uk-alert-text">{NEW_WEEK}</span>' in card
    # the check still comes first; the pull is now the primary
    assert card.index('id="hub-check"') < card.index('id="hub-pull"')
    assert 'class="quiet" id="hub-check"' in card
    assert 'class="gold" id="hub-pull"' in card


def test_before_a_check_no_outcome_and_the_fold_says_not_checked(
        hub, monkeypatch):  # noqa: F811
    card = _card(monkeypatch, None)
    assert '<div id="hub-outcome"></div>' in card
    assert '<span class="uk-badge-t">not checked</span>' in _fold(card)
    assert '<p class="hint" id="hub-detail" hidden></p>' in _fold(card)
    assert 'class="gold" id="hub-check"' in card


def test_the_json_answer_carries_the_outcome(hub, monkeypatch):  # noqa: F811
    monkeypatch.setattr(data_mod, "check_freshness", lambda: _behind())
    r = client.post("/freshness", headers={"Accept": "application/json"})
    assert r.json() == {
        "ok": True, "fresh": False, "pill": "neutral",
        "words": "46 commits behind",
        "detail": "46 commits behind origin, no new week of data",
        "new_data": False,
        "outcome": {"state": "info", "new": False, "text": NEW_FORECASTS}}


# ------------------------------------------------- the kit's fold macro

def test_the_fold_remembers_only_when_asked_and_named():
    # a fold that remembers: data-remember after the page's own state
    html = render('{% call t.fold("Hub clone details", id="x", remember=True) %}'
                  "b{% endcall %}")
    assert html.startswith('<details class="uk-fold" id="x" data-remember>'
                           '<summary><span class="uk-fold-sum">Hub clone '
                           'details</span></summary>')
    assert render('{% call t.fold("a", id="x", open=True, remember=True) %}'
                  "b{% endcall %}").startswith(
        '<details class="uk-fold" id="x" open data-remember><summary>')
    # nothing to key it by: no memory
    assert "data-remember" not in render(
        '{% call t.fold("a", remember=True) %}b{% endcall %}')
    # every other fold is drawn as before: closed unless asked, no memory
    assert render('{% call t.fold("a", id="y") %}b{% endcall %}').startswith(
        '<details class="uk-fold" id="y"><summary>')


# ------------------------------------------ the fold's memory, as served

#: the page's browser, as far as tips.js and the hub card's script reach:
#: `window` with listeners and a storage that logs its writes (or throws),
#: `location`, a details element's `open` (its toggle event queued, as a
#: browser queues it, and only on a change), a button's className
_PRELUDE = r"""
var LS = %(ls)s, WRITES = [], DENY = %(deny)s;
var window = {L: {}, addEventListener: function (t, f) {
  (this.L[t] = this.L[t] || []).push(f); }};
Object.defineProperty(window, 'localStorage', {get: function () {
  if (DENY) throw new Error('SecurityError: storage is off');
  return {getItem: function (k) {
            return Object.prototype.hasOwnProperty.call(LS, k) ? LS[k] : null; },
          setItem: function (k, v) { WRITES.push([k, String(v)]);
                                     LS[k] = String(v); }};
}});
var location = {hash: %(hash)s, reload: function () { location.reloaded = true; }};
document.documentElement = document.querySelector('html');
document.querySelectorAll('details').forEach(function (d) {
  Object.defineProperty(d, 'open', {
    get: function () { return this.hasAttribute('open'); },
    set: function (v) {
      var was = this.hasAttribute('open'), self = this;
      if (v) this.setAttribute('open', ''); else this.removeAttribute('open');
      if (!!v !== was) setTimeout(function () {
        self.dispatchEvent({type: 'toggle', bubbles: false}); });
    }});
});
document.querySelectorAll('button').forEach(function (b) {
  Object.defineProperty(b, 'className', {
    get: function () { return this.getAttribute('class') || ''; },
    set: function (v) { this.setAttribute('class', v); }});
});
"""


def _prelude(ls=None, deny=False, hash_="") -> str:
    return _PRELUDE % {"ls": json.dumps(ls or {}), "deny": json.dumps(deny),
                       "hash": json.dumps(hash_)}


def _data_page(monkeypatch) -> str:
    monkeypatch.setattr(data_mod, "vintages", lambda: [])
    monkeypatch.setattr(data_mod, "live_newest_week", lambda: "2026-11-21")
    return client.get("/data").text


_STATE = """
flush();
var d = document.getElementById('hub-clone-fold');
return {open: d.open, writes: WRITES, ls: LS};
"""


@needs_js
def test_a_fold_with_nothing_kept_stays_closed_and_writes_nothing(
        hub, monkeypatch, tmp_path):  # noqa: F811
    out = SD.run(tmp_path, _data_page(monkeypatch), [TIPS_JS], _STATE,
                 prelude=_prelude())
    assert out == {"open": False, "writes": [], "ls": {}}


@needs_js
def test_a_fold_left_open_opens_again_and_the_readers_choice_is_kept(
        hub, monkeypatch, tmp_path):  # noqa: F811
    page = _data_page(monkeypatch)
    # left open last time: open again, and opening it is not a new write
    out = SD.run(tmp_path, page, [TIPS_JS], _STATE,
                 prelude=_prelude({"fold:hub-clone-fold": "1"}))
    assert out == {"open": True, "writes": [],
                   "ls": {"fold:hub-clone-fold": "1"}}
    # the reader closes it, then opens it: each choice kept under its id
    out = SD.run(tmp_path, page, [TIPS_JS], """
      flush();
      var d = document.getElementById('hub-clone-fold');
      d.open = false; flush();
      var closed = LS['fold:hub-clone-fold'];
      d.open = true; flush();
      return [closed, LS['fold:hub-clone-fold'], WRITES.length];
    """, prelude=_prelude({"fold:hub-clone-fold": "1"}))
    assert out == ["0", "1", 2]
    # kept closed: the page's closed fold stays closed
    out = SD.run(tmp_path, page, [TIPS_JS], _STATE,
                 prelude=_prelude({"fold:hub-clone-fold": "0"}))
    assert out["open"] is False


@needs_js
def test_without_storage_the_fold_still_opens_and_closes(
        hub, monkeypatch, tmp_path):  # noqa: F811
    out = SD.run(tmp_path, _data_page(monkeypatch), [TIPS_JS], """
      flush();
      var d = document.getElementById('hub-clone-fold'), was = d.open;
      d.open = true; flush();
      return [was, d.open, WRITES.length];
    """, prelude=_prelude(deny=True))
    assert out == [False, True, 0]


@needs_js
def test_a_fold_the_page_asks_open_stays_open(hub, monkeypatch, tmp_path):  # noqa: F811
    page = _data_page(monkeypatch).replace(
        'id="hub-clone-fold" data-remember>',
        'id="hub-clone-fold" open data-remember>')
    out = SD.run(tmp_path, page, [TIPS_JS], _STATE,
                 prelude=_prelude({"fold:hub-clone-fold": "0"}))
    assert out["open"] is True and out["writes"] == []


@needs_js
def test_a_link_into_a_closed_fold_opens_it_without_counting_as_a_choice(
        hub, monkeypatch, tmp_path):  # noqa: F811
    page = _data_page(monkeypatch)
    # on load: the address points at the badge inside the fold
    out = SD.run(tmp_path, page, [TIPS_JS], _STATE,
                 prelude=_prelude(hash_="#hub-pill"))
    assert out == {"open": True, "writes": [], "ls": {}}
    # on a hash change after load
    out = SD.run(tmp_path, page, [TIPS_JS], """
      flush();
      var d = document.getElementById('hub-clone-fold'), was = d.open;
      location.hash = '#hub-detail';
      (window.L.hashchange || []).forEach(function (f) { f({}); });
      flush();
      return [was, d.open, WRITES.length];
    """, prelude=_prelude())
    assert out == [False, True, 0]


# --------------------------------------- the hub card's script, as served

def _hub_script(page: str, tmp_path: Path) -> Path:
    """The Data page's inline script for the hub card's two buttons, as
    a file the harness runs after tips.js."""
    src = next(c.split("</script>", 1)[0] for c in page.split("<script>")
               if ".hubacts form" in c.split("</script>", 1)[0])
    p = tmp_path / "hub-card.js"
    p.write_text(src, encoding="utf-8")
    return p


_CHECK = r"""
var ANSWERS = %s, asked = [];
window.fetch = function (url, opts) {
  asked.push([url, opts.method, opts.headers.Accept]);
  var a = ANSWERS.shift();
  function done(v) { return {then: function (f) { return done(f(v)); },
                             'catch': function () { return this; }}; }
  return done({json: function () { return a; }});
};
var fetch = window.fetch;
"""

_PRESS = r"""
flush();
var out = [], n = ANSWERS.length;
for (var i = 0; i < n; i++) {
  var ev = {type: 'submit', bubbles: true, defaultPrevented: false,
            preventDefault: function () { this.defaultPrevented = true; }};
  document.getElementById('hub-check').parentNode.dispatchEvent(ev);
  var pill = document.getElementById('hub-pill');
  out.push({outcome: document.getElementById('hub-outcome').innerHTML,
            status: document.getElementById('hub-status').textContent,
            pill: [pill.getAttribute('data-state'), pill.innerHTML],
            detail: [document.getElementById('hub-detail').textContent,
                     document.getElementById('hub-detail').hidden],
            check: document.getElementById('hub-check').className,
            pull: document.getElementById('hub-pull').className,
            busy: document.getElementById('hub-check').disabled,
            error: document.getElementById('hub-error').innerHTML || ''});
}
return {asked: asked, out: out};
"""


@needs_js
def test_the_cards_script_shows_each_checks_outcome(hub, monkeypatch, tmp_path):  # noqa: F811
    page = _data_page(monkeypatch)
    answers = []
    for f in (_behind(), F(None, None, 3, False, "new data upstream",
                           local_live="2026-11-21", remote_live="2026-11-28")):
        monkeypatch.setattr(data_mod, "check_freshness", lambda f=f: f)
        answers.append(client.post(
            "/freshness", headers={"Accept": "application/json"}).json())
    got = SD.run(tmp_path, page, [TIPS_JS, _hub_script(page, tmp_path)],
                 _PRESS, prelude=_prelude() + _CHECK % json.dumps(answers))
    assert got["asked"] == [["/freshness", "POST", "application/json"]] * 2
    same, new = got["out"]
    # no new week: the info line naming the new forecasts, spoken by the
    # status line; the count in the fold as a quiet fact; Check for new
    # data stays the primary
    assert 'class="uk-alert uk-alert--info"' in same["outcome"]
    assert f'<span class="uk-alert-text">{NEW_FORECASTS}</span>' in same["outcome"]
    assert "role=" not in same["outcome"]
    assert same["status"] == NEW_FORECASTS
    assert same["pill"][0] == "neutral" and "46 commits behind" in same["pill"][1]
    assert same["detail"] == ["46 commits behind origin, no new week of data",
                              False]
    assert (same["check"], same["pull"], same["busy"]) == ("gold", "quiet", False)
    assert same["error"] == ""
    # a new week: the info line, and Update data becomes the primary
    assert 'class="uk-alert uk-alert--info"' in new["outcome"]
    assert f'<span class="uk-alert-text">{NEW_WEEK}</span>' in new["outcome"]
    assert new["status"] == NEW_WEEK
    assert (new["check"], new["pull"]) == ("quiet", "gold")


@needs_js
def test_a_check_that_cannot_compare_still_shows_and_says_a_line(
        hub, monkeypatch, tmp_path):  # noqa: F811
    from app.ui import templating
    monkeypatch.setattr(templating, "_platform", lambda: "linux")
    page = _data_page(monkeypatch)
    answers, want = [], []
    for f, text in (
            # no hub folder: the card's no-data sentence
            (F(None, None, None, False,
               "no hub clone: there is no hub folder at /x"),
             "No FluSight data: there is no hub folder at /x. To fetch it, "
             "run ./setup.sh and relaunch the console."),
            # the commits could not be counted: git's reason
            (F(None, None, None, False,
               "could not compare with origin: fatal: bad revision "
               "'HEAD..origin/main'", local_live="2026-11-21"),
             "Could not read the hub clone: bad revision "
             "'HEAD..origin/main'"),
            # git refused the clone: its reason, not the internet line
            (F(None, None, None, False,
               "fetch failed: fatal: not a git repository (or any of the "
               "parent directories): .git"),
             "Could not check the FluSight hub: not a git repository (or "
             "any of the parent directories): .git")):
        monkeypatch.setattr(data_mod, "check_freshness", lambda f=f: f)
        answers.append(client.post(
            "/freshness", headers={"Accept": "application/json"}).json())
        want.append(text)
    assert [a["outcome"]["text"] for a in answers] == want
    got = SD.run(tmp_path, page, [TIPS_JS, _hub_script(page, tmp_path)],
                 _PRESS, prelude=_prelude() + _CHECK % json.dumps(answers))
    for o, text in zip(got["out"], want):
        # a warn line under the buttons, and the status line speaks it
        assert 'class="uk-alert uk-alert--warn"' in o["outcome"]
        assert f'<span class="uk-alert-text">{text}</span>' in o["outcome"]
        assert o["status"] == text
        # none makes Update data the primary
        assert (o["check"], o["pull"], o["busy"]) == ("gold", "quiet", False)


def test_the_cards_busy_words_are_plain():
    src = (Path(__file__).resolve().parents[1] / "ui" / "templates"
           / "data.html").read_text(encoding="utf-8")
    assert ("busy(true,pull?'Updating the flu data':'Checking the FluSight "
            "hub for new data');") in src
    assert "Checking origin" not in src and "Pulling the hub clone" not in src


# ------------------------------------- operator detail on other pages

def test_home_keeps_component_versions_in_a_fold(monkeypatch):
    html = client.get("/").text
    card = html.split('<div class="card hm-setup">', 1)[1]
    # the outcome (the heading's badge) first, outside the fold
    assert card.index('id="hm-setup-state"') < card.index('id="hm-versions-fold"')
    assert ('<details class="uk-fold hm-versions-fold" id="hm-versions-fold" '
            'data-remember><summary><span class="uk-fold-sum">Component '
            'versions</span></summary>') in card
    fold = card.split('id="hm-versions-fold"', 1)[1].split("</details>", 1)[0]
    assert 'aria-label="Component versions"' in fold


def _run_page(tmp_path, monkeypatch, build) -> str:
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    led = Ledger()
    rid = led.open_run(RunSpec(engine="all", forecast_date="2098-01-03"),
                       Path("pending"), {"pybnf": "1.8.1", "pybnf_build": build})
    led.close_run(rid, "ok", {})
    return client.get(f"/runs/{rid}").text


def test_the_run_page_keeps_software_versions_in_a_fold(tmp_path, monkeypatch):
    from app.core import engine_build as EB
    prod = {"branch": EB.PRODUCTION_ENGINE_BRANCH,
            "commit": EB.PRODUCTION_ENGINE_COMMIT[:8], "dirty": False,
            "source": "git"}
    page = _run_page(tmp_path, monkeypatch, prod)
    rec = page.split('class="card runrec"', 1)[1]
    assert ('<details class="uk-fold" id="run-versions" data-remember>'
            '<summary><span class="uk-fold-sum">Software versions</span>'
            '</summary>') in rec
    fold = rec.split('id="run-versions"', 1)[1].split("</details>", 1)[0]
    assert "<dt>pybnf</dt><dd>1.8.1</dd>" in fold
    assert "<dt>PyBNF build</dt>" in fold
    assert "Produced by" not in page
    # another build than production says so on the fold's own line
    other = {"branch": "main", "commit": "deadbeef", "dirty": False,
             "source": "git"}
    page = _run_page(tmp_path / "other", monkeypatch, other)
    summary = page.split('id="run-versions"', 1)[1].split("</summary>", 1)[0]
    assert '<span class="uk-fold-sum">Software versions</span>' in summary
    assert 'id="run-versions-warn"' in summary
    assert '<span class="uk-badge-t">not the production build</span>' in summary
