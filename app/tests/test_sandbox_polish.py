"""The Sandbox's words and small defects (bug hunt 2026-10-25, G31).

  * The diagram's captions count the model's rules and the network's
    reactions, a rule or reaction that draws no arrow too (SB-07), and its
    labels follow the box's width and the page's text size (UI-19), a
    change of size with no reload too.
  * Load, Simulate and Upload save and name only the files that changed,
    and data.exp only when they did not replace it after all (SB-18);
    "1 week" (SB-25).
  * Without the engine, the page's notice says so in words and a refused
    run points at it, or says the reason when the model is not here to
    open (SB-19).
  * One rule between a run's summary and the section under it (SB-20).
  * What changed names its settings and writes 10,000 (SB-21).
  * A dataset start has no Oracle step card; the step's donors are said
    in words and w once (SB-22).
  * The engine keys table leaves out the engine's plumbing (SB-23).
  * Why Load is off is said once (SB-24).
  * The run zip carries the engine's messages (SB-26).
  * A model copied from an example changed when it was copied (UI-16).
"""
import io
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import contactmap                          # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.ui import server as srv                         # noqa: E402
from app.ui import state as ui_state                     # noqa: E402
from app.ui.routes import sandbox as ui_sandbox          # noqa: E402
from test_sandbox_export import _finish                  # noqa: E402

client = TestClient(srv.app)
UI = Path(__file__).resolve().parents[1] / "ui"

SITES = """begin model
begin molecule types
 L(r)
 R(l,p~0~1)
 Tally()
end molecule types
begin reaction rules
 L(r)+R(l)->L(r!1).R(l!1)+Tally() k1
 R(p~0)->R(p~1) k2
end reaction rules
end model
"""


def _flash():
    return ui_state._status.get("flash") or ""


# --------------------------------------------- SB-07, UI-19: the diagram

def test_the_captions_count_rules_and_reactions_drawn_or_not():
    flow = contactmap.rule_flow(SITES)
    # the state change draws no arrow; it is still one of the 2 rules
    assert {e["rule"] for e in flow["edges"]} == {"1"}
    assert flow["rules"] == 2
    net = {"species": [{"index": i, "pattern": p} for i, p in
                       enumerate(["L(r)", "R(l,p~0)", "R(l,p~1)"], 1)],
           "reactions": [{"index": 1, "reactants": [2], "products": [3],
                          "rate": "k2", "rule": "_R2"},
                         {"index": 2, "reactants": [2], "products": [3],
                          "rate": "k2", "rule": "_R2"}]}
    assert contactmap.network_graph(net)["reactions"] == 2
    views = (UI / "templates" / "sandbox_views.html").read_text(encoding="utf-8")
    assert "typeof g.rules === 'number' ? g.rules" in views
    js = (UI / "static" / "model-views.js").read_text(encoding="utf-8")
    assert "typeof graph.reactions === 'number' ? graph.reactions" in js
    # drawings cached before are redrawn with the counts
    assert sb.VIEW_VERSION == 3


def test_the_drawing_reads_its_box_and_the_text_size():
    js = (UI / "static" / "model-views.js").read_text(encoding="utf-8")
    net = js.split("  function network(box, graph) {", 1)[1].split(
        "the contact map", 1)[0]
    # no function in there may hoist over the box parameter
    assert "function box(" not in net
    assert "var k = textScale(), W = Math.max(320, box.clientWidth || 640) / k" in net
    assert "svg.style.height = Hpx + 'px';" in net
    assert ("var k = textScale(), W = Math.max(320, box.clientWidth || 640) / k,"
            " H = tall() / k;") in js


# ---------------------------------------- SB-18, SB-25: what was saved

def test_only_changed_files_are_saved_and_named(sandbox_root, monkeypatch):
    sb.add_example("sir_example", as_name="mine")
    files = sb.read_model("mine")
    d = sb.MODELS / "mine"
    old = time.time() - 3600
    for f in sb.REQUIRED:
        os.utime(d / f, (old, old))
    assert ui_sandbox._sandbox_save_posted(
        "mine", files["model.bngl"], files["data.exp"], files["priors.conf"]) == []
    assert all(abs((d / f).stat().st_mtime - old) < 1 for f in sb.REQUIRED)
    # a load replaces data.exp: an edited priors.conf is said, data.exp never
    monkeypatch.setattr(sb, "simulate_data", lambda name, seed=1: {
        "rows": 1, "column": "Cobs", "r": 0})
    ui_state._status.pop("flash", None)
    client.post("/sandbox/models/mine/simulate-data", data={
        "model_bngl": files["model.bngl"], "data_exp": files["data.exp"] + "\n",
        "priors_conf": files["priors.conf"] + "\n", "sim_seed": "1"},
        follow_redirects=False)
    said = _flash()
    assert said.startswith("Saved priors.conf first.")
    assert "data.exp filled with 1 simulated week of Cobs." in said


