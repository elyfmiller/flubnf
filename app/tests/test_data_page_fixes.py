"""The Data page (G24): a store or delete notice in view, the comparators'
remedy and primary action, the live target file in the vintage browser,
one colour per season on the page, and a snapshot's title."""
from pathlib import Path

from app.core import data as data_mod                # noqa: E402
from app.ui import state as ui_state                 # noqa: E402
from app.ui.routes import data as ui_data            # noqa: E402
from test_data_view import _write_vintage, archive, client, V1, V2  # noqa: E402,F401
from test_datasets_ui import isolated, upload        # noqa: E402,F401

DATA_T = (Path(__file__).resolve().parents[1] / "ui" / "templates"
          / "data.html").read_text(encoding="utf-8")


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


# -------------------------------------------------------------------- DA-23

def test_a_snapshot_datasets_chart_title_names_the_snapshot():
    assert "const VDSVT = {{ (ds.vintage_true if ds else false) | tojson }};" in DATA_T
    assert "VLOC+' · '+VDS+(VDSVT ? ' · as of '+VVINTAGE : '')" in DATA_T
    assert "': season over season'+(VDSVT ? ', as of '+VVINTAGE : '')" in DATA_T
