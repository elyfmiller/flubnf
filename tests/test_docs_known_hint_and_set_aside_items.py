"""Four things known and left as they are, recorded in the App lane's
notes (docs/team/app.md, Now, 2026-11-10 night), and the facts that note
states, read from the code as it is or worked out by it.

1. The "more earlier seasons" hint counts a first season that holds part
   of the donor window as a whole one, so its figure can be too large.
2. Zeros that fall by chance in low counts can make the hint say "would
   not help" where more seasons would help.
3. A Replace's old run can stay beside the new one for good (app-final's
   8a7a4dd7; until that is merged here, the sweep deletes such a run once
   any whole import is at the run's name).
4. Builds a003431d to 1ce301ed deleted a set-aside run with its
   imported.json in place; the sweep since 0433736d would put part of a
   run such a delete left back under the run's name as whole.

And eight more recorded beside them (Now, 2026-11-10 late night), two
with a fix to follow:

5. A Replace whose rename of the old run to .dropping- is refused deletes
   it where it is, and a delete stopped part way leaves part of a run
   under its .replaced- name, which every import names for good.
6. An import that fails with a disk error (OSError) does not name a kept
   set-aside run.
7. A Delete of a run leaves its set-aside and temp trees and says nothing
   of them; the next import puts an older run back (fix to follow).
8. A report build that meets a delete's mark at the national aggregate
   goes on without it, and a refused delete lets the report be written
   so (fix to follow).
9. A report build that meets a delete which already removed weeks
   answers with the no-observed-data sentence, a 404 or a 500.
10. Nothing asks again after a 503 with Retry-After.
11. For a file of the newest season only, the figure counts every group,
    zeros and gaps alike.
12. A season holding MMWR week 53 is taken for an ordinary one.

When the code changes so that one no longer holds, a test here fails: the
note is then to be brought up to date (or dropped, once it is fixed).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """Prose is hard-wrapped, so a phrase may straddle a line break."""
    return " ".join(text.split())


def _note() -> str:
    """The App notes' entry on the four items."""
    notes = _read("docs/team/app.md")
    now = notes[notes.index("## Now"):notes.index("## Decided")]
    at = now.index("- 2026-11-10 (night): four more things are known")
    return _flat(now[at:now.index("\n- ", at + 1)])


def test_the_app_notes_record_the_four_items():
    note = _note()
    assert "known and left as they are" in note
    assert ("**A first season that holds part of the donor window counts "
            "as a whole one.**") in note
    assert '"give about 8 more earlier seasons of data"' in note
    assert "Left as is: the figure errs large" in note
    assert '**Zeros that fall by chance can say "would not help".**' in note
    assert ('"At 1 horizon no earlier season in the file has a week like '
            'it, so more seasons like these would not help there"') in note
    assert ("**A Replace's old run can stay beside the new one for "
            "good.**") in note
    assert "app-final has it from 8a7a4dd7" in note
    assert "`<run>.replaced-<pid>-<hex>`" in note
    assert "It is deleted by hand." in note
    assert ("**Builds a003431d to 1ce301ed deleted a set-aside run with its "
            "imported.json in place.**") in note
    assert "those builds were never released" in note


# ------------------------------------------------ 1 and 2: the donor hint

def _saturdays(start: date, end: date):
    d = start + timedelta(days=(5 - start.weekday()) % 7)
    while d <= end:
        yield d
        d += timedelta(days=7)


def _hint(rows) -> tuple:
    """(donor weeks per horizon, the hint's fix) for one series."""
    from app.core import datasets as D
    from app.core.datasets import checks as CK
    from app.ui import datasets_ui as DU
    raw = ("week_ending,cases\n"
           + "\n".join(f"{d},{v}" for d, v in rows) + "\n").encode()
    rep = D.validate(raw)
    assert rep.ok, [str(p) for p in rep.problems]
    don = CK.groundhog_donors(rep)
    return don["counts"], DU.model_view(rep, {}, "count")["groundhog_fix"]


