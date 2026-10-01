"""The Liu-West filter alone, scored beside the Oracle SIHRS.

The Oracle step blends each forecast path with a donor path; the filter's
own forecast before it is kept in each week's oracle.json
(quantiles.null). The Retrospective scores it as a third member
(retro_store.FILTER_MEMBER), so the step's effect shows, without a second
replay. Only weeks where the step ran carry it, and only weeks stored since
addendum A3 carry its US cell: the season page shows that US figure only
for a season whose every week has one."""
from __future__ import annotations

import json
import os
import re

import pandas as pd
import pytest
from markupsafe import escape

from app.core import retro
from app.core import retro_store as RS
from app.core import us_national as usn
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


# --------------------------------------- the US cell (addendum A3)

W_PRE, W_A3 = "2098-01-03", "2098-01-10"
#: the national cell's filter quantiles sit off its truth, so its relWIS
#: differs from the states' and a US row pooled in would move the figure
US_TRUTH, US_NULL = 200.0, 280.0


def _week_oracle(a3: bool) -> dict:
    """A stored week's oracle.json with the US cell as apply_week records
    it before addendum A3 (outside the member, not in quantiles.null) and
    since (stepped under the RNG key 0, its null quantiles kept)."""
    locs = {"Ohio": {"fips": "39", "rng_key": "39", "state": "both"},
            "Utah": {"fips": "49", "rng_key": "49", "state": "both"}}
    null = {"Ohio": _null(100.0, 30.0), "Utah": _null(100.0, 30.0)}
    if a3:
        locs["US"] = {"fips": "US", "rng_key": "0", "state": "both"}
        null["US"] = _null(US_NULL, 30.0)
    else:
        locs["US"] = {"fips": "US", "state": "outside", "reason":
                      "outside the registered member (no integer FIPS key)"}
    return {"written_by": "test", "applied": True,
            "cells": {"outside_member": [] if a3 else ["US"]},
            "locations": locs,
            "quantiles": {"levels": list(QL), "null": null}}


def _a3_season(tmp_path, monkeypatch, eras: dict):
    """A finished two-state season with a fitted US row, its weeks of the
    given eras ({asof: stored since addendum A3}), scored and warmed as the
    finalize job leaves it, so the real season route renders in one
    request."""
    from app.core import playback as _pb
    from app.core import scoring as _scoring
    from app.ui import retro_seasons as ui_retro_seasons

    season = "2098-99"
    n2f = {"Ohio": "39", "Utah": "49", "US": "US"}
    truth = {(f, pd.Timestamp(W_PRE) + pd.Timedelta(days=7 * k)):
             (US_TRUTH if f == "US" else 100.0)
             for f in n2f.values() for k in range(-8, 10)}

    def _bases(a, fips_set, _t):
        return {(f, a, h): 2.0 for f in fips_set for h in range(4)}

    for mod in (_pb, _scoring):
        monkeypatch.setattr(mod, "load_truth", lambda: (truth, dict(n2f)))
        monkeypatch.setattr(mod, "_baseline_cells", _bases)
    monkeypatch.setattr(_pb, "HUB", tmp_path / "hub")         # no officials
    monkeypatch.setattr("app.core.data.truth_mtime", lambda: 0.0)
    root = tmp_path / season
    for asof, a3 in eras.items():
        wd = root / "weeks" / asof
        wd.mkdir(parents=True)
        at = {loc: (US_TRUTH if loc == "US" else 100.0) for loc in n2f}
        pf = {loc: {str(h): [at[loc] - 1, at[loc], at[loc] + 1]
                    for h in range(5)} for loc in n2f}
        an = {loc: {str(h): {str(L): at[loc] + (L - 0.5) * 10 for L in QL}
                    for h in range(1, 5)} for loc in n2f}
        (wd / "samples.json").write_text(
            json.dumps({"asof": asof, "pf": pf, "analogue": an}))
        (wd / RS.ORACLE_NAME).write_text(json.dumps(_week_oracle(a3)))
    retro.write_meta(root, {"status": "done", "weeks_completed": len(eras),
                            "total_weeks": len(eras),
                            "settings": {"oracle": "applied"}})
    RS._FILTER_CACHE.clear()
    retro.finalize_season(root, season)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    return root, season


def _season_page(season):
    """The real season route's page up to the player's host script, flat;
    its US tiles by member and the US table row."""
    from fastapi.testclient import TestClient

    from app.ui import server as srv
    html = TestClient(srv.app).get(f"/retro/{season}").text
    assert "preparing results" not in html and "Season player" in html
    page = " ".join(html.split("// live host for the shared player", 1)[0]
                    .split())
    tiles = dict(re.findall(r"<h2>(US \(fitted\): [^<]+)</h2>(.*?)</div></div>",
                            page))
    row = page.split('<tr class="usagg"', 1)[1].split("</tr>", 1)[0]
    return page, tiles, row


def _us_rel(df, model) -> float:
    us = df[(df.model == model) & df.location.map(usn.is_us)]
    return float(us.wis.sum() / us.base_wis.sum())


