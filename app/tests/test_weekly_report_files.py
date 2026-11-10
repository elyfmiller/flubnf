"""The weekly and season report files (bug hunt 2026-10-25, G16).

  * A modified run's weekly report saves with its files' "-modified"; the
    date's name stays the hub reference date's otherwise (Decided
    2026-10-01). Every run's report carries its run id before that, so two
    runs of a week never share a name; only Output's archived week keeps
    the reference date's name alone (Decided 2026-11-10). With no ledger
    row the folder's own record says which; /output/report/download names
    it as the run page does.
  * The report's keys list only the models its panels drew.
  * "back to FluBNF" returns to the console page that opened the report,
    past any jump inside it (its onclick run under node).
  * A hidden section's figures are drawn when it opens, not at load, so
    the page and its controls are ready in a second or two.
  * A member whose scoring failed says why, on the run page and in the
    report (the pipeline's own report step).
  * An archived run's season report saves under its own name.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                               # noqa: E402
from app.core import report_grid, report_season, report_v2      # noqa: E402
from app.core.runs import Ledger, RunSpec                      # noqa: E402
from app.core.scoring import summary_table_html                # noqa: E402
from app.core.submit import hub_model_id                       # noqa: E402
from app.ui import server as srv                               # noqa: E402
from app.ui import shared as ui_shared                         # noqa: E402
from app.ui import state as ui_state                           # noqa: E402
from app.ui.routes import output as O                          # noqa: E402

client = TestClient(srv.app)
NO_BASELINE = ("the hub clone has no model-output/FluSight-baseline. Press "
               "Update data on the Data tab to fetch it, then rescore.")


@pytest.fixture()
def root(tmp_path, monkeypatch):
    before = dict(ui_state._status)
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    for k in ("running", "workroot", "phase", "flash", "flash_kind",
              "flash_detail"):
        ui_state._status[k] = None
    ui_shared._invalidate_scans()
    yield tmp_path
    ui_state._status.clear()
    ui_state._status.update(before)
    ui_shared._invalidate_scans()


def _run(root, extra=None, outcome=None) -> str:
    """A closed ledger row and its workroot with a report."""
    import time
    time.sleep(1.05)                     # run ids sort by their start second
    led = Ledger()
    rid = led.open_run(RunSpec(engine="analogue", forecast_date="2026-10-17",
                               locations=["Ohio"], extra=extra or {}),
                       Path("pending"), {})
    w = root / "workroots" / rid
    w.mkdir(parents=True)
    (w / "results.json").write_text(json.dumps(
        {"forecast_date": "2026-10-17", "models": {}}))
    (w / "report.html").write_text("<p>r</p>")
    led.set_workroot(rid, w)
    led.close_run(rid, "ok", outcome or {"report": "report.html"})
    return rid


def _tagged(rid: str, suffix: str = "") -> str:
    """A run's report name: the reference date's, then the run's id."""
    return f"2026-10-24-NAU_PyBNF-weekly-report-{rid}{suffix}.html"


def _saved_as(path: str) -> str:
    r = client.get(path)
    assert r.status_code == 200
    return r.headers["content-disposition"].split("filename=", 1)[1].strip('"')


# ------------------------------------- OU-03: a modified run's report name

def test_a_modified_runs_report_saves_with_its_files_suffix(root, monkeypatch):
    monkeypatch.setattr(O, "_report_for_serving", lambda d: None)
    shipped = _run(root)
    modified = _run(root, extra={"knobs": {"oracle.w": 0.25}})
    override = _run(root, extra={"knobs": {"oracle.w": 0.25},
                                 "knobs_override": "the registered weight"})
    assert _saved_as(f"/runs/{shipped}/report/download") == _tagged(shipped)
    assert _saved_as(f"/runs/{modified}/report/download") == \
        _tagged(modified, "-modified")
    # exported under the hub names by override: named as its files are
    assert _saved_as(f"/runs/{override}/report/download") == \
        _tagged(override)


MODIFIED = {"knobs": {"oracle.w": 0.25}}
OVERRIDE = {**MODIFIED, "knobs_override": "the registered weight"}


def _as_recorded(root, rid: str) -> Path:
    """The workroot's own record, as the pipeline writes it: the spec in
    results.json, and knobs.json for a modified run."""
    from app.core import knobs as K
    w = root / "workroots" / rid
    spec = Ledger().row(rid)["spec"]
    res = json.loads((w / "results.json").read_text())
    (w / "results.json").write_text(json.dumps({**res, "spec": spec}))
    # nothing for a shipped run
    K.write_record(w / "knobs.json", RunSpec(**json.loads(spec)))
    return w


