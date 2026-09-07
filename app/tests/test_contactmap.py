"""The contact map: BNG2.pl's GraphML reduced to molecules, components,
states and bonds, and drawn as an inline SVG in the page's own colours
(app/core/contactmap.py, the /api/sandbox/models/<name>/contactmap
route). BNG2.pl is faked: what is tested is the parse, the drawing and
the route's contract.
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import contactmap as cm                    # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.ui import server as srv                         # noqa: E402

HERE = Path(__file__).resolve().parent
BIND = (HERE / "contactmap_bind.graphml").read_text()
client = TestClient(srv.app)


def test_parse_reads_molecules_components_states_and_bonds():
    d = cm.parse(BIND)
    assert [m["name"] for m in d["molecules"]] == ["A", "B"]
    a, b = d["molecules"]
    assert [c["name"] for c in a["components"]] == ["b", "p"]
    assert a["components"][1]["states"] == ["0", "1"]
    assert b["components"] == [{"name": "a", "states": []}]
    assert d["bonds"] == [[[0, 0], [1, 0]]]                # A.b bound to B.a


def test_svg_draws_every_name_and_bond_in_page_tokens():
    s = cm.svg(cm.parse(BIND))
    assert s.startswith("<svg") and s.endswith("</svg>")
    for name in ("A", "B", ">b<", ">p<", ">a<", ">0<", ">1<"):
        assert name in s, name
    assert s.count("<path") == 1                         # the one bond
    assert "var(--ink)" in s and "var(--accent-ink)" in s and "#" not in s.split("aria-label")[0]
    assert "2 molecule types, 1 bonds" in s
    # a model with no components draws molecules alone, no bonds
    plain = cm.svg({"molecules": [{"name": "S", "components": []},
                                  {"name": "I", "components": []}], "bonds": []})
    assert ">S<" in plain and ">I<" in plain and "<path" not in plain
    assert "no molecule types" in cm.svg({"molecules": [], "bonds": []})
    assert "&lt;x&gt;" in cm.svg({"molecules": [{"name": "<x>", "components": []}], "bonds": []})


def test_visualize_copy_replaces_the_actions_block():
    bngl = "begin model\nbegin parameters\nk 1\nend parameters\nend model\n" \
           "begin actions\ngenerate_network({overwrite=>1})\nsimulate({suffix=>\"x\"})\nend actions\n"
    out = cm.visualize_bngl(bngl)
    assert "simulate(" not in out and "generate_network" not in out
    assert out.rstrip().endswith('visualize({type=>"contactmap"})\nend actions')
    assert out.startswith("begin model")
    with pytest.raises(cm.ContactMapError, match="end model"):
        cm.visualize_bngl("begin parameters\nk 1\nend parameters\n")


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "SANDBOX", tmp_path / "sandbox")
    monkeypatch.setattr(sb, "MODELS", tmp_path / "sandbox" / "models")
    monkeypatch.setattr(sb, "RUNS", tmp_path / "sandbox" / "runs")

    def fake_bng(cmd, **kw):
        cwd = Path(kw.get("cwd", "."))
        src = (cwd / "cm.bngl").read_text()
        assert 'visualize({type=>"contactmap"})' in src
        if "broken" not in src:
            (cwd / "cm_contactmap.graphml").write_text(BIND)
        return types.SimpleNamespace(stdout="ABORT: no such molecule\n", stderr="", returncode=0)
    monkeypatch.setattr(cm.subprocess, "run", fake_bng)
    return tmp_path / "sandbox"


def test_route_draws_a_saved_model_and_reports_bngs_words(box):
    sb.new_model("mine")
    r = client.get("/api/sandbox/models/mine/contactmap")
    assert r.status_code == 200
    d = r.json()
    assert d["molecules"] == 2 and d["bonds"] == 1 and d["svg"].startswith("<svg")
    assert (box / "contactmap" / "mine" / "cm.bngl").is_file()   # its own folder
    sb.save_model("mine", {"model.bngl": "# broken\n" + sb.read_model("mine")["model.bngl"]})
    d = client.get("/api/sandbox/models/mine/contactmap").json()
    assert "ABORT: no such molecule" in d["error"]
    assert "error" in client.get("/api/sandbox/models/nope/contactmap").json()
    html = client.get("/sandbox?model=mine").text
    assert 'id="cmap"' in html and 'data-model="mine"' in html
