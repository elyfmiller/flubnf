"""An experiment's replay (app/core/retro.py run_season with weeks=): the
frozen plan's weeks replace the season's vintages, are recorded at the
first start and replayed on every resume; a tree is resumed only as the
experiment it holds (settings.experiment), and a week list that is not
distinct weeks of the season is refused before anything is written,
cleared or removed. A replay without weeks runs as it always has.

The weeks are faked (test_run_timing.py's season fake): each writes its
samples file and the fake records what it was asked.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import retro                               # noqa: E402

SEASON = "2098-99"
W1, W2, W3 = "2098-11-07", "2098-11-14", "2098-11-21"
A, B = "a" * 64, "b" * 64
#: what an experiment passes beside its fingerprint (experiments.replay)
MODEL = {"model": "beta@1", "model_fingerprint": "f" * 64}


@pytest.fixture
def season(monkeypatch, tmp_path):
    """The season's three vintages and a fake week; {"root", "calls" (each
    week run, in order), "extras" (the vintages each week_extra was
    handed), "stop_after" (weeks after which STOP is requested), "seen"
    (the run record's settings as each week ran)}."""
    root = tmp_path / SEASON
    got = {"root": root, "calls": [], "extras": [], "stop_after": set(),
           "seen": []}
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2, W3])

    def fake_week(r, season, asof, locations, replicates, particles, width,
                  **kw):
        got["calls"].append(asof)
        got["seen"].append(retro.read_meta(r).get("settings") or {})
        wd = Path(r) / "weeks" / asof
        wd.mkdir(parents=True, exist_ok=True)
        (wd / "samples.json").write_text(json.dumps({"asof": asof}),
                                         encoding="utf-8")
        if asof in got["stop_after"]:
            retro.request_stop(r)
        return {"asof": asof}
    monkeypatch.setattr(retro, "run_week", fake_week)
    return got


def _extra(got):
    """A week_extra that records the vintages it is handed."""
    def week_extra(asof, i, vintages):
        got["extras"].append(list(vintages))
        return {}
    week_extra.__name__ = "recorded"
    return week_extra


def _run(got, **kw):
    return retro.run_season(got["root"], SEASON, ["Ohio"], width=1, **kw)


def test_without_weeks_nothing_changes(season):
    assert _run(season) == [W1, W2, W3]
    assert season["calls"] == [W1, W2, W3]
    m = retro.read_meta(season["root"])
    assert m["total_weeks"] == 3 and m["status"] == "done"
    assert "weeks" not in m["settings"] and "experiment" not in m["settings"]
    # and a shipped-style tree resumes as before
    season["calls"].clear()
    assert _run(season) == [] and season["calls"] == []


def test_weeks_replace_the_vintages(season):
    assert _run(season, weeks=[W1, W3], week_extra=_extra(season)) == [W1, W3]
    assert season["calls"] == [W1, W3]
    assert season["extras"] == [[W1, W3], [W1, W3]]
    m = retro.read_meta(season["root"])
    assert m["total_weeks"] == 2 and m["settings"]["weeks"] == [W1, W3]


@pytest.mark.parametrize("again", [[W1, W2, W3], None])
def test_a_resume_replays_the_recorded_weeks(season, again):
    season["stop_after"].add(W1)
    settings = {**MODEL, "experiment": A}
    with pytest.raises(retro.SeasonStopped):
        _run(season, weeks=[W1, W2], settings=settings)
    assert season["calls"] == [W1]
    season["calls"].clear()
    assert _run(season, weeks=again, settings=settings) == [W2]
    assert season["calls"] == [W2]
    m = retro.read_meta(season["root"])
    assert m["settings"]["weeks"] == [W1, W2] and m["status"] == "done"


