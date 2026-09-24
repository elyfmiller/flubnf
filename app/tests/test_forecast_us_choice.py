"""US national on the Forecast tab: a location of its own, and the FluSight
comparators drawn over a vintage run's fans.

US (national) is the 53rd checkbox. "all 52 jurisdictions" is the 52 alone;
the default run (a full hub submission) ticks both, and a custom pick runs
exactly what was ticked: US is never added behind the user's back.

A run's Forecasts card overlays the hub's recorded FluSight-ensemble and
FluSight-baseline forecasts for the same week, read with the
Retrospective's reader (playback._official_quantiles); a date the hub has
no file for yields no overlay and no toggle.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd                                 # noqa: E402
import pytest                                       # noqa: E402
from fastapi.testclient import TestClient           # noqa: E402

import flubnf.settings as fsettings                 # noqa: E402
from app.core import data as core_data              # noqa: E402
from app.core import playback                       # noqa: E402
from app.core import runs as runs_mod               # noqa: E402
from app.core import ttlcache                       # noqa: E402
from app.ui import pipeline as ui_pipeline          # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons  # noqa: E402
from app.ui import server as srv                    # noqa: E402
from app.ui import state as ui_state                # noqa: E402
from app.ui.routes import forecast as fc            # noqa: E402

client = TestClient(srv.app)
SATURDAY = "2025-12-06"
TEMPLATE = (Path(__file__).resolve().parents[1] / "ui" / "templates"
            / "forecast.html").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _isolated_state():
    status_before = dict(ui_state._status)
    form_before = dict(ui_state._last_form)
    ttlcache.clear_all()
    yield
    ui_state._status.clear(); ui_state._status.update(status_before)
    ui_state._last_form.clear(); ui_state._last_form.update(form_before)
    ttlcache.clear_all()


def _locations_frame():
    return pd.DataFrame({
        "abbreviation": ["US", "OH", "UT"],
        "location": ["US", "39", "49"],
        "location_name": ["US", "Ohio", "Utah"]})


@pytest.fixture
def started(tmp_path, monkeypatch):
    """/run with the engine faked: returns the list of specs it started."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(core_data, "vintage_path", lambda d: tmp_path)
    monkeypatch.setattr(core_data, "vintages", lambda: [SATURDAY])
    monkeypatch.setattr(fsettings, "load_locations", _locations_frame)
    out = []
    monkeypatch.setattr(ui_pipeline, "_run_all", lambda s: out.append(s))
    ui_state._status.update({"running": None})
    return out


def _post(locations):
    return client.post("/run", data={
        "forecast_date": SATURDAY, "locations": locations,
        "engine": "analogue", "mode": "vintage"}, follow_redirects=False)


@pytest.mark.parametrize("ticked, expected", [
    (["Ohio"], ["Ohio"]),                               # no US added
    (["Ohio", "US (national)"], ["Ohio", "US"]),
    (["US (national)"], ["US"]),
    (["all"], ["Ohio", "Utah"]),                        # the 52 alone
    (["all", "US (national)"], ["Ohio", "Utah", "US"]),  # the hub's 53
])
def test_a_run_fits_exactly_the_ticked_locations(started, ticked, expected):
    r = _post(ticked)
    assert r.status_code == 303
    assert len(started) == 1
    assert started[0].locations == expected


def test_the_progress_label_names_us_only_when_it_runs(started):
    _post(["Ohio"])
    assert ui_state._status["run_label"].endswith("1 state(s) · queued")
    ui_state._status.update({"running": None})
    _post(["Ohio", "US (national)"])
    assert ui_state._status["run_label"].endswith("1 state(s) + US · queued")


def test_the_run_scope_reads_without_us_for_a_state_run():
    assert runs_mod.locations_phrase(["California"]) == "1 state: California"
    assert fc._scope_label(["US"]) == "US only"


def test_the_default_form_is_the_full_hub_submission(monkeypatch):
    """A fresh console ticks all 52 AND US: the default real-time run is a
    complete hub submission, stated on the form rather than implied."""
    ui_state._last_form.clear()
    html = client.get("/forecast").text
    assert re.search(r'id="ck-all" value="all" name="locations"\s+checked', html)
    assert re.search(r'id="ck-us" name="locations" value="US \(national\)"\s+checked',
                     html)
    assert "<b>US (national)</b>" in html
    # the national box comes after the jurisdictions (the template's order)
    assert TEMPLATE.index('id="ck-us"') > TEMPLATE.index('class="ck-one"')


def test_the_form_script_keeps_us_apart_from_all():
    """Ticking all ticks US too; leaving all for a custom pick unticks it;
    the count names US apart ("all 52 + US", "1 + US selected")."""
    assert "if(CKUS) CKUS.checked=true;" in TEMPLATE
    assert "if(c.checked && all.checked){ all.checked=false; if(CKUS) CKUS.checked=false; }" in TEMPLATE
    assert "(us?' + US':'')" in TEMPLATE
    assert "US national is always fitted" not in TEMPLATE


def test_a_rerun_keeps_a_recorded_scope_without_us(tmp_path, monkeypatch,
                                                   started):
    spec = runs_mod.RunSpec(engine="analogue", forecast_date=SATURDAY,
                            locations=["Ohio"])
    led = runs_mod.Ledger()
    rid = led.open_run(spec, Path("pending"), {})
    led.close_run(rid, "stopped", {})
    r = client.post(f"/runs/{rid}/rerun", follow_redirects=False)
    assert r.status_code == 303
    assert [s.locations for s in started] == [["Ohio"]]


# ------------------------------------------------ the FluSight overlay

def _hub_file(root: Path, model: str, ref: str):
    d = root / "model-output" / model
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    for loc in ("US", "39", "06"):
        for h in (0, 1, 2, 3):
            for q, v in ((0.25, 90.0), (0.5, 100.0 + h), (0.75, 110.0)):
                rows.append({"reference_date": ref, "target": "wk inc flu hosp",
                             "horizon": h, "location": loc,
                             "output_type": "quantile",
                             "output_type_id": q, "value": v})
    pd.DataFrame(rows).to_csv(d / f"{ref}-{model}.csv", index=False)


def test_the_overlay_reads_the_hub_forecasts_on_the_run_keys(tmp_path,
                                                            monkeypatch):
    monkeypatch.setattr(playback, "HUB", tmp_path)
    monkeypatch.setattr(fsettings, "load_locations", _locations_frame)
    _hub_file(tmp_path, "FluSight-ensemble", "2025-12-13")   # asof + 7
    got = fc._official_overlay(SATURDAY, ["Ohio", "US"])
    assert list(got) == ["FluSight-ensemble"]          # baseline file absent
    ens = got["FluSight-ensemble"]
    assert set(ens) == {"Ohio", "US"}                  # a location not run: left out
    # the hub's horizon 0 is the run's physical week 1
    assert set(ens["Ohio"]) == {"1", "2", "3", "4"}
    assert ens["Ohio"]["1"]["0.5"] == 100.0 and ens["Ohio"]["4"]["0.5"] == 103.0


def test_no_hub_file_means_no_overlay(tmp_path, monkeypatch):
    monkeypatch.setattr(playback, "HUB", tmp_path)
    assert fc._official_overlay(SATURDAY, ["Ohio"]) == {}
    assert fc._official_overlay("", ["Ohio"]) == {}
    # the toggle is cloned in only when there is something to draw
    assert "if(OFFMODELS.length && oslot && otpl)" in TEMPLATE
    assert 'id="fan-offctl"' in TEMPLATE
