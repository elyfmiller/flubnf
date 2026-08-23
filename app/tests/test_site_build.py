"""The public site generator, run against the repository's REAL state.

These tests deliberately do not fabricate a season. The generator's whole
job is to read what is actually on disk, so a fixture would test the
fixture. Instead the suite builds the site from the lab's own retrospectives
when they are present, and skips itself cleanly when they are not -- which
is exactly the CI case (no hub clone, no app/state), matching how every
other hub-dependent test in this repo behaves.

What is pinned here, and why each one is worth a test:

  * THE NUMBERS REACH THE PAGE. 2024-25 ensemble 0.651 and pooled 0.704 are
    the lab's published record. They must be computed from the forecasts on
    disk and appear in the HTML -- not merely in the payload, because a
    payload nobody renders is not a published figure.
  * THE ENSEMBLE IS THE SHIPPED ONE. A season's scores.json blends with the
    frozen LOSO weights, which the lab evaluated and REJECTED. Scoring from
    it would put 0.635 on the page under the name of the 0.651 forecast, and
    nothing about the page would look wrong. The test asserts the computed
    figure differs from scores.json and matches the equal-weight blend.
  * NOTHING LEAVES THE MACHINE. The page must reference no remote script,
    stylesheet, image or fetch beyond the Google Fonts stylesheet, or it is
    not the offline artifact a reviewer opens before committing.
  * NO UNRESOLVED PLACEHOLDERS. An unrendered Jinja tag or a literal None in
    a cell is the failure mode of a generator that half-worked; the BNGL
    listing's own {{TOKENS}} are the one legitimate exception and are
    scoped to it.
"""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import site_build as sb                 # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def _have_state() -> bool:
    """Real retrospectives AND a usable truth source. Both are needed; a
    season with no truth to score against would build an empty table."""
    try:
        from app.core.scoring import load_truth
        if not sb.discover_seasons():
            return False
        load_truth()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _have_state(),
    reason="no retrospective seasons or no settled truth on this machine "
           "(CI runs with FLUBNF_HUB=/nonexistent and no app/state)")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    res = sb.build(out_dir=out)
    html = (out / sb.PAGE_NAME).read_text(encoding="utf-8")
    payload = json.loads((out / sb.PAYLOAD_NAME).read_text(encoding="utf-8"))
    return res, out, html, payload


# ----------------------------------------------------------------- the build

def test_build_emits_page_payload_and_a_cached_plotly(built):
    res, out, html, payload = built
    assert (out / "index.html").is_file()
    assert (out / "site.json").is_file()
    assert (out / ".nojekyll").is_file()

    # Plotly is a SIBLING, never inlined: a 4.9 MB blob inside the page
    # would dominate every diff of the file whose diff is the review
    js = out / "plotly.min.js"
    assert js.is_file() and js.stat().st_size > 1_000_000
    assert 'src="plotly.min.js"' in html
    assert "plotly.js v" not in html


def test_payload_beside_the_page_is_the_bytes_the_page_reads(built):
    """The page embeds its data so it works from file://, and site.json is
    the same bytes so the diff a reviewer reads is the data the page uses.
    If these ever diverge the review is reviewing a different artifact."""
    res, out, html, payload = built
    m = re.search(r'<script type="application/json" id="flubnf-payload">'
                  r"(.*?)</script>", html, re.S)
    assert m, "the page carries no embedded payload"
    assert json.loads(m.group(1)) == payload
    assert m.group(1) == (out / "site.json").read_text(
        encoding="utf-8").rstrip("\n")


def test_payload_is_diff_reviewable(built):
    """One field per line and stable key order, or a rebuild that moved one
    number produces an unreadable diff and stops being reviewed."""
    res, out, _html, _payload = built
    text = (out / "site.json").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert len(lines) > 200, "payload collapsed onto too few lines to review"
    assert max(len(x) for x in lines) < 4000


# ---------------------------------------------------------------- no network

_REMOTE_ATTR = re.compile(r'(?:src|href)\s*=\s*"(https?:)?//([^"]+)"', re.I)


def test_the_page_loads_nothing_remote_but_the_font_stylesheet(built):
    res, out, html, _payload = built
    hosts = set()
    for m in _REMOTE_ATTR.finditer(html):
        tag_start = html.rfind("<", 0, m.start())
        tag = html[tag_start:m.start()].lower()
        # <a href> is a link the reader may follow, not a resource the page
        # fetches; only fetched subresources are constrained here
        if tag.startswith("<a "):
            continue
        hosts.add(m.group(2).split("/")[0].lower())
    assert hosts <= {"fonts.googleapis.com", "fonts.gstatic.com"}, hosts

    # and nothing fetches at runtime either
    for banned in ("fetch(", "XMLHttpRequest", "importScripts",
                   "new WebSocket", "navigator.sendBeacon"):
        assert banned not in html, banned


