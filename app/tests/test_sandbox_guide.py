"""The sandbox as a place to learn in (app/core/sandbox.py): the model at
its written values beside the data (expected_counts, Check's scale
warning, Simulate data), a prior that disagrees with the model, the
run's outcome in plain words (fit_health), run settings refused before
the engine, and the examples themselves. BNG2.pl is faked: the fake
writes the network and, for a simulate action, the ODE solution of the
skeleton's one conversion A -> B + Tally at rate k.
"""
import json
import math
import re
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import contactmap as cm                    # noqa: E402
from app.core import sandbox as sb                       # noqa: E402

NET = """begin parameters
    1 k 0.5
end parameters
begin species
    1 A() 100
    2 B() 0
    3 Tally() 0
end species
begin reactions
    1 1 2,3 k #_R1
end reactions
"""


def _param(text, name):
    return float(re.search(rf"^\s*{name}\s+(\S+)", text, flags=re.M).group(1))


@pytest.fixture
def box(sandbox_root, monkeypatch, tmp_path):
    """BNG2.pl present and faked; a simulate action writes cm.gdat with
    the exact solution of the skeleton (Tobs = scale*N*(1 - exp(-k t)))."""
    bng = tmp_path / "BNG2.pl"
    bng.write_text("# stub\n")
    monkeypatch.setattr(sb, "BNG", str(bng))

    def fake_bng(cmd, **kw):
        cwd = Path(kw.get("cwd", "."))
        if not (cwd / "cm.bngl").is_file():          # a run's own netgen
            (cwd / "m.net").write_text("# net\n")
            return types.SimpleNamespace(stdout="", stderr="", returncode=0)
        src = (cwd / "cm.bngl").read_text()
        (cwd / "cm.net").write_text(NET)
        m = re.search(r"t_end=>(\d+)", src.split("begin actions")[-1])
        if m and "simulate(" in src.split("begin actions")[-1]:
            k, scale, n = (_param(src, "k__FREE"), _param(src, "scale__FREE"),
                           _param(src, "N"))
            rows = ["# time A B T_Cum Tobs"]
            for t in range(int(m.group(1)) + 1):
                done = n * (1 - math.exp(-k * t))
                rows.append(f"{t} {n - done} {done} {done} {scale * done}")
            (cwd / "cm.gdat").write_text("\n".join(rows) + "\n")
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)
    monkeypatch.setattr(cm.subprocess, "run", fake_bng)
    return sandbox_root


def _files():
    return dict(sb.skeleton("mine"))


# ------------------------------------------------- the model as written

def test_the_skeleton_counts_are_the_models_own_weekly_increments(box):
    """Row t is the increment over the week ending at t, the model
    starting one week before the first row (pf_start_time = -1)."""
    files = _files()
    rows = sb.read_exp(files["data.exp"])["rows"]
    ex = sb.expected_counts(files)
    assert ex["column"] == "Tobs" and ex["times"] == [r[0] for r in rows]
    assert [round(v) for v in ex["expected"]] == [r[1] for r in rows]
    # and the two first weeks differ: no week is counted twice
    assert rows[0][1] > rows[1][1] > rows[2][1]


def test_check_puts_the_model_beside_the_data_and_warns_on_a_tenfold_scale(box):
    files = _files()
    r = sb.check(files)
    assert r["ok"] and r["warnings"] == []
    assert r["facts"]["at_start"].startswith("at its written values the model gives")
    files["model.bngl"] = files["model.bngl"].replace(
        "N            100000", "N            5000000")
    r = sb.check(files)
    assert r["ok"]                                        # a warning, never a block
    assert any("50 times the data's" in w and "check N, the starting state"
               in w for w in r["warnings"]), r["warnings"]


def test_a_written_value_outside_its_prior_is_named(box):
    files = _files()
    files["model.bngl"] = files["model.bngl"].replace("k__FREE      0.5",
                                                      "k__FREE      5")
    text = " ".join(sb.check(files)["warnings"])
    assert "k__FREE is written as 5 in model.bngl but its prior runs 0.05 to 2.0" in text


def test_simulate_data_writes_counts_from_the_model_and_drops_the_sidecar(box):
    sb.new_model("mine")
    d = sb.MODELS / "mine"
    (d / sb.SOURCE_FILE).write_text("{}")
    facts = sb.simulate_data("mine", seed=4)
    assert facts == {"rows": sb.SKELETON_WEEKS, "r": 10.0, "seed": 4,
                     "column": "Tobs"}
    exp = sb.read_exp(sb.read_model("mine")["data.exp"])
    assert exp["columns"] == ["time", "T_weekly"]
    assert [r[0] for r in exp["rows"]] == list(range(sb.SKELETON_WEEKS))
    assert all(float(r[1]).is_integer() and r[1] >= 0 for r in exp["rows"])
    assert not (d / sb.SOURCE_FILE).exists()
    # the same seed draws the same counts
    again, _ = sb.synthetic_exp(sb.skeleton("mine"), seed=4)
    assert again == sb.read_model("mine")["data.exp"]


