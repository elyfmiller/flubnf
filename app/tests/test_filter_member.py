"""The Liu-West filter alone, scored beside the Oracle SIHRS.

The Oracle step blends each forecast path with a donor path; the filter's
own forecast before it is kept in each week's oracle.json
(quantiles.null). The Retrospective scores it as a third member
(retro_store.FILTER_MEMBER), so the step's effect shows, without a second
replay. Only weeks where the step ran carry it."""
from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from app.core import retro
from app.core import retro_store as RS
from app.core.floor import floor_quantiles
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL


def _null(center: float, half: float) -> dict:
    """oracle.json's null block for one location: 23 levels per horizon."""
    return {h: {"internal_h": int(h) + 1,
                "unrounded": [center + (L - 0.5) * 2 * half for L in QL]}
            for h in ("0", "1", "2", "3")}


def _write_oracle(wd, applied=True, null=None):
    prov = {"written_by": "test", "applied": applied}
    if applied:
        prov["quantiles"] = {"levels": list(QL), "null": null or {}}
    (wd / RS.ORACLE_NAME).write_text(json.dumps(prov), encoding="utf-8")


@pytest.fixture()
def season(tmp_path, monkeypatch):
    """One stored week, two states, the Oracle step's record beside it."""
    from app.tests.test_us_national import _console_season
    root, name = _console_season(tmp_path, monkeypatch)
    monkeypatch.setattr("app.core.data.truth_mtime", lambda: 0.0)
    wd = next(root.glob("weeks/*"))
    _write_oracle(wd, null={"Ohio": _null(100.0, 30.0),
                            "Utah": _null(100.0, 30.0)})
    RS._FILTER_CACHE.clear()
    return root, name, wd


def test_the_filter_quantiles_are_oracle_json_null_with_the_floor(season):
    _root, _name, wd = season
    fq = RS.filter_quantiles(wd)
    assert set(fq) == {"Ohio", "Utah"}
    assert set(fq["Ohio"]) == {"0", "1", "2", "3"}
    want = floor_quantiles({"1": dict(zip(QL, _null(100.0, 30.0)["1"]["unrounded"]))})
    assert fq["Ohio"]["1"] == pytest.approx(want["1"])


def test_a_week_without_the_step_has_no_filter_member(season):
    root, _name, wd = season
    _write_oracle(wd, applied=False)                  # oracle = none
    RS._FILTER_CACHE.clear()
    assert RS.filter_quantiles(wd) is None
    (wd / RS.ORACLE_NAME).unlink()                    # a sealed record
    assert RS.filter_quantiles(wd) is None
    (wd / RS.QUANTILES_NAME).unlink(missing_ok=True)
    mq = RS.week_member_quantiles(root, wd.name)
    assert RS.FILTER_MEMBER not in mq and {"pf", "analogue"} <= set(mq)


def test_an_older_sidecar_gains_the_filter_once(season):
    root, _name, wd = season
    rec = RS.read_week_samples(root, wd.name)
    RS.write_week_quantiles(wd, RS.member_quantiles(rec))   # before this change
    st = (wd / RS.QUANTILES_NAME).stat()
    os.utime(wd / RS.QUANTILES_NAME, (st.st_atime + 5, st.st_mtime + 5))
    assert RS.FILTER_MEMBER not in RS.read_week_quantiles(wd)
    mq = RS.week_member_quantiles(root, wd.name)
    assert set(mq) == {"pf", RS.FILTER_MEMBER, "analogue"}
    assert RS.FILTER_MEMBER in RS.read_week_quantiles(wd)   # written back


def test_score_season_scores_the_filter_beside_the_members(season):
    root, name, _wd = season
    df = retro.score_season(root, name)
    assert set(df.model) == {"pf", RS.FILTER_MEMBER, "analogue"}
    f = df[df.model == RS.FILTER_MEMBER]
    assert set(f.location) == {"Ohio", "Utah"} and set(f.horizon) == {0, 1, 2, 3}
    # the same cells as the shipped member, so the two compare directly
    p = df[df.model == "pf"]
    key = ["location", "asof", "horizon"]
    assert set(map(tuple, f[key].values)) == set(map(tuple, p[key].values))


def test_scores_from_before_the_filter_are_rescored_once(season):
    root, name, _wd = season
    df = retro.score_season(root, name)
    old = df[df.model != RS.FILTER_MEMBER]
    old.to_json(root / "scores.json")
    assert retro.filter_scores_missing(root, old)
    assert not retro.scores_current(root)
    df.to_json(root / "scores.json")
    assert not retro.filter_scores_missing(root, df)
    assert retro.scores_current(root)


def test_a_root_without_the_step_is_not_asked_for_the_filter(season):
    root, name, wd = season
    (wd / RS.ORACLE_NAME).unlink()
    (wd / RS.QUANTILES_NAME).unlink(missing_ok=True)
    df = retro.score_season(root, name)
    assert RS.FILTER_MEMBER not in set(df.model)
    assert not retro.filter_scores_missing(root, df)


def test_the_season_page_shows_the_filter_as_its_own_model(season,
                                                          monkeypatch):
    from fastapi.testclient import TestClient

    from app.ui import retro_seasons as ui_retro_seasons
    from app.ui import server as srv
    root, name, _wd = season
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", root.parent)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", root.parent / "noseal")
    html = TestClient(srv.app).get(f"/retro/{name}").text
    assert "preparing results" not in html
    assert "Liu-West filter" in html                 # its tile and column
    assert 'data-key="pf_filter"' in html            # a sortable table column
    scores = pd.read_json(root / "scores.json")
    assert RS.FILTER_MEMBER in set(scores.model)     # rescored in place
