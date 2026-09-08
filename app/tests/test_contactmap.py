"""The model views: BNG2.pl's GraphML reduced to molecules, components,
states and bonds and drawn in RuleBender's style, and its .net reduced to
species and reactions and drawn as a network, both as inline SVG in the
page's own colours (app/core/contactmap.py, the /api/sandbox/models/<name>/
contactmap and /network routes). BNG2.pl is faked: what is tested is the
parse, the drawing and the routes' contract.
"""
import re
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

#: The network BNG2.pl writes for the SIHRS example, cut to the lines the
#: parser reads: the rate law names live in the parameters block (a
#: constant expression) or the functions block (one that reads an
#: observable), a plain parameter name (gammaH) stays a name.
NET = """# Created by BioNetGen 2.9.2
begin parameters
    1 Reff__FREE     1.20  # Constant
    9 gamma          2.187500  # Constant
   10 rho            0.02  # Constant
   12 gammaH         1.17  # Constant
   13 omega          0.019  # Constant
   17 N              5000000  # Constant
   22 _rateLaw1      1  # Constant
   23 _rateLaw3      rho*gamma  # ConstantExpression
   25 _rateLaw5      rho*gamma  # ConstantExpression
end parameters
begin functions
    1 beta0() (Reff*gamma)/s0
    2 beta() beta0*exp((eps1*cos((((2*pi)*(t-phi1))/52))))
    4 _rateLaw2() beta()/N
end functions
begin species
    1 S() _InitialConc1
    2 I() _InitialConc2
    3 H() 0
    4 R() _InitialConc3
    5 Hadm() 0
    6 counter() 0
end species
begin reactions
    1 0 6 _rateLaw1 #_R1
    2 1,2 2,2 _rateLaw2 #_R2
    3 2 3 _rateLaw3 #_R3
    5 3 4 gammaH #_R5
    7 2 2,5 _rateLaw5 #_R7
end reactions
begin groups
    1 S                    1
end groups
"""

BIG_NET = ("begin species\n" + "".join(f"    {i} X{i}() 0\n" for i in range(1, 14))
           + "end species\nbegin reactions\nend reactions\n")

TOKEN = re.compile(r'(?:fill|stroke)="([^"]+)"')


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


def test_rulebender_style_panels_components_state_ellipses_and_the_bond_arc():
    s = cm.svg(cm.parse(BIND))
    for name in (">A<", ">B<", ">b<", ">p<", ">a<", ">0<", ">1<"):
        assert name in s, name
    assert s.count("<path") == 1 and " Q" in s              # the one bond, an arc
    assert s.count("<ellipse") == 2                          # the states 0 and 1
    assert s.count('fill-opacity="0.25"') == 2               # one header strip per panel
    assert s.count('fill="var(--card)"') == 3                # the component boxes b, p, a
    for colour in TOKEN.findall(s):                          # every colour a page token
        assert colour == "none" or colour.startswith("var(--"), colour
    # the bond joins the tops of the two component boxes and rises above the panels
    m = re.search(r'<path d="M([\d.]+),([\d.]+) Q([\d.]+),(-?[\d.]+) ([\d.]+),([\d.]+)"', s)
    assert m and float(m.group(4)) < float(m.group(2)) and float(m.group(4)) < float(m.group(6))
    # a molecule without components is a header-only panel: ground, tint, outline
    plain = cm.svg({"molecules": [{"name": "S", "components": []}], "bonds": []})
    assert plain.count("<rect") == 3 and "<ellipse" not in plain and "<path" not in plain
    # panels wrap into rows past 640 px
    wide = cm.svg({"molecules": [{"name": "M" * 12, "components": []} for _ in range(8)],
                   "bonds": []})
    ys = {float(v) for v in re.findall(r'<rect x="[\d.]+" y="([\d.]+)"', wide)}
    assert len(ys) > 1 and float(re.search(r'width="([\d.]+)"', wide).group(1)) <= 660


