"""The fixes from the 2026-10-13 Sandbox audit (students' "hits and
misses"): a run the engine refuses says why; a refusal keeps its remedy;
this computer's missing pieces are named before a run is tried; a
half-made run leaves no folder; run settings are read as typed; Save
never stalls on a run setting; a freshly picked dataset shows its own
weeks; Set N refuses before writing. Check's own fixes are in
test_sandbox_check.py. BNG2.pl and the engine are faked.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import datasets as D                       # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf as pf_engine             # noqa: E402
from app.tests.test_sandbox_upload import GROUPED        # noqa: E402
from app.ui import server as srv                         # noqa: E402
from app.ui import state as ui_state                     # noqa: E402

client = TestClient(srv.app)


@pytest.fixture
def box(sandbox_root):
    return sandbox_root


def _post(url, data):
    return client.post(url, data=data, follow_redirects=False)


def _flash():
    return (ui_state._status.get("flash") or "",
            ui_state._status.get("flash_detail") or "")


def _no_runs():
    return not sb.RUNS.exists() or not any(sb.RUNS.iterdir())


def _results(html):
    return html[html.index('id="results"'):html.index("sb-runfacts")]


# ------------------------------------------- a run the engine refuses

def test_an_engine_refusal_is_the_runs_error_and_offers_no_full_fit(box, monkeypatch):
    # the runner records "FAIL: <reason>" per cell and writes nothing to
    # stderr: that reason is what the page shows for the failed run
    sb.add_example("kinetics_example")
    w = sb.prepare("kinetics_example")
    said = "FAIL: \"'Cobs' is not an observable of the model\""
    monkeypatch.setattr(pf_engine, "execute",
                        lambda root, width=1: {"kinetics_example_r0": said})
    meta = sb.run(w)
    assert meta["status"] == "failed" and meta["error"] == said
    html = client.get(f"/sandbox?model=kinetics_example&run={w.name}").text
    assert "is not an observable of the model" in _results(html)
    assert "Run the full fit" not in html
    # no outcome at all is said too
    monkeypatch.setattr(pf_engine, "execute", lambda root, width=1: {})
    assert sb.run(sb.prepare("kinetics_example"))["error"] == (
        "the engine reported no outcome for the run")


@pytest.mark.parametrize("status", ["stopped", "interrupted", "ok"])
def test_the_full_fit_is_offered_only_after_a_quick_check_that_worked(box, status):
    sb.add_example("kinetics_example")
    w = sb.prepare("kinetics_example", particles=200)
    sb.mark(w, "running" if status == "interrupted" else status)  # no live fit
    html = client.get(f"/sandbox?model=kinetics_example&run={w.name}").text
    assert ("Run the full fit" in html) == (status == "ok")


# ---------------------------------------- refusals keep their remedy

def test_split_reason_keeps_the_remedy_in_the_tip():
    assert sb.split_reason("short") == ("short", "")
    assert sb.split_reason("first line\nsecond line") == ("first line", "second line")
    msg = pf_engine.perl_missing_message("win32")
    notice, tip = sb.split_reason(msg)
    assert notice == "Perl was not found on PATH."
    assert "install Strawberry Perl" in tip and len(notice) <= 200
    # a path is never cut at an initial, a parenthesis or a quoted span
    for path in ("C:\\Users\\J. Smith\\flubnf", "/Users/J. Q. Public/flubnf"):
        for said in (f"The PyBNF fork at {path} does not provide fit_type = pf: "
                     "there is no such directory. ",
                     f"The engine's Python is missing ({path}. Bin) so no fit "
                     "can start. ",
                     f"PF configuration cannot express a path: '{path}. X'. "):
            notice, tip = sb.split_reason(said + "To install it, " + "x " * 120)
            assert notice == said.strip(), notice
            assert tip.startswith("To install it, ")
    words = "word " * 80                           # no sentence end to split at
    notice, tip = sb.split_reason(words.strip())
    assert notice.endswith(" ...") and len(notice) <= 205
    assert (notice[:-4] + " " + tip).split() == words.split()


@pytest.mark.parametrize("why, notice, remedy", [
    ("perl", "Perl was not found on PATH.", "PATH"),
    ("engine", "does not provide fit_type = pf", "Downloads"),
    ("python", "The engine's Python is missing", "FLUBNF_PY_ENGINE"),
])
def test_a_preflight_refusal_flashes_its_reason_and_its_remedy(box, monkeypatch,
                                                                why, notice, remedy):
    sb.add_example("kinetics_example")
    if why == "perl":
        monkeypatch.setattr(pf_engine, "perl_available", lambda: False)
    elif why == "engine":
        monkeypatch.setattr(pf_engine, "engine_available", lambda: False)
    else:
        monkeypatch.setattr(pf_engine, "PY310", Path("/nonexistent/bin/python"))
    _post("/sandbox/run", {"model": "kinetics_example"})
    msg, detail = _flash()
    assert msg.startswith("Not started: ") and notice in msg
    # the remedy is shown: in the tip, or on the line when the whole
    # reason is short (FluBNF.bat's remedy on Windows is)
    assert remedy in msg + detail, (msg, detail)
    assert _no_runs()                                       # nothing made


# --------------------------------------- what this computer lacks

def test_the_workbench_names_what_this_computer_lacks(box, monkeypatch):
    sb.add_example("kinetics_example")
    html = client.get("/sandbox?model=kinetics_example").text
    assert 'id="sb-machine"' not in html                    # ready here
    monkeypatch.setattr(pf_engine, "perl_available", lambda: False)
    html = client.get("/sandbox?model=kinetics_example").text
    assert 'id="sb-machine"' in html
    assert "This computer cannot fit yet:</strong> Perl was not found on PATH." in html
    assert 'id="sb-machine"' not in client.get("/sandbox").text   # the gallery


def test_a_half_installed_engine_is_refused_before_a_folder_is_made(box, monkeypatch):
    sb.add_example("kinetics_example")
    monkeypatch.setattr(pf_engine, "PY310", Path("/nonexistent/bin/python"))
    with pytest.raises(sb.SandboxError, match="The engine's Python is missing"):
        sb.prepare("kinetics_example")
    assert _no_runs()


# ---------------------------------------- no half-made run folders

def test_a_folder_with_a_space_is_refused_in_words_with_nothing_made(
        sandbox_root, tmp_path, monkeypatch):
    # no space-free short form (Windows usually has one, and uses it)
    monkeypatch.setattr(pf_engine, "_short_path_win", lambda s: None)
    spaced = tmp_path / "box with space" / "sandbox"
    monkeypatch.setattr(sb, "SANDBOX", spaced)
    monkeypatch.setattr(sb, "MODELS", spaced / "models")
    monkeypatch.setattr(sb, "RUNS", spaced / "runs")
    sb.add_example("kinetics_example")
    with pytest.raises(sb.SandboxError, match="path containing a space"):
        sb.prepare("kinetics_example")
    assert not any((spaced / "runs").iterdir())


def test_a_model_that_does_not_generate_leaves_no_run_folder(box):
    sb.add_example("kinetics_example")
    files = sb.read_model("kinetics_example")
    sb.save_model("kinetics_example",
                  {"model.bngl": files["model.bngl"] + "\n# broken\n"})
    with pytest.raises(sb.SandboxError, match="could not generate the network"):
        sb.prepare("kinetics_example")
    assert _no_runs()


def test_a_network_that_takes_too_long_is_refused_in_words(box, monkeypatch):
    sb.add_example("kinetics_example")

    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
    monkeypatch.setattr(sb.subprocess, "run", slow)
    with pytest.raises(sb.SandboxError, match="did not finish the model's actions"):
        sb.prepare("kinetics_example")
    assert _no_runs()


# --------------------------------------------- run settings as typed

def test_run_settings_are_read_as_typed_and_refused_in_words(box, monkeypatch):
    sb.add_example("kinetics_example")
    monkeypatch.setattr(sb, "run", lambda w, width=1: {"status": "ok"})
    files = sb.read_model("kinetics_example")
    r = _post("/sandbox/models/kinetics_example/run",
              {**{k: files[f] for k, f in (("model_bngl", "model.bngl"),
                                           ("data_exp", "data.exp"),
                                           ("priors_conf", "priors.conf"))},
               "particles": "1e4", "jitter": "0.15"})
    assert r.status_code == 303
    assert "started with 10000 particles" in _flash()[0]
    ui_state._status.pop("flash", None)
    edited = files["model.bngl"] + "# my edit\n"
    r = _post("/sandbox/models/kinetics_example/run",
              {"model_bngl": edited, "particles": "lots"})
    assert r.status_code == 303 and r.headers["location"] == (
        "/sandbox?model=kinetics_example")
    assert "Not started: particles 'lots' is not a number" in _flash()[0]
    assert sb.read_model("kinetics_example")["model.bngl"] == edited  # kept
    r = _post("/sandbox/run", {"model": "kinetics_example", "seed": "1.5"})
    assert r.status_code == 303
    assert "seed '1.5' is not a whole number" in _flash()[0]


def test_save_and_the_data_buttons_skip_the_run_settings_checks(store):
    # a run setting out of its range must not stop Save, Load, Upload or
    # Simulate: those buttons skip the browser's checks; the run buttons keep them
    client.post("/sandbox/models/mine/upload-data", data={"kind": "count"},
                files={"csv": ("grouped.csv", GROUPED.encode(), "text/csv")})
    html = client.get("/sandbox?model=mine").text
    form = html[html.index('id="sbform"'):html.index("</form>", html.index('id="sbform"'))]
    assert 'class="sb-default" tabindex="-1" aria-hidden="true" formnovalidate>' in form
    assert 'formaction="/sandbox/models/mine/save" formnovalidate>Save' in form
    for action in ("fill-data", "upload-data", "simulate-data"):
        i = form.index(f'formaction="/sandbox/models/mine/{action}"')
        assert "formnovalidate" in form[i:form.index(">", i)], action
    runs = [j for j in range(len(form))
            if form.startswith('formaction="/sandbox/models/mine/run"', j)]
    assert len(runs) == 2
    for i in runs:
        assert "formnovalidate" not in form[i:form.index(">", i)]


# ------------------------------------------------------------ pages

def test_another_models_run_falls_back_to_this_models_newest(box):
    sb.add_example("kinetics_example")
    sb.add_example("sir_example")
    mine = sb.prepare("kinetics_example")
    other = sb.prepare("sir_example")
    html = client.get(f"/sandbox?run={other.name}&model=kinetics_example").text
    assert f'data-run="{mine.name}"' in html and "No runs yet" not in html
    html = client.get("/sandbox?run=20990101-000000_gone&model=kinetics_example").text
    assert f'data-run="{mine.name}"' in html


def test_name_fields_say_what_they_take(box):
    sb.add_example("kinetics_example")
    for url in ("/sandbox", "/sandbox?model=kinetics_example"):
        assert 'title="Letters, digits, _ and -, starting with a letter or digit (no spaces), up to 64 characters"' in (
            client.get(url).text)


def test_ctrl_s_saves_from_anywhere_on_the_workbench():
    js = (Path(__file__).resolve().parents[1] / "ui/static/sandbox.js").read_text()
    i = js.index("var saveBtn")
    assert "document.addEventListener('keydown'" in js[i:i + 200]


# ------------------------------------------------------------ data

@pytest.fixture
def store(box, tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    monkeypatch.setattr(sb, "locations", lambda: [])       # no hub here
    monkeypatch.setattr(sb, "vintages", lambda: [])
    sb.new_model("mine")
    return box


def test_a_fresh_dataset_shows_its_own_weeks(store):
    r = client.post("/sandbox/models/mine/upload-data", data={"kind": "count"},
                    files={"csv": ("grouped.csv", GROUPED.encode(), "text/csv")},
                    follow_redirects=False)
    assert len(D.list_datasets()) == 1
    for url in (r.headers["location"], "/sandbox?model=mine"):  # no hub: the only source
        html = client.get(url).text
        assert '<input id="sbfill-start" name="start" type="date" value="2022-01-01">' in html, url
        assert '<input id="sbfill-end" name="end" type="date" value="2022-03-05">' in html, url


def test_set_n_on_a_model_without_n_loads_nothing(store):
    client.post("/sandbox/models/mine/upload-data", data={"kind": "count"},
                files={"csv": ("grouped.csv", GROUPED.encode(), "text/csv")},
                follow_redirects=False)
    (ds,) = D.list_datasets()
    files = sb.read_model("mine")
    sb.save_model("mine", {"model.bngl": files["model.bngl"].replace(
        "N            100000", "Npop         100000").replace("N*", "Npop*")})
    before = sb.read_model("mine")["data.exp"]
    with pytest.raises(sb.SandboxError, match="no line named N to set, so nothing was loaded"):
        sb.fill_data("mine", "Overall", "", "", dataset=ds.id, set_pop=True)
    assert sb.read_model("mine")["data.exp"] == before
    assert sb.read_data_source("mine") is None