def test_nothing_on_the_page_needs_an_origin(built):
    """file:// has a null origin: localStorage can throw outright, and any
    origin-derived URL resolves to nothing. The page must survive both, or
    "open it before you commit it" is not a real instruction."""
    res, out, html, _payload = built
    for api in ("location.origin", "document.domain", "window.open(",
                "sessionStorage", "indexedDB", "caches.", "Worker("):
        assert api not in html, api
    # every localStorage touch is guarded, because on file:// it raises
    n_uses = html.count("localStorage")
    assert n_uses, "the accessibility choices are not persisted at all"
    for m in re.finditer(r"localStorage", html):
        window = html[max(0, m.start() - 400):m.start() + 400]
        assert "try {" in window or "try{" in window, \
            "an unguarded localStorage access would throw on file://"


def test_every_local_reference_resolves_on_disk(built):
    """"Works offline" means every non-remote src/href either names a file
    that shipped or is a same-page anchor."""
    res, out, html, _payload = built
    for m in re.finditer(r'(?:src|href)\s*=\s*"([^"]+)"', html):
        ref = m.group(1)
        if ref.startswith(("http://", "https://", "//", "#", "data:",
                           "mailto:")):
            continue
        assert (out / ref.split("#")[0]).exists(), ref


# ------------------------------------------------------------- the real data

def test_known_scores_reach_the_html(built):
    """The lab's published record, computed here and printed there."""
    res, out, html, payload = built
    by_season = {s["season"]: s for s in payload["seasons"]}

    if "2024-25" in by_season:
        rel = by_season["2024-25"]["models"]["ensemble"]["rel"]
        assert round(rel, 3) == 0.651, rel
        assert '<td class="n okc">0.651</td>' in html
        # the members that make that blend
        assert round(by_season["2024-25"]["models"]["pf"]["rel"], 3) == 0.636
        assert round(by_season["2024-25"]["models"]["analogue"]["rel"],
                     3) == 0.835

    if {"2023-24", "2024-25", "2025-26"} <= set(by_season):
        assert round(by_season["2023-24"]["models"]["ensemble"]["rel"],
                     3) == 0.848
        assert round(by_season["2025-26"]["models"]["ensemble"]["rel"],
                     3) == 0.691
        pooled = payload["pooled"]["ensemble"]["rel"]
        assert round(pooled, 3) == 0.704, pooled
        assert "0.704" in html
        # a member that LOST to the baseline must not read as neutral
        assert '<td class="n badc">1.023</td>' in html


def test_the_scored_ensemble_is_the_shipped_fifty_fifty_blend():
    """The trap this generator exists to avoid.

    retro.score_season writes scores.json with the FROZEN LOSO weights. The
    lab rejected those weights; the shipped forecast is the equal-weight
    blend. Both are called "ensemble". If the generator ever starts reading
    scores.json, this test fails -- because the two disagree, and the
    published number is the equal-weight one.
    """
    pd = pytest.importorskip("pandas")
    seasons = sb.discover_seasons()
    if "2024-25" not in seasons:
        pytest.skip("2024-25 not on this machine")
    sf = Path(seasons["2024-25"]["root"]) / "scores.json"
    if not sf.is_file():
        pytest.skip("this 2024-25 root has no stored scores.json")
    df = pd.read_json(sf)
    g = df[df.model == "ensemble"]
    loso = float(g.wis.sum() / g.base_wis.sum())

    from app.core.scoring import load_truth
    truth, n2f = load_truth()
    computed = sb.score_season("2024-25", seasons["2024-25"], truth,
                               n2f)["models"]["ensemble"]["rel"]
    assert round(computed, 3) == 0.651
    assert abs(computed - loso) > 0.01, (
        "the computed ensemble now equals the stored LOSO ensemble; the "
        "generator may have started reading scores.json")


def test_the_baseline_scores_exactly_one_against_itself(built):
    """A free proof that the whole scoring chain is wired correctly.

    relWIS divides each cell's WIS by the FluSight baseline's WIS on the
    same cell, and the baseline's own submitted forecast is separately
    parsed from the hub and scored through the identical path. If the
    baseline construction, the hub join (reference_date = asof + 7), the
    horizon offset, or the truth lookup were wrong anywhere, this would not
    come out at 1.000.
    """
    res, out, html, payload = built
    for s in payload["seasons"]:
        base = s["models"].get("FluSight-baseline")
        if base:
            assert abs(base["rel"] - 1.0) < 5e-4, (s["season"], base)


