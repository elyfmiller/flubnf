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

When the code changes so that one no longer holds, a test here fails: the
note is then to be brought up to date (or dropped, once it is fixed).
"""
from __future__ import annotations

import hashlib
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
    before it, any whole import at the name lets it go."""
    rb = _read("app/core/replay_bundle.py")
    if "def _same_bundle(" in rb:
        assert "if p in asides and not _same_bundle(p, dst):" in rb
        assert "return bool(sha) and _bundle_of(dst) == sha" in rb
        assert ('f"An earlier Replace set a run of {season} aside in "'
                in rb)
        assert "deleted by hand once the run imported as {stamp} is the" \
            in rb
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
