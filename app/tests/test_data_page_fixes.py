"""The Data page (G24): a store or delete notice in view, the comparators'
remedy and primary action, the live target file in the vintage browser,
one colour per season on the page (a dataset's page: its own seasons), a
pull's "up to date" that does not outlive its minute, and a snapshot's
title.

The chart's colours and titles are read from the page's own script, run
under node with stand-ins for the document and the chart library (those
checks are skipped where node is absent)."""
import json
import re
import shutil
import subprocess

import pytest

from app.core import data as data_mod                # noqa: E402
from app.core import datasets as D                   # noqa: E402
from app.ui import shared as ui_shared               # noqa: E402
from app.ui import state as ui_state                 # noqa: E402
from app.ui.routes import data as ui_data            # noqa: E402
from test_data_view import _write_vintage, archive, client, V1, V2  # noqa: E402,F401
from test_datasets_ui import isolated, stored, upload  # noqa: E402,F401
from test_dataset_snapshots import ASOFS, as_of_csv  # noqa: E402

NODE = shutil.which("node")

#: runs the vintage chart's script (stdin) with stand-ins: a CSS variable
#: reads as its own name, so a colour comes out as its token; prints each
#: chart drawn (the script's own first draw, raw, then season over season)
#: as {title, traces: [{name, color}]}
_RUNNER = r"""
const vm = require('vm');
const src = require('fs').readFileSync(0, 'utf8');
const drawn = [];
const els = {};
const ctx = {
  document: {documentElement: {},
             getElementById: id => (els[id] = els[id] ||
               {classList: {toggle() {}}, setAttribute() {}, onclick: null})},
  getComputedStyle: () => ({getPropertyValue: v => v, fontSize: '16px'}),
  FluCharts: {react: (el, traces, layout) => drawn.push({
    title: layout.title.text,
    traces: traces.map(t => ({name: t.name,
                              color: t.line ? t.line.color : null}))})},
  addEventListener() {},
};
vm.createContext(ctx);
vm.runInContext(src, ctx);
vm.runInContext("drawVintage('season')", ctx);
process.stdout.write(JSON.stringify(drawn));
"""


def _drawn(page: str) -> list:
    """The charts the page's vintage script draws: [raw, season over
    season], each {title, traces}."""
    if NODE is None:
        pytest.skip("node is not installed")
    script = next(c.split("</script>", 1)[0] for c in page.split("<script>")
                  if "const VSERIES = " in c.split("</script>", 1)[0])
    out = subprocess.run([NODE, "-e", _RUNNER], input=script, text=True,
                         capture_output=True, timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout)


def _season_vars_of(page: str) -> dict:
    return json.loads(re.search(r"const SEASON_VARS = (\{.*?\});",
                                page).group(1))


# -------------------------------------------------------------------- DA-04

def test_a_store_or_delete_lands_with_its_notice_in_view(isolated):  # noqa: F811
    # dates on Sundays: one warning (the days moved to Saturdays)
    raw = ("date,target_group,value,population\n"
           + "\n".join(f"2022-01-{2 + 7 * i:02d},Pediatric,{40 + i},1752418"
                       for i in range(4))).encode()
    r = upload(raw, "Sundays")
    assert r.status_code == 303
    # #main, where the flash is: a redirect without a fragment would keep
    # the form's own #datasets and land below the notice
    assert r.headers["location"].startswith("/data?source=")
    assert r.headers["location"].endswith("#main")
    flash = ui_state._status.get("flash", "")
    assert flash.startswith("Stored Sundays:")
    assert flash.endswith(" 2 warnings.") and "warning(s)" not in flash
    ds_id = r.headers["location"].split("source=")[1].split("#")[0]
    r = client.post(f"/data/datasets/{ds_id}/delete", data={"confirm": "Sundays"},
                    follow_redirects=False)
    assert r.status_code == 303, r.text[:200]
    assert r.headers["location"] == "/data#main", r.headers["location"]
    assert "Deleted Sundays: " in ui_state._status.get("flash", "")


# -------------------------------------------------------------------- DA-05

def test_missing_comparators_name_their_remedy_and_make_update_data_primary(archive, monkeypatch):  # noqa: F811
    html = client.get("/data").text
    assert 'id="comp-missing"' in html
    assert ("baseline, ensemble missing</span></span> "
            '<span class="hint">Update data adds them.</span>') in html
    assert 'class="gold" id="hub-pull"' in html
    assert 'class="quiet" id="hub-check"' in html
    # a check's JSON answer counts them as "behind" too
    monkeypatch.setattr(data_mod, "check_freshness",
                        lambda: data_mod.Freshness(local_latest=V2, remote_latest=V2,
                                                   behind=0, is_fresh=True,
                                                   detail="up to date"))
    r = client.post("/freshness", headers={"accept": "application/json"})
    assert r.json()["behind"] is True

    # a pull that adds the folders says so
    def fake_pull():
        for _name, sub in data_mod.COMPARATORS:
            (data_mod.HUB / sub).mkdir(parents=True, exist_ok=True)
        return True, "Updated"
    monkeypatch.setattr(data_mod, "pull_hub", fake_pull)
    monkeypatch.setattr(ui_data, "_live_values", lambda: None)
    ok, msg = ui_data._pull()
    assert ok and "baseline and ensemble comparators added" in msg
    html = client.get("/data").text
    assert 'id="comp-ok"' in html and 'class="quiet" id="hub-pull"' in html


