"""The sandbox as one workbench: the gallery's New model form (skeleton,
example, copy), the per-model page (editor, run settings with presets,
Save / Check / Save and run, its own runs), deleting models and runs,
the diagram cache, the Storage line, and the page script's rules.
Hub-free and engine-free (conftest.sandbox_root fakes BNG2.pl).
"""
import json
import re
import shutil
import subprocess
import sys
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import contactmap as cm                    # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.ui import server as srv                         # noqa: E402

client = TestClient(srv.app)
STATIC = Path(srv.__file__).parent / "static"
NODE = shutil.which("node") or "/opt/node22/bin/node"


@pytest.fixture
def box(sandbox_root):
    return sandbox_root


def _post(url, data):
    return client.post(url, data=data, follow_redirects=False)


# ------------------------------------------------------------ new models

def test_new_model_start_options(box):
    r = _post("/sandbox/new", {"name": "blank", "start": "skeleton"})
    assert r.headers["location"] == "/sandbox?model=blank"
    assert sb.read_info("blank")["origin"] == "skeleton"
    r = _post("/sandbox/new", {"name": "mine", "start": "example:sir_example"})
    assert r.headers["location"] == "/sandbox?model=mine"
    assert sb.read_model("mine") == {f: (sb.EXAMPLES / "sir_example" / f).read_text()
                                     for f in sb.REQUIRED}
    assert sb.read_info("mine")["origin"] == "example:sir_example"
    # a copy takes the files and the data sidecar, and names its source
    (sb.MODELS / "mine" / sb.SOURCE_FILE).write_text('{"location": "x"}')
    r = _post("/sandbox/new", {"name": "mine2", "start": "copy:mine"})
    assert r.headers["location"] == "/sandbox?model=mine2"
    assert sb.read_model("mine2") == sb.read_model("mine")
    assert (sb.MODELS / "mine2" / sb.SOURCE_FILE).is_file()
    assert sb.read_info("mine2")["origin"] == "copy:mine"
    assert {m["name"]: m["origin"] for m in sb.list_models()} == {
        "blank": "skeleton", "mine": "example sir_example", "mine2": "copy of mine"}
    # refusals leave nothing behind
    for data in ({"name": "mine", "start": "skeleton"},
                 {"name": "bad name", "start": "example:sir_example"},
                 {"name": "x1", "start": "example:nope"},
                 {"name": "x2", "start": "copy:nobody"},
                 {"name": "x3", "start": "shipped:everything"}):
        srv._status.pop("flash", None)
        _post("/sandbox/new", data)
        assert srv._status.get("flash"), data
    assert sorted(p.name for p in sb.MODELS.iterdir()) == ["blank", "mine", "mine2"]


def test_an_example_can_be_added_twice_under_new_names(box):
    sb.add_example("sir_example", as_name="a")
    sb.add_example("sir_example", as_name="b")
    html = client.get("/sandbox").text
    assert 'value="example:sir_example"' in html                # still offered
    assert 'value="copy:a"' in html and 'value="copy:b"' in html


def test_the_gallery_shows_each_models_note_origin_and_last_run(box):
    sb.add_example("kinetics_example")
    w = sb.prepare("kinetics_example")
    html = client.get("/sandbox").text
    assert "A model that is not an epidemic: first-order conversion A -&gt; B." in html
    assert "example kinetics_example" in html
    assert f'href="/sandbox?run={w.name}&amp;model=kinetics_example">interrupted<' in html


def test_a_note_is_the_first_sentence_over_lines(box):
    sb.add_example("seir_example")
    note = {m["name"]: m["note"] for m in sb.list_models()}["seir_example"]
    assert note.startswith("An SEIR outbreak: infection, a latent stage")
    assert note.endswith("is the observed count.")


# ------------------------------------------------------------ workbench

