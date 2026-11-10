"""The bug-fix review's leftovers (2026-11-10).

  * A wrapped segmented switch tucks every choice's left divider under
    the outline at a row's start: the element rule keeps the -1px margin
    the wrap rule gives (it is the more specific of the two).
  * Home's map comment names the legend's gray as the legend words it.
  * With no hub folder, Update data is never the Data page's primary
    action (a pull is refused then), nor does a check's answer make it so.
  * Retrospective's archive mode and a replay import's replace refuse a
    protected folder in words, as the other protected-folder refusals do,
    and move or delete nothing.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import data as data_mod                          # noqa: E402
from app.ui import shared as ui_shared                         # noqa: E402
from app.ui import state as ui_state                           # noqa: E402
from test_data_view import archive, client                     # noqa: E402,F401
from test_state_folder_protect import state                    # noqa: E402,F401

UI = Path(__file__).resolve().parents[1] / "ui"


# ------------------------------------------- the segmented switch's divider

def _rule(css: str, selector: str) -> str:
    """The declarations of the one rule whose selector list is `selector`."""
    m = re.search(re.escape(selector) + r"\{([^}]*)\}", css)
    assert m, selector
    return m.group(1)


def test_a_wrapped_segmented_switch_tucks_each_divider_under_the_outline():
    css = (UI / "static" / "ui-kit.css").read_text(encoding="utf-8")
    # the wrap rule pulls each choice 1px left, under the outline ...
    assert "margin-left:-1px" in _rule(css, ".uk-seg > *")
    # ... and the element rule, more specific, keeps it (margin:0 there
    # reset it, so a second row started with a double divider)
    own = _rule(css, ".uk-seg > button,.uk-seg > a,.uk-seg > span")
    margin = re.search(r"(?:^|;|\s)margin:([^;]*)", own).group(1).split()
    assert margin == ["0", "0", "0", "-1px"], margin


# ------------------------------------------------ Home's legend comment

def test_the_maps_comment_names_the_legends_gray_as_the_legend_does():
    from app.ui.routes import home as H
    src = (UI / "templates" / "home.html").read_text(encoding="utf-8")
    note = src.split("{# the rest of the map", 1)[1].split("#}", 1)[0]
    note = " ".join(note.split())
    # every word the legend can give the gray (routes/home._gray_words)
    said = {H._gray_words([], None, None)}
    for scope in (set(), {"39"}):
        said.add(H._gray_words([{}], scope, set()))
    assert said <= {"no data", "not in this run", "no forecast",
                    "not in this run or no forecast"}
    for words in ("no data", "not in this run", "no forecast",
                  "not in this run or no forecast"):
        assert f'"{words}"' in note, words


# ---------------------------------------- the Data page with no hub folder

def test_with_no_hub_folder_update_data_is_never_the_primary(
        archive, monkeypatch, hub_check_real):  # noqa: F811
    monkeypatch.setattr(data_mod, "HUB", archive / "nohub")
    ui_shared._invalidate_scans()
    assert data_mod.hub_missing(data=False)
    html = client.get("/data").text
    # the comparators are missing too, which alone made the pull primary
    assert 'id="comp-missing"' in html
    assert 'class="quiet" id="hub-pull"' in html
    assert 'class="gold" id="hub-check"' in html
    # a check's answer does not make it primary either
    monkeypatch.setattr(data_mod, "check_freshness",
                        lambda: data_mod.Freshness(local_latest=None,
                                                   remote_latest=None,
                                                   behind=0, is_fresh=False,
                                                   detail="no hub"))
    r = client.post("/freshness", headers={"accept": "application/json"})
    assert r.json()["behind"] is False


# ------------------------------------------------ protected folders

def test_archiving_a_protected_season_is_refused_and_moves_nothing(
        state, monkeypatch, request):  # noqa: F811
    from app.ui import retro_seasons
    from app.ui.routes import retro as ui_retro
    from test_retro_archive import SEASON, _roots, _season_tree, _tree_snapshot
    kept = [(d, type(d)(d)) for d in (retro_seasons._retro_status,
                                      retro_seasons._retro_claim_at,
                                      retro_seasons._retro_stop)]
    request.addfinalizer(lambda: [(d.clear(), d.update(v)) for d, v in kept])
    rr = _roots(state, monkeypatch)
    live = _season_tree(rr, SEASON)
    before = _tree_snapshot(live)
    started = []
    monkeypatch.setattr(ui_retro, "_retro_bg",
                        lambda *a, **k: started.append(a[0]))
    archive_form = {"season": SEASON, "mode": "archive",
                    "engine": "analogue", "locations": "panel6",
                    "knob.groundhog.zero_anchor": "abstain"}
    monkeypatch.setenv("FLUBNF_PROTECT_ROOTS", str(live))
    ui_state._status.pop("flash", None)
    client.post("/retro/run", data=archive_form, follow_redirects=False)
    assert ui_state._status.get("flash") == (
        f"Not started: the {SEASON} results are in a protected folder, "
        "which the console never moves.")
    assert ui_state._status.get("flash_detail") == "Nothing was moved."
    assert started == [] and _tree_snapshot(live) == before
    assert [d.name for d in rr.iterdir() if "__archived_" in d.name] == []
    # nothing protected: the same post archives it and starts
    monkeypatch.delenv("FLUBNF_PROTECT_ROOTS")
    client.post("/retro/run", data=archive_form, follow_redirects=False)
    assert started == [SEASON]
    assert [d for d in rr.iterdir() if "__archived_" in d.name]


def test_replacing_a_protected_import_is_refused_and_deletes_nothing(
        tmp_path, monkeypatch):
    from app.core import replay_bundle as rb
    from test_retro_archive import SEASON, _season_tree
    rr = tmp_path / "retro"
    rr.mkdir()
    _season_tree(rr, SEASON)
    p = rb.export_season(rr / SEASON, SEASON, tmp_path / "out")
    other = tmp_path / "other"
    r = rb.import_bundle(p, other)
    (r.root / "notes.txt").write_text("kept")
    monkeypatch.setenv("FLUBNF_PROTECT_ROOTS", str(r.root))
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(p, other, replace=True)
    assert str(e.value) == (
        f"{SEASON} from this bundle is imported as {r.stamp} in a protected "
        "folder, which the console never deletes; nothing was replaced.")
    assert (r.root / "notes.txt").read_text() == "kept"
    assert [d.name for d in other.iterdir()] == [r.root.name]
    # unprotected, the replace goes ahead as before
    monkeypatch.delenv("FLUBNF_PROTECT_ROOTS")
    rb.import_bundle(p, other, replace=True)
    assert not (r.root / "notes.txt").exists()