def _record(root: Path, settings) -> bytes:
    """A run record holding `settings` (none when it is ...), or, given
    bytes, those bytes as the whole record (damaged by hand), or no
    record at all for None; its bytes (None without one)."""
    if isinstance(settings, bytes):
        root.mkdir(parents=True, exist_ok=True)
        retro.meta_path(root).write_bytes(settings)
    elif settings is not None:
        meta = {"season": SEASON, "status": "stopped"}
        if settings is not ...:
            meta["settings"] = settings
        retro.write_meta(root, meta)
    p = retro.meta_path(root)
    return p.read_bytes() if p.exists() else None


@pytest.mark.parametrize("had, want, weeks_done", [
    ({"experiment": A, "weeks": [W1, W2]}, B, 0),
    ({"experiment": A, "weeks": [W1, W2]}, B, 1),
    ({"experiment": A, "weeks": [W1, W2]}, None, 1),
    ({"engine": "pf", "replicates": 3}, A, 1),           # a shipped tree
    ([], A, 0), ("x", A, 0), (..., A, 0),               # damaged records
    (b"{not json", A, 1), (b"[1, 2]", A, 1), (None, A, 1),
], ids=["A-then-B", "A-then-B-one-week", "A-then-none", "shipped-then-A",
        "list", "string", "missing", "unreadable", "not-an-object",
        "weeks-without-a-record"])
def test_another_experiment_is_never_resumed(season, had, want, weeks_done):
    root = season["root"]
    for w in (W1, W2)[:weeks_done]:
        (root / "weeks" / w).mkdir(parents=True)
        (root / "weeks" / w / "samples.json").write_text("{}")
    before = _record(root, had)
    retro.request_pause(root)
    settings = {**MODEL, "experiment": want} if want else None
    with pytest.raises(retro.ResumeMismatch, match="mix two experiments"):
        _run(season, weeks=[W1, W2], settings=settings)
    assert season["calls"] == []
    p = retro.meta_path(root)
    assert (p.read_bytes() if p.exists() else None) == before
    assert retro.pause_path(root).exists()


def test_a_damaged_record_resumes_a_shipped_tree_as_before(season):
    """Without an experiment on either side, a record that cannot be read
    is resumed as it always was: its weeks on disk are not run again."""
    root = season["root"]
    (root / "weeks" / W1).mkdir(parents=True)
    (root / "weeks" / W1 / "samples.json").write_text("{}")
    _record(root, b"{not json")
    assert _run(season) == [W2, W3] and season["calls"] == [W2, W3]


def test_a_bad_week_list_is_refused_before_anything(season, tmp_path):
    root = season["root"]
    for weeks in (["2099-01-01"], ["../x"], [W1, W1], [], [W1, 3], "x"):
        with pytest.raises(ValueError,
                           match="distinct weeks of the season") as e:
            _run(season, weeks=weeks)
        assert not isinstance(e.value, retro.ResumeMismatch)
        assert not retro.meta_path(root).exists(), weeks
    # a recorded week names a folder a week's rebuild would remove
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("mine")
    assert (root / "weeks" / "../../victim").resolve() == victim.resolve()
    before = _record(root, {"weeks": ["../../victim"]})
    retro.request_pause(root)
    retro.request_stop(root)
    with pytest.raises(ValueError, match="distinct weeks of the season"):
        _run(season)
    assert (victim / "keep.txt").read_text() == "mine"
    assert season["calls"] == []
    assert retro.meta_path(root).read_bytes() == before
    assert retro.stop_path(root).exists()


def test_the_four_keys_are_recorded_and_kept(season):
    settings = {**MODEL, "experiment": A}
    season["stop_after"].add(W1)
    with pytest.raises(retro.SeasonStopped):
        _run(season, weeks=[W1, W3], settings=settings)
    _run(season, weeks=[W1, W3], settings=settings)
    assert season["calls"] == [W1, W3]
    for st in season["seen"] + [retro.read_meta(season["root"])["settings"]]:
        assert {k: st.get(k) for k in ("model", "model_fingerprint",
                                       "experiment", "weeks")} == {
            **MODEL, "experiment": A, "weeks": [W1, W3]}