def test_the_workbench_carries_one_form_with_presets_and_three_actions(box, monkeypatch):
    monkeypatch.setattr(sb, "locations", lambda: [{"name": "US", "fips": "US"}])
    sb.add_example("kinetics_example")
    html = client.get("/sandbox?model=kinetics_example").text
    form = html[html.index('<form method="post" action="/sandbox/models/kinetics_example/save" id="sbform"'):]
    form = form[:form.index("</form>")]
    # Enter in a field saves: the first submit button is the hidden Save
    first = re.search(r"<button[^>]*>", form).group(0)
    assert 'class="sb-default"' in first and "formaction" not in first
    assert form.index('class="sb-default"') < form.index("fill-data")
    assert 'formaction="/sandbox/models/kinetics_example/run" data-guard="sandbox-run"' in form
    assert 'id="sb-check"' in form and ">Save and run<" in form
    assert ">Quick check (200)<" in form and ">Full fit (10,000)<" in form and ">Custom<" in form
    for name in ("particles", "jitter", "forecast_weeks", "seed"):
        assert f'name="{name}"' in form, name
    # the standalone run card and the per-row dry run are gone
    assert 'action="/sandbox/run"' not in html and ">Dry run<" not in html
    assert "<h2>Run</h2>" not in html
    # the engine-keys table shows the real values
    assert "<code>pf_cumulative_observable</code></td><td>Bobs</td><td>priors.conf</td>" in html
    assert "<code>pf_bounds</code></td><td>reflect</td><td>default</td>" in html


def test_the_run_settings_start_from_the_models_last_run(box, monkeypatch):
    sb.add_example("kinetics_example")
    sb.prepare("kinetics_example", particles=10_000, jitter=0.2, forecast_weeks=3, seed=9)
    html = client.get("/sandbox?model=kinetics_example").text
    assert 'value="full" selected' in html and 'name="particles" id="sb-particles" type="number" value="10000"' in html
    assert 'value="0.2"' in html and 'value="3"' in html and 'value="9"' in html


def test_save_and_run_saves_the_posted_text_then_prepares_it(box, monkeypatch):
    sb.add_example("kinetics_example")
    ran = []
    monkeypatch.setattr(sb, "run", lambda w, width=1: ran.append(Path(w)) or {"status": "ok"})
    files = sb.read_model("kinetics_example")
    edited = files["model.bngl"].replace("k__FREE 0.30", "k__FREE 0.31")
    r = _post("/sandbox/models/kinetics_example/run",
              {"model_bngl": edited, "data_exp": files["data.exp"],
               "priors_conf": files["priors.conf"], "particles": "300"})
    assert r.headers["location"].endswith("&model=kinetics_example")
    for _ in range(100):
        if ran:
            break
        time.sleep(0.02)
    assert sb.read_model("kinetics_example")["model.bngl"] == edited
    assert (ran[0] / "kinetics_example_r0" / "m.bngl").read_text() == edited
    assert "pf_particles = 300" in (ran[0] / "kinetics_example_r0" / "pf.conf").read_text()
    # a post without the editor fields (a script, an alias) blanks nothing
    _post("/sandbox/models/kinetics_example/run", {"particles": "200"})
    assert sb.read_model("kinetics_example")["model.bngl"] == edited


def test_the_open_run_must_belong_to_the_open_model(box):
    sb.add_example("kinetics_example")
    sb.add_example("sir_example")
    w = sb.prepare("sir_example")
    html = client.get(f"/sandbox?run={w.name}&model=kinetics_example").text
    assert f'data-run="{w.name}"' not in html


# ------------------------------------------------------------ deleting

def test_delete_a_run_and_a_model_with_its_runs(box):
    sb.add_example("kinetics_example")
    sb.add_example("sir_example")
    w1, w2 = sb.prepare("kinetics_example"), sb.prepare("kinetics_example")
    other = sb.prepare("sir_example")
    # the confirmation must name the run
    _post(f"/sandbox/runs/{w1.name}/delete", {"confirm": "no"})
    assert w1.is_dir()
    r = _post(f"/sandbox/runs/{w1.name}/delete", {"confirm": w1.name})
    assert not w1.exists() and r.headers["location"] == "/sandbox?model=kinetics_example"
    # the live fit is never deleted
    srv._sandbox_status["running"] = w2.name
    _post(f"/sandbox/runs/{w2.name}/delete", {"confirm": w2.name})
    assert w2.is_dir()
    _post("/sandbox/models/kinetics_example/delete", {"confirm": "kinetics_example"})
    assert (sb.MODELS / "kinetics_example").is_dir()                 # its run fits
    srv._sandbox_status["running"] = None
    (box / "contactmap" / "kinetics_example").mkdir(parents=True)
    r = _post("/sandbox/models/kinetics_example/delete", {"confirm": "kinetics_example"})
    assert r.headers["location"] == "/sandbox"
    assert not (sb.MODELS / "kinetics_example").exists() and not w2.exists()
    assert not (box / "contactmap" / "kinetics_example").exists()
    assert other.is_dir() and (sb.MODELS / "sir_example").is_dir()   # others kept
    assert client.get("/sandbox").status_code == 200
    with pytest.raises(sb.SandboxError):
        sb.delete_run("../models")