def test_a_modified_run_with_no_ledger_row_keeps_its_files_suffix(
        root, monkeypatch):
    """OU-03: the ledger row deleted (or the ledger cleared), the workroot
    kept: the name comes from the folder's own record, not the row."""
    monkeypatch.setattr(O, "_report_for_serving", lambda d: None)
    ids = {"shipped": _run(root), "modified": _run(root, extra=MODIFIED),
           "override": _run(root, extra=OVERRIDE)}
    w = {k: _as_recorded(root, rid) for k, rid in ids.items()}
    before = {k: (w[k] / "report.html").read_bytes() for k in ids}
    assert Ledger().delete_runs(list(ids.values())) == 3
    assert all(Ledger().row(rid) is None for rid in ids.values())

    def name(k):
        return _saved_as(f"/runs/{ids[k]}/report/download")
    shipped, override = _tagged(ids["shipped"]), _tagged(ids["override"])
    modified = _tagged(ids["modified"], "-modified")
    # results.json's spec, as the pipeline named the files from
    assert (name("shipped"), name("modified"), name("override")) == (
        shipped, modified, override)
    # an older results.json without the spec: knobs.json says it
    for k in ids:
        res = json.loads((w[k] / "results.json").read_text())
        res.pop("spec")
        (w[k] / "results.json").write_text(json.dumps(res))
    assert (name("shipped"), name("modified"), name("override")) == (
        shipped, modified, override)
    # neither: the submission folders' own names
    (w["modified"] / "knobs.json").unlink()
    gh = hub_model_id("analogue")                 # NAU_PyBNF-GroundHogCGR
    sub = w["modified"] / "submission"
    (sub / f"{gh}-modified").mkdir(parents=True)
    assert name("modified") == modified
    (sub / f"{gh}-modified").rename(sub / gh)
    assert name("modified") == _tagged(ids["modified"])
    # only the name: the report's bytes are the same
    assert all((w[k] / "report.html").read_bytes() == before[k] for k in ids)


def test_the_output_reports_download_takes_its_runs_suffix(root, monkeypatch):
    """/output/report/download, for the report Home shows, is named as the
    run page's download is; a date's archived report keeps the reference
    date's name, with its run's suffix."""
    from app.core import archive_record as _ar
    monkeypatch.setattr(O, "_report_for_serving", lambda d: None)
    shipped = "2026-10-24-NAU_PyBNF-weekly-report.html"
    modified = "2026-10-24-NAU_PyBNF-weekly-report-modified.html"
    # the shipped rule (no date): the run Home shows
    rid = _run(root, extra=OVERRIDE)
    _as_recorded(root, rid)
    ui_shared._invalidate_scans()          # as a finished run does
    assert _saved_as("/output/report/download") == _tagged(rid)
    # a date's archive, the run named in its archive.json
    arch = root / "archive" / "2026-10-17"
    arch.mkdir(parents=True)
    (arch / "report.html").write_text("<p>a</p>")
    (arch / "results.json").write_text(json.dumps(
        {"forecast_date": "2026-10-17", "models": {}}))
    mod = _run(root, extra=MODIFIED)
    _ar.write_record(arch, mod, True, True)
    assert _saved_as("/output/report/download?date=2026-10-17") == modified
    _ar.write_record(arch, rid, True, True)
    assert _saved_as("/output/report/download?date=2026-10-17") == shipped
    # the archive's run no longer in the ledger: the archive's own copy of
    # its record
    Ledger().delete_runs([mod])
    _ar.write_record(arch, mod, True, True)
    (arch / "results.json").write_text(json.dumps(
        {"forecast_date": "2026-10-17", "models": {},
         "spec": RunSpec(engine="analogue", forecast_date="2026-10-17",
                         locations=["Ohio"], extra=MODIFIED).to_json()}))
    assert _saved_as("/output/report/download?date=2026-10-17") == modified


# --------------------------------- OU-04: the keys list the models drawn