# -------------------------------------------------------------------- DA-07

def test_the_browser_shows_the_live_file_when_the_archive_lags(archive):  # noqa: F811
    live = archive / "target-data"
    live.mkdir()
    # the live file holds a week the archive (through V2) does not
    (live / "target-hospital-admissions.csv").write_text(
        "date,location,location_name,value,weekly_rate\n"
        + "\n".join(f"{d},{f},{n},{v},0.0" for d, f, n, v in [
            ("2098-01-10", "39", "Ohio", 190), ("2098-01-17", "39", "Ohio", 210),
            ("2098-01-10", "US", "US", 1600), ("2098-01-17", "US", "US", 1700)])
        + "\n")
    from app.ui import shared as ui_shared
    ui_shared._invalidate_scans()
    html = client.get("/data?loc=Ohio").text
    # the live week leads the Vintage list, named for what it is, selected
    assert ('<option selected value="2098-01-17">2098-01-17 (target-data, '
            'not archived)</option>') in html
    assert 'id="vb-live"' in html and "2098-01-17</span>" in html
    assert "const VLIVE = true" in html
    # the archive's own tiles still describe the archive
    assert f'id="latest-vintage"><span class="dt-nw">{V2}</span>' in html
    # an archived vintage still opens on request
    html = client.get(f"/data?vintage={V2}&loc=Ohio").text
    assert f"<option selected>{V2}</option>" in html
    assert "const VLIVE = false" in html


# -------------------------------------------------------------------- DA-19

def test_a_season_keeps_one_colour_on_the_page():
    # one map by season label: the newest --gold, older ones the season
    # tokens by rank (test_season_palette pins the chart's rule)
    assert ui_data._season_vars(["2023-24", "2025-26", "2024-25"]) == {
        "2025-26": "--gold", "2024-25": "--season-1", "2023-24": "--season-2"}
    ctx = {"vintage_rows": [{"season": "2025-26"}, {"season": "2024-25"}]}
    # the chart's older season continues the strip's order
    ui_data._set_season_vars(ctx, ["2023-24", "2024-25", "2025-26"])
    assert [r["var"] for r in ctx["vintage_rows"]] == ["--gold", "--season-1"]
    assert ctx["season_vars"]["2023-24"] == "--season-2"
    assert ui_data._season_label("2024-01-06") == "2023-24"
    assert ui_data._season_label("2024-08-03") == "2024-25"


def test_the_strip_and_the_chart_read_the_same_map(archive):  # noqa: F811
    page = client.get("/data").text
    strip = page.split('class="archive-strip"', 1)[1].split("</svg>", 1)[0]
    assert 'style="fill:var(--gold)"' in strip
    sv = page.split("const SEASON_VARS = ", 1)[1].split(";", 1)[0]
    assert '"2097-98": "--gold"' in sv
    assert "SEASON_VARS[k]&&css(SEASON_VARS[k])" in page


#: the hub as the review saw it: one vintage a season, 2021-22 to 2026-27,
#: each holding Ohio's weeks up to its own
HUB_WEEKS = ("2021-11-06", "2022-11-05", "2023-11-04", "2024-11-02",
             "2025-11-01", "2026-10-31")
#: grouped_bytes' weeks (stored()): 2019-08-03 to 2024-02-24
DS_SEASONS = ["2019-20", "2020-21", "2021-22", "2022-23", "2023-24"]


@pytest.fixture()
def seasons_hub(tmp_path, monkeypatch):
    root = tmp_path / "hub"
    root.mkdir()
    for i, v in enumerate(HUB_WEEKS):
        _write_vintage(root, v, [(w, "39", "Ohio", 100 + j)
                                 for j, w in enumerate(HUB_WEEKS[:i + 1])])
    (root / "auxiliary-data").mkdir()
    monkeypatch.setattr(data_mod, "ARCHIVE", root)
    monkeypatch.setattr(data_mod, "HUB", root)
    monkeypatch.setattr(data_mod, "shipped_weeks", lambda: [])
    ui_shared._invalidate_scans()
    yield root
    ui_shared._invalidate_scans()


