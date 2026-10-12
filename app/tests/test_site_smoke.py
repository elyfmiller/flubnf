"""The public site built from a small SYNTHETIC tree, so it runs in CI.

test_site_build.py holds the real record to its numbers and skips without
app/state; this module only checks that a build from any tree is a clean
public page: house wording (no en or em dashes, no "--" standing in for
one), nothing about the builder's machine ("not installed", local paths),
and one name for the mechanistic member (a tree replayed by the plain
filter never names the Oracle SIHRS outside Methods, which describes it).
The numbers are invented and asserted on nowhere.
"""
import json
import math
import random
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pd = pytest.importorskip("pandas")
pytest.importorskip("fastapi")       # Methods renders through the console

from app.core import data as data_mod                  # noqa: E402
from app.core import playback, retro, scoring          # noqa: E402
from app.core import site_build as sb                  # noqa: E402
from app.core import site_page                         # noqa: E402

SEASONS = {"2023-24": "2023-12-30", "2024-25": "2025-02-01"}
WEEKS = 4


def _truth():
    from flubnf.settings import load_locations
    loc = load_locations()
    loc = loc[loc.location != "US"]
    n2f = dict(zip(loc.location_name, loc.location.str.zfill(2)))
    pop = dict(zip(loc.location_name, loc.population.astype(float)))
    rng = random.Random(3)
    truth = {}
    for season, peak in SEASONS.items():
        pk = pd.Timestamp(peak)
        start = pd.Timestamp(f"{season[:4]}-10-05")
        start += pd.Timedelta(days=(5 - start.weekday()) % 7)
        for name, fips in n2f.items():
            amp = pop[name] / 1e5 * rng.uniform(4, 9)
            for k in range(40):
                d = start + pd.Timedelta(days=7 * k)
                w = (d - pk).days / 7
                truth[(fips, d)] = round(
                    amp * math.exp(-(w / 4.5) ** 2) + pop[name] / 1e6 * 2, 0)
    for d in sorted({k[1] for k in truth}):
        truth[("US", d)] = sum(v for (f, dd), v in truth.items()
                               if dd == d and f != "US")
    return truth, n2f


def _tree(root: Path, season: str, truth, n2f, oracle: bool):
    from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
    rng = random.Random(season)
    y = int(season[:4])
    start = pd.Timestamp(f"{y}-11-02")
    start += pd.Timedelta(days=(5 - start.weekday()) % 7)
    weeks = [(start + pd.Timedelta(days=7 * k)).date().isoformat()
             for k in range(WEEKS)]
    for asof in weeks:
        wd = root / "weeks" / asof
        wd.mkdir(parents=True, exist_ok=True)
        A = pd.Timestamp(asof)
        pf, an = {}, {}
        for name, fips in n2f.items():
            pf[name], an[name] = {}, {}
            for h in range(5):
                at = truth.get((fips, A + pd.Timedelta(days=7 * (h + 1))), 0)
                sd = 0.15 * (h + 1) * max(at, 1)
                pf[name][str(h)] = [max(0.0, rng.gauss(at, sd))
                                    for _ in range(30)]
                if h >= 1:
                    an[name][str(h)] = {str(L): max(0.0, at + (L - .5) * sd)
                                        for L in QL}
        (wd / "samples.json").write_text(json.dumps(
            {"asof": asof, "pf": pf, "analogue": an}))
        (wd / "oracle.json").write_text(json.dumps({"applied": oracle}))
    retro.write_meta(root, {"season": season, "status": "done",
                            "total_weeks": WEEKS, "weeks_completed": WEEKS,
                            "settings": {"season": season, "engine": "pf",
                                         "locations": sorted(n2f)}})
    return weeks


class _Text(HTMLParser):
    """Visible text and attribute prose, per tab; code, BNGL and scripts
    are left out (a CLI flag's "--" is not a dash)."""
    SKIP = ("script", "style", "pre", "code")

    def __init__(self):
        super().__init__()
        self.skip = 0
        self.page = "head"
        self.text = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self.skip += 1
        if a.get("id", "").startswith("p-"):
            self.page = a["id"]
        if tag == "footer":
            self.page = "footer"
        for k in ("content", "title", "aria-label", "alt"):
            if a.get(k) and tag != "link":
                self.text.setdefault(self.page, []).append(a[k])

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.text.setdefault(self.page, []).append(data)


def _pages(html: str) -> dict:
    p = _Text()
    p.feed(html)
    return {k: " ".join(" ".join(v).split()) for k, v in p.text.items()}


@pytest.fixture(scope="module", params=[False, True],
                ids=["filter-tree", "oracle-tree"])
