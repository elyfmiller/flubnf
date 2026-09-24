"""pf is named for what a season tree stores, on every Retrospective surface.

The shared map calls pf the Oracle SIHRS, but every sealed record and
pre-Oracle replay stores the particle filter alone under pf. The console
names pf per tree by site_build.tree_carries_oracle: no oracle.json and no
run record naming the step means "Particle filter alone" on the index,
season page and exported report; otherwise "Oracle SIHRS". An export built
before per-tree names is rebuilt, not served.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient                  # noqa: E402

from app.core import playback, report_season, retro, scoring  # noqa: E402
from app.core import site_build                            # noqa: E402
from app.ui import server as srv                           # noqa: E402
from app.ui import retro_prep as ui_retro_prep             # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons       # noqa: E402
from app.ui import shared as ui_shared                     # noqa: E402
from app.ui import templating as ui_templating             # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL      # noqa: E402

client = TestClient(srv.app)

SEASON, OTHER = "2098-99", "2097-98"
W1, W2 = "2098-01-03", "2098-01-10"
N2F = {"Ohio": "39", "Utah": "49"}
STAMP_PLAIN, STAMP_ORACLE = "20980204T101500Z", "20980205T101500Z"

FILTER = "Particle filter alone"
ORACLE = "Oracle SIHRS"

PLAYER = Path(__file__).resolve().parents[1] / "ui" / "static" / "player.js"
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/"
           "Versions/Current/Helpers/jsc")


def _truth():
    t = {}
    for fips, base in (("39", 100.0), ("49", 50.0)):
        for k in range(-8, 8):
            t[(fips, pd.Timestamp(W1) + pd.Timedelta(days=7 * k))] = base + k
    return t


def _tree(root: Path, oracle: str = "", season: str = SEASON) -> Path:
    """A finished, scored two-week season tree. oracle="" is the plain filter
    (as every sealed record stores it); "weeks" writes oracle.json beside
    each week; "meta" records settings.oracle = "applied" instead."""
    truth = _truth()
    for asof in (W1, W2):
        wd = root / "weeks" / asof
        wd.mkdir(parents=True, exist_ok=True)
        pf, an = {}, {}
        for loc, fips in N2F.items():
            at = {h: truth[(fips, pd.Timestamp(asof) + pd.Timedelta(days=7 * h))]
                  for h in range(5)}
            pf[loc] = {str(h): [at[h] + d for d in (-1.0, 0.0, 1.0)]
                       for h in range(5)}
            an[loc] = {str(h): {str(L): at[h] + (L - 0.5) * 10 for L in QL}
                       for h in range(1, 5)}
        (wd / "samples.json").write_text(
            json.dumps({"asof": asof, "pf": pf, "analogue": an}))
        if oracle == "weeks":
            (wd / "oracle.json").write_text(json.dumps(
                {"applied": True, "member": ORACLE, "asof": asof}))
    settings = {"season": season, "engine": "pf", "locations": sorted(N2F)}
    if oracle == "meta":
        settings["oracle"] = "applied"
    retro.write_meta(root, {"season": season, "status": "done",
                            "total_weeks": 2, "weeks_completed": 2,
                            "settings": settings})
    retro.finalize_season(root, season)
    return root


@pytest.fixture
def world(monkeypatch, tmp_path):
    """Truth and baselines stubbed for both scoring surfaces, console trees
    pointed at empty dirs, and a controlled season list."""
    truth = _truth()
    for mod in (scoring, playback):
        monkeypatch.setattr(mod, "load_truth", lambda: (truth, dict(N2F)))
        monkeypatch.setattr(mod, "_baseline_cells",
                            lambda asof, fips_set, tr: {(f, asof, h): 2.0
                                                        for f in fips_set
                                                        for h in range(4)})
    monkeypatch.setattr(playback, "HUB", tmp_path / "hub")
    monkeypatch.setattr(report_season, "_plotlyjs", lambda: "/* stub */")
    live, seal, reseal = (tmp_path / "retro", tmp_path / "retro_seal",
                          tmp_path / "retro_reseal")
    for d in (live, seal, reseal):
        d.mkdir()
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", live)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", seal)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_RESEAL", reseal)
    monkeypatch.setattr(retro, "available_seasons", lambda: [SEASON, OTHER])
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])
    monkeypatch.setattr(srv, "_retro_bg", lambda *a, **k: None)
    status_before = dict(ui_retro_seasons._retro_status)
    ui_retro_seasons._retro_status.clear()
    ui_retro_prep._results_jobs.clear()
    ui_shared._invalidate_scans()
    yield {"live": live, "seal": seal, "reseal": reseal}
    ui_retro_prep._results_jobs.clear()
    ui_retro_seasons._retro_status.clear()
    ui_retro_seasons._retro_status.update(status_before)
    ui_shared._invalidate_scans()


def _text(html: str) -> str:
    return " ".join(html.split())


def _card(html: str, marker: str) -> str:
    """The index card or row that starts at `marker`, up to the next one."""
    i = html.index(marker)
    ends = [j for j in (html.find('<div class="card', i + 1),
                        html.find('<div class="archrow"', i + 1)) if j > 0]
    return _text(html[i:min(ends) if ends else len(html)])


def _page(season: str, query: str = "") -> str:
    r = client.get(f"/retro/{season}{query}")
    assert r.status_code == 200
    assert "preparing results" not in r.text, "the fixture must be warm"
    return r.text


def _report(season: str, query: str = "") -> str:
    r = client.get(f"/retro/{season}/report{query}")
    assert r.status_code == 200
    return r.text


# ------------------------------------------------------------ the index

def test_each_season_card_names_pf_for_the_tree_it_reads(world):
    # a sealed record storing the filter alone beside a live replay whose
    # run record says the step was applied
    _tree(world["reseal"] / SEASON)
    _tree(world["live"] / OTHER, oracle="meta", season=OTHER)
    html = client.get("/retro").text
    sealed = _card(html, f'data-season="{SEASON}"')
    live = _card(html, f'data-season="{OTHER}"')
    assert "the production engine" in sealed          # the seal, named
    assert f"{FILTER} relWIS" in sealed
    assert f"{ORACLE} relWIS" not in sealed
    assert f"{ORACLE} relWIS" in live
    assert FILTER not in live


def test_each_archived_run_is_named_for_its_own_tree(world):
    rr = world["live"]
    _tree(rr / SEASON)
    retro.archive_run(rr, SEASON, stamp=STAMP_PLAIN)
    _tree(rr / SEASON, oracle="weeks")
    retro.archive_run(rr, SEASON, stamp=STAMP_ORACLE)
    ui_shared._invalidate_scans()
    html = client.get("/retro").text
    assert "2 archived runs kept" in html
    rows = html.split('<div class="archrow">')[1:]
    by_stamp = {s: _text(next(r for r in rows if f'?archive={s}"' in r))
                for s in (STAMP_PLAIN, STAMP_ORACLE)}
    assert f"{FILTER} relWIS" in by_stamp[STAMP_PLAIN]
    assert f"{ORACLE} relWIS" not in by_stamp[STAMP_PLAIN]
    assert f"{ORACLE} relWIS" in by_stamp[STAMP_ORACLE]
    assert FILTER not in by_stamp[STAMP_ORACLE]


def test_the_replay_form_names_the_oracle_sihrs(world):
    """The run form's full preset is the Oracle SIHRS beside the Groundhog;
    its value is still the member's internal key."""
    t = _text(client.get("/retro").text)
    assert '<option value="pf">Oracle SIHRS and the Groundhog (hours)</option>' in t
    assert "Particle filter with the Groundhog" not in t
    assert "Each week fits the Oracle SIHRS from the season start" in t
    assert srv.retro_engine_label("pf") == "Oracle SIHRS and the Groundhog"