def test_one_week_and_one_missing_week_are_singular():
    assert ui_sandbox._weeks(1) == "1 week"
    assert ui_sandbox._weeks(3, "simulated week") == "3 simulated weeks"
    ui_state._status.pop("flash", None)
    ui_sandbox._sandbox_fill_flash({
        "asof": "settled", "location": "Ohio", "rows": 1, "dropped": 1,
        "start": "2026-10-17", "end": "2026-10-17", "dates": ["2026-10-17"]})
    assert _flash().startswith("data.exp filled: 1 week of Ohio, ")
    assert ui_state._status.get("flash_detail") == (
        "Source: settled truth. 1 missing week dropped.")


# ------------------------------------------------ SB-19: the engine

def test_without_the_engine_the_notice_is_plain_and_said_once(sandbox_root,
                                                             monkeypatch):
    from app.core.engines import pf
    monkeypatch.setattr(pf, "engine_available", lambda: False)
    notice, tip = sb.split_reason(sb.machine_problem())
    assert notice == "The fitting engine is not installed."
    assert tip.startswith("The PyBNF fork at ")
    with pytest.raises(sb.MachineProblem):
        sb.preflight()
    sb.add_example("sir_example", as_name="mine")
    ui_state._status.pop("flash", None)
    client.post("/sandbox/models/mine/run", data={"particles": "500"},
                follow_redirects=False)
    assert _flash() == ("Not started: this computer cannot fit yet; the "
                        "notice above the editor says why.")
    assert not ui_state._status.get("flash_detail")


# ---------------------------------------- SB-20, SB-21, SB-22: results

def test_one_rule_under_a_summary_with_nothing_after_it():
    css = (UI / "static" / "tabs" / "sandbox.css").read_text(encoding="utf-8")
    assert ".sb-rsum + .sb-rsec{border-top:0;padding-top:0}" in css


def test_what_changed_names_its_settings_and_writes_numbers(sandbox_root):
    sb.add_example("kinetics_example")
    a = sb.prepare("kinetics_example", particles=10000, seed=1)
    _finish(a)
    time.sleep(1.1)
    b = sb.prepare("kinetics_example", particles=500, seed=1)
    _finish(b)
    diff = sb.diff_runs(a.name, b.name)
    assert diff["settings"] == [{"key": "particles", "label": "particles",
                                 "a": 10000, "b": 500}]
    html = client.get(f"/sandbox?model=kinetics_example&run={b.name}"
                      f"&compare={a.name}").text
    assert "<td>particles</td><td>10,000</td><td>500</td>" in html
    tpl = (UI / "templates" / "sandbox.html").read_text(encoding="utf-8")
    assert '"typed"' not in tpl and '{{ da.location or "as written" }}' in tpl
    from app.core import sandbox_export as SX
    assert SX.RUN_SETTING_LABELS["n_obs"] == "weeks of data"


def test_a_dataset_start_has_no_oracle_step_card():
    tpl = (UI / "templates" / "sandbox.html").read_text(encoding="utf-8")
    assert ("{% if oracle or (shipped and shipped.shipped and not "
            "shipped.dataset) %}") in tpl
    # the donors in words; w is the input's, said once
    assert '"both": "both donor banks"' in tpl
    assert 'tips.stat("w", oracle.w' not in tpl


def test_shipped_state_says_a_dataset_start(sandbox_root):
    sb.add_example("sir_example", as_name="mine")
    sb._write_info("mine", {"origin": sb.SHIPPED_DATASET})
    assert sb.shipped_state("mine")["dataset"] is True
    sb._write_info("mine", {"origin": sb.SHIPPED})
    assert sb.shipped_state("mine")["dataset"] is False


# ------------------------------------------------ SB-23, SB-24: the editor

def test_the_engine_keys_table_leaves_out_the_plumbing(sandbox_root):
    sb.add_example("sir_example", as_name="mine")
    html = client.get("/sandbox?model=mine").text
    keys = html.split('id="sb-keys"', 1)[1].split("</table>", 1)[0]
    for k in ("fit_type", "population_size", "max_iterations"):
        assert f"<code>{k}</code>" not in keys, k
    assert "<code>objfunc</code>" in keys


def test_why_load_is_off_is_said_once():
    tpl = (UI / "templates" / "sandbox_data.html").read_text(encoding="utf-8")
    assert "sbfill-load-why" not in tpl
    assert 'formnovalidate id="sbfill-load">Load into data.exp</button>' in tpl
    js = (UI / "static" / "sandbox.js").read_text(encoding="utf-8")
    assert "setReason(load" not in js
    assert "load.setAttribute('aria-describedby', 'sbfill-why');" in js