def site(request, tmp_path_factory):
    oracle = request.param
    mp = pytest.MonkeyPatch()
    truth, n2f = _truth()
    n2f_all = dict(n2f, US="US")
    for mod in (scoring, playback):
        mp.setattr(mod, "load_truth", lambda: (truth, dict(n2f_all)))
        mp.setattr(mod, "_baseline_cells", lambda asof, fips_set, tr: {
            (f, asof, h): max(1.0, 0.2 * tr.get(
                (f, pd.Timestamp(asof) + pd.Timedelta(days=7 * (h + 1))),
                0) + 2)
            for f in fips_set for h in range(4)})
    tmp = tmp_path_factory.mktemp("site_smoke")
    mp.setattr(playback, "HUB", tmp / "hub")
    mp.setattr(data_mod, "truth_mtime", lambda: 0.0)

    def no_vintage(*_a, **_k):
        raise FileNotFoundError("no vintage")
    mp.setattr(data_mod, "load_vintage", no_vintage)
    mp.setattr(data_mod, "vintage_path", no_vintage)
    mp.setattr(sb, "_newest_run_source", lambda: (None, None, None))
    # the builder here has no engine: the page must not say so
    from app.ui import server
    for k in sb.ENGINE_KEYS:
        mp.setitem(server.VERSIONS, k, "not installed")
    mp.setitem(server.VERSIONS, "perl", "/usr/bin/perl")

    seasons = {}
    for s in SEASONS:
        root = tmp / "trees" / s
        weeks = _tree(root, s, truth, n2f, oracle)
        seasons[s] = {"root": root, "origin": "lab run", "weeks": weeks}
    out = tmp / "out"
    try:
        res = sb.build(out_dir=out, seasons=seasons)
    finally:
        mp.undo()
    html = (out / sb.PAGE_NAME).read_text(encoding="utf-8")
    payload = json.loads((out / sb.PAYLOAD_NAME).read_text(encoding="utf-8"))
    return oracle, res, html, payload


def test_the_tree_decides_the_mechanistic_name(site):
    oracle, _res, _html, payload = site
    want = sb.PF_LABEL_ORACLE if oracle else sb.PF_LABEL_FILTER
    assert payload["pf_label"] == want
    assert payload["outlook"]["source"]["pf_label"] == want
    assert payload["outlook"]["labels"]["pf"].startswith(want)


def test_no_dashes_in_any_visible_text(site):
    _o, _res, html, _payload = site
    for page, text in _pages(html).items():
        for bad in ("–", "—", "--"):
            assert bad not in text, (page, bad,
                                     text[max(0, text.find(bad) - 60):
                                          text.find(bad) + 60])


def test_nothing_about_the_builders_machine(site):
    _o, res, html, payload = site
    assert "not installed" not in html
    assert "/usr/bin" not in html
    assert set(res["engines_missing"]) == set(sb.ENGINE_KEYS)
    assert "perl" not in payload["build"]["versions"]
    assert all(v != "not installed"
               for v in payload["build"]["versions"].values())
    # Methods keeps its stack table, without the builder's Version column
    assert 'class="mt-stack"' in html
    assert "<th>Version</th>" not in html
    assert "Strawberry Perl" not in html


def test_a_filter_tree_never_names_the_oracle_sihrs(site):
    oracle, _res, html, _payload = site
    pages = _pages(html)
    outside_methods = " ".join(t for p, t in pages.items()
                               if p != "p-methods")
    if oracle:
        assert "Oracle SIHRS" in outside_methods
    else:
        assert "Oracle SIHRS" not in outside_methods
        assert "Particle filter alone" in outside_methods


def test_home_carries_the_record_and_the_wording(site):
    _o, _res, html, payload = site
    home = _pages(html)["p-home"]
    assert "Retrospective record" in home
    assert "Live standing" not in home
    assert "below 1 beats the CDC baseline" in home
    assert ("Both are fitted only on the data that existed on each forecast "
            "date and scored against settled truth.") in home
    for m in ("pf", "analogue"):
        assert f'{payload["pooled"][m]["rel"]:.3f}' in home
    # the convention sits behind a disclosure, not in the lead
    assert re.search(r"<details><summary>How the pooled figure is computed"
                     r"</summary><p>Every relWIS here is a ratio of sums",
                     html)
    assert ("53 locations: 52 jurisdictions plus the national total"
            in _pages(html)["p-methods"])


def test_retrospectives_drop_the_withdrawn_column(site):
    _o, _res, html, payload = site
    retro_text = _pages(html)["p-retro"]
    assert "FluSight field" not in re.findall(r"<th[^>]*>([^<]*)</th>", html)
    assert retro_text.count("placement withdrawn") == 1
    assert "relWIS by member" not in html
    for s in payload["seasons"]:
        assert f'data-cum="{s["season"]}"' in html
        assert s["weekly"] and "pf" in s["weekly"][-1]["cum"]


def test_the_page_is_addressable_and_shareable(site):
    _o, _res, html, _payload = site
    assert re.search(r"<title>FluBNF: [^<]{10,}</title>", html)
    assert '<meta property="og:title"' in html
    assert '<meta property="og:description"' in html
    assert '<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,' \
        in html
    assert 'href="site.json" download' in html
    assert "#install-and-run" in html
    js = site_page.JS
    assert "'fan=' + encodeURIComponent" in js and "showTab(h)" in js
    assert "visible:'legendonly'" not in js
    assert "displayModeBar = false" in js


def test_drift_alarm_reaches_home():
    payload = {"consistency": [{"what": "2024-25 Oracle SIHRS relWIS",
                                "computed": 0.8, "app": 0.7, "ok": False}]}
    alarm = site_page._drift_alarm(payload)
    assert "Scores disagree with the console" in alarm and "0.800" in alarm
    assert site_page._drift_alarm({"consistency": [
        {"what": "x", "computed": 0.7, "app": 0.7, "ok": True}]}) == ""


def test_timestamps_read_as_dates():
    assert site_page._when("2026-10-05T18:21:07+00:00") \
        == "5 October 2026, 18:21 UTC"