def test_the_keys_list_only_the_models_the_panels_drew():
    def fan(med):                 # horizon -> {level: value}, as members give
        return {str(h): {L: med * (1 + 0.2 * z) for L, z in
                         ((0.025, -1.9), (0.5, 0), (0.975, 1.9))}
                for h in range(4)}
    names = ["US", "Ohio"]
    obs = {n: [("2098-01-03", 10.0)] for n in names}

    def grid(models):
        return report_grid.grid_data(
            "2098-01-03", names, {"US": "US", "Ohio": "OH"},
            {"US": "United States"}, obs,
            {m: {n: fan(20.0) for n in names} for m in models}, {})
    colors = report_v2.MEMBER_COLORS
    gh_only = grid(["analogue"])                  # a Groundhog-only run
    for html in (report_grid.us_feature_html(gh_only, colors),
                 report_grid.grid_html(gh_only, colors)):
        assert 'data-s="analogue"' in html and 'data-s="obs"' in html
        assert 'data-s="pf"' not in html and "Oracle SIHRS" not in html
    assert 'data-s="pf"' in report_grid.grid_html(grid(["analogue", "pf"]),
                                                  colors)


# ------------------------------------ OU-05 and OU-06: the way back, early

def test_back_to_flubnf_goes_to_the_page_that_opened_the_report():
    back = report_v2.page_header().split('id="appback"', 1)[1].split(">", 1)[0]
    assert "document.referrer" in back and "location.origin" in back
    assert "history.back()" in back       # a saved copy with no console


@pytest.mark.skipif(not shutil.which("node"), reason="no node")
def test_the_back_buttons_click_under_each_referrer(tmp_path):
    """The button's own onclick, run with stand-in document, location and
    history: a console page that opened the report is gone back to by its
    address; another site, no referrer, or the report itself (a jump
    inside it) take the browser's back."""
    import html
    tag = report_v2.page_header().split('<a id="appback"', 1)[1] \
                                 .split(">", 1)[0]
    onclick = html.unescape(tag.split('onclick="', 1)[1].split('"', 1)[0])
    app = "http://127.0.0.1:8710"
    report = f"{app}/output/report?date=2026-10-17#st-OH"
    harness = """
function click(referrer, href) {
  var document = {referrer: referrer};
  var location = {origin: %s, href: href};
  var backs = 0;
  var history = {back: function () { backs++; }};
  var ret = (function () { ONCLICK })();
  return [location.href, backs, ret];
}
var cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify(cases.map(function (c) { return click(c[0], c[1]); })));
""".replace("%s", json.dumps(app)).replace("ONCLICK", onclick)
    f = tmp_path / "back.js"
    f.write_text(harness, encoding="utf-8")
    cases = [
        (f"{app}/output", report),                       # the console page
        (f"{app}/runs/20261017T120000Z", report),
        ("https://example.org/flu", report),             # another site
        ("", report),                                    # no referrer
        (f"{app}/output/report?date=2026-10-17", report),  # a jump inside
        ("http://127.0.0.1:87100/output", report),       # a lookalike port
    ]
    got = json.loads(subprocess.run(
        [shutil.which("node"), str(f), json.dumps(cases)],
        capture_output=True, text=True, check=True).stdout)
    assert got == [[f"{app}/output", 0, False],
                   [f"{app}/runs/20261017T120000Z", 0, False],
                   [report, 1, False],
                   [report, 1, False],
                   [report, 1, False],
                   [report, 1, False]]


def _charted(tmp_path) -> str:
    rng = __import__("numpy").random.default_rng(5)
    f_t = ["2098-01-10", "2098-01-17", "2098-01-24", "2098-01-31"]
    q = report_v2.fan_quantiles(
        f_t, {t: rng.gamma(4.0, 30.0, 300).tolist() for t in f_t})
    fan = report_v2.fan_figure_from_quantiles(
        ["2098-01-03"], [110.0], f_t, q, title="t")
    return report_v2.build_report(
        "2098-01-03", {}, {"OH": {"name": "Ohio", "fan": fan,
                                  "cat": report_v2.cat_bar({"stable": 1.0}),
                                  "table_rows": []}},
        {}, tmp_path / "c.html").read_text(encoding="utf-8")