@pytest.fixture
def engine_ready(monkeypatch):
    from app.ui import pipeline
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "ready")


def test_a_part_season_counts_as_a_whole_one(engine_ready):
    """The note's series: 6 at each horizon, "about 8", and 30 when it
    starts five years earlier. The divisor counts a season by any week of
    the window it holds, and each such season gives an equal share."""
    from flubnf import analogue as AN
    end = date(2025, 3, 15)
    assert AN.epiweek(date(2023, 4, 1)) == 13 and AN.epiweek(end) == 11
    assert AN.DEFAULT_BANDWIDTH == 2

    def series(start):
        return [(d, 10 + (i * 7) % 40)
                for i, d in enumerate(_saturdays(start, end))]
    counts, fix = _hint(series(date(2023, 4, 1)))
    assert counts == (6, 6, 6, 6)
    assert "give about 8 more earlier seasons of data." in fix
    assert _hint(series(date(2018, 4, 7)))[0] == (30, 30, 30, 30)
    ck = _read("app/core/datasets/checks.py")
    assert ("seasons = {AN.season_of(d) for g, d in bank\n"
            "               if d in window and (g, AN.season_of(d)) in "
            "cased}") in ck
    assert "return -(-(need - n) * seasons // n)" in ck


def _u(x) -> float:
    return int(hashlib.md5(repr(x).encode()).hexdigest()[:8], 16) / 2 ** 32


def test_zeros_that_fall_by_chance_can_say_would_not_help(engine_ready):
    """The note's series of low counts: 0 in its winter weeks (MMWR 48 to
    9) and, at random, in about half of the others. Two seasons whose
    zeros fall at one horizon's weeks say "would not help there"; the
    same series started eight years earlier counts 15 there."""
    from flubnf import analogue as AN

    def value(d):
        w = AN.epiweek(d)
        if w >= 48 or w <= 9 or _u(("sp", "series", d)) < 0.5:
            return 0
        return 10 + int(40 * _u(("series", d)))
    end = date(2025, 4, 5)
    counts, fix = _hint([(d, value(d))
                         for d in _saturdays(date(2023, 4, 15), end)])
    assert counts == (0, 1, 1, 1)
    assert fix.startswith("At 1 horizon no earlier season in the file has "
                          "a week like it, so more seasons like these "
                          "would not help there.")
    longer, _ = _hint([(d, value(d))
                       for d in _saturdays(date(2015, 4, 18), end)])
    assert longer[0] == 15


# ------------------------------------ 3 and 4: the old run a Replace set aside

def test_a_set_aside_run_is_no_storage_row_and_reclaim_passes_over_it():
    from app.core import replay_bundle as rb
    from app.core.retro_archive import archive_stamp_of
    name = "2098-99__archived_20980101T000000Z.replaced-123-0a0b0c0d"
    assert archive_stamp_of(name, "2098-99") == ""
    assert rb.is_temp_name(name)


def test_the_sweep_s_rule_for_a_set_aside_run_is_as_the_note_says():
    """With app-final's 8a7a4dd7 here, a set-aside run goes only for a
    whole import of its own bundle and every import names one kept;
    before it, any whole import at the name lets it go. The words the
    note quotes are read from what the code says, not from its source:
    since app-final's 89693ba1 they are built in parts, and they are the
    note's while a whole import (of any bundle) is at the run's name."""
    rb = _read("app/core/replay_bundle.py")
    if "def _same_bundle(" in rb:
        from app.core import replay_bundle
        assert "if p in asides and not _same_bundle(p, dst):" in rb
        assert "return bool(sha) and _bundle_of(dst) == sha" in rb
        # a refused import and a finished one both name a kept run, and
        # both ask whether a whole import of any bundle is at the name
        assert _flat(rb).count(
            "_asides_left(dst, but=mine), _whole_import(dst))") == 2
        kept = Path("/r/2098-99__archived_20980101T000000Z"
                    ".replaced-123-0a0b0c0d")
        assert replay_bundle._asides_left_words(
            "2098-99", "20980101T000000Z", [kept], True) == (
            f"An earlier Replace set a run of 2098-99 aside in {kept}, and "
            "the console keeps it there: it can be deleted by hand once "
            "the run imported as 20980101T000000Z is the one wanted.")
    else:
        assert "whole = _whole_import(dst)" in rb
        assert "if p in asides and not whole:" in rb
    # with nothing at the name, a set-aside run with its imported.json is
    # taken for whole and put back
    assert "asides = [p for p in asides if _whole_import(p)]" in rb
    assert "it is back under its own name" in rb


