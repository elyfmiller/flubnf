"""Two sealed records, one Retrospective tab. The production engine's
record (the reseal) is served ahead of the v1.0.0 seal, a live replay of
the app's own wins when it has more weeks, and both sealed trees are read
only and protected from the storage page."""
from pathlib import Path

import pytest

from app.ui import server as srv


def _season_tree(root: Path, season: str, weeks: int) -> Path:
    d = root / season / "weeks"
    for i in range(weeks):
        w = d / ("2098-01-%02d" % (i + 1))
        w.mkdir(parents=True)
        (w / "samples.json").write_text("{}")
    return root / season


@pytest.fixture()
def roots(tmp_path, monkeypatch):
    live, reseal, seal = (tmp_path / "retro", tmp_path / "retro_reseal",
                          tmp_path / "retro_seal")
    monkeypatch.setattr(srv, "RETRO_ROOT", live)
    monkeypatch.setattr(srv, "RETRO_RESEAL", reseal)
    monkeypatch.setattr(srv, "RETRO_SEAL", seal)
    return live, reseal, seal


def test_the_production_record_is_served_ahead_of_the_seal(roots):
    live, reseal, seal = roots
    _season_tree(reseal, "2025-26", 26)
    _season_tree(seal, "2025-26", 26)
    root, is_seal = srv._season_root("2025-26")
    assert is_seal and root == reseal / "2025-26"
    assert "production engine" in srv._sealed_label(root)
    assert "v1.0.0" in srv._sealed_label(seal / "2025-26")
    assert srv._sealed_label(live / "2025-26") == ""


def test_the_seal_is_served_when_it_is_the_only_record(roots):
    live, reseal, seal = roots
    _season_tree(seal, "2024-25", 27)
    root, is_seal = srv._season_root("2024-25")
    assert is_seal and root == seal / "2024-25"


def test_the_apps_own_replay_wins_on_a_tie_and_when_longer(roots):
    live, reseal, seal = roots
    _season_tree(live, "2023-24", 32)
    _season_tree(reseal, "2023-24", 32)
    assert srv._season_root("2023-24") == (live / "2023-24", False)
    _season_tree(live, "2024-25", 5)
    _season_tree(reseal, "2024-25", 4)
    assert srv._season_root("2024-25") == (live / "2024-25", False)
    # and loses to a fuller record
    _season_tree(live, "2025-26", 3)
    _season_tree(reseal, "2025-26", 26)
    assert srv._season_root("2025-26") == (reseal / "2025-26", True)


def test_both_sealed_trees_are_read_only_and_protected(roots):
    live, reseal, seal = roots
    for base in (reseal, seal):
        season = _season_tree(base, "2025-26", 1)
        assert srv._is_sealed_root(season)
        assert srv._storage_protected(season / "weeks")
    assert not srv._is_sealed_root(_season_tree(live, "2025-26", 1))
