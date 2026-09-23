"""The Retrospective tab shows backfilled Oracle SIHRS seasons, read only.

`flubnf oracle backfill` refuses app/state, so its seasons live in a
separate directory: app/state/retro_oracle by default, or the directory
FLUBNF_RETRO_ORACLE names. The tab reads it under src=oracle:

  * the index lists the source's seasons with the source named, a
    selector between it and the console's own replays, and no control that
    writes;
  * the season page renders a backfilled root, names the source and what
    its second member is, and shows the Oracle SIHRS relWIS the app's own
    scorer computes for it (the member, never the filter kept beside it);
  * the playback, map-swap and status routes read the same root;
  * the console's live and sealed trees are never written, and a source
    configured inside one of them is refused.
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient                  # noqa: E402

from app.core import playback, reclaim, retro, scoring     # noqa: E402
from app.ui import server as srv                           # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL      # noqa: E402

client = TestClient(srv.app)

SEASON = "2098-99"
W1, W2 = "2098-01-03", "2098-01-10"
N2F = {"Ohio": "39", "Utah": "49"}
GRID = "/grid/J15/2098-99"


def _truth():
    t = {}
    for fips, base in (("39", 100.0), ("49", 50.0)):
        for k in range(-8, 8):
            t[(fips, pd.Timestamp(W1) + pd.Timedelta(days=7 * k))] = base + k
    return t


def _backfilled_root(source: Path) -> Path:
    """A season root in the shape `flubnf oracle backfill` writes: pf the
    member, pf_filter the filter kept beside it, the source's analogue, the
    week's oracle.json, and a run record carrying the backfill block."""
    root = source / SEASON
    truth = _truth()
    for asof in (W1, W2):
        wd = root / "weeks" / asof
        wd.mkdir(parents=True, exist_ok=True)
        pf, flt, an = {}, {}, {}
        for loc, fips in N2F.items():
            at = {h: truth[(fips, pd.Timestamp(asof) + pd.Timedelta(days=7 * h))]
                  for h in range(5)}
            # the member sits on the truth; the filter it came from runs
            # 30 percent high, so the two score very differently
            pf[loc] = {str(h): [at[h] + d for d in (-1.0, 0.0, 1.0)]
                       for h in range(5)}
            flt[loc] = {"0": pf[loc]["0"]}
            flt[loc].update({str(h): [1.3 * at[h] + d for d in (-1.0, 0.0, 1.0)]
                             for h in range(1, 5)})
            an[loc] = {str(h): {str(L): at[h] + (L - 0.5) * 10 for L in QL}
                       for h in range(1, 5)}
        (wd / "samples.json").write_text(json.dumps(
            {"asof": asof, "pf": pf, "pf_filter": flt, "analogue": an}))
        (wd / "oracle.json").write_text(json.dumps(
            {"applied": True, "member": "Oracle SIHRS", "asof": asof}))
        # the sidecar the backfill writes beside every week, current
        retro.write_week_quantiles(
            wd, retro.member_quantiles(retro.read_week_samples(root, asof)))
    retro.write_meta(root, {
        "season": SEASON, "status": "done",
        "settings": {"season": SEASON, "engine": "pf", "week_extra": "J15",
                     "locations": sorted(N2F), "oracle": "applied"},
        "backfill": {"source_root": GRID, "keep_filter": True,
                     "prereg_sha256": "67c9fa49a195908312f34ca783b21d85"
                                      "377759309df14461f86fbfd54d30c56f",
                     "source_settings": {"week_extra": "J15", "grid": True},
                     "weeks_done": [W1, W2]}})
    return root


def _snapshot(root: Path) -> dict:
    if not root.exists():
        return {}
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def world(monkeypatch, tmp_path):
    """Truth and baselines stubbed for both scoring surfaces, the console's
    own trees pointed at controlled directories (each holding a file, so a
    write would show), and the source configured by the environment."""
    truth = _truth()
    for mod in (scoring, playback):
        monkeypatch.setattr(mod, "load_truth", lambda: (truth, dict(N2F)))
        monkeypatch.setattr(mod, "_baseline_cells",
                            lambda asof, fips_set, tr: {(f, asof, h): 2.0
                                                        for f in fips_set
                                                        for h in range(4)})
    monkeypatch.setattr(playback, "HUB", tmp_path / "hub")
    live, seal, reseal = (tmp_path / "retro", tmp_path / "retro_seal",
                          tmp_path / "retro_reseal")
    for d in (live, seal, reseal):
        d.mkdir()
        (d / "KEEP").write_text("untouched")
    monkeypatch.setattr(srv, "RETRO_ROOT", live)
    monkeypatch.setattr(srv, "RETRO_SEAL", seal)
    monkeypatch.setattr(srv, "RETRO_RESEAL", reseal)
    source = tmp_path / "backfill_out"
    source.mkdir()
    monkeypatch.setenv(srv.RETRO_ORACLE_ENV, str(source))
    srv._results_jobs.clear()
    srv._invalidate_scans()
    yield {"source": source, "live": live, "seal": seal, "reseal": reseal}
    srv._results_jobs.clear()


def _text(html: str) -> str:
    return " ".join(html.split())


def test_the_index_lists_the_backfilled_source_read_only(world):
    _backfilled_root(world["source"])
    html = client.get("/retro?src=oracle").text
    t = _text(html)
    assert 'aria-label="Retrospective source"' in html
    assert "Oracle SIHRS backfill" in t and "Console replays" in t
    assert str(world["source"]) in t                   # the source, named
    assert "set by FLUBNF_RETRO_ORACLE" in t
    assert f'href="/retro/{SEASON}?src=oracle"' in html
    assert "2 backfilled weeks" in t
    assert GRID in t                                    # where it came from
    # nothing here can write: the page body carries no form at all, so no
    # run, season control, archive or delete (the shell around it is the
    # same on every page)
    start = html.index("<h1>Retrospective</h1>")
    body = html[start:html.index("<script", start)]
    assert "<form" not in body
    assert "data-del-archive" not in body and "data-startover" not in body
    # the console's own index still carries its own view and the selector
    own = client.get("/retro").text
    assert 'action="/retro/run"' in own
    assert "Oracle SIHRS backfill" in own