def test_a_set_aside_run_s_imported_json_goes_first_now():
    """What builds a003431d to 1ce301ed did not do: _drop_aside and the
    sweep's removal take the imported.json out before the delete."""
    rb = _read("app/core/replay_bundle.py")
    drop = rb[rb.index("def _drop_aside("):rb.index("def _put_back(")]
    assert drop.index("IMPORTED_MARK).unlink(missing_ok=True)") \
        < drop.index("retro.delete_tree(")
    rq = rb[rb.index("def _remove_quietly("):]
    rq = rq[:rq.index("\ndef ")]
    assert rq.index("IMPORTED_MARK).unlink(missing_ok=True)") \
        < rq.index("shutil.rmtree(")


# ---------------------------- 5 to 12: the eight recorded beside them

def _note8() -> str:
    """The App notes' entry on the eight items."""
    notes = _read("docs/team/app.md")
    now = notes[notes.index("## Now"):notes.index("## Decided")]
    at = now.index("- 2026-11-10 (late night): eight more things are known")
    return _flat(now[at:now.index("\n- ", at + 1)])


def _body(src: str, start: str) -> str:
    """One top-level def of `src`, from `start` to the next top-level
    statement (or the end of the file)."""
    at = src.index(start)
    end = re.compile(r"\n(?=[A-Za-z_@#])").search(src, at + 1)
    return src[at:end.start() if end else len(src)]


def test_the_app_notes_record_the_eight_items():
    note = _note8()
    assert "A fix is to follow for two of them" in note
    assert ("**A Replace's old run can stay, in part, beside the new one "
            "for good.**") in note
    assert "`<run>.dropping-<pid>-<hex>`" in note
    assert "It is deleted by hand." in note
    assert ("**An import that fails on a disk error does not name a kept "
            "run.**") in note
    assert '"Could not import: <error>."' in note
    assert ("**A Delete of a run leaves the trees beside it, and says "
            "nothing of them.**") in note
    assert ('"<season> is imported as <stamp> from another file; a Replace '
            'import puts this bundle\'s run in its place."') in note
    assert ('"An earlier Replace stopped part way and left an earlier run '
            'from another file in <folder>; it is back under its own name '
            'now."') in note
    assert "A fix is to follow that merge." in note
    assert ("**A refused delete can leave a cached season report with no "
            "national figures for the run.**") in note
    assert ('("the run is being deleted or moved, so its national '
            'aggregate was not built")') in note
    assert ("Fix to follow: the report build raises `TreeBusy` there too, "
            "and asks later.") in note
    assert ('**A report build that meets a delete which already removed '
            'weeks does not say "ask later".**') in note
    assert ('("No observed data to score against. Update data from the '
            'Data tab.", 503 with no Retry-After)') in note
    assert '**Nothing asks again after "ask later".**' in note
    assert "on a paused player left alone it never clears" in note
    assert ("**For a file of the newest season only, the figure counts "
            "every group, zeros and gaps alike.**") in note
    assert '"give about 6 more earlier seasons of data"' in note
    assert '"give about 1 more earlier season of data"' in note
    assert ("**A season that holds MMWR week 53 is taken for an ordinary "
            "one**") in note
    assert ('count (8, 6, 4, 2) and say "about 14"; fourteen more seasons '
            'give (96, 66, 36, 6)') in note