# ------------------------------------------------------- the season page

def test_the_season_page_names_pf_for_the_tree_it_shows(world):
    _tree(world["reseal"] / SEASON)
    _tree(world["live"] / OTHER, oracle="weeks", season=OTHER)

    html = _page(SEASON)                  # the sealed record, filter alone
    t = _text(html)
    # the verdict tile, the chart legend and the table header
    assert f"<h2>{FILTER}</h2>" in t
    assert f"<h2>{ORACLE}</h2>" not in t
    assert "&#9632;</span> " + FILTER in t
    assert f"aria-pressed=\"false\">{FILTER}<" in t
    # the map toggle the week's two models draw
    assert 'id="retro-model"' in html
    assert f"{FILTER} categorical forecast" in t and f"{ORACLE} categorical forecast" not in t
    # the in-page player's shared map is set before the player is built
    line = f"FluBNFPlayer.MODEL_NAMES.pf = {json.dumps(FILTER)};"
    assert line in html
    assert html.index(line) < html.index("const MNAMES")
    assert html.index(line) < html.index("FluBNFPlayer.init(")
    # and nothing on the page names the stored filter the Oracle SIHRS
    assert ORACLE not in t

    html = _page(OTHER)                   # a tree that carries the step
    t = _text(html)
    assert f"<h2>{ORACLE}</h2>" in t
    assert f"{ORACLE} categorical forecast" in t
    assert f"FluBNFPlayer.MODEL_NAMES.pf = {json.dumps(ORACLE)};" in html
    assert FILTER not in t


