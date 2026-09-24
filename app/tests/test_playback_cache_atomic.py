"""Playback cache files land atomically: write beside, then os.replace.

Any file in playback_cache/ is served as a complete payload (megabytes), so
a torn bare write_text would become truth on the next request.
"""
import inspect
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import playback                            # noqa: E402


def _tmp_residue(d: Path) -> list:
    return sorted(p.name for p in d.glob("*.tmp"))


def test_write_cache_leaves_valid_json_and_no_tmp_residue(tmp_path):
    cf = tmp_path / "playback_cache" / "2026-01-03.json"
    playback._write_cache(cf, {"_v": 2, "asof": "2026-01-03"})
    assert json.loads(cf.read_text()) == {"_v": 2, "asof": "2026-01-03"}
    assert _tmp_residue(cf.parent) == []


def test_write_cache_replaces_an_existing_payload_whole(tmp_path):
    cf = tmp_path / "playback_cache" / "stats_cells.json"
    playback._write_cache(cf, {"weeks": {"a": 1}})
    playback._write_cache(cf, {"weeks": {"a": 1, "b": 2}})
    assert json.loads(cf.read_text()) == {"weeks": {"a": 1, "b": 2}}
    assert _tmp_residue(cf.parent) == []


def test_a_failed_replace_never_touches_the_served_payload(tmp_path,
                                                           monkeypatch):
    """A writer dying before the replace leaves the previous complete payload,
    not a prefix of the new one."""
    cf = tmp_path / "playback_cache" / "2026-01-03.json"
    playback._write_cache(cf, {"_v": 2, "n": 1})

    def die(src, dst):
        raise OSError("killed between write and replace")
    monkeypatch.setattr(playback.os, "replace", die)
    with pytest.raises(OSError):
        playback._write_cache(cf, {"_v": 2, "n": 2})
    assert json.loads(cf.read_text()) == {"_v": 2, "n": 1}


def test_no_playback_cache_write_bypasses_the_helper():
    """Both cache sites (build_week's payload and _stats' stats_cells) go
    through _write_cache; never a bare json.dumps into write_text."""
    src = inspect.getsource(playback)
    assert ".write_text(json.dumps" not in src.replace(
        "tmp.write_text(json.dumps", ""), (
        "a playback cache is written with a bare write_text again; route "
        "it through _write_cache")
    assert src.count("_write_cache(") >= 3   # the def plus both call sites