def test_visualize_copy_replaces_the_actions_block():
    bngl = "begin model\nbegin parameters\nk 1\nend parameters\nend model\n" \
           "begin actions\ngenerate_network({overwrite=>1})\nsimulate({suffix=>\"x\"})\nend actions\n"
    out = cm.visualize_bngl(bngl)
    assert "simulate(" not in out and "generate_network" not in out
    assert out.rstrip().endswith('visualize({type=>"contactmap"})\nend actions')
    assert out.startswith("begin model")
    with pytest.raises(cm.ContactMapError, match="end model"):
        cm.visualize_bngl("begin parameters\nk 1\nend parameters\n")
    # the network copy keeps the one generate_network call
    out = cm.network_bngl(bngl)
    assert "simulate(" not in out and "visualize(" not in out
    assert out.rstrip().endswith("generate_network({overwrite=>1})\nend actions")
    with pytest.raises(cm.ContactMapError, match="end model"):
        cm.network_bngl("begin parameters\nk 1\nend parameters\n")


# ------------------------------------------------------ the reaction network

def test_parse_net_reads_species_reactions_and_resolves_rate_laws():
    net = cm.parse_net(NET)
    assert [s["pattern"] for s in net["species"]] == ["S()", "I()", "H()", "R()", "Hadm()", "counter()"]
    assert [s["index"] for s in net["species"]] == [1, 2, 3, 4, 5, 6]
    rx = {r["index"]: r for r in net["reactions"]}
    assert sorted(rx) == [1, 2, 3, 5, 7]
    assert rx[1] == {"index": 1, "reactants": [], "products": [6], "rate": "1", "rule": "_R1"}
    assert rx[2]["reactants"] == [1, 2] and rx[2]["products"] == [2, 2]
    assert rx[2]["rate"] == "beta()/N"                       # from the functions block
    assert rx[3]["rate"] == "rho*gamma" and rx[3]["rule"] == "_R3"   # from the parameters block
    assert rx[5] == {"index": 5, "reactants": [3], "products": [4], "rate": "gammaH", "rule": "_R5"}
    assert rx[7]["reactants"] == [2] and rx[7]["products"] == [2, 5] and rx[7]["rate"] == "rho*gamma"
    # a scaled rate law keeps its scale and brackets the expression it names
    assert cm._resolve("0.5*_rateLaw3", {"_rateLaw3": "rho*gamma"}) == "0.5*(rho*gamma)"
    assert cm._resolve("_rateLaw2()", {"_rateLaw2": "beta()/N"}) == "beta()/N"
    assert cm._resolve("_rateLaw9", {}) == "_rateLaw9"
    assert cm.parse_net("# nothing BNG2.pl wrote\n") == {"species": [], "reactions": []}


def test_svg_network_draws_species_reactions_rates_and_edges():
    net = cm.parse_net(NET)
    s = cm.svg_network(net)
    assert s.startswith("<svg") and s.endswith("</svg>")
    for pat in ("S()", "I()", "H()", "R()", "Hadm()", "counter()"):
        assert f">{pat}<" in s, pat
    for rate in ("beta()/N", "rho*gamma", "gammaH", "1"):
        assert f">{rate}<" in s, rate
    assert s.count("<circle") == 5 and "6 species, 5 reactions" in s
    assert '<marker id="arw"' in s and "<title>_R2 beta()/N</title>" in s
    for colour in TOKEN.findall(s):
        assert colour == "none" or colour.startswith("var(--"), colour
    lines = re.findall(r"<line [^>]*/>", s)

    def of(index):
        return [l for l in lines if f'data-rx="{index}"' in l]
    # S + I -> I + I: S solid in, I one dashed edge (a catalyst, net produced)
    assert len(of(2)) == 2
    dashed = [l for l in of(2) if "stroke-dasharray" in l]
    assert len(dashed) == 1 and 'data-sp="2"' in dashed[0] and "marker-end" in dashed[0]
    solid = [l for l in of(2) if "stroke-dasharray" not in l]
    assert len(solid) == 1 and 'data-sp="1"' in solid[0] and "marker-end" not in solid[0]
    # the zero-order source draws only its product edge, with the arrowhead
    assert len(of(1)) == 1 and "marker-end" in of(1)[0] and 'data-sp="6"' in of(1)[0]
    # H -> R: one edge in, one arrowed edge out
    assert len(of(5)) == 2 and sum("marker-end" in l for l in of(5)) == 1
    # I -> I + Hadm: I dashed, Hadm arrowed; the two catalyst edges are the only dashes
    assert sum("stroke-dasharray" in l for l in of(7)) == 1 and s.count("stroke-dasharray") == 2
    # reactions alternate above and below the species line, in order
    top = float(re.search(r'<rect x="[\d.]+" y="([\d.]+)" width="[\d.]+" height="24"', s).group(1))
    cys = [float(v) for v in re.findall(r'<circle cx="[\d.]+" cy="([\d.]+)"', s)]
    assert [cy < top for cy in cys] == [True, False, True, False, True]