# ------------------------------------------------------ diagram cache

def test_views_are_cached_by_the_model_text(box, monkeypatch):
    from app.tests.test_contactmap import BIND, NET
    calls = []

    def fake_bng(cmd, **kw):
        cwd = Path(kw.get("cwd", "."))
        calls.append(cwd)
        src = (cwd / "cm.bngl").read_text()
        if "visualize" in src:
            (cwd / "cm_contactmap.graphml").write_text(BIND)
        else:
            (cwd / "cm.net").write_text(NET)
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)
    monkeypatch.setattr(cm.subprocess, "run", fake_bng)
    sb.new_model("mine")
    a = client.get("/api/sandbox/models/mine/contactmap").json()
    b = client.get("/api/sandbox/models/mine/contactmap").json()
    assert a == b and len(calls) == 1
    client.get("/api/sandbox/models/mine/network")
    client.get("/api/sandbox/models/mine/network")
    assert len(calls) == 2
    sb.save_model("mine", {"model.bngl": sb.read_model("mine")["model.bngl"] + "\n# edited\n"})
    client.get("/api/sandbox/models/mine/contactmap")
    assert len(calls) == 3
    # a BNG2.pl elsewhere is another key
    monkeypatch.setattr(sb, "BNG", "/elsewhere/BNG2.pl")
    client.get("/api/sandbox/models/mine/contactmap")
    assert len(calls) == 4


# ------------------------------------------------------------- storage

def test_storage_shows_the_sandbox_size_outside_its_total(box):
    before = srv._storage_inventory()["total_bytes"]
    sb.add_example("kinetics_example")
    sb.prepare("kinetics_example")
    line = srv._sandbox_storage_line()
    assert line["models"] == 1 and line["runs"] == 1 and line["bytes"] > 0
    assert srv._storage_inventory()["total_bytes"] == before
    html = client.get("/storage").text
    assert "Sandbox models and runs" in html and line["size_h"] in html
    shutil.rmtree(box)
    assert srv._sandbox_storage_line() == {}


# ---------------------------------------------------------- the script

def test_sandbox_js_keeps_the_consoles_rules():
    js = (STATIC / "sandbox.js").read_text(encoding="utf-8")
    assert "–" not in js and "—" not in js
    assert "http://" not in js and "https://" not in js
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", js)
    assert not re.search(r"\.style\.(color|background)", js)
    assert "=>" not in js and "`" not in js
    assert not re.search(r"^\s*(const|let|class|async)\s", js, flags=re.M)
    assert "themechange" in js and "fontsizechange" in js
    html = (Path(srv.__file__).parent / "templates" / "sandbox.html").read_text()
    assert '<script defer src="/static/sandbox.js"></script>' in html


@pytest.mark.skipif(not Path(NODE).exists(), reason="node not available")
def test_the_plot_places_points_by_real_spacing_under_node(tmp_path):
    drv = tmp_path / "d.js"
    drv.write_text(
        "var g = {}; (function(){ %s }).call(g);\n"
        "var S = g.SandboxPage;\n"
        "console.log(JSON.stringify([S.xsFor([0,1,3],[],6),\n"
        "  S.xsFor([0,0.5,1],[],5),\n"
        "  S.xsFor([0,1,3],['2024-10-05','2024-10-12','2024-10-26'],5),\n"
        "  S.fmtEta(40), S.fmtEta(600), S.fmtEta(9000), S.fmtEta(0)]));\n"
        % (STATIC / "sandbox.js").read_text())
    out = subprocess.run([NODE, str(drv)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got[0] == [0, 1, 3, 4, 5, 6]                  # weekly past a gap
    assert got[1] == [0, 0.5, 1, 1.5, 2]                  # the data's own unit
    assert got[2] == ["2024-10-05", "2024-10-12", "2024-10-26", "2024-11-02", "2024-11-09"]
    assert got[3:] == ["about 40 s", "about 10 min", "about 2.5 h", ""]