def test_a_hidden_sections_figures_wait_for_it_to_open(tmp_path):
    html = _charted(tmp_path)
    section = html.split('<section class="state" id="st-OH"', 1)[1] \
                  .split("</section>", 1)[0]
    assert section.count('<script type="application/json" class="rp-figjson"') == 2
    assert "Plotly.newPlot" not in section
    assert '<\\/' not in section.split("rp-figjson")[0]
    # the figure's JSON holds its data, layout and the save-PNG config
    payload = json.loads(section.split('data-for="', 1)[1]
                         .split(">", 1)[1].split("</script>", 1)[0])
    assert set(payload) == {"data", "layout", "config"}
    assert payload["config"]["toImageButtonOptions"]["filename"] == \
        "flubnf_report_figure"
    # show() draws them once, retinted and fitted like the rest
    show = html.split("function show(id", 1)[1].split("window.backToMap", 1)[0]
    assert "rpDraw(el);" in show
    draw = html.split("window.rpDraw = function(el)", 1)[1].split("};", 1)[0]
    for step in ("Plotly.newPlot(gd, f.data, f.layout, f.config)",
                 "rpRetint(gd)", "FluCharts.adopt(gd)", "js[i].remove()"):
        assert step in draw, step
    assert "window.rpRetint=pass" in html
    # a report without figures carries none of it
    bare = report_v2.build_report("2098-01-03", {}, {}, {},
                                  tmp_path / "b.html").read_text(encoding="utf-8")
    assert "window.rpDraw = function" not in bare and "FluCharts" not in bare


# --------------------------------- FC-20: a failed score says why it failed

def test_a_member_whose_scoring_failed_says_why():
    line = summary_table_html(pd.DataFrame(), model="analogue",
                              error=NO_BASELINE)
    assert "Groundhog could not be scored: the hub clone has no " \
        "model-output/FluSight-baseline." in line
    assert "no scored weeks" not in line
    assert "Groundhog: no scored weeks yet." in summary_table_html(
        pd.DataFrame(), model="analogue")


def test_the_pipeline_puts_a_members_scoring_error_in_the_report(
        tmp_path, monkeypatch):
    """The weekly report's accuracy card, built by the pipeline's own step
    from a Groundhog-only run whose scoring failed, says why; the data
    reads are stand-ins (no hub)."""
    from types import SimpleNamespace

    from app.core import ensemble as ens
    from app.ui import pipeline as P
    from flubnf.settings import load_locations
    monkeypatch.setattr(ui_state, "data_mod", SimpleNamespace(
        vintages=lambda: [], vintage_path=lambda v: None))
    locs = load_locations()
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    rng = __import__("numpy").random.default_rng(11)
    an_q = {"Ohio": ens.member_quantiles_from_samples(
        {h: rng.gamma(5.0, 20.0, 300).tolist() for h in ("0", "1", "2", "3")})}
    obs = {"Ohio": [[f"2097-12-{d:02d}", 100.0 + d] for d in (6, 13, 20, 27)]}
    spec = RunSpec(engine="analogue", forecast_date="2098-01-03",
                   locations=["Ohio"])

    def card(outcome):
        w = tmp_path / str(len(list(tmp_path.iterdir())))
        w.mkdir()
        P._write_weekly_report(spec, w, {}, obs, pd.DataFrame(), locs, n2f,
                               1.0, outcome, an_q=an_q)
        bundle = json.loads((w / report_v2.BUNDLE_NAME).read_text())
        html = (w / "report.html").read_text(encoding="utf-8")
        return bundle["national"]["summary_html"], html
    said = ("Groundhog could not be scored: the hub clone has no "
            "model-output/FluSight-baseline.")
    for outcome in ({"analogue_score_error": NO_BASELINE},
                    {"score_error": NO_BASELINE}):     # the run-wide one
        summary, html = card(dict(outcome))
        assert said in summary and said in html
        assert "no scored weeks" not in summary
    # no error: the plain line
    summary, _ = card({})
    assert "Groundhog: no scored weeks yet." in summary
    assert "could not be scored" not in summary


def test_the_run_page_names_the_groundhogs_scoring_error(root):
    rid = _run(root, outcome={"report": "report.html",
                              "analogue_score_error": NO_BASELINE})
    page = client.get(f"/runs/{rid}").text
    assert "<code>analogue_score_error</code>" in page
    assert "model-output/FluSight-baseline" in page


# ---------------------------- RE-26: an archived season report's own name

def test_an_archived_season_report_saves_under_its_own_name(monkeypatch,
                                                            tmp_path):
    from app.ui.routes import retro as R
    built = tmp_path / "2026-27-FluBNF-season-report.html"
    built.write_text("<p>s</p>")
    monkeypatch.setattr(R, "_season_report", lambda season, archive: built)
    assert _saved_as("/retro/2026-27/report") == \
        "2026-27-FluBNF-season-report.html"
    assert _saved_as("/retro/2026-27/report?archive=20260204T101500Z") == \
        "2026-27-FluBNF-season-report-20260204T101500Z.html"
    # the page's own download takes the job's name
    assert report_season.download_name("2026-27", "20260204T101500Z") == \
        "2026-27-FluBNF-season-report-20260204T101500Z.html"