def test_the_season_page_shows_the_members_relwis_and_names_the_source(world):
    root = _backfilled_root(world["source"])
    before = {k: _snapshot(world[k]) for k in ("live", "seal", "reseal")}
    weeks_before = _snapshot(root / "weeks")

    r = client.get(f"/retro/{SEASON}?src=oracle")
    assert r.status_code == 200
    t = _text(r.text)
    assert "weeks scored" in t
    # the source and the second member, named on the page
    assert "Oracle SIHRS backfill, read only." in t
    assert f"{world['source']}/{SEASON}" in t
    assert GRID in t and "no refit" in t
    assert "not the shipped Groundhog" in t
    # the Oracle SIHRS tile is the app's own scorer on the stored member
    sc = pd.read_json(root / "scores.json")
    assert set(sc.model) == {"pf", "analogue"}          # never pf_filter
    pf = sc[sc.model == "pf"]
    expected = pf.wis.sum() / pf.base_wis.sum()
    m = re.search(r'<h2>Oracle SIHRS</h2><div class="big (ok|bad)">'
                  r'([0-9.]+)</div>', t)
    assert m, "no Oracle SIHRS tile"
    assert m.group(2) == f"{expected:.3f}"
    # and it is the member's, not the filter's: scoring the filter kept
    # beside it gives a different, worse figure
    filt = tmp_filter_score(root)
    assert filt > expected + 0.05
    # every link and fetch on the page stays on the source
    assert "src=oracle" in r.text and 'const SRC = "oracle"' in r.text
    # the weeks are untouched, the console's own trees never written
    assert _snapshot(root / "weeks") == weeks_before
    for k, snap in before.items():
        assert _snapshot(world[k]) == snap, k
    # reclaim protects the source: no finalize prune reaches its weeks
    assert reclaim.is_protected(root / "weeks" / W1)


def tmp_filter_score(root: Path) -> float:
    """The same scorer on a copy whose pf is the filter kept beside it."""
    import shutil
    copy = root.parent.parent / "filter_copy" / SEASON
    shutil.copytree(root, copy)
    for wd in (copy / "weeks").iterdir():
        d = json.loads((wd / "samples.json").read_text())
        d["pf"] = d.pop("pf_filter")
        (wd / "samples.json").write_text(json.dumps(d))
    df = retro.score_season(copy, SEASON)
    g = df[df.model == "pf"]
    return float(g.wis.sum() / g.base_wis.sum())


def test_the_players_routes_read_the_same_root(world):
    _backfilled_root(world["source"])
    client.get(f"/retro/{SEASON}?src=oracle")              # scores and warms
    pl = client.get(f"/api/retro/{SEASON}/playback/{W1}?src=oracle")
    assert pl.status_code == 200
    assert set(pl.json()["models"]) == {"pf", "analogue"}
    mp = client.get(f"/api/retro/{SEASON}/mapswap/{W1}?src=oracle")
    assert mp.status_code == 200 and "pf" in mp.json()["models"]
    st = client.get(f"/api/retro/{SEASON}/results_status?src=oracle").json()
    assert st["pending"] is False
    # the console's own (empty) season is a different root: nothing there
    assert client.get(f"/api/retro/{SEASON}/playback/{W1}").status_code == 404


def test_a_source_inside_the_consoles_trees_is_refused(world, monkeypatch):
    inside = world["seal"] / "backfill"
    _backfilled_root(inside)
    monkeypatch.setenv(srv.RETRO_ORACLE_ENV, str(inside))
    before = _snapshot(world["seal"])
    t = _text(client.get("/retro?src=oracle").text)
    assert "one of the console" in t and "retrospective trees" in t
    assert f'href="/retro/{SEASON}?src=oracle"' not in t
    r = client.get(f"/retro/{SEASON}?src=oracle", follow_redirects=False)
    assert r.status_code == 303
    assert client.get(f"/api/retro/{SEASON}/playback/{W1}?src=oracle") \
        .status_code == 404
    assert _snapshot(world["seal"]) == before
    # the live tree, and a parent of every tree, are refused the same way
    for bad in (world["live"], world["live"].parent):
        monkeypatch.setenv(srv.RETRO_ORACLE_ENV, str(bad))
        assert srv._retro_source()["refused"]


def test_unknown_sources_and_mixed_selectors_are_refused(world):
    _backfilled_root(world["source"])
    assert client.get("/retro?src=elsewhere",
                      follow_redirects=False).status_code == 303
    r = client.get(f"/retro/{SEASON}?src=oracle&archive=20980204T101500Z",
                   follow_redirects=False)
    assert r.status_code == 303
    assert client.get(f"/api/retro/{SEASON}/playback/{W1}?src=nope") \
        .status_code == 404


def test_the_default_source_is_under_app_state_and_gitignored(monkeypatch):
    monkeypatch.delenv(srv.RETRO_ORACLE_ENV, raising=False)
    s = srv._retro_source()
    assert s["root"] == srv.RETRO_ORACLE
    assert srv.RETRO_ORACLE.parent.name == "state"
    assert srv.RETRO_ORACLE.parent.parent.name == "app"
    gi = (Path(__file__).resolve().parents[2] / ".gitignore").read_text()
    assert "app/state/" in gi.split()