def test_official_comparators_are_scored_on_our_cells(built):
    """The columns sit in one row, so they must rest on one cell set. An
    unrestricted official column would cover weeks and locations ours does
    not, and a reader would compare them anyway."""
    res, out, html, payload = built
    for s in payload["seasons"]:
        ens = s["models"].get("ensemble")
        off = s["models"].get("FluSight-ensemble")
        if ens and off:
            assert off["cells"] == ens["cells"], (s["season"], ens, off)
    if any("FluSight-ensemble" in s["models"] for s in payload["seasons"]):
        assert "scored on exactly the cells" in html


def test_placements_are_harvested_not_invented(built):
    """The FluSight standings come from the console's own table. A season
    it does not cover gets no placement rather than a made-up one."""
    res, out, html, payload = built
    harvested = sb.harvest_placement()
    for s in payload["seasons"]:
        pl = s.get("placement")
        if s["season"] in harvested:
            assert pl and pl["text"] == harvested[s["season"]]["text"]
            assert pl["text"] in html
        else:
            assert pl is None
            assert "not yet scored against the field" in html


def test_every_computed_score_matches_what_the_console_publishes(built):
    """The drift alarm. The console states its performance in prose; this
    build recomputes it. They must agree, or one of them has moved."""
    res, out, html, payload = built
    checks = payload["consistency"]
    assert checks, "nothing was cross-checked"
    bad = [c for c in checks if not c["ok"]]
    assert not bad, bad
    assert "matches the figure the console publishes" in html


# ------------------------------------------------------------- the whole page

def test_no_unresolved_placeholders(built):
    """A half-rendered generator leaves Jinja tags and literal Nones behind.
    The BNGL listing's own {{TOKENS}} are legitimate and scoped to it."""
    res, out, html, _payload = built
    pre = re.search(r"<pre>(.*?)</pre>", html, re.S)
    assert pre, "the BNGL listing did not render"
    body = html.replace(pre.group(0), "")

    for bad in ("{{", "{%", "{#", "TODO", "FIXME", "Lorem ipsum",
                "PLACEHOLDER", "undefined"):
        assert bad not in body, bad
    for bad in (">None<", ">nan<", ">NaN<", ">null<", "0.0%</td>"):
        assert bad not in body, bad
    # the BNGL tokens survive where they belong, and are explained
    assert "{{POP}}" in pre.group(1)
    assert "filled per state and week at run time" in html


def test_methods_is_the_consoles_own_page_diagrams_included(built):
    """Harvested, not restated: the same headings, the same SVGs, and the
    version numbers the console reports for its own engines."""
    res, out, html, _payload = built
    src = (REPO / "app" / "ui" / "templates" / "methods.html").read_text()
    for heading in re.findall(r"<h2>([^<{]+)</h2>", src):
        heading = heading.strip()
        if heading == "Measured performance":
            continue          # deliberately dropped; the site computes it
        assert heading in html, heading
    assert html.count("<svg") >= 4, "the console's diagrams did not render"
    from app.ui.server import VERSIONS
    assert VERSIONS["pybnf"] in html
    # and no console-relative link survives onto a static site
    assert not re.search(r'href="/(?!/)', html)


def test_bibliography_comes_from_the_priors_module(built):
    res, out, html, _payload = built
    from flubnf import sihrs_priors as P
    for doi in (P.GT_SOURCE, P.R0_SOURCE, P.UNDERDETECTION_SOURCE):
        assert doi in html, doi


def test_outlook_is_a_real_national_map_with_a_working_toggle(built):
    """The map, its per-model fills, and the fans must describe the same
    forecast, and the toggle must actually change something."""
    res, out, html, payload = built
    ol = payload["outlook"]
    assert ol["coverage"] >= sb.MIN_OUTLOOK_LOCATIONS
    assert ol["default_model"] in ol["models"]
    assert 'id="usmap"' in html and "data-fips=" in html

    # every model paints exactly the shapes the map draws, and the page
    # states out loud any jurisdiction it forecasts but cannot draw
    drawn = set(ol["fills"][ol["default_model"]])
    for model in ol["models"]:
        assert f'data-m="{model}"' in html
        assert set(ol["fills"][model]) == drawn
    assert ol["mapped"] == len(drawn & set(ol["hover"]))
    assert ol["mapped"] <= ol["coverage"]
    for name in ol["unmapped"]:
        assert name in html, name
        assert name in payload["fans"], name

    if len(ol["models"]) > 1:
        a, b = ol["models"][0], ol["models"][1]
        assert any(ol["fills"][a][f] != ol["fills"][b][f]
                   for f in ol["fills"][a]), \
            "the model toggle swaps identical fills"

    # every hovered state has a fan to click through to
    for fips, card in ol["hover"].items():
        assert card["name"] in payload["fans"], card["name"]
        if fips in drawn:
            assert f'data-fips="{fips}"' in html, fips

    assert sum(ol["modal_tally"].values()) == ol["coverage"]