# ------------------------------------------------ SB-26: the run zip

def test_the_run_zip_carries_the_engines_messages(sandbox_root):
    sb.add_example("kinetics_example")
    w = sb.prepare("kinetics_example", particles=100, seed=1)
    _finish(w)
    # bytes, as the engine writes them (text mode would add \r on Windows)
    (w / "pf_runner_0.err").write_bytes(b"x" * 10 + b"WARNING: ESS fell\n")
    z = zipfile.ZipFile(io.BytesIO(sb.run_zip(w.name)))
    assert z.read(f"{w.name}/pf_runner_0.err").endswith(b"WARNING: ESS fell\n")
    from app.core import sandbox_export as SX
    (w / "pf_runner_0.err").write_bytes(b"a" * (SX.ERR_ZIP_MAX + 10) + b"END")
    got = zipfile.ZipFile(io.BytesIO(sb.run_zip(w.name))).read(
        f"{w.name}/pf_runner_0.err")
    assert SX.ERR_ZIP_MAX == 64 * 1024
    assert len(got) == SX.ERR_ZIP_MAX and got.endswith(b"END")


# ------------------------------------------------ UI-16: Changed

def test_a_copied_example_changed_when_it_was_copied(sandbox_root):
    before = time.time() - 1
    sb.add_example("sir_example", as_name="mine")
    for f in sb.REQUIRED:
        assert (sb.MODELS / "mine" / f).stat().st_mtime >= before, f
    assert json.loads((sb.MODELS / "mine" / sb.MODEL_FILE).read_text())[
        "origin"] == "example:sir_example"


# ------------------------------- S3 pass: UI-19, SB-18, SB-19 follow-ups

#: stand-in elements, enough for model-views.js and the diagram card's
#: script; the window keeps its listeners and a root font size
_DOM = r"""
var fontPx = 16;
function El(tag) {
  this.tagName = tag; this.attrs = {}; this.children = []; this.style = {};
  this.dataset = {}; this.on = {}; this.parentNode = null; this.hidden = false;
  this.textContent = ''; this.className = ''; this.clientWidth = 0;
}
El.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
El.prototype.getAttribute = function (k) { return k in this.attrs ? this.attrs[k] : null; };
El.prototype.appendChild = function (c) { c.parentNode = this; this.children.push(c); return c; };
El.prototype.removeChild = function (c) {
  this.children.splice(this.children.indexOf(c), 1); c.parentNode = null; return c;
};
Object.defineProperty(El.prototype, 'firstChild', {get: function () { return this.children[0] || null; }});
El.prototype.addEventListener = function (t, f) { (this.on[t] = this.on[t] || []).push(f); };
El.prototype.removeEventListener = function () {};
El.prototype.querySelectorAll = function () { return []; };
El.prototype.querySelector = function () { return this.mviews || (this.mviews = new El('div')); };
var de = new El('html'), card = new El('div'), box = new El('div');
card.dataset.model = 'mine';
box.clientWidth = 800;
var document = {
  readyState: 'complete', documentElement: de,
  getElementById: function (id) { return id === 'cmap' ? card : id === 'cmap-svg' ? box : null; },
  createElement: function (t) { return new El(t); },
  createElementNS: function (ns, t) { return new El(t); },
  addEventListener: function () {}, removeEventListener: function () {}
};
var heard = {};
var window = {
  document: document, innerWidth: 1280,
  getComputedStyle: function () { return {fontSize: fontPx + 'px'}; },
  addEventListener: function (t, f) { (heard[t] = heard[t] || []).push(f); },
  dispatchEvent: function (e) { (heard[e.type] || []).forEach(function (f) { f(e); }); }
};
function fetch() {
  return Promise.resolve({json: function () { return Promise.resolve(DATA); }});
}
// the drawing in the box now: its view box against its pixel box
function frame() {
  var svg = box.children[0].children[0].children[0], vb = svg.getAttribute('viewBox').split(' ');
  return {w: +vb[2], h: +vb[3], pw: box.clientWidth, ph: parseFloat(svg.style.height),
          svg: svg};
}
"""


