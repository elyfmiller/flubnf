"""The public site generator, run against this machine's REAL state.

No fabricated season (a fixture would test the fixture); the module skips
cleanly without retrospectives, as in CI. Pinned: members' figures are
computed from on-disk forecasts and rendered into the HTML; no retired
blend is printed; nothing loads remotely except Google Fonts; no
unresolved placeholder outside the BNGL listing's {{TOKENS}}.
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
    """Real retrospectives AND a usable truth source (without truth a season
    builds an empty table)."""
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

    # Plotly is a SIBLING, never inlined (4.9 MB would swamp every diff)
    js = out / "plotly.min.js"
    assert js.is_file() and js.stat().st_size > 1_000_000
    assert 'src="plotly.min.js"' in html
    assert "plotly.js v" not in html


def test_payload_beside_the_page_is_the_bytes_the_page_reads(built):
    """The embedded payload (for file://) and site.json are the same bytes,
    so the reviewed diff is the data the page uses."""
    res, out, html, payload = built
    m = re.search(r'<script type="application/json" id="flubnf-payload">'
                  r"(.*?)</script>", html, re.S)
    assert m, "the page carries no embedded payload"
    assert json.loads(m.group(1)) == payload
    assert m.group(1) == (out / "site.json").read_text(
        encoding="utf-8").rstrip("\n")


def test_payload_is_diff_reviewable(built):
    """One field per line, stable key order: a rebuild's diff stays readable."""
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
        # <a href> is a link, not a fetched subresource
        if tag.startswith("<a "):
            continue
        hosts.add(m.group(2).split("/")[0].lower())
    assert hosts <= {"fonts.googleapis.com", "fonts.gstatic.com"}, hosts

    # and nothing fetches at runtime either
    for banned in ("fetch(", "XMLHttpRequest", "importScripts",
                   "new WebSocket", "navigator.sendBeacon"):
        assert banned not in html, banned


def test_nothing_on_the_page_needs_an_origin(built):
    """file:// has a null origin (localStorage can throw, origin URLs resolve
    to nothing); the page must survive both."""
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
    """Every non-remote src/href names a shipped file or a same-page anchor."""
    res, out, html, _payload = built
    for m in re.finditer(r'(?:src|href)\s*=\s*"([^"]+)"', html):
        ref = m.group(1)
        if ref.startswith(("http://", "https://", "//", "#", "data:",
                           "mailto:")):
            continue
        assert (out / ref.split("#")[0]).exists(), ref


# ------------------------------------------------------------- the real data

def _is_seal(root) -> bool:
    return "retro_seal" in str(root)


def test_known_scores_reach_the_html(built):
    """The sealed record's numbers are computed here and printed there; other
    trees are checked for shape and for the absence of any blend."""
    res, out, html, payload = built
    by_season = {s["season"]: s for s in payload["seasons"]}
    seasons = sb.discover_seasons()
    for s in payload["seasons"]:
        models = s["models"]
        assert "ensemble" not in models, s["season"]       # nothing blended
        assert ("pf" in models) or ("analogue" in models), s["season"]
        for m in ("pf", "analogue"):
            if m in models:
                assert models[m]["cells"] > 0 and models[m]["rel"] > 0
    assert "ensemble" not in payload["pooled"]

    if "2024-25" in by_season and _is_seal(seasons["2024-25"]["root"]):
        assert round(by_season["2024-25"]["models"]["pf"]["rel"], 3) == 0.636
        assert round(by_season["2024-25"]["models"]["analogue"]["rel"],
                     3) == 0.756
        assert '<td class="n okc">0.636</td>' in html

    if ({"2023-24", "2024-25", "2025-26"} <= set(by_season)
            and all(_is_seal(seasons[s]["root"]) for s in by_season)):
        assert round(by_season["2023-24"]["models"]["pf"]["rel"],
                     3) == 1.023
        assert round(by_season["2025-26"]["models"]["pf"]["rel"],
                     3) == 0.825
        assert round(by_season["2025-26"]["models"]["analogue"]["rel"],
                     3) == 0.621
        # a model that LOST to the baseline must not read as neutral
        assert '<td class="n badc">1.023</td>' in html


def test_site_build_never_reads_a_stored_scores_file():
    """site_build never reads a stored scores.json (older ones carry retired
    "ensemble" blends); it recomputes from the per-week payloads. Checked on
    the code path, whatever vintage is on disk.
    """
    import inspect
    src = inspect.getsource(sb)
    body = "".join(line for line in src.splitlines(keepends=True)
                   if not line.lstrip().startswith("#"))
    body = body.split('"""', 2)[-1]        # drop the module docstring
    assert "scores.json" not in body, (
        "site_build's code now mentions scores.json; the generator must "
        "recompute from playback payloads, never read a stored score file")


def test_the_site_never_scores_a_blend_even_where_a_stored_one_exists():
    """A tree scored before the blend's retirement keeps its rows in
    scores.json; the site still prints none, and member figures match."""
    pd = pytest.importorskip("pandas")
    seasons = sb.discover_seasons()
    if "2024-25" not in seasons:
        pytest.skip("2024-25 not on this machine")
    from app.core.scoring import load_truth
    truth, n2f = load_truth()
    computed = sb.score_season("2024-25", seasons["2024-25"], truth,
                               n2f)["models"]
    assert "ensemble" not in computed
    assert "pf" in computed or "analogue" in computed
    sf = Path(seasons["2024-25"]["root"]) / "scores.json"
    if not sf.is_file():
        return
    df = pd.read_json(sf)
    for m in ("pf", "analogue"):
        g = df[df.model == m] if "model" in df.columns else df[:0]
        if len(g) and m in computed:
            stored = float(g.wis.sum() / g.base_wis.sum())
            # same members, cells and formula; an older cell rule may differ
            # only within its own margin
            assert abs(stored - computed[m]["rel"]) < 0.05, (m, stored,
                                                             computed[m])


def test_the_baseline_scores_exactly_one_against_itself(built):
    """The baseline scores 1.000 against itself: any error in the baseline,
    the hub join (reference_date = asof + 7), the horizon offset or the truth
    lookup would break it."""
    res, out, html, payload = built
    for s in payload["seasons"]:
        base = s["models"].get("FluSight-baseline")
        if base:
            assert abs(base["rel"] - 1.0) < 5e-4, (s["season"], base)


def test_official_comparators_are_scored_on_our_cells(built):
    """Official comparator columns are scored on our cell set."""
    res, out, html, payload = built
    for s in payload["seasons"]:
        ens = s["models"].get("ensemble")
        off = s["models"].get("FluSight-ensemble")
        if ens and off:
            assert off["cells"] == ens["cells"], (s["season"], ens, off)
    if any("FluSight-ensemble" in s["models"] for s in payload["seasons"]):
        # the note says one cell set carries both columns...
        assert "on the same cells" in html
        # ...and names the comparator. The same-cells sentence is
        # unconditional, so only this line proves the has_official branch ran.
        assert "the hub's own combination of every team's forecasts" in html


def test_placements_are_harvested_not_invented(built):
    """Standings come from the console's own table, never invented. Since
    placement was withdrawn the table carries none, so this normally tests
    the empty branch."""
    res, out, html, payload = built
    harvested = sb.harvest_placement()
    for s in payload["seasons"]:
        pl = s.get("placement")
        stand = {k: v for k, v in harvested.get(s["season"], {}).items()
                 if k != "app_rel"}
        if stand:
            assert pl and pl["text"] == stand["text"]
            assert pl["text"] in html
        else:
            assert pl is None
            # the empty cell says WITHDRAWN, matching Methods
            assert "placement withdrawn, see Methods" in html
            assert "not yet scored against the field" not in html


def test_every_computed_score_matches_what_the_console_publishes(built):
    """The drift alarm: the console's published figures (home.html) agree
    with this recomputation. Only the reseal tree can match the numbers;
    others keep the structural half."""
    res, out, html, payload = built
    checks = payload["consistency"]
    assert checks, "nothing was cross-checked"
    # the mechanistic column is named for what the trees store (Oracle SIHRS,
    # or the particle filter for trees that predate it)
    assert payload["pf_label"] in (sb.PF_LABEL_ORACLE, sb.PF_LABEL_FILTER)
    assert all(payload["pf_label"] in c["what"] for c in checks)
    seasons = sb.discover_seasons()
    if not all("retro_reseal" in str(v["root"]) for v in seasons.values()):
        pytest.skip("the console publishes the reseal; this machine's "
                    "trees are another record")
    bad = [c for c in checks if not c["ok"]]
    assert not bad, bad
    assert "matches the figure the console publishes" in html


# ------------------------------------------------------------- the whole page

def test_no_unresolved_placeholders(built):
    """No Jinja tags or literal Nones outside the BNGL listing's {{TOKENS}}."""
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
    """Methods is harvested from the console: same headings, SVGs, versions."""
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
    """Map, per-model fills and fans describe one forecast; the toggle changes
    something."""
    res, out, html, payload = built
    ol = payload["outlook"]
    assert ol["coverage"] >= sb.MIN_OUTLOOK_LOCATIONS
    assert ol["default_model"] in ol["models"]
    assert 'id="usmap"' in html and "data-fips=" in html

    # every model paints the drawn shapes; undrawable jurisdictions are named
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
    """A settled point exists only where truth arrived, at most four weeks."""
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
    """Observed line and map anchor use the VINTAGE the forecast saw (NHSN
    revises the freshest week up ~4-5%); only the overlay uses settled truth.
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

    # the settled overlay comes from settled truth, not the vintage
    import pandas as pd
    for name, fan in list(payload["fans"].items())[:8]:
        for d, v in (fan.get("settled") or []):
            fips = n2f.get(name)
            assert truth.get((fips, pd.Timestamp(d))) == v, (name, d)


def test_discovery_finds_seasons_rather_than_naming_them():
    """No hardcoded season list: each is a directory of completed weeks under
    a known root."""
    seasons = sb.discover_seasons()
    assert seasons
    roots = {str(p) for _o, p in sb.ROOT_ORDER}
    for name, info in seasons.items():
        assert re.fullmatch(r"\d{4}-\d{2}", name)
        assert info["weeks"]
        assert str(Path(info["root"]).parent) in roots
        assert Path(info["root"]).name == name


def test_a_pinned_outlook_week_is_honoured_and_recorded(tmp_path):
    """A pinned outlook week takes effect and is recorded in the payload."""
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