def test_svg_network_guards_its_size_and_still_draws_the_largest():
    note = cm.svg_network(cm.parse_net(BIG_NET))
    assert "<svg" not in note and "13 species" in note and "0 reactions" in note and "\n" not in note
    net = cm.parse_net(NET)
    many = {"species": net["species"],
            "reactions": [dict(net["reactions"][2], index=i) for i in range(1, 22)]}
    note = cm.svg_network(many)
    assert "<svg" not in note and "21 reactions" in note
    assert "no species" in cm.svg_network({"species": [], "reactions": []})
    # the largest drawable network lays out, its same-side repeats on further rows
    largest = {"species": [{"index": i, "pattern": f"X{i}()"} for i in range(1, 13)],
               "reactions": [{"index": i, "reactants": [1], "products": [2],
                              "rate": "k_long_rate_name", "rule": f"_R{i}"} for i in range(1, 21)]}
    s = cm.svg_network(largest)
    assert s.startswith("<svg") and s.count("<circle") == 20
    cys = [float(v) for v in re.findall(r'<circle cx="[\d.]+" cy="([\d.]+)"', s)]
    assert len(set(cys)) == 20                               # no two circles on one spot


# ------------------------------------------------------------- the routes

@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "SANDBOX", tmp_path / "sandbox")
    monkeypatch.setattr(sb, "MODELS", tmp_path / "sandbox" / "models")
    monkeypatch.setattr(sb, "RUNS", tmp_path / "sandbox" / "runs")

    def fake_bng(cmd, **kw):
        cwd = Path(kw.get("cwd", "."))
        src = (cwd / "cm.bngl").read_text()
        if "broken" not in src:
            if 'visualize({type=>"contactmap"})' in src:
                (cwd / "cm_contactmap.graphml").write_text(BIND)
            elif "generate_network({overwrite=>1})" in src:
                (cwd / "cm.net").write_text(BIG_NET if "big" in src else NET)
            else:
                raise AssertionError("the copy names no view action")
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


def test_network_route_draws_a_saved_model_and_reports_bngs_words(box):
    sb.new_model("mine")
    r = client.get("/api/sandbox/models/mine/network")
    assert r.status_code == 200
    d = r.json()
    assert d["species"] == 6 and d["reactions"] == 5 and d["svg"].startswith("<svg")
    work = box / "contactmap" / "mine"                          # the contact map's folder
    assert (work / "cm.net").is_file()
    src = (work / "cm.bngl").read_text()
    assert "generate_network({overwrite=>1})" in src and "simulate(" not in src
    # too large: no drawing, the counts in a note
    sb.save_model("mine", {"model.bngl": "# big\n" + sb.read_model("mine")["model.bngl"]})
    d = client.get("/api/sandbox/models/mine/network").json()
    assert d["svg"] == "" and d["species"] == 13 and "13 species" in d["note"]
    # a model that does not generate: BNG's words, and never the stale net
    sb.save_model("mine", {"model.bngl": "# broken\n" + sb.read_model("mine")["model.bngl"]})
    d = client.get("/api/sandbox/models/mine/network").json()
    assert "ABORT: no such molecule" in d["error"] and "generate the network" in d["error"]
    assert not (work / "cm.net").exists()
    assert "error" in client.get("/api/sandbox/models/nope/network").json()


def test_editor_page_carries_the_two_view_pills(box):
    sb.new_model("mine")
    html = client.get("/sandbox?model=mine").text
    assert 'id="cmap"' in html and 'id="cmap-svg"' in html and "Model views" in html
    assert 'class="pill mode" data-view="contactmap" role="tab" aria-selected="true">Contact map<' in html
    assert 'class="pill mode" data-view="network" role="tab" aria-selected="false">Reaction network<' in html
    assert "/network'" in html                                  # the card's own script fetches it
    assert "as BNG2.pl reads the saved model." in html and "with its rate law." in html


# ------------------------------------------- the graphs the page draws

STATIC = HERE.parent / "ui" / "static"