@pytest.mark.skipif(not shutil.which("node"), reason="no node")
def test_the_diagram_follows_the_text_size_without_a_reload(tmp_path):
    """UI-19's own steps: the Model view is drawn at 100%, then Display
    text size goes to 160% (base.html sends fontsizechange once the slider
    rests). The drawing shown is built again at the new size: its view
    box is 1/1.6 of its pixel box, with no reload. The page's own lines
    run here on stand-in elements."""
    bngl = (sb.EXAMPLES / "sir_example" / "model.bngl").read_text(encoding="utf-8")
    data = {"flow": contactmap.rule_flow(bngl), "sites": False}
    assert data["flow"]["edges"]
    tpl = (UI / "templates" / "sandbox_views.html").read_text(encoding="utf-8")
    page = tpl.split("<script>\n", 1)[1].split("</script>", 1)[0]
    mv = (UI / "static" / "model-views.js").read_text(encoding="utf-8")
    drv = tmp_path / "d.js"
    drv.write_text(_DOM + "var DATA = " + json.dumps(data) + ";\n" + mv + "\n"
                   + page + """
setTimeout(function () {
  var a = frame();
  fontPx = 25.6;
  window.dispatchEvent(new Event('fontsizechange'));
  setTimeout(function () {
    var b = frame();
    console.log(JSON.stringify([a.w, a.h, a.pw, a.ph, b.w, b.h, b.pw, b.ph,
                                a.svg === b.svg]));
  }, 0);
}, 0);
""", encoding="utf-8")
    out = subprocess.run([shutil.which("node"), str(drv)], capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    aw, ah, apw, aph, bw, bh, bpw, bph, same = json.loads(out.stdout)
    assert (aw, ah) == (apw, aph)                    # 100%: one unit a pixel
    assert not same                                  # drawn again
    assert abs(bw * 1.6 - bpw) < 1e-6 and abs(bh * 1.6 - bph) < 1e-6


def _edited(name="mine"):
    return {"model_bngl": "", "priors_conf": "",
            "data_exp": sb.read_model(name)["data.exp"] + "\n"}


def test_an_edit_to_data_exp_is_named_when_the_action_keeps_it(
        sandbox_root, tmp_path, monkeypatch):
    """SB-18's rule (data.exp is never said as saved, since the action
    replaces it) holds only once data.exp has been replaced: an upload of
    several groups, an upload with no file and a refused Load save the
    edit and say so."""
    from app.core import datasets as D
    from test_sandbox_upload import GROUPED, HUBVERSE
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    monkeypatch.setattr(sb, "locations", lambda: [])
    monkeypatch.setattr(sb, "vintages", lambda: [])
    sb.new_model("mine")
    url = "/sandbox/models/mine/upload-data"
    # several groups: stored, nothing loaded, the edit kept
    form = _edited()
    ui_state._status.pop("flash", None)
    client.post(url, data=form, files={"csv": ("grouped.csv", GROUPED.encode(),
                                               "text/csv")},
                follow_redirects=False)
    assert _flash().startswith("Saved data.exp first.")
    assert "(3 groups); pick one under Load data." in _flash()
    assert sb.read_model("mine")["data.exp"] == form["data_exp"]
    # no file chosen
    form = _edited()
    ui_state._status.pop("flash", None)
    client.post(url, data=form, files={"csv": ("", b"", "application/octet-stream")},
                follow_redirects=False)
    assert ui_sandbox._sandbox_upload_report["mine"]["problems"] == [
        "Choose a CSV file to upload."]
    assert _flash() == "Saved data.exp first."
    assert sb.read_model("mine")["data.exp"] == form["data_exp"]
    # a Load refused (no location here)
    form = _edited()
    ui_state._status.pop("flash", None)
    client.post("/sandbox/models/mine/fill-data",
                data={**form, "source": "settled", "location": "Nowhere"},
                follow_redirects=False)
    assert _flash().startswith("Saved data.exp first.  Not filled: ")
    assert sb.read_model("mine")["data.exp"] == form["data_exp"]
    # a one-group upload fills it: replaced, so not said
    form = _edited()
    ui_state._status.pop("flash", None)
    client.post(url, data=form, files={"csv": ("hub.csv", HUBVERSE.encode(),
                                               "text/csv")},
                follow_redirects=False)
    assert "Saved" not in _flash()
    assert _flash().startswith("data.exp filled: 5 weeks of Springfield")


def test_a_refused_run_of_a_model_not_here_says_why(sandbox_root, monkeypatch):
    """SB-19: the notice above the editor is on the page only when the
    model opens; for a name with no model the reason is in the notice."""
    from app.core.engines import pf
    monkeypatch.setattr(pf, "engine_available", lambda: False)
    ui_state._status.pop("flash", None)
    r = client.post("/sandbox/run", data={"model": "nosuch",
                                          "particles": "500"},
                    follow_redirects=False)
    said = _flash()
    assert said.startswith("Not started: The fitting engine is not installed.")
    assert "notice above the editor" not in said
    assert ui_state._status.get("flash_detail", "").startswith(
        "The PyBNF fork at ")
    page = client.get(r.headers["location"]).text
    assert "The fitting engine is not installed." in page
