"""The time a sandbox fit takes (app/core/sandbox.py): the cost model
scaled by this computer's last finished fit, a span before one has
finished, and the page while a fit runs (its time so far against the
estimate, Save and run off and counting, the server refusing a second
run). Hub-free and engine-free (conftest.sandbox_root fakes BNG2.pl).
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import sandbox as sb                       # noqa: E402
from app.ui import server as srv                         # noqa: E402
from app.ui import state as ui_state                     # noqa: E402

client = TestClient(srv.app)
FULL = sb.FULL_FIT_PARTICLES
QUICK = sb.DRY_RUN_PARTICLES


@pytest.fixture
def box(sandbox_root):
    return sandbox_root


def _meta(status="ok", seconds=None, n_obs=30, particles=FULL, model="m",
          run_id="20990101-000000_m", ratio=None):
    """A run's meta.json as prepare and run write it; `ratio` sets its
    seconds to that multiple of the cost model's prediction."""
    if ratio is not None:
        seconds = ratio * sb.eta_seconds(n_obs, particles)
    m = {"model": model, "status": status, "particles": particles,
         "n_obs": n_obs, "observed": [1.0] * n_obs, "run_id": run_id,
         "started_utc": "2099-01-01T00:00:00Z"}
    if seconds is not None:
        m["seconds"] = seconds
    return m


def _write_run(run_id, meta):
    d = sb.RUNS / run_id
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps(meta))
    return d


# ------------------------------------------------- the calibration maths

def test_a_runs_ratio_is_its_seconds_over_the_cost_model_for_its_own_size():
    # the walkthrough's laptop: 97 s where the cost model said 33
    m = _meta(n_obs=46, seconds=97.0)
    predicted = sb.eta_seconds(46, FULL)
    assert predicted == pytest.approx(33.0, abs=0.1)
    assert sb._run_ratio(m) == pytest.approx(97.0 / predicted)
    # the rows from observed when n_obs is missing (an older meta.json)
    del m["n_obs"]
    assert sb._run_ratio(m) == pytest.approx(97.0 / predicted)
    # a quick check is measured against its own particles
    q = _meta(particles=QUICK, ratio=12.0)
    assert sb._run_ratio(q) == pytest.approx(12.0)
    # only a finished run with a time can say
    for bad in (_meta(status="failed", seconds=40.0),
                _meta(status="stopped", seconds=40.0),
                _meta(status="running"), _meta(seconds=None),
                _meta(seconds=0.0), _meta(seconds=float("nan")),
                {**_meta(seconds=40.0), "particles": "lots"}):
        assert sb._run_ratio(bad) is None, bad


def test_the_ratio_comes_from_the_newest_full_fit_of_any_model():
    runs = [_meta(model="b", particles=QUICK, ratio=12.0),     # newest
            _meta(model="b", status="failed", seconds=5.0),
            _meta(model="a", ratio=2.9),                       # a full fit
            _meta(model="c", ratio=3.3)]                       # older one
    assert sb.eta_ratio(runs) == pytest.approx(2.9)
    # with no full fit, the newest finished run of any size
    assert sb.eta_ratio([_meta(status="stopped", seconds=1.0),
                         _meta(particles=QUICK, ratio=12.0),
                         _meta(particles=2000, ratio=4.0)]) == pytest.approx(12.0)
    # a run above the full fit's particles counts as one
    assert sb.eta_ratio([_meta(particles=QUICK, ratio=12.0),
                         _meta(particles=20_000, ratio=3.1)]) == pytest.approx(3.1)
    # before any run has finished here: no ratio
    assert sb.eta_ratio([]) is None
    assert sb.eta_ratio([_meta(status="running"), _meta(status="failed")]) is None


def test_the_ratio_reads_this_computers_runs_newest_first(box):
    _write_run("20990101-000000_a", _meta(model="a", ratio=3.3))
    _write_run("20990102-000000_b", _meta(model="b", ratio=2.9))
    _write_run("20990103-000000_b", _meta(model="b", particles=QUICK, ratio=12.0))
    assert sb.eta_ratio() == pytest.approx(2.9)


def test_the_estimate_is_the_cost_model_times_the_ratio():
    base = sb.eta_seconds(30, FULL)
    assert base == pytest.approx(22.8, abs=0.1)
    # one time once a fit has finished here: on a laptop at 2.9, the cost
    # model's 23 s is about 66 s
    lo, hi = sb.eta_span(30, FULL, 2.9)
    assert lo == hi == pytest.approx(66.2, abs=0.05)
    assert sb.eta_words(lo, hi) == "about 1:06"
    # linear in particles, as the page scales it
    assert sb.eta_span(30, 2 * FULL, 2.9)[0] == pytest.approx(2 * lo, abs=0.1)
    # before any: the span from the production machine to the laptops
    assert sb.eta_span(30, FULL, None) == (round(base * sb.ETA_FIRST_SPAN[0], 1),
                                           round(base * sb.ETA_FIRST_SPAN[1], 1))
    assert sb.eta_words(*sb.eta_span(30, FULL, None)) == "about 0:23 to 1:31"
    # it holds every laptop the walkthroughs timed (2.9 to 3.3 times)
    assert sb.ETA_FIRST_SPAN[0] <= 1 and sb.ETA_FIRST_SPAN[1] > 3.3


