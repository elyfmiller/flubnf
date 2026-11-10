"""The Storage page after the second review-fix pass (bug hunt 2026-10-25,
review of the fix pull requests, S3).

  * ST-06: a protected season, archived run or report archive wears the
    lock and has no Delete, as a protected workroot does; an unprotected
    sibling keeps its Delete.
  * ST-11: the ledger's clear says "rows not running", one row plainly.
  * ST-14: a workroot's delete hint names only the files its folder holds,
    and a ledger row only for a recorded run (a cleared ledger leaves
    none).
  * ST-08: Storage keeps no "?" on Reclaim, the Sandbox or the students'
    experiments; the Sandbox and the students say theirs in a plain hint.
"""
import os
import re

import css_cascade
from app.core import sandbox as sb
from app.ui import shared as ui_shared
from app.ui.routes import storage as ui_storage
from test_fewer_marks import marks
from test_storage import (ARCH_STAMP, OTHER, SEASON,          # noqa: F401
                          _isolated_status, client, runner_pc, state,
                          students)

OTHER_STAMP = "20980211T090000Z"


def _rows(html: str, section: str) -> list:
    """The rows of one Storage section (by its heading id), each up to its
    closing </div>."""
    sec = html.split(f'aria-labelledby="h-{section}"', 1)[1].split(
        "</section>", 1)[0]
    return [r.split("</div>", 1)[0]
            for r in sec.split('<div class="st-row"')[1:]]


def _row(html: str, section: str, key: str) -> str:
    found = [r for r in _rows(html, section) if key in r]
    assert len(found) == 1, (section, key, len(found))
    return found[0]


def _locked(row: str) -> bool:
    return ('<span class="uk-badge-t">protected</span>' in row
            and "/storage/delete" not in row
            and "data-del-storage" not in row and "<form" not in row)


def _deletable(row: str) -> bool:
    return ('action="/storage/delete"' in row and "data-del-storage" in row
            and "uk-badge-t\">protected<" not in row)


# ----------------------------------------- ST-06: protected rows, every kind

def test_protected_season_archive_and_report_archive_rows_have_no_delete(
        state, monkeypatch):                               # noqa: F811
    root, rr = state["root"], state["retro_root"]
    # an unprotected sibling of each kind
    (rr / OTHER / "weeks").mkdir(parents=True)
    (rr / OTHER / "weeks" / "x.json").write_text("{}")
    sib_arch = rr / f"{SEASON}__archived_{OTHER_STAMP}"
    sib_arch.mkdir()
    (sib_arch / "scores.json").write_text("{}")
    sib_rep = root / "archive" / "2098-01-17"
    sib_rep.mkdir(parents=True)
    (sib_rep / "report.html").write_text("<p>r</p>")
    arch = rr / f"{SEASON}__archived_{ARCH_STAMP}"
    rep = root / "archive" / "2098-01-03"
    monkeypatch.setenv("FLUBNF_PROTECT_ROOTS", os.pathsep.join(
        str(p) for p in (rr / SEASON, arch, rep)))
    ui_shared._invalidate_scans()
    inv = ui_storage._storage_inventory()
    assert {s["id"]: s["protected"] for s in inv["retro"]} == {
        OTHER: False, SEASON: True}
    assert {a["id"]: a["protected"] for a in inv["retro_archives"]} == {
        arch.name: True, sib_arch.name: False}
    assert {f["id"]: f["protected"] for f in inv["report_archives"]} == {
        "2098-01-17": False, "2098-01-03": True}
    html = client.get("/runs").text
    # the season, the archived run and the report archive: the lock, no
    # Delete
    assert _locked(_row(html, "st-rs", f'href="/retro/{SEASON}"'))
    assert _locked(_row(html, "st-ra", f"archive={ARCH_STAMP}"))
    assert _locked(_row(html, "st-rp", 'date=2098-01-03"'))
    # each unprotected sibling keeps its Delete
    assert _deletable(_row(html, "st-rs", f'href="/retro/{OTHER}"'))
    assert _deletable(_row(html, "st-ra", f"archive={OTHER_STAMP}"))
    assert _deletable(_row(html, "st-rp", 'date=2098-01-17"'))
    # nothing protected: every one of them has its Delete again
    monkeypatch.delenv("FLUBNF_PROTECT_ROOTS")
    ui_shared._invalidate_scans()
    html = client.get("/runs").text
    for sec, key in (("st-rs", f'href="/retro/{SEASON}"'),
                     ("st-ra", f"archive={ARCH_STAMP}"),
                     ("st-rp", 'date=2098-01-03"')):
        assert _deletable(_row(html, sec, key)), sec


# ------------------------------------------- ST-11: the ledger's clear words

def test_the_ledger_clear_says_rows_not_running(state):  # noqa: F811
    words = " ".join(client.get("/runs").text.split())
    # ok, stopped and error rows; the running run's row is not counted
    assert "Clear 3 rows not running (files kept)</button>" in words
    assert "completed row" not in words
    state["ledger"].delete_runs([state["rids"]["ok"],
                                 state["rids"]["stopped"]])
    words = " ".join(client.get("/runs").text.split())
    assert "Clear 1 row not running (files kept)</button>" in words


# ------------------------------------- ST-14: the workroot delete hint's parts

def _hint(html: str, wid: str) -> str:
    row = html.split(f'data-wid="{wid}"', 1)[1].split("</div>", 1)[0]
    return re.search(r'data-hint="([^"]*)"', row).group(1)