def test_network_graph_is_a_species_graph_with_the_rate_on_the_arrow():
    g = cm.network_graph(cm.parse_net(NET))
    kinds = {n["kind"] for n in g["nodes"]}
    assert kinds <= {"species", "source", "sink"}           # no parameter circles
    by_label = {n["label"]: n["id"] for n in g["nodes"] if n["kind"] == "species"}
    assert sorted(by_label) == ["H", "Hadm", "I", "R", "S", "counter"]
    assert by_label["S"] == "s1" and by_label["counter"] == "s6"

    def edge(frm, to):
        found = [e for e in g["edges"] if e["from"] == by_label[frm] and e["to"] == by_label[to]]
        assert len(found) == 1, (frm, to, found)
        return found[0]
    s_i, i_h, h_r = edge("S", "I"), edge("I", "H"), edge("H", "R")
    assert (s_i["label"], s_i["kind"], s_i["rule"]) == ("beta()/N", "transfer", "_R2")
    assert s_i["text"] == "S + I -> I + I, rate beta()/N, rule _R2"
    assert (i_h["label"], i_h["kind"]) == ("rho*gamma", "transfer")
    assert (h_r["label"], h_r["kind"], h_r["text"]) == ("gammaH", "transfer", "H -> R, rate gammaH, rule _R5")
    # I drives S -> I: an influence on that arrow, not an arrow of its own
    assert g["influences"] == [{"from": by_label["I"], "edge": s_i["id"]}]
    # I -> I + Hadm: a dashed arrow from the unchanged species to the product
    i_hadm = edge("I", "Hadm")
    assert (i_hadm["kind"], i_hadm["label"], i_hadm["text"]) == \
        ("catalytic", "rho*gamma", "I -> I + Hadm, rate rho*gamma, rule _R7")
    # 0 -> counter: a source dot with an arrow to the product
    src = [n for n in g["nodes"] if n["kind"] == "source"]
    assert len(src) == 1 and src[0]["id"] == "src1"
    into = [e for e in g["edges"] if e["to"] == by_label["counter"]]
    assert len(into) == 1 and into[0]["from"] == "src1" and into[0]["kind"] == "source"
    assert into[0]["label"] == "1" and into[0]["text"] == "0 -> counter, rate 1, rule _R1"
    # every edge joins two nodes of the graph; ids are unique
    ids = {n["id"] for n in g["nodes"]}
    assert all(e["from"] in ids and e["to"] in ids for e in g["edges"])
    assert len({e["id"] for e in g["edges"]}) == len(g["edges"]) == 5
    assert all(e["from"].startswith(("s", "src")) for e in g["edges"])


def test_network_graph_sinks_stoichiometry_and_null_reactions():
    sp = [{"index": 1, "pattern": "A()"}, {"index": 2, "pattern": "B()"}, {"index": 3, "pattern": "E()"}]
    net = {"species": sp, "reactions": [
        {"index": 1, "reactants": [1], "products": [], "rate": "kd", "rule": "_R1"},      # A -> 0
        {"index": 2, "reactants": [1, 3], "products": [3], "rate": "kc", "rule": "_R2"},  # A + E -> E
        {"index": 3, "reactants": [1, 1], "products": [2], "rate": "k2", "rule": ""},     # 2 A -> B
        {"index": 4, "reactants": [2], "products": [2], "rate": "k0", "rule": "_R4"},     # B -> B
        {"index": 5, "reactants": [1], "products": [1, 1], "rate": "ka", "rule": "_R5"}]} # A -> 2 A
    g = cm.network_graph(net)
    sinks = [n["id"] for n in g["nodes"] if n["kind"] == "sink"]
    assert sinks == ["snk1", "snk2"]
    by_rule = {}
    for e in g["edges"]:
        by_rule.setdefault(e["rule"], []).append(e)
    assert [(e["from"], e["to"], e["kind"]) for e in by_rule["_R1"]] == [("s1", "snk1", "sink")]
    assert [(e["from"], e["to"], e["kind"]) for e in by_rule["_R2"]] == [("s1", "snk2", "sink")]
    assert g["influences"] == [{"from": "s3", "edge": by_rule["_R2"][0]["id"]}]   # E, the catalyst
    two = [e for e in g["edges"] if e["text"].startswith("A + A -> B")]
    assert len(two) == 1 and two[0]["kind"] == "transfer" and two[0]["text"] == "A + A -> B, rate k2"
    assert "_R4" not in by_rule                                                    # nothing changes
    assert [(e["from"], e["to"], e["kind"]) for e in by_rule["_R5"]] == [("s1", "s1", "catalytic")]
    assert cm.network_graph({"species": [], "reactions": []}) == {"nodes": [], "edges": [], "influences": []}