# ------------------------------------------------------------- the words

def test_times_are_written_m_ss():
    assert [sb.clock(s) for s in (0, 9.9, 27, 59.9, 60, 600, 3599, 3600, 3725, -4)] == [
        "0:00", "0:09", "0:27", "0:59", "1:00", "10:00", "59:59", "1:00:00",
        "1:02:05", "0:00"]
    assert sb.eta_words(51.2, 51.4) == "about 0:51"
    assert sb.eta_words(40, 120) == "about 0:40 to 2:00"
    assert sb.eta_words(0.2, 0.7) == "about 0:01"              # never 0:00
    assert sb.eta_words(0, 0) == ""
    assert sb.eta_words(59.5, 59.5) == "about 1:00"            # half up


def test_the_live_line_counts_and_then_says_stopping_is_safe():
    assert sb.fitting_line(27, 51, 51) == "0:27 so far · about 0:51 in all"
    assert sb.fitting_line(27, 40, 120) == "0:27 so far · about 0:40 to 2:00 in all"
    # past 1.5 times the estimate (the span's top before calibration)
    assert sb.slow_after(51) == 76.5 and sb.slow_after(120) == 180
    assert sb.fitting_line(76.5, 51, 51).startswith("1:16 so far")
    assert sb.fitting_line(76.6, 51, 51) == "Taking longer than usual. Stopping is safe."
    assert sb.fitting_line(179, 40, 120).startswith("2:59 so far")
    assert sb.fitting_line(181, 40, 120) == "Taking longer than usual. Stopping is safe."
    # a quick check (a second by the cost model) is never slow while the
    # engine starts
    assert sb.slow_after(1.2) == sb.ETA_SLOW_FLOOR_S == 30
    assert sb.fitting_line(8, 0.3, 1.2) == "0:08 so far · about 0:01 in all"
    assert sb.fitting_line(31, 0.3, 1.2) == "Taking longer than usual. Stopping is safe."
    # no estimate: the time only, never slow
    assert sb.fitting_line(5000, 0, 0) == "1:23:20 so far"


def test_a_runs_elapsed_time_is_from_its_start():
    import calendar
    m = {"started_utc": "2099-01-01T00:00:00Z"}
    t0 = float(calendar.timegm((2099, 1, 1, 0, 0, 0)))
    assert sb.run_elapsed(m, now=t0 + 27) == pytest.approx(27)
    assert sb.run_elapsed(m, now=t0 - 5) == 0             # a clock set back
    assert sb.run_elapsed({}, now=t0) == 0
    assert sb.run_elapsed({"started_utc": "soon"}, now=t0) == 0


# ------------------------------------------------- the run settings' estimate

def _eta_span_html(html):
    return re.search(r'<span class="sb-eta" id="sb-eta"[^>]*>.*?</span></span>',
                     html, flags=re.S).group(0)


def test_before_a_first_fit_the_estimate_is_a_span(box):
    sb.add_example("kinetics_example")
    n_obs = len(sb.read_exp(sb.read_model("kinetics_example")["data.exp"])["rows"])
    html = client.get("/sandbox?model=kinetics_example").text
    eta = _eta_span_html(html)
    lo, hi = sb.eta_span(n_obs, FULL, None)
    assert f'data-low="{lo}" data-high="{hi}"' in eta and " hidden" not in eta
    words = sb.eta_words(lo, hi)
    assert re.fullmatch(r"about \d+:\d\d to \d+:\d\d", words)
    assert f'<span class="sb-eta-v">{words}</span>' in eta
    assert "A span until a fit finishes on this computer" in eta


def test_after_a_finished_fit_the_estimate_is_one_time_from_its_ratio(box):
    sb.add_example("kinetics_example")
    n_obs = len(sb.read_exp(sb.read_model("kinetics_example")["data.exp"])["rows"])
    # another model's full fit, 3 times the cost model, is this computer's
    _write_run("20990101-000000_other", _meta(model="other", ratio=3.0))
    html = client.get("/sandbox?model=kinetics_example").text
    eta = _eta_span_html(html)
    t = round(sb.eta_seconds(n_obs, FULL) * 3.0, 1)
    assert f'data-low="{t}" data-high="{t}"' in eta
    assert f'<span class="sb-eta-v">{sb.eta_words(t, t)}</span>' in eta
    assert " to " not in sb.eta_words(t, t)
    assert "scaled by how long this computer&#39;s last fit took" in eta


# ------------------------------------------------------ while a fit runs