def test_fans_cover_every_location_and_carry_settled_only_where_true(built):
    """The conditional overlay: a settled point may only exist where truth
    for that target week actually arrived, and never beyond four weeks."""
    res, out, html, payload = built
    fans = payload["fans"]
    assert len(fans) >= sb.MIN_OUTLOOK_LOCATIONS
    asof = payload["outlook"]["source"]["asof"]
    for name, f in fans.items():
        assert f["obs"], name
        assert len(f["obs"]) <= sb.OBS_WEEKS
        assert all(d <= asof for d, _v in f["obs"]), name
        assert set(f["q"]) <= set(sb.HORIZONS)
        for level_map in f["q"].values():
            assert set(level_map) == {str(x) for x in sb.FAN_LEVELS}
        st = f.get("settled") or []
        assert len(st) <= 4, name
        assert all(d > asof and v is not None for d, v in st), name


def test_observations_are_the_vintage_the_forecast_saw(built):
    """Vintage-true observations, settled truth only in the overlay.

    A replayed week's playback payload carries SETTLED truth, because the
    console's replay viewer shows what happened. But the observed line and
    the map's "current" anchor describe what the forecast SAW, and NHSN
    revises the freshest week upward by a median 4-5%. Using settled values
    there moved a real state across a category cutpoint when this was
    written. The two series must come from the two different sources.
    """
    res, out, html, payload = built
    src = payload["outlook"]["source"]
    if src["kind"] != "retrospective":
        pytest.skip("outlook came from a live run, which has one vintage")
    assert "vintage" in src["observations"] or "no vintage" in \
        src["observations"]
    if "no vintage" in src["observations"]:
        pytest.skip("no vintage archived for this forecast date")

    from app.core import data as data_mod
    vin = data_mod.load_vintage(src["asof"])
    vin["location"] = vin["location"].str.zfill(2)
    from app.core.scoring import load_truth
    truth, n2f = load_truth()

    checked = 0
    for fips, card in payload["outlook"]["hover"].items():
        name = card["name"]
        rows = vin[(vin.location == fips)
                   & (vin.date.astype(str).str[:10] <= src["asof"])]
        if rows.empty:
            continue
        want = float(rows.sort_values("date").value.iloc[-1])
        assert abs(card["current"] - want) < 0.05, (name, card["current"],
                                                    want)
        assert payload["fans"][name]["obs"][-1][1] == card["current"], name
        checked += 1
    assert checked > 20, "too few locations checked to mean anything"

    # and the settled overlay still comes from settled truth, not the
    # vintage -- that is the whole point of drawing it separately
    import pandas as pd
    for name, fan in list(payload["fans"].items())[:8]:
        for d, v in (fan.get("settled") or []):
            fips = n2f.get(name)
            assert truth.get((fips, pd.Timestamp(d))) == v, (name, d)


def test_discovery_finds_seasons_rather_than_naming_them():
    """No season list is hardcoded: every discovered season is a directory
    that actually holds completed weeks, under a known root."""
    seasons = sb.discover_seasons()
    assert seasons
    roots = {str(p) for _o, p in sb.ROOT_ORDER}
    for name, info in seasons.items():
        assert re.fullmatch(r"\d{4}-\d{2}", name)
        assert info["weeks"]
        assert str(Path(info["root"]).parent) in roots
        assert Path(info["root"]).name == name


def test_a_pinned_outlook_week_is_honoured_and_recorded(tmp_path):
    """The override exists so a deliberate choice is deliberate: it must
    take effect AND leave a mark in the payload saying it was made."""
    seasons = sb.discover_seasons()
    season = min(seasons)
    asof = seasons[season]["weeks"][len(seasons[season]["weeks"]) // 2]
    res = sb.build(out_dir=tmp_path, pin=(season, asof))
    payload = json.loads((tmp_path / sb.PAYLOAD_NAME).read_text())
    src = payload["outlook"]["source"]
    assert src["asof"] == asof and src["season"] == season
    assert src["pinned"] is True
    assert asof in (tmp_path / sb.PAGE_NAME).read_text()

    with pytest.raises(sb.BuildError):
        sb.build(out_dir=tmp_path, pin=(season, "1999-01-01"))