# ----------------------------------- 5 to 7: the import and the Delete

def _whole(p: Path, sha: str, weeks=("2098-01-03",)) -> Path:
    from app.core import replay_bundle as rb
    for w in weeks:
        (p / "weeks" / w).mkdir(parents=True)
        (p / "weeks" / w / "samples.json").write_text("{}", encoding="utf-8")
    (p / rb.IMPORTED_MARK).write_text(json.dumps({"bundle_sha256": sha}),
                                      encoding="utf-8")
    return p


def test_a_drop_whose_rename_is_refused_leaves_part_of_a_run_for_good(
        tmp_path, monkeypatch):
    """The note's case: the rename to .dropping- refused, the delete in
    place stopped by a held file. What is left has no imported.json: it
    is never put back, never swept, and named as a run set aside."""
    from app.core import replay_bundle as rb
    from app.core import retro
    season, stamp = "2098-99", "20980101T000000Z"
    dst = _whole(retro.archive_dir(tmp_path, season, stamp), "b" * 64)
    aside = _whole(rb._aside_name(dst), "a" * 64,
                   weeks=("2098-01-03", "2098-01-10"))
    rename = rb.os.rename

    def refused(src, to):
        if ".dropping-" in str(to):
            raise PermissionError(13, "a file is held open", str(src))
        return rename(src, to)

    def stopped(p):
        (Path(p) / "weeks" / "2098-01-03" / "samples.json").unlink()
        raise PermissionError(13, "a file is held open", str(p))
    monkeypatch.setattr(rb.os, "rename", refused)
    monkeypatch.setattr(retro, "delete_tree", stopped)
    rb._drop_aside(aside, dst)
    monkeypatch.undo()
    assert not (aside / rb.IMPORTED_MARK).exists()
    assert (aside / "weeks" / "2098-01-10" / "samples.json").is_file()
    # never swept (it names no bundle), never put back (not whole)
    assert rb._sweep_stale_temps(dst, now=time.time()
                                 + 2 * rb.STALE_TEMP_S) == []
    assert aside.is_dir() and rb._whole_import(dst, "b" * 64)
    assert rb._restore_aside(dst.with_name("elsewhere"), [aside]) is None
    # every import names it, as a run set aside
    left = rb._asides_left(dst)
    assert left == [aside]
    src = _read("app/core/replay_bundle.py")
    whole = ((True,) if "left: list,\n                       whole: bool)"
             in src else ())
    assert rb._asides_left_words(season, stamp, left, *whole).startswith(
        f"An earlier Replace set a run of {season} aside in {aside}, and "
        "the console keeps it there: ")


def test_an_import_s_disk_error_gets_no_words_of_a_kept_run():
    """import_bundle adds the kept run's sentence to a BundleError and to
    a finished import's notes only; an OSError passes through, and the
    console and the command line give it in a line of their own."""
    rb = _read("app/core/replay_bundle.py")
    body = _body(rb, "def import_bundle(")
    assert "except BundleError as e:" in body
    for other in ("except OSError", "except Exception", "except BaseException",
                  "except:"):
        assert other not in body, other
    assert body.count("_asides_left_words(") == 2
    assert ('return (f"Could not import: {type(e).__name__}: '
            '{str(e)[:160]}.",') in _read("app/ui/routes/retro.py")
    assert ('typer.echo(f"could not import: {type(e).__name__}: {e}", '
            'err=True)') in _read("flubnf/cli_retro.py")