def test_an_a3_week_carries_the_filters_us_cell(tmp_path, monkeypatch):
    root, _s = _a3_season(tmp_path, monkeypatch, {W_PRE: False, W_A3: True})
    assert "US" not in RS.filter_quantiles(root / "weeks" / W_PRE)
    assert set(RS.filter_quantiles(root / "weeks" / W_A3)) == {"Ohio", "Utah", "US"}
    df = pd.read_json(root / "scores.json")
    f_us = df[(df.model == RS.FILTER_MEMBER) & df.location.map(usn.is_us)]
    assert set(f_us["asof"].astype(str).str[:10]) == {W_A3}
    # pooled figures never take it in, for the filter as for every member
    assert not usn.pooled_frame(df).location.map(usn.is_us).any()


def test_a_stepped_season_shows_the_filters_us_figure(tmp_path, monkeypatch):
    root, season = _a3_season(tmp_path, monkeypatch,
                              {W_PRE: True, W_A3: True})
    df = pd.read_json(root / "scores.json")
    want = _us_rel(df, RS.FILTER_MEMBER)
    assert want != pytest.approx(_us_rel(df, "pf"))   # its own figure
    page, tiles, row = _season_page(season)
    assert "US (fitted): Liu-West filter" in tiles
    assert f"{want:.3f}" in tiles["US (fitted): Liu-West filter"]
    assert f'data-pf_filter="{want:.6f}"' in row
    # the Oracle SIHRS US tile adds nothing: the step covers US
    assert "fitted nationally" in tiles["US (fitted): Oracle SIHRS"]
    assert usn.PF_US_SHORT not in page and usn.PF_US_SHORT_MIXED not in page
    assert str(escape(usn.PF_FILTER_US_WITHHELD)) not in page
    assert usn.PF_US_NOTES[usn.STEPPED] in page
    # the pooled Liu-West tile is the two states' figure, US left out
    states = usn.pooled_frame(df[df.model == RS.FILTER_MEMBER])
    pooled = float(states.wis.sum() / states.base_wis.sum())
    f = df[df.model == RS.FILTER_MEMBER]
    leaked = float(f.wis.sum() / f.base_wis.sum())
    assert f"{pooled:.3f}" != f"{leaked:.3f}"
    tile = page.split("<h2>Liu-West filter</h2>", 1)[1].split("</div></div>", 1)[0]
    assert f"{pooled:.3f}" in tile and f"{leaked:.3f}" not in tile


def test_a_filter_era_season_has_no_filter_us_figure(tmp_path, monkeypatch):
    root, season = _a3_season(tmp_path, monkeypatch,
                              {W_PRE: False, W_A3: False})
    df = pd.read_json(root / "scores.json")
    assert not (df[df.model == RS.FILTER_MEMBER].location
                .map(usn.is_us).any())
    page, tiles, row = _season_page(season)
    assert "US (fitted): Liu-West filter" not in tiles
    assert 'data-pf_filter=""' in row
    assert str(escape(usn.PF_FILTER_US_WITHHELD)) in row
    assert (usn.PF_US_SHORT + ", fitted nationally"
            in tiles["US (fitted): Oracle SIHRS"])
    assert usn.PF_US_NOTES[usn.FILTER] in page


def test_a_mixed_season_withholds_the_filters_us_figure(tmp_path,
                                                        monkeypatch):
    root, season = _a3_season(tmp_path, monkeypatch,
                              {W_PRE: False, W_A3: True})
    df = pd.read_json(root / "scores.json")
    there = _us_rel(df, RS.FILTER_MEMBER)            # the A3 week alone
    page, tiles, row = _season_page(season)
    assert "US (fitted): Liu-West filter" not in tiles
    assert 'data-pf_filter=""' in row and f"{there:.3f}" not in row
    assert str(escape(usn.PF_FILTER_US_WITHHELD)) in row
    assert (usn.PF_US_SHORT_MIXED + ", fitted nationally"
            in tiles["US (fitted): Oracle SIHRS"])
    assert (f"The filter alone: 1 week, {W_PRE}; the Oracle step: 1 week, "
            f"{W_A3}.") in page
    # the player hears it per week, from the same oracle.json
    from fastapi.testclient import TestClient

    from app.ui import server as srv
    c = TestClient(srv.app)
    pre = c.get(f"/api/retro/{season}/playback/{W_PRE}").json()
    a3 = c.get(f"/api/retro/{season}/playback/{W_A3}").json()
    assert (pre["us_step"], a3["us_step"]) == (usn.FILTER, usn.STEPPED)
    assert "US" not in pre["models"][RS.FILTER_MEMBER]
    assert "US" in a3["models"][RS.FILTER_MEMBER]


def test_the_season_report_says_what_the_page_says(tmp_path, monkeypatch):
    """The exported season report renders the same template: the same US
    tiles and row, and the player's payloads carry each week's era."""
    from app.core import report_season
    root, season = _a3_season(tmp_path, monkeypatch,
                              {W_PRE: False, W_A3: True})
    page, tiles, row = _season_page(season)
    rep = report_season.build_season_report(root, season).read_text(
        encoding="utf-8")
    flat = " ".join(rep.split())
    assert usn.PF_US_SHORT_MIXED + ", fitted nationally" in flat
    assert row in flat
    for t in tiles.values():
        assert t in flat
    assert '"us_step":"filter"' in rep and '"us_step":"stepped"' in rep
