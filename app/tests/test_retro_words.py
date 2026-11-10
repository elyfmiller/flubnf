"""The Retrospective's words and marks (bug hunt 2026-10-25, G28).

  * The zero-anchor refusal names the Run form's own control.
  * The FluSight hub tab has one explainer, the page's; the season rows'
    badges and figures carry no tips of their own (an error keeps its
    text). The Your data tab has one, its replays' heading, and the
    replay page one, its Scores heading.
  * Import refusals name the file the student chose, and a folder as a
    folder.
  * Deleting an imported run says where it came from.
  * Refusals and notices say settings, scopes and archives in words: no
    keys, digests or folder names.
  * docs/RETROSPECTIVES.md puts Import a replay on its own card.
"""
import json
from pathlib import Path

import pytest

from app.core import replay_bundle, retro_settings
from app.ui import state as ui_state
from app.ui.routes import retro as ui_retro
from test_datasets_ui import client, isolated, stored        # noqa: F401
from test_retro_archive import SEASON, _roots                 # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "app" / "ui" / "templates"


def _flash():
    return (ui_state._status.get("flash") or "",
            ui_state._status.get("flash_detail") or "")


# ------------------------------------------ RE-16: the form's own label

def test_the_zero_anchor_refusal_names_the_forms_control(tmp_path,
                                                         monkeypatch):
    _roots(tmp_path, monkeypatch)
    ui_state._status.pop("flash", None)
    client.post("/retro/run", data={"season": SEASON, "engine": "analogue",
                                    "locations": "custom",
                                    "custom_locations": "Ohio"},
                follow_redirects=False)
    msg, detail = _flash()
    assert msg.startswith("Not started: choose what the Groundhog does")
    assert detail == ("Set Groundhog when the newest week reads 0: abstain, "
                      "level, extend or blend.")


# --------------------------------------------------- RE-18, RE-19: marks

def test_the_season_rows_carry_no_tips_of_their_own():
    page = (UI / "retro.html").read_text(encoding="utf-8")
    for gone in ('call tips.stat("Wall time"', '"rt-resume-"', '"rt-arch-"',
                 '"rt-eta-"',
                 "relWIS vs FluSight baseline, ratio of sums",
                 "Run resumes it from the last completed week."):
        assert gone not in page, gone
    # their words are the page's one explainer
    assert "relWIS: the summed WIS over the FluSight baseline's" in page
    assert '<span class="rbasis uk-sr">' in page          # the screen reader's
    # an error's text and the seal's name stay with their badges: each is
    # said nowhere else
    assert 'tips.badge("error", "error", s.status' in page
    assert 'tips.badge("info", "sealed", s.seal_label' in page


def test_the_your_data_tab_has_one_explainer(tmp_path, monkeypatch):
    ds = stored()
    page = client.get(f"/retro?dataset={ds.id}").text
    for gone in ('id="tip-rt-page"', 'id="tip-dsr-src"', 'id="tip-dsr-groups"',
                 'id="tip-dsr-engine"', 'id="tip-dsr-fs"', 'id="tip-dsr-kind"'):
        assert gone not in page, gone
    tip = page.split('id="tip-rt-ds-about"', 1)[1].split("</span></span>")[0]
    assert "a national group is scored beside the others" in tip
    assert "relWIS below 1 beats that baseline." in tip
    assert '"dsr-rel-"' not in (UI / "_dataset_replay.html").read_text(
        encoding="utf-8")
    assert "Add FluSurv-NET donors (US flu hospitalizations only)" in page
    rd = (UI / "retro_dataset.html").read_text(encoding="utf-8")
    for gone in ('"rd-rel"', '"rd-beside"', '"rd-h"', "rd-abst-\" ~ m) }}\n"):
        assert gone not in rd, gone
    assert "Horizon 0 is the week after the forecast date." in rd


# ------------------------------------- RE-20: the chosen file, a folder

def test_an_import_refusal_names_the_chosen_file_and_a_folder(tmp_path,
                                                             monkeypatch):
    _roots(tmp_path, monkeypatch)
    ui_state._status.pop("flash", None)
    client.post("/retro/import",
                files={"file": ("notzip.zip", b"not a zip", "application/zip")},
                follow_redirects=False)
    assert _flash()[0] == "Not imported: notzip.zip is not a zip file."
    ui_state._status.pop("flash", None)
    client.post("/retro/import", data={"path": str(tmp_path)},
                follow_redirects=False)
    assert _flash()[0] == (f"Not imported: {tmp_path} is a folder, not a "
                           "bundle.")
    with pytest.raises(replay_bundle.BundleError, match="^a.zip is not a"):
        replay_bundle.inspect_bundle(_write(tmp_path / "x.bin"), "a.zip")


def _write(p: Path) -> Path:
    p.write_bytes(b"not a zip")
    return p


# --------------------------------------- RE-21: an imported run's delete

def test_deleting_an_imported_run_says_where_it_came_from(tmp_path,
                                                          monkeypatch):
    rr = _roots(tmp_path, monkeypatch)
    arch = rr / "2096-97__archived_20261025T191112Z"
    arch.mkdir()
    (arch / replay_bundle.IMPORTED_MARK).write_text(json.dumps(
        {"from": "vm", "imported_at": "2026-10-25T19:20:00Z"}))
    ui_state._status.pop("flash", None)
    client.post("/retro/2096-97/archive/20261025T191112Z/delete",
                data={"confirm": "2096-97"}, follow_redirects=False)
    assert _flash()[0].startswith("Deleted the 2096-97 run imported from vm "
                                  "on 2026-10-25: ")
    page = (UI / "retro.html").read_text(encoding="utf-8")
    assert "(d.imported?d.season+' run '+d.when" in page


# --------------------------------------------- RE-22: words, not keys

def test_refusals_say_settings_scopes_and_archives_in_words():
    words = ui_retro._settings_words
    assert words({"groundhog.zero_anchor": "level"}) == (
        "Groundhog when the newest week reads 0: level")
    assert words({"groundhog.zero_anchor": "abstain", "oracle.w": 0.25}) == (
        "Groundhog when the newest week reads 0: abstain, Oracle blend "
        "weight 0.25 (default 0.5)")
    assert words({}) == "the default settings"
    change = retro_settings.location_scope_change
    assert change(["Ohio", "Utah"], ["Ohio", "Utah", "US"]) == (
        "replayed without US; this run adds it")
    assert change(["Ohio", "Utah", "US"], ["Ohio", "Utah"]) == (
        "replayed with US; this run leaves US out")
    assert change(["Ohio", "Utah"], ["Ohio"]) == (
        "replayed over 2 locations; this run asks for 1, a different list")
    src = (ROOT / "app/ui/routes/retro.py").read_text(encoding="utf-8")
    assert "(set aside \"\n" in src or "(set aside " in src
    assert "{dst.name}" not in src


# ------------------------------------------------------- RE-27: the doc

def test_the_doc_puts_import_on_its_own_card():
    doc = (ROOT / "docs" / "RETROSPECTIVES.md").read_text(encoding="utf-8")
    assert "(Settings card)" not in doc
    assert "(its own card under\nSettings)" in doc
