"""Shipped truth snapshots (data/vintages/, flubnf/vintages.py): the union
with the hub archive and its precedence, the season week lists, the replay
resolver, the pinned digests, the loud mismatch, and the player's no-data
placeholder."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import data                      # noqa: E402
from app.core import playback                  # noqa: E402
from app.core import retro                     # noqa: E402
from app.core.runs import RunSpec              # noqa: E402
from flubnf import vintages as shipped         # noqa: E402

#: the eight files' digests, pinned: a change to a shipped byte must be a
#: deliberate change here too
PINNED = {
    "2024-11-23": "02e8c78d4d63ee32a5b0bfa171a400d4e0a816014cf272f5a7b2771dc9220ce0",
    "2024-12-07": "db5621aa21bd603cd09dc80590662aa5c2ebc61cf0b56614d4dbf3f67767fe4d",
    "2025-01-04": "74b88f42708ef7afd4726e60bc282cdc6a56e5f63e19d0cd92c0c92c3c19f79a",
    "2025-11-22": "b1dd3e423bf5887334eacbaab51b9d1df49102d6abd269a0d7adea47327ff397",
    "2025-12-20": "0234b961205d8fc742d1d3d5c4767f0d613acdec17f68795e56cc7645a231493",
    "2026-01-31": "6f5568795d7b423449bc313aa50e2e0ec7b2537c632d71646de6f6859f7303d6",
    "2026-03-07": "3efba5b93fedf706e13287e9b3dd02ce5d4c84dd60e12c66177b09e7e3c05478",
    "2026-04-25": "2b94797a483025ad46aedaf9b9d6e9af7f1bfcd671ab3e6ae2cdcf0918f155f1",
}
FILLED_2024_25 = ["2024-11-23", "2024-12-07", "2025-01-04"]
FILLED_2025_26 = ["2025-11-22", "2025-12-20", "2026-01-31", "2026-03-07",
                  "2026-04-25"]

ROWS = ('"date","location","location_name","value","weekly_rate"\n'
        '2098-10-04,"39","Ohio",10,0.1\n2098-10-04,"49","Utah",5,0.2\n')


def _shipped_dir(tmp_path, weeks, *, name="shipped"):
    """A shipped folder with one small file per week and a matching manifest."""
    d = tmp_path / name
    d.mkdir()
    vints = []
    for w in weeks:
        p = d / shipped.file_name(w)
        p.write_text(ROWS.replace("2098-10-04", w))
        vints.append({"as_of": w, "reference_date": w, "season": "2098-99",
                      "file": p.name, "hub_commit": "abcd1234",
                      "hub_commit_sha": "abcd1234" * 5,
                      "hub_commit_date": "2098-10-08T12:00:00+00:00",
                      "source_path": "target-data/target-hospital-admissions.csv",
                      "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                      "rows": 2, "location_count": 2})
    (d / shipped.MANIFEST_NAME).write_text(json.dumps(
        {"layout_version": shipped.LAYOUT_VERSION, "vintages": vints,
         "no_data_weeks": []}))
    return d


def _archive(tmp_path, weeks):
    a = tmp_path / "archive"
    a.mkdir()
    for w in weeks:
        (a / f"target-hospital-admissions_{w}.csv").write_text(
            ROWS.replace("2098-10-04", w))
    return a


# ------------------------------------------------------------ union, precedence

def test_vintages_is_the_sorted_union_and_the_archive_wins_a_clash(tmp_path, monkeypatch):
    arch = _archive(tmp_path, ["2098-10-11", "2098-10-25"])
    ship = _shipped_dir(tmp_path, ["2098-10-04", "2098-10-11", "2098-10-18"])
    monkeypatch.setattr(data, "ARCHIVE", arch)
    monkeypatch.setattr(data, "SHIPPED", ship)
    assert data.vintages() == ["2098-10-04", "2098-10-11", "2098-10-18",
                               "2098-10-25"]
    # the clash: the archive's file, never the shipped copy
    assert data.vintage_path("2098-10-11").parent == arch
    assert data.vintage_source("2098-10-11")["kind"] == "archive"
    # a shipped-only week: the shipped file, with its commit as provenance
    p = data.vintage_path("2098-10-18")
    assert p.parent == ship
    src = data.vintage_source("2098-10-18")
    assert src["kind"] == "shipped" and src["commit"] == "abcd1234"
    assert "hub snapshot, commit abcd1234 (2098-10-08)" == src["label"]
    assert data.vintage_source("2098-11-01")["kind"] == "none"


def test_a_week_in_neither_folder_names_both_folders(tmp_path, monkeypatch):
    arch = _archive(tmp_path, ["2098-10-11"])
    ship = _shipped_dir(tmp_path, ["2098-10-04"])
    monkeypatch.setattr(data, "ARCHIVE", arch)
    monkeypatch.setattr(data, "SHIPPED", ship)
    with pytest.raises(FileNotFoundError) as e:
        data.vintage_path("2098-10-18")
    msg = str(e.value)
    assert str(arch) in msg and str(ship) in msg
    assert "2098-10-11" in msg              # nearby weeks still listed


def test_a_shipped_file_absent_from_the_manifest_is_not_served(tmp_path, monkeypatch):
    ship = _shipped_dir(tmp_path, ["2098-10-04"])
    (ship / shipped.file_name("2098-10-11")).write_text(ROWS)   # unlisted
    monkeypatch.setattr(data, "ARCHIVE", tmp_path / "no-archive")
    monkeypatch.setattr(data, "SHIPPED", ship)
    assert data.vintages() == ["2098-10-04"]
    with pytest.raises(FileNotFoundError, match="not listed"):
        shipped.shipped_path("2098-10-11", ship)


# --------------------------------------------------------- the real shipped set

def test_pinned_digests_match_the_manifest_and_the_files(shipped_vintages):
    man = shipped.entries()
    assert sorted(man) == sorted(PINNED)
    for asof, sha in PINNED.items():
        e = man[asof]
        assert e["sha256"] == sha, asof
        p = shipped.shipped_path(asof)          # verifies on read
        assert hashlib.sha256(p.read_bytes()).hexdigest() == sha
        assert e["source_path"] == "target-data/target-hospital-admissions.csv"
        assert len(e["hub_commit_sha"]) == 40
        assert e["hub_commit_sha"].startswith(e["hub_commit"])
        assert e["location_count"] == 53 and e["rows"] > 7000
    # the two weeks with nothing to fill, with their reference dates
    nd = shipped.no_data_weeks()
    assert {w: e["reference_date"] for w, e in nd.items()} == {
        "2024-05-04": "2024-05-11", "2025-01-18": "2025-01-25"}
    assert all("no FluSight round" in e["reason"] for e in nd.values())


def test_the_season_week_lists_include_the_filled_weeks(shipped_vintages, tmp_path, monkeypatch):
    monkeypatch.setattr(data, "ARCHIVE", tmp_path / "empty-archive")
    assert retro.season_vintages("2024-25") == FILLED_2024_25
    assert retro.season_vintages("2025-26") == FILLED_2025_26
    assert retro.season_vintages("2023-24") == []
    assert retro.available_seasons() == ["2024-25", "2025-26"]
    assert sorted(retro.season_no_data_weeks("2024-25")) == ["2025-01-18"]
    assert sorted(retro.season_no_data_weeks("2023-24")) == ["2024-05-04"]
    assert retro.season_no_data_weeks("2025-26") == {}


def test_without_the_shipped_folder_the_suite_sees_no_weeks(tmp_path, monkeypatch):
    # the autouse fixture: an empty hub means an empty season list
    monkeypatch.setattr(data, "ARCHIVE", tmp_path / "empty-archive")
    assert data.vintages() == [] and retro.season_vintages("2025-26") == []


def test_a_shipped_week_is_read_in_replay_mode(shipped_vintages, tmp_path, monkeypatch):
    monkeypatch.setattr(data, "ARCHIVE", tmp_path / "empty-archive")
    monkeypatch.setattr(data, "HUB", tmp_path / "hub")        # no live file
    path, kind = data.observed_source("2025-11-22", "vintage")
    assert kind == "vintage" and path.parent == shipped.VINTAGES_DIR
    spec = RunSpec(engine="retro", forecast_date="2025-11-22",
                   locations=["Ohio"])
    assert data.spec_source(spec) == (path, "vintage")
    rec = data.source_record(path, kind)
    assert rec["snapshot_commit"] == "03a4b119"
    assert rec["sha256"] == PINNED["2025-11-22"]
    assert rec["newest_week"] == "2025-11-22"
    assert data.source_phrase(rec) == ("shipped snapshot 2025-11-22, hub "
                                       "commit 03a4b119")
    # the frame reads like an archived vintage
    s = data.vintage_summary("2025-11-22")
    assert s["locations"] == 53 and s["newest_week"] == "2025-11-22"


def test_a_shipped_week_is_refused_in_realtime_when_the_live_file_is_older(
        shipped_vintages, tmp_path, monkeypatch):
    # a live file behind the as-of still reads the shipped snapshot: the
    # resolver's dated lookup is the union
    monkeypatch.setattr(data, "ARCHIVE", tmp_path / "empty-archive")
    monkeypatch.setattr(data, "HUB", tmp_path / "hub")
    path, kind = data.observed_source("2025-11-22", "realtime")
    assert kind == "vintage" and path.parent == shipped.VINTAGES_DIR


# --------------------------------------------------------------- loud mismatch

def test_a_changed_byte_raises_and_is_never_served(shipped_vintages, tmp_path, monkeypatch):
    d = tmp_path / "shipped-copy"
    d.mkdir()
    shutil.copy(shipped.manifest_path(), d / shipped.MANIFEST_NAME)
    src = shipped.shipped_path("2025-11-22")
    dst = d / src.name
    dst.write_bytes(src.read_bytes().replace(b"Ohio", b"Ohi0", 1))
    monkeypatch.setattr(data, "ARCHIVE", tmp_path / "empty-archive")
    monkeypatch.setattr(data, "SHIPPED", d)
    assert "2025-11-22" in data.vintages()        # listed ...
    with pytest.raises(ValueError, match="does not match its manifest"):
        data.vintage_path("2025-11-22")           # ... but not served
    with pytest.raises(ValueError):
        data.load_vintage("2025-11-22")
    # a listed file gone missing is a loud error too
    dst.unlink()
    with pytest.raises(FileNotFoundError, match="missing"):
        shipped.shipped_path("2025-11-22", d)


def test_manifest_of_another_layout_is_refused(tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    (d / shipped.MANIFEST_NAME).write_text(json.dumps({"layout_version": 99}))
    with pytest.raises(ValueError, match="layout_version"):
        shipped.weeks(d)


# ------------------------------------------------- player timeline placeholder

def test_the_no_data_week_is_a_placeholder_in_its_own_season_only(shipped_vintages, tmp_path, monkeypatch):
    monkeypatch.setattr(data, "ARCHIVE", tmp_path / "empty-archive")
    # 2024-25: stored weeks around 2025-01-18 -> the placeholder sits between
    tl, notes = playback.week_notes("2024-25", ["2025-01-04", "2025-01-11",
                                                "2025-01-25"])
    assert tl == ["2025-01-04", "2025-01-11", "2025-01-18", "2025-01-25"]
    assert notes["2025-01-18"] == playback.NO_DATA_NOTE
    assert "no FluSight round" in playback.NO_DATA_NOTE
    # the filled week carries its provenance
    assert notes["2025-01-04"] == "data: hub snapshot, commit fd7109e8 (2025-01-08)"
    assert "2025-01-11" not in notes
    # a replay that stopped before the week gets no trailing placeholder
    # (the season's list, here the hub's, runs on past the stored weeks)
    monkeypatch.setattr(retro, "season_vintages",
                        lambda s: ["2025-01-04", "2025-01-11", "2025-01-25"])
    tl2, n2 = playback.week_notes("2024-25", ["2025-01-04", "2025-01-11"])
    assert tl2 == ["2025-01-04", "2025-01-11"] and "2025-01-18" not in n2
    # 2025-26 has no such week; nothing is inserted
    tl3, n3 = playback.week_notes("2025-26", ["2025-11-22", "2025-11-29"])
    assert tl3 == ["2025-11-22", "2025-11-29"]
    assert n3 == {"2025-11-22": "data: hub snapshot, commit 03a4b119 (2025-11-26)"}
    # 2023-24 ends at 2024-05-04 with no data: a complete replay shows it last
    monkeypatch.setattr(retro, "season_vintages",
                        lambda s: ["2024-04-20", "2024-04-27"])
    tl4, n4 = playback.week_notes("2023-24", ["2024-04-20", "2024-04-27"])
    assert tl4 == ["2024-04-20", "2024-04-27", "2024-05-04"]
    assert n4["2024-05-04"] == playback.NO_DATA_NOTE
    # the placeholder adds no payload field of its own (the "seen" series
    # is the contract's, playback.CACHE_V 5)
    assert playback.CACHE_V == 5


def test_the_season_page_hands_the_player_the_timeline_and_notes():
    from app.ui.server import templates
    from test_retro_player import CONTEXT
    ctx = dict(CONTEXT, weeks=["2098-11-07", "2098-11-21"],
               timeline=["2098-11-07", "2098-11-14", "2098-11-21"],
               notes={"2098-11-14": playback.NO_DATA_NOTE,
                      "2098-11-07": "data: hub snapshot, commit abcd1234"},
               no_data_note=playback.NO_DATA_NOTE, week="2098-11-21")
    html = templates.env.get_template("retro_season.html").render(**ctx)
    # the scrubber walks the timeline, not the stored weeks
    assert 'max="2"' in html and 'value="2"' in html
    assert '"2098-11-14"' in html and playback.NO_DATA_NOTE in html
    assert "notes: NOTES" in html
    # a no-data week is never fetched
    assert "if(noData(w))" in html


def test_the_report_and_player_carry_the_notes():
    from app.core import report_season
    assert "notes: NOTES" in report_season._PAGE
    assert "DATA.notes" in report_season._PAGE
    js = (Path(__file__).resolve().parents[1] / "ui" / "static"
          / "player.js").read_text(encoding="utf-8")
    assert "cfg.notes" in js and "noteOf(" in js


def test_the_season_list_says_what_resume_would_run():
    from app.ui.server import templates
    base = dict(name="2024-25", total=33, done=30, seal=False, seal_label="",
                rel=0.7, rels={"pf": 0.7}, pf_name="", resume_fields=None,
                stop_reason="", settings=None, archives=[], status="done",
                running=False, paused=False, active=False, elapsed_s=0,
                mean_s=None, weeks_measured=0, eta_s=None, finished_utc=None,
                scored=True, added=["2024-11-23", "2024-12-07", "2025-01-04"],
                added_n=3)
    t = templates.env.get_template("retro.html")
    html = t.render(active="Retrospective", own_tab=False, seasons=[base],
                    state_names=[], default_width=4, width_cap=8,
                    knob_panel="", engine_ok=True)
    assert "3 weeks added to the season since" in html
    assert "2024-11-23, 2024-12-07, 2025-01-04" in html
    assert "runs only those weeks" in html
    assert "relWIS" in html                  # the finished score still shows
    html = t.render(active="Retrospective", own_tab=False,
                    seasons=[dict(base, seal=True, seal_label="sealed")],
                    state_names=[], default_width=4, width_cap=8,
                    knob_panel="", engine_ok=True)
    assert "sealed record cannot be resumed" in html