def test_a_delete_of_a_run_takes_its_own_folder_alone():
    """Both Deletes remove the run's folder by retro.delete_tree, which
    looks at nothing beside it; neither names a set-aside or temp tree.
    The import's sweep puts the newest whole one back at a free name."""
    routes = {"app/ui/routes/retro.py": "def retro_archive_delete(",
              "app/ui/routes/storage.py": "def storage_delete("}
    for rel, start in routes.items():
        body = _body(_read(rel), start)
        assert "retro.delete_tree(p)" in body, rel
        for beside in ("replaced", "importing", "_sweep_stale_temps",
                       "_asides_left", "is_temp_name"):
            assert beside not in body, (rel, beside)
    tree = _body(_read("app/core/retro_archive.py"), "def delete_tree(")
    assert "replaced" not in tree and "glob(" not in tree \
        and "iterdir(" not in tree
    rb = _read("app/core/replay_bundle.py")
    assert "back = max(asides, key=lambda p: (_newest_mtime(p), p.name))" \
        in rb


# ------------------------- 8 to 10: the report and the page meeting a delete

def test_a_report_build_takes_a_refused_aggregate_as_the_us_row_s_reason(
        tmp_path, monkeypatch):
    """The aggregate's TreeBusy is a reason, not a refusal: the report goes
    on, and only its own write looks at the mark again."""
    from app.core import retro, us_national
    from app.core.retro_store import TreeBusy
    words = ("the run is being deleted or moved, so its national "
             "aggregate was not built")

    def busy(root):
        raise TreeBusy(words)
    monkeypatch.setattr(retro, "national_aggregate", busy)
    assert us_national.aggregate_row(tmp_path) == (None, words)
    assert f'raise TreeBusy("{words[:46]}' in _read("app/core/retro.py")
    build = _body(_read("app/core/report_season.py"),
                  "def build_season_report(")
    assert build.count("raise TreeBusy(") == 1
    assert build.index("render_season_report(") \
        < build.index("with writing_into(root) as ok:") \
        < build.index("raise TreeBusy(")
    # the aggregate's cache is one of the report's inputs
    newest = _body(_read("app/core/report_season.py"), "def _newest_input(")
    assert 'pc = root / "playback_cache"' in newest
    assert 'pc.glob("*.json")' in newest


def test_a_report_build_that_meets_removed_weeks_does_not_ask_later():
    routes = _read("app/ui/routes/retro.py")
    assert ('NO_TRUTH = "No observed data to score against. Update data '
            'from the Data tab."') in routes
    body = _body(routes, "def _season_report(")
    assert body.index("except playback.UnknownWeek as e:\n        return "
                      "PlainTextResponse(str(e), status_code=404)") \
        < body.index("except FileNotFoundError:\n        return "
                     "PlainTextResponse(NO_TRUTH, status_code=503)") \
        < body.index("except TreeBusy:")
    for other in ("except OSError", "except Exception", "except:"):
        assert other not in body, other
    job = _read("app/ui/season_export.py")
    assert 'error=f"{type(e).__name__}: {str(e)[:300]}")' in job


def test_nothing_asks_again_after_ask_later():
    """Retry-After is read as there or not, never as a time; an answer to
    ask later is kept for no week, and nothing re-asks on a timer."""
    page = _read("app/ui/templates/retro_season.html")
    assert page.count("Retry-After')") == 1
    assert ("function later(r){ return !r.ok && "
            "!!r.headers.get('Retry-After'); }") in page
    assert ".catch(e => {if(!(e && e.later)) PAY[w] = null;" in page
    assert ("if(e && e.later) SLATER[w] = e.message || ('map unavailable "
            "for ' + w);") in page
    player = _read("app/ui/static/player.js")
    assert "headers.get(" not in player and "Retry-After" not in player
    draw = player[player.index("function drawFC(){"):]
    draw = draw[:draw.index("var loc = P.loc")]
    assert "el.msg.textContent =\n          failMsg(w, " in draw
    assert "setTimeout" not in draw


# ------------------------------------------- 11 and 12: the donor hint

def _file_hint(lines) -> tuple:
    """(donor weeks per horizon, the hint's fix) for a file's lines."""
    from app.core import datasets as D
    from app.core.datasets import checks as CK
    from app.ui import datasets_ui as DU
    rep = D.validate(("\n".join(lines) + "\n").encode())
    assert rep.ok, [str(p) for p in rep.problems]
    return (CK.groundhog_donors(rep)["counts"],
            DU.model_view(rep, {}, "count")["groundhog_fix"])


