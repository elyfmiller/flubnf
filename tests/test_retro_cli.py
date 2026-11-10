"""`flubnf retro run` says which weeks were stored and which failed, and a
season with a failed week exits non-zero.

It used to print "<week> done" for every week run_season reported, a week
the engine refused included, and exit 0 with "0 weeks complete" when the
public engine's lock check refused all 32 (found 2026-10-30). The engine is
never run here: run_season is replaced by one that reports three weeks and
stores the ones the test names."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from flubnf.cli import app

WEEKS = ["2023-10-07", "2023-10-14", "2023-10-21"]


@pytest.fixture
def season(monkeypatch, tmp_path):
    import flubnf.settings as S
    from app.core import knobs, retro
    locs = tmp_path / "locations.csv"
    locs.write_text("abbreviation,location,location_name\nAK,02,Alaska\n")
    monkeypatch.setattr(S, "LOCATIONS", locs)
    monkeypatch.setattr(retro, "season_vintages", lambda s: list(WEEKS))
    monkeypatch.setattr(knobs, "resolve", lambda *a, **k: {})
    stored = set()

    def run_season(root, season, names, progress=None, **kw):
        for w in WEEKS:
            if w in stored:
                (root / "weeks" / w).mkdir(parents=True, exist_ok=True)
            progress(w)
        return [w for w in WEEKS if w in stored]
    monkeypatch.setattr(retro, "run_season", run_season)
    monkeypatch.setattr(retro, "week_done", lambda root, w: w in stored)
    return stored, tmp_path / "root"


def _run(root):
    return CliRunner().invoke(app, ["retro", "run", "2023-24", "--locations",
                                    "Alaska", "--root", str(root)])


def test_every_week_stored_says_done_and_exits_zero(season):
    stored, root = season
    stored.update(WEEKS)
    r = _run(root)
    assert r.exit_code == 0, r.output
    assert r.output.count(" done") == 3 and "FAILED" not in r.output
    assert "2023-24: 3 weeks complete" in r.output


def test_a_refused_season_never_says_done(season):
    _, root = season
    r = _run(root)
    assert r.exit_code == 1, r.output
    assert " done" not in r.output
    assert r.output.count("FAILED") == 3
    assert "0 of 3 weeks stored; 3 failed (first 2023-10-07)" in r.output
    assert "weeks complete" not in r.output


def test_one_failed_week_is_named_and_exits_nonzero(season):
    stored, root = season
    stored.update({WEEKS[0], WEEKS[2]})
    r = _run(root)
    assert r.exit_code == 1, r.output
    assert f"{WEEKS[1]} FAILED" in r.output
    assert "2 of 3 weeks stored; 1 failed (first 2023-10-14)" in r.output
