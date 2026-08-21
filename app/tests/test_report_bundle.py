"""Weekly report staleness contract: the run persists an inputs bundle
(report_inputs.json) beside report.html; serving a report whose builder
sources moved on rebuilds it from that bundle, once; a fresh report is
served verbatim; a broken bundle degrades to the stored file; reports that
predate the bundle get a conservative serve-time theme carry or a quiet
line, with the stored file never modified."""
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