def test_a_page_model_name_shadows_the_template_global():
    """A context variable named model_name shadows the template global for
    that render only."""
    env = srv.templates.env
    assert env.globals["model_name"]("pf") == ORACLE
    tpl = env.from_string("{{ model_name('pf') }}|{{ model_name('analogue') }}")
    got = tpl.render(model_name=ui_templating._name_fn(dict(ui_templating._model_names(),
                                                  pf=FILTER)))
    assert got == f"{FILTER}|Groundhog"
    assert tpl.render() == f"{ORACLE}|Groundhog"      # the global, untouched


@pytest.mark.skipif(not JSC.is_file(),
                    reason="JavaScriptCore jsc not available")
def test_the_page_line_renames_pf_in_the_players_shared_map(world, tmp_path):
    """Run after player.js, the emitted line renames pf in the player's one
    shared MODEL_NAMES object (read by reference)."""
    _tree(world["reseal"] / SEASON)
    html = _page(SEASON)
    m = re.search(r"FluBNFPlayer\.MODEL_NAMES\.pf = [^;\n]+;", html)
    assert m, "the season page must hand the player the tree's pf name"
    drv = tmp_path / "driver.js"
    drv.write_text(m.group(0) + "\nvar I = FluBNFPlayer._internals;\n"
                   "print(JSON.stringify([I.nameOf('pf'), I.nameOf('analogue'),"
                   " I.MODEL_NAMES.pf]));\n")
    out = subprocess.run([str(JSC), str(PLAYER), str(drv)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, (out.stderr or out.stdout)
    assert json.loads(out.stdout.strip().splitlines()[-1]) == \
        [FILTER, "Groundhog", FILTER]


# ------------------------------------------------------ the season report

def test_the_report_names_pf_for_the_tree_it_exports(world):
    _tree(world["reseal"] / SEASON)
    _tree(world["live"] / OTHER, oracle="meta", season=OTHER)

    html = _report(SEASON)                # the sealed record, filter alone
    assert f'class="tilename">{FILTER}<' in html
    assert f'class="tilename">{ORACLE}<' not in html
    assert f'<th class="num">{FILTER}</th>' in html
    assert f'<th class="num">{ORACLE}</th>' not in html
    # the embedded player gets the same names via the overriding line (the
    # inlined player.js still carries the shared literal)
    line = report_season._names_line(
        dict(report_season.MODEL_NAMES, pf=FILTER))
    assert line in html
    assert html.index("var FluBNFPlayer") < html.index(line) \
        < html.rindex("FluBNFPlayer.init(")
    # the shared module map is never rewritten by a build
    assert report_season.MODEL_NAMES["pf"] == ORACLE

    html = _report(OTHER)                 # a tree that carries the step
    assert f'class="tilename">{ORACLE}<' in html
    assert f'class="tilename">{FILTER}<' not in html
    assert report_season._names_line(dict(report_season.MODEL_NAMES)) in html


def test_an_export_built_before_names_were_per_tree_is_rebuilt(world):
    """A cached export fresh by mtime but titled under the old names is
    rebuilt."""
    import os
    root = _tree(world["reseal"] / SEASON)
    p = report_season.build_season_report(root, SEASON)
    stale = ("Run settings " + report_season._timing_note(root)
             + f'<div class="tilename">{ORACLE}</div>')
    p.write_text(stale)
    future = p.stat().st_mtime + 60
    os.utime(p, (future, future))
    html = _report(SEASON)
    assert html != stale
    assert f'class="tilename">{FILTER}<' in html
    assert f'class="tilename">{ORACLE}<' not in html


# ------------------------------------------------------------ the helper

def test_the_names_helper_fails_closed(world, monkeypatch, tmp_path):
    plain = _tree(world["live"] / SEASON)
    assert ui_templating._names_for_root(plain)["pf"] == FILTER
    assert ui_templating._names_for_root(tmp_path / "no" / "such" / "tree")["pf"] \
        == FILTER
    oracle = _tree(tmp_path / "o" / SEASON, oracle="weeks")
    assert ui_templating._names_for_root(oracle)["pf"] == ORACLE

    def boom(root):
        raise RuntimeError("unreadable")
    monkeypatch.setattr(site_build, "tree_carries_oracle", boom)
    assert ui_templating._names_for_root(oracle)["pf"] == FILTER
    # every other name is the shared map's, and the map itself is a copy
    names = ui_templating._names_for_root(oracle)
    assert {k: v for k, v in names.items() if k != "pf"} == \
        {k: v for k, v in ui_templating._model_names().items() if k != "pf"}
    assert ui_templating._model_names()["pf"] == ORACLE
