"""The public engine reached by the default alone (review finding 14).

Nearly every test of the public engine names it (FLUBNF_ENGINE=public), so
a later reader of the variable that skipped engine_choice would pass them
all and be wrong on every default install. Here FLUBNF_ENGINE is unset and
the install records nothing (conftest points settings.INSTALL_ROOT at an
empty folder): the default is what reaches the code that acts on it. A
season's engine guard, the engine build it records, and the Sandbox's
engine are each taken through settings' own dispatch, never a stub of it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core import engine_build as EB
from app.core import retro
from app.core.engines import lwf
from app.core.engines import pf as pf_engine
from flubnf import settings

PRIVATE = {"branch": "feature/particle-filter", "commit": "2fdadee0",
           "dirty": False, "source": "git", "path": "/x/PyBNF-pf"}
PUBLIC = {"branch": "lanl/PyBNF", "commit": "8410f794", "dirty": False,
          "source": "wheel", "path": "/v/bin/python", "engine": "public",
          "full_commit": "8410f794e3fa4817572fd07fceb043ddec39d77b"}

SEASON, W1, W2 = "2098-99", "2098-11-07", "2098-11-14"


def _to_the_default(monkeypatch) -> None:
    """Nothing set and no record: the public engine, the default."""
    monkeypatch.delenv("FLUBNF_ENGINE", raising=False)
    settings.forget_record()
    assert settings.engine_source() == ("default", None)
    assert settings.engine_choice() == "public"


@pytest.fixture
def default(monkeypatch):
    _to_the_default(monkeypatch)


def _fake_season(monkeypatch):
    """run_week writes a week's samples file; no filter runs."""
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])

    def fake_week(root, _season, asof, *a, **k):
        wd = Path(root) / "weeks" / asof
        wd.mkdir(parents=True, exist_ok=True)
        (wd / retro.SAMPLES_JSON).write_text("{}")
    monkeypatch.setattr(retro, "run_week", fake_week)


def test_the_engine_build_on_the_default_is_the_public_engines(default,
                                                               monkeypatch):
    """engine_build's own dispatch: the public build, never the fork's."""
    monkeypatch.setattr(lwf, "public_build", lambda: dict(PUBLIC))
    assert EB.engine_build() == PUBLIC
    assert EB.engine_of(EB.record(EB.engine_build())) == "public"
    assert pf_engine.cell_seconds({"n_obs": 20, "particles": 10000}) > 0


def test_a_private_season_is_refused_on_the_default_and_resumes_on_it(
        tmp_path, monkeypatch):
    """A season begun on the private engine (the suite's pin), then the
    copy goes back to the default: the resume is refused in words (W5)
    naming the private engine and the step back to it. A season begun on
    the default resumes on it, its record naming the public build."""
    _fake_season(monkeypatch)
    monkeypatch.setattr(settings, "_windows", lambda: False)
    monkeypatch.setattr(lwf, "public_build", lambda: dict(PUBLIC))
    real = EB.engine_build
    monkeypatch.setattr(EB, "engine_build", lambda path=None: dict(PRIVATE))
    root = tmp_path / SEASON

    def stop_after_first(asof):
        retro.stop_path(root).touch()
    with pytest.raises(retro.SeasonStopped):
        retro.run_season(root, SEASON, ["Ohio"], width=1,
                         progress=stop_after_first)
    assert EB.engine_of(retro.read_meta(root)["settings"]["engine_build"]) \
        == "private"

    _to_the_default(monkeypatch)
    monkeypatch.setattr(EB, "engine_build", real)
    with pytest.raises(retro.EngineBuildMismatch) as e:
        retro.run_season(root, SEASON, ["Ohio"], width=1)
    said = str(e.value)
    assert "Resuming would mix two engine builds in one season." in said
    assert ("To finish it on the private engine it began on: "
            "./setup_engine.sh --private in the FluBNF folder; or archive or "
            "discard the existing results to replay it on this one.") in said
    assert not retro.week_done(root, W2)

    # a season begun on the default: its record names the public build,
    # and it resumes on the default
    other = tmp_path / "other" / SEASON
    with pytest.raises(retro.SeasonStopped):
        retro.run_season(other, SEASON, ["Ohio"], width=1,
                         progress=lambda asof: retro.stop_path(other).touch())
    rec = retro.read_meta(other)["settings"]["engine_build"]
    assert rec["engine"] == "public" and rec["commit"] == "8410f794"
    retro.run_season(other, SEASON, ["Ohio"], width=1)
    meta = retro.read_meta(other)
    assert meta["status"] == "done" and retro.week_done(other, W2)


def test_a_week_begun_on_the_private_engine_is_never_finished_on_the_default(
        tmp_path, monkeypatch):
    """W4, the week's own engine: begun on the private engine (the pin),
    refused on the default."""
    from app.core.retro_settings import EngineBuildMismatch
    retro._week_engine(tmp_path, settings.engine_choice())   # private
    retro.mark_cell_done(tmp_path, "A_r0", "ok")             # a fit finished
    _to_the_default(monkeypatch)
    with pytest.raises(EngineBuildMismatch,
                       match="began on the private engine and this install "
                             "now runs the public one"):
        retro._week_engine(tmp_path, settings.engine_choice())