def test_contact_graph_carries_ids_for_the_page():
    g = cm.contact_graph(cm.parse(BIND))
    assert [m["name"] for m in g["molecules"]] == ["A", "B"]
    assert [m["id"] for m in g["molecules"]] == ["m0", "m1"]
    comps = [c for m in g["molecules"] for c in m["components"]]
    assert [(c["id"], c["name"]) for c in comps] == [("m0c0", "b"), ("m0c1", "p"), ("m1c0", "a")]
    assert comps[1]["states"] == ["0", "1"] and comps[0]["states"] == [] and comps[2]["states"] == []
    assert g["bonds"] == [{"from": "m0c0", "to": "m1c0"}]              # A.b bound to B.a
    assert cm.contact_graph({"molecules": [], "bonds": []}) == {"molecules": [], "bonds": []}


def test_routes_return_the_graphs_beside_the_svg(box):
    sb.new_model("mine")
    d = client.get("/api/sandbox/models/mine/contactmap").json()
    assert d["svg"].startswith("<svg") and d["molecules"] == 2
    assert [m["name"] for m in d["graph"]["molecules"]] == ["A", "B"]
    assert d["graph"]["bonds"] == [{"from": "m0c0", "to": "m1c0"}]
    d = client.get("/api/sandbox/models/mine/network").json()
    assert d["svg"].startswith("<svg") and d["species"] == 6
    assert len(d["graph"]["nodes"]) == 7 and len(d["graph"]["edges"]) == 5
    assert d["graph"]["influences"] == [{"from": "s2", "edge": "e2"}]
    # too large for the server's drawing: the graph still comes, beside the note
    sb.save_model("mine", {"model.bngl": "# big\n" + sb.read_model("mine")["model.bngl"]})
    d = client.get("/api/sandbox/models/mine/network").json()
    assert d["svg"] == "" and "13 species" in d["note"] and len(d["graph"]["nodes"]) == 13


def test_editor_page_loads_the_renderer_and_the_page_script_no_longer_writes_the_map(box):
    sb.new_model("mine")
    html = client.get("/sandbox?model=mine").text
    assert '<link rel="stylesheet" href="/static/model-views.css">' in html
    assert '<script defer src="/static/model-views.js"></script>' in html
    assert 'id="cmap-svg"' in html and "ModelViews" in html
    # the old fetch in the page's own script, which wrote the server SVG into #cmap-svg
    assert "var cm = document.getElementById('cmap');" not in html
    assert "box.innerHTML = d.svg" not in html
    assert html.count("/contactmap'") == 1                       # the views card alone fetches it
    for name in ("model-views.js", "model-views.css"):
        assert (STATIC / name).is_file(), name
    for name in ("model-views.js", "model-views.css"):
        text = (STATIC / name).read_text()
        assert "\u2014" not in text and "\u2013" not in text, name   # no long dashes anywhere
    js = (STATIC / "model-views.js").read_text()
    assert "root.ModelViews = {network: network, contactmap: contactmap" in js
    css = (STATIC / "model-views.css").read_text()
    assert "#" not in "".join(l.split("/*")[0] for l in css.splitlines())   # colours are tokens
    for token in ("--card", "--bg", "--ink", "--mut", "--line", "--accent", "--accent-ink", "--slate"):
        assert "var(%s)" % token in css, token


@pytest.mark.skipif(not __import__("shutil").which("osascript"), reason="JavaScriptCore via osascript only")
def test_model_views_js_parses_under_javascriptcore():
    import subprocess
    path = str(STATIC / "model-views.js")
    script = ('var s = $.NSString.stringWithContentsOfFileEncodingError("%s", 4, null).js; '
              'try { new Function(s); "syntax ok" } catch (e) { "SYNTAX ERROR: " + e }' % path)
    r = subprocess.run(["osascript", "-l", "JavaScript", "-e", script], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0 and "syntax ok" in r.stdout, r.stdout + r.stderr
