"""The bug-fix review's leftovers (2026-11-10).

  * A wrapped segmented switch tucks every choice's left divider under
    the outline at a row's start: the element rule keeps the -1px margin
    the wrap rule gives (it is the more specific of the two).
  * Home's map comment names the legend's gray as the legend words it.
  * With no hub folder, Update data is never the Data page's primary
    action (a pull is refused then), nor does a check's answer make it so.
  * Retrospective's archive mode and a replay import's replace refuse a
    protected folder in words, as the other protected-folder refusals do,
    and move or delete nothing; an earlier import's stale tree too.
  * Decided 2026-11-10: only a week's shipped run saves its report under
    the plain name (OU-03); the template's "Overall" is its national row
    (RE-17); the Sandbox's file formats live in its guide (UI-14); the
    public site's buttons work with storage blocked, and site.json never
    names a moved state folder's own path.
"""
import re
import shutil
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
    # an earlier attempt's tree in a protected retro root is not deleted
    stale = r.root.with_name(r.root.name + ".importing")
    stale.mkdir()
    (stale / "half.json").write_text("{}")
    monkeypatch.setenv("FLUBNF_PROTECT_ROOTS", str(stale))
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(p, other, replace=True)
    assert str(e.value) == (
        f"An earlier import of {SEASON} left {stale.name} in a protected "
        "folder, which the console never deletes; nothing was imported.")
    assert (stale / "half.json").is_file()
    assert (r.root / "notes.txt").read_text() == "kept"
    # unprotected, the replace goes ahead as before (the stale tree too)
    monkeypatch.delenv("FLUBNF_PROTECT_ROOTS")
    rb.import_bundle(p, other, replace=True)
    assert not (r.root / "notes.txt").exists() and not stale.exists()


# ------------------------------------- OU-03: one name per run of a week

def test_only_the_weeks_shipped_run_saves_its_report_under_the_plain_name(
        monkeypatch, tmp_path):
    """The run Output lists as the week's shipped run (the one the date's
    archive holds) keeps the plain name; every other run of that week
    carries its run id. A run's name never changes because another run of
    the week appears."""
    import app.core.runs as runs_mod
    from app.ui.routes import output as O
    from test_weekly_report_files import _run, _saved_as
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    monkeypatch.setattr(O, "_report_for_serving", lambda d: None)
    ui_shared._invalidate_scans()
    plain = "2026-10-24-NAU_PyBNF-weekly-report.html"
    shipped, other = _run(tmp_path), _run(tmp_path)
    from app.core import archive_record as _ar
    arch = tmp_path / "archive" / "2026-10-17"
    arch.mkdir(parents=True)
    (arch / "report.html").write_text("<p>a</p>")
    _ar.write_record(arch, shipped, True, True)
    names = {rid: _saved_as(f"/runs/{rid}/report/download")
             for rid in (shipped, other)}
    assert names == {shipped: plain,
                     other: f"2026-10-24-NAU_PyBNF-weekly-report-{other}.html"}
    # the date's own download is the shipped run's, under the same name
    assert _saved_as("/output/report/download?date=2026-10-17") == plain
    # a third run of the week moves neither name
    third = _run(tmp_path)
    assert {rid: _saved_as(f"/runs/{rid}/report/download")
            for rid in (shipped, other)} == names
    assert _saved_as(f"/runs/{third}/report/download") == \
        f"2026-10-24-NAU_PyBNF-weekly-report-{third}.html"
    ui_shared._invalidate_scans()


# --------------------------- RE-17: the template's 'Overall' is its national

def test_the_templates_overall_is_its_national_row_and_only_that_word(
        tmp_path, monkeypatch):
    from app.core import datasets as D
    from app.core.datasets import checks
    from test_datasets import TPL, grouped_csv, grouped_series, only
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    # the console's own template: Overall, the sum of the others, is kept
    # out of their pooled scores
    ds = D.ingest(TPL, "tpl", kind="count")
    assert ds.national_group == "Overall"
    flags = {g["name"]: g["national"] for g in ds.meta["groups"]}
    assert flags == {"Adult": False, "Pediatric": False, "Overall": True}
    # any letter case, and no other aggregate word
    assert checks.is_national_name("overall")
    for word in ("Total", "All ages", "Overall total"):
        assert not checks.is_national_name(word), word
    # one national row a dataset, still: US and Overall together refused
    rows = grouped_series(groups=("Adult", "US", "Overall"))
    p = only(D.validate(grouped_csv(rows), kind="count"), "national_multiple")
    assert "'Overall'" in p.message and "'US'" in p.message
    # a dataset stored before keeps the flag it was stored with
    names = checks.NATIONAL_NAMES
    monkeypatch.setattr(checks, "NATIONAL_NAMES",
                        tuple(n for n in names if n != "OVERALL"))
    old = D.ingest(TPL, "old", kind="count")
    monkeypatch.setattr(checks, "NATIONAL_NAMES", names)
    assert D.get(old.id).national_group is None