def test_simulate_needs_a_cumulative_observable_and_whole_weeks(box):
    files = _files()
    files["priors.conf"] = files["priors.conf"].replace(
        "pf_cumulative_observable = Tobs\n", "")
    with pytest.raises(sb.SandboxError, match="no pf_cumulative_observable"):
        sb.expected_counts(files)
    files = _files()
    files["data.exp"] = "# time y\n0.5 3\n1.5 4\n"
    with pytest.raises(sb.SandboxError, match="whole-number times"):
        sb.expected_counts(files)


def test_the_simulate_route_fills_data_exp(box):
    from fastapi.testclient import TestClient
    from app.ui import server as srv
    from app.ui import state as ui_state
    client = TestClient(srv.app)
    sb.new_model("mine")
    before = sb.read_model("mine")["data.exp"]
    r = client.post("/sandbox/models/mine/simulate-data", data={},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/sandbox?model=mine"
    assert sb.read_model("mine")["data.exp"] != before
    assert "simulated from the model at the values written" in ui_state._status["flash"]


# ------------------------------------------------ the run in plain words

def _res(particles=200, ess=(), params=None, sample=200, distinct=200,
         observed=(), traj=None):
    return {"meta": {"particles": particles, "observed": list(observed)},
            "ess": [{"t": float(t), "ess": e, "distinct": d, "degenerate": g}
                    for t, e, d, g in ess],
            "params": params or [], "sample": sample, "distinct": distinct,
            "traj": traj}


def test_a_collapsed_fit_says_so_and_what_to_try():
    p = [{"name": "Reff__FREE", "p5": 2.003, "p50": 2.003, "p95": 2.003}]
    h = sb.fit_health(_res(ess=[(0, 11.3, 8, 0), (1, 2.1, 1, 1)], params=p,
                           distinct=1))
    assert h["level"] == "collapsed" and h["at"] == 0.0
    assert h["title"] == "The fit collapsed"
    assert "from t = 0 on" in h["says"] and "not a real estimate" in h["says"]
    assert h["tries"][0].startswith("Run the full fit with 10,000 particles")
    assert "first data row" in h["tries"][1]
    assert any("Jitter" in t for t in h["tries"])


def test_a_thin_fit_is_rough_and_a_varied_one_healthy():
    h = sb.fit_health(_res(particles=10_000, sample=1000, distinct=900,
                           ess=[(0, 5000, 9000, 0), (1, 700, 800, 0)]))
    assert h["level"] == "rough" and h["at"] == 1.0
    assert "lowest ESS 700 of 10,000" in h["says"]
    assert not any("full fit" in t for t in h["tries"])   # it was one
    h = sb.fit_health(_res(particles=10_000, sample=1000, distinct=900,
                           ess=[(0, 5000, 9000, 0), (1, 4000, 8000, 0)]))
    assert h["level"] == "good" and h["tries"] == []
    assert h["says"] == ("The particles stayed varied at every week "
                         "(lowest ESS 4,000 of 10,000).")
    assert sb.fit_health(_res()) is None                  # nothing to read


def test_a_band_that_misses_the_data_is_named():
    traj = {"q10": [1, 1, 1, 1], "q50": [2, 2, 2, 2], "q90": [3, 3, 3, 3]}
    h = sb.fit_health(_res(particles=10_000, sample=1000, distinct=900,
                           ess=[(0, 5000, 9000, 0)], observed=[2, 9, 9, 9],
                           traj=traj))
    assert h["misses"] and "Only 1 of the 4 data points" in h["says"]
    assert any("the model, not the filter" in t for t in h["tries"])


def test_results_carry_the_health(box):
    sb.add_example("kinetics_example")
    w = sb.prepare("kinetics_example", particles=100)
    assert sb.results(w)["health"] is None                # no output yet


# ------------------------------------------------------- run settings

@pytest.mark.parametrize("kw, words", [({"jitter": 1.5}, "not between 0 and 1"),
                                       ({"jitter": 0}, "not between 0 and 1"),
                                       ({"seed": -3}, "negative")])
def test_settings_the_engine_would_refuse_are_refused_first(box, kw, words):
    sb.add_example("kinetics_example")
    with pytest.raises(sb.SandboxError, match=words):
        sb.prepare("kinetics_example", **kw)
    assert not sb.RUNS.exists() or not any(sb.RUNS.iterdir())


# ------------------------------------------------------------ examples

def test_every_example_says_its_data_were_simulated_from_it():
    for e in sb.list_examples():
        bngl = (sb.EXAMPLES / e / "model.bngl").read_text()
        words = " ".join(l.lstrip("# ").strip() for l in bngl.splitlines()
                         if l.startswith("#"))
        assert "were simulated from this model at the values written" in words, e


def test_the_template_marks_what_to_edit_and_fits_as_shipped(box):
    assert "seihr_template" in sb.list_examples()
    files = {f: (sb.EXAMPLES / "seihr_template" / f).read_text()
             for f in sb.REQUIRED}
    assert files["model.bngl"].count("# EDIT") >= 8
    priors, keys = sb.split_priors(files["priors.conf"])
    assert keys["pf_cumulative_observable"] == "Hobs"
    assert sorted(p.split()[2] for p in priors) == ["Reff__FREE", "mult__FREE",
                                                    "r__FREE"]
    note = sb._first_comment(sb.EXAMPLES / "seihr_template" / "model.bngl")
    assert note.startswith("A template for a new respiratory pathogen")
    assert note.endswith("weekly hospital admissions.")


# ------------------------------------------------------------- the pages

def _client():
    from fastapi.testclient import TestClient
    from app.ui import server as srv
    return TestClient(srv.app)


def _finish(w, collapsed=False):
    """What the engine writes for a finished run (as test_sandbox_export
    fakes it); collapsed: one parameter vector, ESS 2, and the engine's
    own warnings on its stderr."""
    import numpy as np
    meta = json.loads((w / "meta.json").read_text())
    cell = w / f"{meta['model']}_r0"
    runs = cell / "out" / "Results" / "PF" / "Runs"
    runs.mkdir(parents=True)
    n = meta["particles"]
    (runs / "params_0.txt").write_text(
        "k__FREE\tscale__FREE\tr__FREE\n" + "\n".join(
            ("0.3 0.5 8.0" if collapsed else f"{0.2 + 0.001 * i} 0.5 8.0")
            for i in range(n)) + "\n")
    cols = meta["n_obs"] + meta["forecast_weeks"]
    np.savetxt(runs / "traj_noise_kinB_weekly_chain_0.txt",
               np.tile(np.array(meta["observed"] + [1.0] * meta["forecast_weeks"]),
                       (n, 1)))
    ess = (f"0\t11\t{n}\t8\t0\n1\t2\t{n}\t1\t1\n" if collapsed
           else f"0\t{0.8 * n}\t{n}\t{n}\t0\n")
    (cell / "out" / "Results" / "PF" / "ess_0.txt").write_text(
        "# t\tess\tparticles\tdistinct\tdegenerate\n" + ess)
    if collapsed:
        (w / "pf_runner_0.err").write_text(
            "WARNING: min ESS 2 is under 2% of 200 particles: the cloud collapsed\n")
    meta["status"] = "ok"
    (w / "meta.json").write_text(json.dumps(meta))


def test_a_collapsed_quick_check_explains_itself_and_offers_the_full_fit(box):
    sb.add_example("kinetics_example")
    w = sb.prepare("kinetics_example", particles=200, jitter=0.2, seed=3)
    _finish(w, collapsed=True)
    html = _client().get(f"/sandbox?model=kinetics_example&run={w.name}").text
    assert '<span class="pill sbh sbh-collapsed">The fit collapsed</span>' in html
    assert "What to try" in html
    # the engine's words stay, folded under their own summary
    assert "<summary>Engine messages</summary>" in html
    assert "the cloud collapsed" in html
    # one click to the full fit, with this run's other settings
    form = html[html.index('class="row sbfull"') - 80:]
    form = form[:form.index("</form>")]
    assert 'action="/sandbox/models/kinetics_example/run"' in form
    for field, value in (("particles", "10000"), ("jitter", "0.2"),
                         ("forecast_weeks", "4"), ("seed", "3")):
        assert f'name="{field}" value="{value}"' in form, field
    assert ">Run the full fit (10,000 particles)<" in form


def test_a_healthy_full_fit_says_so_and_offers_nothing_more(box):
    sb.add_example("kinetics_example")
    w = sb.prepare("kinetics_example", particles=10_000)
    _finish(w)
    html = _client().get(f"/sandbox?model=kinetics_example&run={w.name}").text
    assert '<span class="pill sbh sbh-good">The fit looks healthy</span>' in html
    assert "sbfull" not in html and "What to try" not in html


def test_a_first_run_defaults_to_the_full_fit(box):
    sb.add_example("kinetics_example")
    html = _client().get("/sandbox?model=kinetics_example").text
    assert '<option value="full" selected>Full fit (10,000)</option>' in html
    assert 'id="sb-particles" type="number" value="10000"' in html


def test_the_gallery_guides_a_first_visit(box):
    html = _client().get("/sandbox").text
    # no models yet: How the Sandbox works is open
    assert '<details class="card sbhow" open>' in html
    assert "<strong>Start a model.</strong>" in html
    # the template comes first and is the default start, with its note
    start = html[html.index('id="sbnew-start"'):]
    start = start[:start.index("</select>")]
    assert start.index('label="Templates"') < start.index('label="Examples"')
    assert '<option value="example:seihr_template" data-note="A template' in start
    assert 'selected>seihr_template</option>' in start
    assert 'value="skeleton"' in start
    about = html[html.index('id="sbnew-about"'):]
    assert about.split(">", 1)[1].startswith("A template for a new respiratory")
    # with a model the card starts folded
    sb.add_example("sir_example")
    assert '<details class="card sbhow">' in _client().get("/sandbox").text


def test_the_workbench_carries_the_help_menu_and_simulate(box):
    sb.add_example("sir_example")
    html = _client().get("/sandbox?model=sir_example").text
    assert "<summary>How it works</summary>" in html
    assert html.index("<summary>How it works</summary>") < html.index("<summary>Manage</summary>")
    assert 'formaction="/sandbox/models/sir_example/simulate-data"' in html