def _fitting(monkeypatch, model="kinetics_example", ago=20):
    """A prepared run of `model` as the live fit, started `ago` seconds ago."""
    w = sb.prepare(model)
    meta = json.loads((w / "meta.json").read_text())
    meta["status"] = "running"
    meta["started_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                        time.gmtime(time.time() - ago))
    (w / "meta.json").write_text(json.dumps(meta))
    monkeypatch.setitem(ui_state._sandbox_status, "running", w.name)
    return w


def _form(html, name="kinetics_example"):
    form = html[html.index(f'<form method="post" action="/sandbox/models/{name}/save" id="sbform"'):]
    return form[:form.index("</form>")]


def test_save_and_run_is_off_and_counting_while_a_run_of_this_model_fits(box, monkeypatch):
    sb.add_example("kinetics_example")
    w = _fitting(monkeypatch)
    html = client.get(f"/sandbox?run={w.name}&model=kinetics_example").text
    form = _form(html)
    # both Save and run buttons: off, the guard kept, the fit's time so far
    runs = re.findall(r'<button class="gold" formaction="/sandbox/models/kinetics_example/run"[^>]*>[^<]*</button>', form)
    assert len(runs) == 2
    for b in runs:
        assert 'data-guard="sandbox-run" data-sb-fitting data-idle="Save and run" disabled>' in b
        assert re.search(r">Fitting… 0:2\d</button>$", b), b
    assert ">Save and run<" not in form
    # Check and Simulate data stay on
    assert re.search(r'<button type="button" id="sb-check">Check</button>', form)
    sim = re.search(r"<button formaction=\"/sandbox/models/kinetics_example/simulate-data\"[^>]*>", form).group(0)
    assert "disabled" not in sim
    # the form carries what sandbox.js counts from
    head = form[:form.index(">")]
    lo, hi = sb.eta_span(len(sb.read_exp(sb.read_model("kinetics_example")["data.exp"])["rows"]),
                         QUICK, None)
    assert f'data-fitting="{w.name}"' in head
    assert re.search(r'data-started="\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"', head)
    assert f'data-low="{lo}" data-high="{hi}" data-slow-after="{sb.slow_after(hi)}"' in head
    # the Results line in place of the bar that never moved, Stop beside it
    assert "uk-progress" not in html
    line = re.search(r'<span id="sb-live">([^<]*)</span>', html).group(1)
    assert re.fullmatch(r"0:2\d so far · " + re.escape(sb.eta_words(lo, hi)) + " in all", line), line
    assert f'action="/sandbox/runs/{w.name}/stop"' in html
    # no full fit offered beside a live run
    assert "Run the full fit" not in html


def test_save_and_run_is_off_while_an_older_run_of_this_model_is_open(box, monkeypatch):
    sb.add_example("kinetics_example")
    old = sb.prepare("kinetics_example")
    meta = json.loads((old / "meta.json").read_text())
    meta.update(status="ok", seconds=5.0)
    (old / "meta.json").write_text(json.dumps(meta))
    _fitting(monkeypatch)
    html = client.get(f"/sandbox?run={old.name}&model=kinetics_example").text
    form = _form(html)
    assert form.count('data-sb-fitting data-idle="Save and run" disabled>Fitting… 0:') == 2
    assert 'id="sb-live"' not in html                    # the open run is not live
    # a quick check that worked, but its full fit waits for the live one
    assert "Run the full fit" not in html


def test_a_live_run_slow_past_its_estimate_says_stopping_is_safe(box, monkeypatch):
    sb.add_example("kinetics_example")
    w = _fitting(monkeypatch, ago=3600)
    html = client.get(f"/sandbox?run={w.name}&model=kinetics_example").text
    assert '<span id="sb-live">Taking longer than usual. Stopping is safe.</span>' in html
    assert re.search(r">Fitting… 1:00:0\d</button>", html)


def test_another_models_live_fit_leaves_save_and_run_to_the_guard(box, monkeypatch):
    sb.add_example("kinetics_example")
    sb.add_example("sir_example")
    _fitting(monkeypatch, model="sir_example")
    form = _form(client.get("/sandbox?model=kinetics_example").text)
    assert form.count(">Save and run<") == 2 and "data-sb-fitting" not in form
    assert "data-fitting=" not in form[:form.index(">")]
    assert 'data-guard="sandbox-run"' in form


def test_the_server_refuses_a_second_run_of_a_fitting_model(box, monkeypatch):
    sb.add_example("kinetics_example")
    w = _fitting(monkeypatch)
    ran = []
    monkeypatch.setattr(sb, "run", lambda workroot, width=1: ran.append(workroot))
    before = sorted(p.name for p in sb.RUNS.iterdir())
    files = sb.read_model("kinetics_example")
    r = client.post("/sandbox/models/kinetics_example/run",
                    data={"model_bngl": files["model.bngl"], "data_exp": files["data.exp"],
                          "priors_conf": files["priors.conf"], "particles": "200"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/sandbox?model=kinetics_example"
    # the edits are saved, the run is not
    flash = ui_state._status.pop("flash", "")
    assert flash.endswith(f"Not started: sandbox run {w.name} is still fitting."), flash
    assert sorted(p.name for p in sb.RUNS.iterdir()) == before and ran == []
    assert ui_state._sandbox_status["running"] == w.name    # the live fit untouched
