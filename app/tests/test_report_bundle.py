"""Weekly report staleness contract: the run persists an inputs bundle
(report_inputs.json) beside report.html; serving a report whose builder
sources moved on rebuilds it from that bundle, once; a fresh report is
served verbatim; a broken bundle degrades to the stored file; reports that
predate the bundle get a conservative serve-time theme carry or a quiet
line, with the stored file never modified."""
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

import app.core.runs as runs_mod                    # noqa: E402
import app.ui.server as srv                         # noqa: E402
from app.core import report_v2                      # noqa: E402

client = TestClient(srv.app)

OLD_MTIME = (1_000_000_000, 1_000_000_000)          # 2001: always stale
FUTURE_MTIME = (4_000_000_000, 4_000_000_000)       # 2096: always fresh


def _synth_run(workroot: Path):
    """Drive the real build path (_run_all step 5b) with synthetic samples
    for Ohio and the national row; returns (outcome, spec)."""
    from flubnf.settings import load_locations
    locs = load_locations()
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    spec = runs_mod.RunSpec(engine="pf", forecast_date="2098-01-03",
                            locations=["Ohio", "US"])
    rng = np.random.default_rng(7)
    pf_samples = {loc: {str(h): (rng.gamma(5.0, 20.0, 400) + 10 * h).tolist()
                        for h in (1, 2, 3, 4)}
                  for loc in ("Ohio", "US")}
    obs = {loc: [[f"2097-12-{d:02d}", 100.0 + d] for d in (6, 13, 20, 27)]
           for loc in ("Ohio", "US")}
    workroot.mkdir(parents=True, exist_ok=True)
    (workroot / "cells.json").write_text(json.dumps(
        [{"location": "Ohio", "last_observed": 127.0},
         {"location": "US", "last_observed": 127.0}]))
    outcome = {}
    srv._write_weekly_report(spec, workroot, pf_samples, obs,
                             pd.DataFrame(), locs, n2f, 42.0, outcome)
    return outcome, spec


def test_build_path_writes_bundle_and_report(tmp_path):
    outcome, _ = _synth_run(tmp_path)
    b = tmp_path / report_v2.BUNDLE_NAME
    assert b.is_file()
    bundle = json.loads(b.read_text())
    assert bundle["version"] == report_v2.BUNDLE_VERSION
    assert bundle["reference_date"] == "2098-01-03"
    # fans travel as quantiles, never as raw samples: the bundle stays small
    fan = bundle["details"]["OH"]["fan"]
    assert set(fan) >= {"observed_times", "observed", "forecast_times",
                        "quantiles"}
    assert all(str(lv) in q for q in fan["quantiles"].values()
               for lv in (0.025, 0.5, 0.975))
    assert outcome["report_inputs_bytes"] == b.stat().st_size
    assert outcome["report_inputs_bytes"] < 256 * 1024
    # the rendered report is the current design with both drill-down pages
    html = (tmp_path / "report.html").read_text()
    assert "<em>Flu</em>BNF" in html
    assert 'id="st-OH"' in html and 'id="st-US"' in html
    assert "Ohio: weekly admissions" in html
    assert outcome["report"] == str(tmp_path / "report.html")


def test_render_bundle_matches_direct_build(tmp_path):
    """The quantile path draws the same fan the samples path drew."""
    rng = np.random.default_rng(3)
    samples = {str(h): rng.gamma(4.0, 30.0, 500).tolist()
               for h in (1, 2, 3, 4)}
    f_t = ["2098-01-10", "2098-01-17", "2098-01-24", "2098-01-31"]
    by_t = {f_t[h - 1]: samples[str(h)] for h in (1, 2, 3, 4)}
    o_t, o_v = ["2098-01-03"], [110.0]
    direct = report_v2.fan_figure(o_t, o_v, f_t, by_t, title="t")
    q = report_v2.fan_quantiles(f_t, by_t)
    rebuilt = report_v2.fan_figure_from_quantiles(o_t, o_v, f_t, q,
                                                  title="t")
    assert len(direct.data) == len(rebuilt.data)
    for a, b in zip(direct.data, rebuilt.data):
        assert a.name == b.name
        np.testing.assert_allclose(np.asarray(a.y, float),
                                   np.asarray(b.y, float), atol=1e-3)