def _files(w, *, report=False, sub=False, export=False):
    if report:
        (w / "report.html").write_text("<p>r</p>")
    for kind, on in (("submission", sub), ("export", export)):
        if on:
            f = w / kind / "FluBNF-Model" / "2098-01-10-FluBNF-Model.csv"
            f.parent.mkdir(parents=True)
            f.write_text("reference_date\n")


def test_the_workroot_delete_hint_names_only_what_is_there(state):  # noqa: F811
    root = state["root"]
    ok, stopped = state["rids"]["ok"], state["rids"]["stopped"]
    _files(root / "workroots" / ok, report=True, sub=True)
    # an unrecorded workroot with no report or submission files
    orphan = "20980118T093000-0aacd0"
    (root / "workroots" / orphan).mkdir()
    (root / "workroots" / orphan / "results.json").write_text("{}")
    ui_shared._invalidate_scans()
    html = client.get("/storage").text
    assert _hint(html, ok) == (
        f"Its folder {ok} goes, with the run&#39;s report and submission "
        "files in it. The ledger row stays and shows a dash for disk use.")
    # a stopped run that wrote neither file: no files promised
    assert _hint(html, stopped) == (
        f"Its folder {stopped} goes. The ledger row stays and shows a dash "
        "for disk use.")
    assert _hint(html, orphan) == f"Its folder {orphan} goes."
    # the ledger cleared: every run is unrecorded and no row is promised
    r = client.post("/runs/clear", data={"confirm": "3"},
                    follow_redirects=False)
    assert r.status_code == 303 and state["ledger"].rows(50)
    html = client.get("/storage").text
    assert 'data-what="the unrecorded run ' + ok + '"' in html
    assert _hint(html, ok) == (f"Its folder {ok} goes, with the run&#39;s "
                               "report and submission files in it.")
    assert _hint(html, stopped) == f"Its folder {stopped} goes."


def test_the_workroot_files_words(tmp_path):
    cases = [({}, ""), ({"report": True}, "report"),
             ({"sub": True}, "submission files"),
             ({"export": True}, "export files"),
             ({"report": True, "sub": True}, "report and submission files"),
             ({"report": True, "export": True}, "report and export files"),
             ({"report": True, "sub": True, "export": True},
              "report, submission files and export files")]
    for i, (kw, words) in enumerate(cases):
        w = tmp_path / f"w{i}"
        w.mkdir()
        _files(w, **kw)
        assert ui_storage._workroot_files(w) == words, kw
    # a submission folder with no file in it promises none
    w = tmp_path / "empty"
    (w / "submission" / "FluBNF-Model").mkdir(parents=True)
    assert ui_storage._workroot_files(w) == ""
    # the export folder is the one a dataset run writes
    from app.core.custom_run import EXPORT_DIR
    assert ui_storage._EXPORT_DIR == EXPORT_DIR


# ------------------------------------------------- ST-08: no marks on Storage

def test_storage_keeps_no_marks_with_reclaim_sandbox_and_students(
        state, runner_pc, tmp_path, monkeypatch):          # noqa: F811
    # a Sandbox on disk, this console's own (not a student's)
    mine = tmp_path / "console" / "sandbox"
    monkeypatch.setattr(sb, "SANDBOX", mine)
    monkeypatch.setattr(sb, "MODELS", mine / "models")
    monkeypatch.setattr(sb, "RUNS", mine / "runs")
    (mine / "runs" / "r1").mkdir(parents=True)
    (mine / "runs" / "r1" / "fit.log").write_text("x" * 2048)
    (mine / "models").mkdir()
    ui_shared._invalidate_scans()
    html = client.get("/storage").text
    # every state in place: bytes to reclaim, the Sandbox, the students
    assert 'id="reclaim-btn"' in html
    assert 'aria-labelledby="h-st-sbx"' in html
    assert 'aria-labelledby="h-st-stu"' in html
    for hid in ("st-reclaim", "st-sbx", "st-stu"):
        assert f'id="tip-{hid}"' not in html, hid
        assert f'aria-describedby="tip-{hid}"' not in html, hid
    # the page's marks, its folds opened: none
    opened = html.replace('id="storagefold">', 'id="storagefold" open>')
    assert marks(opened) == []
    # what the marks said, in a plain hint under each heading
    sbx = html.split('aria-labelledby="h-st-sbx"', 1)[1].split(
        "</section>", 1)[0]
    assert ('<p class="hint" id="st-sbx-hint">Not in the total above. '
            'Delete Sandbox models and runs in the Sandbox.</p>') in sbx
    stu = html.split('aria-labelledby="h-st-stu"', 1)[1].split(
        "</section>", 1)[0]
    hint = stu.split('<p class="hint" id="st-stu-hint">', 1)[1].split(
        "</p>", 1)[0]
    assert "(~/Students/&lt;name&gt;/sandbox)" in hint
    for part in ("the runner replays them one at a time",
                 "forecasting samples are dropped",
                 "takes it out of the queue",
                 "its model stays in the student's library",
                 "Not in the total"):
        assert part in hint, part
    assert "–" not in hint and "—" not in hint
    # the students block keeps its ids
    assert 'id="h-st-stu"' in stu
    # each hint reads as one: muted, at the hint size, on a phone too
    cas = css_cascade.Cascade.page("tabs/storage.css")
    for pid in ("st-sbx-hint", "st-stu-hint"):
        chain = css_cascade.path(
            "html", "body", "main", "div.card.st-card",
            "details.ledgerfold#storagefold:open", "section.st-sec",
            f"p.hint#{pid}")
        for width in (1280, 375):
            assert cas.value(chain, "color", width=width) == "var(--mut)"
            assert cas.value(chain, "font-size", width=width) == \
                "var(--fs-hint)"
            assert cas.value(chain, "display", width=width) is None