def test_a_newest_season_file_counts_every_group_zeros_and_gaps_alike(
        engine_ready):
    """The note's file: one series with cases, alone "about 6"; with six
    groups at 0 throughout, or six locations reported every other week,
    "about 1", though one more season like the file's gives 5 of 30."""
    from flubnf import analogue as AN
    end = date(2026, 1, 17)
    assert AN.epiweek(end) == 2
    assert AN.season_of(date(2025, 8, 2)) == AN.season_of(end)

    def grouped(zeros: int, start=date(2025, 8, 2)):
        lines = ["week_ending,group,cases"]
        for i, d in enumerate(_saturdays(start, end)):
            lines.append(f"{d},A,{10 + (i * 7) % 40}")
            lines += [f"{d},Z{j},0" for j in range(zeros)]
        return lines

    counts, fix = _file_hint(grouped(0))
    assert counts == (0, 0, 0, 0)
    assert "give about 6 more earlier seasons of data." in fix
    counts, fix = _file_hint(grouped(6))
    assert counts == (0, 0, 0, 0)
    assert "give about 1 more earlier season of data." in fix
    assert _file_hint(grouped(6, start=date(2024, 8, 3)))[0] == (5, 5, 5, 5)
    hub = ["date,location,value"]
    for i, d in enumerate(_saturdays(date(2025, 8, 2), end)):
        hub.append(f"{d},01,{10 + (i * 7) % 40}")
        hub += [f"{d},{j:02d},{'NA' if i % 2 else 10 + i % 20}"
                for j in range(2, 8)]
    assert "give about 1 more earlier season of data." in _file_hint(hub)[1]
    ck = _read("app/core/datasets/checks.py")
    assert "return -(-(need - n) // (ordinary * groups))" in ck
    assert "max(1, len(s.get(\"groups\") or ()))," in ck


def test_a_week_53_season_is_taken_for_an_ordinary_one(engine_ready):
    """The review's two files (pass 7 of the review of #93 at d415a9fa,
    finding 1), as the note gives them."""
    from flubnf import analogue as AN
    assert AN.epiweek(date(2026, 1, 3)) == 53

    def one(end, more=0):
        return _file_hint(["week_ending,cases"] + [
            f"{d},{10 + (i * 7) % 40}" for i, d in
            enumerate(_saturdays(date(2025 - more, 8, 2), end))])

    for end, week in ((date(2026, 12, 26), 51), (date(2027, 1, 2), 52),
                      (date(2027, 1, 9), 1), (date(2027, 1, 16), 2)):
        assert AN.epiweek(end) == week
        counts, fix = one(end)
        assert counts == (6, 6, 6, 6), end
        assert "give about 4 more earlier seasons of data." in fix
    assert one(date(2026, 12, 26), more=4)[0] == (26, 26, 26, 26)
    assert one(date(2026, 12, 26), more=5)[0] == (32, 32, 32, 32)
    counts, fix = one(date(2026, 12, 19))
    assert AN.epiweek(date(2026, 12, 19)) == 50
    assert counts == (5, 5, 5, 5)
    assert "give about 5 more earlier seasons of data." in fix

    def two(more=0):
        lines = ["week_ending,group,cases"]
        for i, d in enumerate(_saturdays(date(2025 - more, 8, 2),
                                         date(2026, 12, 26))):
            for j, g in enumerate("AB"):
                v = (0 if 1 <= AN.epiweek(d) <= 4
                     else 10 + ((i + 5 * j) * 7) % 40)
                lines.append(f"{d},{g},{v}")
        return _file_hint(lines)

    counts, fix = two()
    assert counts == (8, 6, 4, 2)
    assert "give about 14 more earlier seasons of data." in fix
    assert two(more=14)[0] == (96, 66, 36, 6)