def _archived(tmp_path, monkeypatch, date="2098-01-03"):
    """An APP_STATE with one archived run built through the real path."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    d = tmp_path / "archive" / date
    _synth_run(d)
    srv._REPORT_REBUILD_FAILED.clear()
    return d


def test_stale_report_with_bundle_rebuilds_on_serve(tmp_path, monkeypatch):
    d = _archived(tmp_path, monkeypatch)
    (d / "report.html").write_text("<html><body>OLD FACE</body></html>")
    os.utime(d / "report.html", OLD_MTIME)
    calls = []
    real = report_v2.render_bundle
    monkeypatch.setattr(report_v2, "render_bundle",
                        lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    r = client.get("/output/report?date=2098-01-03")
    assert r.status_code == 200
    assert "OLD FACE" not in r.text
    assert "<em>Flu</em>BNF" in r.text and 'id="st-OH"' in r.text
    assert calls == [1]
    # rebuilt IN PLACE: the stored file is now fresh, so the next serve
    # neither rebuilds nor transforms
    disk = (d / "report.html").read_text()
    assert "OLD FACE" not in disk
    assert (d / "report.html").stat().st_mtime >= \
        report_v2.builder_sources_mtime()
    r2 = client.get("/output/report?date=2098-01-03")
    assert r2.text == disk and calls == [1]


def test_fresh_report_served_verbatim(tmp_path, monkeypatch):
    d = _archived(tmp_path, monkeypatch)
    (d / "report.html").write_text("<html><body>FRESH FACE</body></html>")
    os.utime(d / "report.html", FUTURE_MTIME)
    monkeypatch.setattr(report_v2, "render_bundle",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not rebuild fresh")))
    r = client.get("/output/report?date=2098-01-03")
    assert r.status_code == 200 and "FRESH FACE" in r.text


def test_rebuild_failure_serves_stored_file(tmp_path, monkeypatch):
    d = _archived(tmp_path, monkeypatch)
    (d / "report.html").write_text("<html><body>OLD FACE</body></html>")
    os.utime(d / "report.html", OLD_MTIME)
    (d / report_v2.BUNDLE_NAME).write_text("{not json")
    for _ in (1, 2):        # second hit exercises the tried-once memo
        r = client.get("/output/report?date=2098-01-03")
        assert r.status_code == 200 and "OLD FACE" in r.text
    assert "OLD FACE" in (d / "report.html").read_text()
    # an unknown future bundle version degrades the same way
    srv._REPORT_REBUILD_FAILED.clear()
    (d / report_v2.BUNDLE_NAME).write_text(json.dumps({"version": 99}))
    r = client.get("/output/report?date=2098-01-03")
    assert r.status_code == 200 and "OLD FACE" in r.text


LEGACY = """<!doctype html><html><head><meta charset="utf-8">
<title>FluBNF — week of 2098-01-03</title>
<style>
 body{margin:0;background:#0a1626;color:#e9ecf2;font:15px/1.55 system-ui}
 .sub{color:#93a1b5;margin:.2rem 0 1rem}
 .card{background:#0f2440;border:1px solid #1d3a5f}
 .hint{color:#93a1b5;font-size:.85rem}
</style></head><body><main>
<h1>US influenza forecast</h1>
<p class="sub">week of 2098-01-03</p>
<div class="card" id="map-anchor">
 <a id="appback" href="#" hidden
 onclick="history.back();return false">&larr; back to FluBNF</a>
 <p class="hint">map here</p>
</div>
</main></body></html>"""


def test_legacy_report_gets_theme_carry_and_disk_untouched(tmp_path,
                                                           monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    d = tmp_path / "archive" / "2098-01-03"
    d.mkdir(parents=True)
    (d / "report.html").write_text(LEGACY)
    os.utime(d / "report.html", OLD_MTIME)
    before = (d / "report.html").read_bytes()
    r = client.get("/output/report?date=2098-01-03")
    assert r.status_code == 200
    # current stylesheet and header lockup carried in at serve time
    assert "--bg:#0C0D17" in r.text and "#0a1626" not in r.text
    assert 'class="brandrow"' in r.text
    assert r.text.count('id="appback"') == 1        # old floating link gone
    assert report_v2.STALE_NOTE_ID in r.text
    assert "A new run will refresh" in r.text
    # the stored artifact is never modified
    assert (d / "report.html").read_bytes() == before


def test_legacy_carry_injects_the_retint_pass_for_charted_pages():
    # a carried page with embedded charts gains the retint pass, so its
    # baked category bars follow the reader's theme and color-vision mode
    # (the field-found gap: pre-bundle reports served green-to-red bars
    # that ignored the CV-safe toggle); the carried tokens it resolves
    # arrive with the swapped stylesheet
    charted = LEGACY.replace(
        "<p class=\"hint\">map here</p>",
        "<p class=\"hint\">map here</p>\n<div id=\"fig1\"></div>"
        "<script>Plotly.newPlot('fig1',[],{});</script>")
    out = report_v2.legacy_theme_carry(charted)
    assert 'class="brandrow"' in out                 # the swap happened
    assert "Plotly.react(g,g.data,g.layout)" in out  # retint rides along
    assert 'css("--cat-stable"' in out               # cvd reach included
    assert "addEventListener('themechange',pass)" in out
    # a chartless page stays retint-free (dead weight otherwise)
    plain = report_v2.legacy_theme_carry(LEGACY)
    assert 'class="brandrow"' in plain
    assert "Plotly.react(g,g.data,g.layout)" not in plain
    # the stored-file contract is untouched: annotated pages pass through
    assert report_v2.legacy_theme_carry(out) == out


def test_legacy_carry_declines_incompatible_markup():
    html = LEGACY.replace(" .hint{", " .gone{color:red}\n .hint{") \
                 .replace('class="hint"', 'class="hint gone"')
    out = report_v2.legacy_theme_carry(html)
    # the swap is refused (a styled-and-used class has no current styling);
    # only the quiet line lands
    assert "#0a1626" in out and 'class="brandrow"' not in out
    assert report_v2.STALE_NOTE_ID in out
    assert "generated with an earlier design" in out
    # idempotent: an annotated page passes through unchanged
    assert report_v2.legacy_theme_carry(out) == out


def test_archive_carries_the_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    w = tmp_path / "workroots" / "20980103T000000-abcdef"
    w.mkdir(parents=True)
    for name in ("results.json", "report.html", report_v2.BUNDLE_NAME):
        (w / name).write_text("{}")
    srv._archive_run(w, "2098-01-03")
    assert (tmp_path / "archive" / "2098-01-03"
            / report_v2.BUNDLE_NAME).is_file()


# ------------------- one computation, one source: home = the report's map


def _synth_run_with_ensemble(workroot: Path):
    """The bundle-test synthetic run, plus a vincentized ensemble and the
    results.json the home page reads, laid out as a real latest workroot."""
    import numpy as np
    from app.core import ensemble as ens
    from flubnf.settings import load_locations
    locs = load_locations()
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    spec = runs_mod.RunSpec(engine="pf", forecast_date="2098-01-03",
                            locations=["Ohio", "US"])
    rng = np.random.default_rng(7)
    pf_samples = {loc: {str(h): (rng.gamma(5.0, 20.0, 400) + 10 * h).tolist()
                        for h in (1, 2, 3, 4)}
                  for loc in ("Ohio", "US")}
    obs = {loc: [[f"2097-12-{d:02d}", 100.0 + d] for d in (6, 13, 20, 27)]
           for loc in ("Ohio", "US")}
    ens_q = {loc: ens.member_quantiles_from_samples(s)
             for loc, s in pf_samples.items()}
    workroot.mkdir(parents=True, exist_ok=True)
    (workroot / "cells.json").write_text(json.dumps(
        [{"location": "Ohio", "last_observed": 127.0},
         {"location": "US", "last_observed": 127.0}]))
    outcome = {}
    srv._write_weekly_report(spec, workroot, pf_samples, obs,
                             pd.DataFrame(), locs, n2f, 42.0, outcome,
                             ens_q=ens_q)
    (workroot / "results.json").write_text(json.dumps({
        "forecast_date": "2098-01-03", "observed": obs,
        "models": {"ensemble": {loc: {h: {str(l): v for l, v in q.items()
                                          if str(l) in ("0.1", "0.25", "0.5",
                                                        "0.75", "0.9")}
                                      for h, q in qd.items()}
                   for loc, qd in ens_q.items()}}}))
    return outcome


def test_home_map_renders_the_reports_exact_cards(tmp_path, monkeypatch):
    """The two-maps bug, resolved: home reads the bundle's cards, so the
    home map and the weekly report's map show the SAME categories from the
    SAME model, and both surfaces are labeled with that model."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    w = tmp_path / "workroots" / "20980103T000000-abcdef"
    _synth_run_with_ensemble(w)
    srv._invalidate_scans()
    rid, res = srv._latest_results()
    assert rid == w.name
    cards, meta = srv._outlook_cards(res, rid)
    bundle = json.loads((w / report_v2.BUNDLE_NAME).read_text())
    assert bundle["cards_model"] == "ensemble"      # the submitted forecast
    expect = {c["fips"]: c for c in bundle["cards"].values() if c.get("fips")}
    assert cards == expect                          # exact, not recomputed
    assert meta == {"model": "ensemble", "approx": False,
                    "label": "FluBNF Ensemble outlook",
                    # the v4 scope record rides with the cards so the home
                    # map can say which card-less states were unfitted
                    "fitted_fips": ["39"]}
    # the model label lands on BOTH surfaces
    assert "FluBNF Ensemble outlook" in (w / "report.html").read_text()
    home = client.get("/")
    assert home.status_code == 200
    assert "FluBNF Ensemble outlook" in home.text
    assert "approximate, from stored quantiles" not in home.text


def test_pf_only_run_records_and_labels_pf(tmp_path):
    _synth_run(tmp_path)
    bundle = json.loads((tmp_path / report_v2.BUNDLE_NAME).read_text())
    assert bundle["cards_model"] == "pf"
    assert "PF-SIHRS outlook" in (tmp_path / "report.html").read_text()


def test_pre_bundle_run_falls_back_and_labels_the_approximation(
        tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    w = tmp_path / "workroots" / "20980103T000000-abcdef"
    _synth_run_with_ensemble(w)
    (w / report_v2.BUNDLE_NAME).unlink()            # a pre-bundle run
    srv._invalidate_scans()
    rid, res = srv._latest_results()
    cards, meta = srv._outlook_cards(res, rid)
    assert meta["approx"] is True and meta["model"] == "ensemble"
    assert any(c.get("probs") for c in cards.values())
    home = client.get("/")
    # the label span is the model toggle's relabel target, so the phrase
    # spans a data-mapmodel-label element
    assert "FluBNF Ensemble outlook" in home.text
    assert "approximate, from stored quantiles" in home.text


def test_v1_bundle_still_loads_and_renders_as_pf(tmp_path, monkeypatch):
    """Additive versioning: a v1 bundle (no cards_model) rebuilds fine and
    wears the PF label its cards were computed with."""
    d = _archived(tmp_path, monkeypatch)
    b = d / report_v2.BUNDLE_NAME
    bundle = json.loads(b.read_text())
    bundle["version"] = 1
    bundle.pop("cards_model", None)
    b.write_text(json.dumps(bundle))
    (d / "report.html").write_text("<html><body>OLD FACE</body></html>")
    os.utime(d / "report.html", OLD_MTIME)
    r = client.get("/output/report?date=2098-01-03")
    assert r.status_code == 200 and "OLD FACE" not in r.text
    assert "PF-SIHRS outlook" in r.text


def test_categorical_probs_from_quantiles_matches_the_sample_computation():
    """The ensemble's quantile-space categorical computation agrees with
    the sample computation on the same distribution, within the grid's
    resolution -- the exactness the old few-values-as-samples stand-in
    lacked (it flipped borderline states)."""
    import numpy as np
    from app.core.report import (categorical_probs,
                                 categorical_probs_from_quantiles)
    from flubnf.quantiles import FLUSIGHT_QUANTILES
    rng = np.random.default_rng(11)
    s = rng.gamma(5.0, 20.0, 200_000)
    pop, lo = 5_000_000, 100.0
    grid = {float(l): float(np.quantile(s, l)) for l in FLUSIGHT_QUANTILES}
    exact = categorical_probs(s, lo, pop, 1)
    approx = categorical_probs_from_quantiles(grid, lo, pop, 1)
    assert set(approx) == set(exact)
    for c in exact:
        assert abs(approx[c] - exact[c]) < 0.02, (c, approx[c], exact[c])
    assert abs(sum(approx.values()) - 1.0) < 1e-9
    # degenerate and hostile grids answer honestly, never raise
    assert categorical_probs_from_quantiles({}, lo, pop, 1) == {}
    assert categorical_probs_from_quantiles(grid, lo, 0, 1) == {}
    point = categorical_probs_from_quantiles({"0.5": 100.0}, lo, pop, 1)
    assert point["stable"] == 1.0


# ------------------------------------------------- saving the weekly report

def _delivery_mismatch(a: str, b: str) -> str:
    """Empty when the two deliveries are identical, else a SHORT locator.

    Compared by digest on purpose, not with a bare ==. report.html is about
    5 MB over 4500 lines because the Plotly bundle is inlined, and the one
    regression this assertion exists to catch -- a line ending creeping into
    one delivery and not the other -- makes EVERY line differ. Handed that,
    pytest's difflib explanation goes quadratic over the whole page: on
    Windows CI run 33200477476 it sat in difflib.find_longest_match long
    enough to be a large share of a 62 minute job, and then printed a
    truncated diff that read as two identical strings. A digest plus the
    first differing offset fails in microseconds and names the cause.
    """
    if hashlib.sha256(a.encode("utf-8")).digest() \
            == hashlib.sha256(b.encode("utf-8")).digest():
        return ""
    i = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y),
             min(len(a), len(b)))
    return ("inline and download deliver different text: lengths "
            f"{len(a)} and {len(b)}, first difference at offset {i}, "
            f"{a[i:i + 12]!r} against {b[i:i + 12]!r}")


def test_weekly_report_downloads_with_a_dated_name(tmp_path, monkeypatch):
    """The season report has been downloadable all along; the weekly one
    was inline-only, so a reader could not keep or send one. Same treatment
    now: an attachment, named for its forecast date rather than the
    report.html every run writes, so several saved weeks do not collide."""
    d = _archived(tmp_path, monkeypatch)
    r = client.get("/output/report/download?date=2098-01-03")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == (
        'attachment; filename="FluBNF-weekly-report-2098-01-03.html"')
    assert r.headers["content-type"].startswith("text/html")
    # the same bytes the inline view serves: one file, two deliveries
    assert r.content == (d / "report.html").read_bytes()
    inline = client.get("/output/report?date=2098-01-03").text
    mismatch = _delivery_mismatch(inline, r.text)
    assert not mismatch, mismatch


def test_download_refreshes_a_stale_report_first(tmp_path, monkeypatch):
    """A saved report must never be the stale one while the browser shows
    the fresh one: the download runs the same freshness pass."""
    d = _archived(tmp_path, monkeypatch)
    (d / "report.html").write_text("<html><body>OLD FACE</body></html>")
    os.utime(d / "report.html", OLD_MTIME)
    r = client.get("/output/report/download?date=2098-01-03")
    assert r.status_code == 200
    assert b"OLD FACE" not in r.content
    assert "<em>Flu</em>BNF" in r.text


def test_download_of_a_missing_report_is_a_404_not_a_500(tmp_path,
                                                         monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    srv._invalidate_scans()
    assert client.get("/output/report/download").status_code == 404
    assert client.get(
        "/output/report/download?date=2098-01-03").status_code == 404
    # and a date-shaped check, same as the inline route's
    assert client.get(
        "/output/report/download?date=not-a-date").status_code == 400


def test_run_report_download_names_the_file_for_the_forecast_date(
        tmp_path, monkeypatch):
    """The run page's link, from the run's own workroot."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    rid = "20980101T000000-aaaaaa"
    w = tmp_path / "workroots" / rid
    _synth_run(w)
    (w / "results.json").write_text(json.dumps(
        {"forecast_date": "2098-01-03", "models": {}, "observed": {}}))
    srv._invalidate_scans()
    r = client.get(f"/runs/{rid}/report/download")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == (
        'attachment; filename="FluBNF-weekly-report-2098-01-03.html"')
    # a run with no results.json yet falls back to the run id, never to a
    # bare report.html
    bare = "20980108T000000-bbbbbb"
    b = tmp_path / "workroots" / bare
    b.mkdir(parents=True)
    (b / "report.html").write_text("<html><body>NO RESULTS</body></html>")
    r2 = client.get(f"/runs/{bare}/report/download")
    assert r2.status_code == 200
    assert f"FluBNF-weekly-report-{bare}.html" in \
        r2.headers["content-disposition"]


def test_both_report_surfaces_offer_the_download(tmp_path, monkeypatch):
    """A download nobody can find is the bug being fixed, so the link is
    pinned where the weekly report is already linked: the Output page (for
    the latest run and for each archived one) and the run page."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    rid = "20980101T000000-aaaaaa"
    w = tmp_path / "workroots" / rid
    w.mkdir(parents=True)
    (w / "report.html").write_text("<html><body>R</body></html>")
    (w / "results.json").write_text(json.dumps(
        {"forecast_date": "2098-01-03", "models": {"ensemble": {}},
         "observed": {}}))
    a = tmp_path / "archive" / "2098-01-03"
    a.mkdir(parents=True)
    (a / "report.html").write_text("<html>A</html>")
    srv._invalidate_scans()
    out = client.get("/output")
    assert out.status_code == 200
    assert 'href="/output/report"' in out.text          # inline view kept
    assert 'href="/output/report/download"' in out.text
    assert "/output/report/download?date=" in out.text  # archived ones too
    run = client.get(f"/runs/{rid}")
    assert run.status_code == 200
    assert f'href="/runs/{rid}/report"' in run.text     # inline view kept
    assert f'href="/runs/{rid}/report/download"' in run.text