# ----------------- UI-14: the Sandbox's file formats live in its guide

def test_the_files_note_is_one_line_that_points_at_the_guide(sandbox_root):
    from app.core import sandbox as sb
    sb.add_example("sir_example")
    html = client.get("/sandbox?model=sir_example").text
    note = html.split('id="tt-sb-files"', 1)[1].split("</span></span>", 1)[0]
    assert note.count('class="uk-tt-line"') == 1
    assert ('<a href="https://github.com/elyfmiller/flubnf/blob/main/docs/'
            'SANDBOX.md#2-the-three-files" target="_blank" rel="noopener">'
            'The three files</a>') in note
    text = re.sub(r"<[^>]+>", " ", note)
    assert len(" ".join(text.split())) < 140
    # the guide's section the link opens names each file
    guide = (Path(__file__).resolve().parents[2] / "docs" / "SANDBOX.md"
             ).read_text(encoding="utf-8")
    assert "\n## 2. The three files\n" in guide
    for f in ("**model.bngl**", "**data.exp**", "**priors.conf**"):
        assert f in guide.split("## 2. The three files", 1)[1], f


def test_the_guide_says_the_state_folder_does_not_move_the_sandbox():
    guide = (Path(__file__).resolve().parents[2] / "docs" / "SANDBOX.md"
             ).read_text(encoding="utf-8")
    assert ("The Sandbox stays in the checkout's `sandbox/` folder: "
            "FLUBNF_STATE_DIR, which moves the console's state folder, does "
            "not move it.") in " ".join(guide.split())


# --------------------------------------------------------- the public site

NODE = shutil.which("node")

#: a document whose storage throws (site data blocked), the a11y picker's
#: one button, and the chart calls the picker makes, stubbed
_BLOCKED = r"""
const attrs = {};
const btn = {dataset: {k: 'theme', v: 'dark'}, attrs: {},
             setAttribute(n, v) { this.attrs[n] = v; }, closest() { return this; }};
let onClick = null;
const PICKER = {querySelectorAll(s) { return s.includes('"theme"') ? [btn] : []; },
                addEventListener(t, f) { onClick = f; }};
const window = {};
Object.defineProperty(window, 'localStorage',
                      {get() { throw new Error('SecurityError'); }});
const document = {
  documentElement: {setAttribute(n, v) { attrs[n] = v; },
                    removeAttribute(n) { delete attrs[n]; }},
  getElementById(id) { return id === 'a11y' ? PICKER
                       : {classList: {contains() { return false; }}}; }};
const sel = {value: 'x'};
function draw() {} function drawCum() {}
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_public_sites_display_buttons_work_with_storage_blocked():
    import json
    import subprocess
    from app.core import site_page as SP
    # the first paint: no error when storage throws
    r = subprocess.run([NODE, "-e", _BLOCKED + SP.BOOT + "console.log('ok')"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr
    # the picker: the button turns the theme on and off for the visit
    js = SP.JS
    a = js.index("  // ---- accessibility pickers")
    b = js.index("  // ---- cumulative relWIS")
    c = js.index("  A.addEventListener('click'")
    d = js.index("    applyA11y();\n  });", c) + len("    applyA11y();\n  });")
    run = _BLOCKED + js[a:b] + js[c:d] + r"""
applyA11y();
const seen = [attrs['data-theme'] || null];
onClick({target: btn});
seen.push([attrs['data-theme'], btn.attrs['aria-pressed']]);
onClick({target: btn});
seen.push([attrs['data-theme'] || null, btn.attrs['aria-pressed']]);
console.log(JSON.stringify(seen));
"""
    r = subprocess.run([NODE, "-e", run], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [None, ["dark", "true"], [None, "false"]]


def test_site_json_names_a_moved_state_folder_by_app_state(tmp_path, monkeypatch):
    from app.core import site_build as SB
    # FLUBNF_STATE_DIR set: the state folder is outside the checkout
    monkeypatch.setattr(SB, "APP_STATE", tmp_path / "state")
    moved = SB.score_season("2025-26", {"root": tmp_path / "state" / "retro" / "2025-26",
                                        "origin": "lab run", "weeks": []}, None, {})
    assert moved["root"] == str(Path("app") / "state" / "retro" / "2025-26")
    assert str(tmp_path) not in moved["root"]
    # without the variable: as it was, relative to the checkout
    here = SB.REPO / "app" / "state" / "retro" / "2025-26"
    monkeypatch.setattr(SB, "APP_STATE", SB.REPO / "app" / "state")
    assert SB.score_season("2025-26", {"root": here, "origin": "lab run",
                                       "weeks": []}, None, {})["root"] == \
        str(Path("app") / "state" / "retro" / "2025-26")