def test_a_datasets_page_gives_each_of_its_seasons_its_own_colour(seasons_hub):
    """Review of #82 (S3): a dataset's page kept the hub's map, so a
    dataset from 2019-20 to 2023-24 drew 2019-20 and 2022-23 in one colour
    and 2020-21 and 2023-24 in another, its newest season not gold."""
    hub = client.get("/data").text
    assert _season_vars_of(hub)["2026-27"] == "--gold"
    ds = stored()
    page = client.get(f"/data?source={ds.id}").text
    # the dataset's own seasons: the newest gold, one token each
    sv = _season_vars_of(page)
    assert sorted(sv) == DS_SEASONS
    assert sv["2023-24"] == "--gold"
    assert len(set(sv.values())) == len(DS_SEASONS)
    # the hub's strip above is another source's seasons: its plain
    # palette, no token that means another season in the chart
    strip = page.split('class="archive-strip"', 1)[1].split("</svg>", 1)[0]
    assert strip.count("<circle") == len(HUB_WEEKS) and "var(--" not in strip
    # as the page's own script draws them, season over season
    colour = {t["name"]: t["color"] for t in _drawn(page)[1]["traces"]}
    assert sorted(colour) == DS_SEASONS
    assert colour["2023-24"] == "--gold"
    assert len(set(colour.values())) == len(DS_SEASONS)
    # the hub's page keeps its one map: the strip's colour is the chart's
    hub_drawn = {t["name"]: t["color"] for t in _drawn(hub)[1]["traces"]}
    assert len(hub_drawn) == len(HUB_WEEKS)
    strip = hub.split('class="archive-strip"', 1)[1].split("</svg>", 1)[0]
    for season, token in hub_drawn.items():
        row = strip.split(f">{season}</text>", 1)[1].split("</text>", 1)[0]
        assert f"fill:var({token})" in row, season


# -------------------------------------------------------------------- DA-22

def test_a_pulls_up_to_date_is_dropped_after_its_minute(archive, monkeypatch):  # noqa: F811
    """Review of #71 (S3): press Update data and leave before the answer;
    the next visit, hours later, said "up to date" though nothing was
    checked then. The pull's answer now waits a minute at most."""
    monkeypatch.setattr(data_mod, "pull_hub", lambda: (True, "pulled"))
    monkeypatch.setattr(ui_data, "_live_values", lambda: None)
    monkeypatch.setattr(ui_data, "_pulled", {})
    now = [5000.0]
    monkeypatch.setattr(ui_data, "_clock", lambda: now[0])

    def pill():
        page = client.get("/data").text
        return page.split('id="hub-pill"', 1)[1].split("</span></span>")[0]

    def pull():
        r = client.post("/data/pull", headers={"Accept": "application/json"})
        assert r.json()["ok"] is True

    # the page the pull reloads, within the minute: up to date, once
    pull()
    now[0] += 5
    assert pill().endswith('<span class="uk-badge-t">up to date')
    assert pill().endswith('<span class="uk-badge-t">not checked')
    # nobody came for it: a visit after the minute has not checked
    pull()
    now[0] += ui_data.PULLED_TTL_S + 1
    assert pill().endswith('<span class="uk-badge-t">not checked')
    assert ui_data._pulled == {}
    # and the next pull's own answer is not held back by the old one
    pull()
    assert pill().endswith('<span class="uk-badge-t">up to date')


# -------------------------------------------------------------------- DA-23

def test_a_snapshot_datasets_chart_title_names_the_snapshot():
    """Both chart titles of a vintage-true dataset name the snapshot
    shown; final data has no snapshot to name. Read off the served page
    as its own script draws it."""
    snap = D.ingest(as_of_csv(), "Snapshots")
    assert snap.vintage_true
    page = client.get(f"/data?source={snap.id}&vintage={ASOFS[2]}").text
    assert "const VDSVT = true;" in page
    assert f"const VVINTAGE = {json.dumps(ASOFS[2])};" in page
    # its seasons' colours are its own whichever snapshot is shown (the
    # fixture's weeks run from 2023-01-07)
    assert _season_vars_of(page) == {"2023-24": "--gold",
                                     "2022-23": "--season-1"}
    raw, season = _drawn(page)
    assert raw["title"].endswith(f" · Snapshots · as of {ASOFS[2]}")
    assert season["title"].endswith(
        f" · Snapshots: season over season, as of {ASOFS[2]}")
    # the newest snapshot by default, named the same way
    raw, _ = _drawn(client.get(f"/data?source={snap.id}").text)
    assert raw["title"].endswith(f" · as of {ASOFS[-1]}")
    # final data: no snapshot, so no "as of"
    ds = stored()
    page = client.get(f"/data?source={ds.id}").text
    assert "const VDSVT = false;" in page
    raw, season = _drawn(page)
    assert raw["title"].endswith(f" · {ds.name}")
    assert season["title"].endswith(f" · {ds.name}: season over season")
