"""The model views of the sandbox, drawn from BNG2.pl's own reading of a
model: the contact map and the reaction network.

BioNetGen's visualize action (type contactmap) writes a yEd GraphML file:
every molecule type is a node (a group node when it has components), each
component a child node, a component's states a nested group of state
nodes, and every bond the rules can form an edge between two component
nodes. parse() reduces that file to molecules, components, states and
bonds; svg() lays them out in RuleBender's style, one panel per molecule
type with a header strip, component boxes inside it, state ellipses under
each component and bonds as arcs between components.

generate_network writes a .net file: the species, the reactions between
them and each reaction's rate law. parse_net() reduces that text to
species and reactions with the _rateLawN names resolved to their
expressions; svg_network() draws the species on one line with the
reaction circles on rows above and below it.

Both drawings are inline SVG whose colours are the page's own tokens, so
they read in every theme. Beside each, contact_graph() and network_graph()
reduce the same parse to the graph JSON model-views.js draws in the
browser, where the drawing pans, zooms, drags and highlights. Nothing here
runs the engine: BNG2.pl is asked for the one file alone, on a copy of the
model whose actions block is replaced by the one call.
"""
from __future__ import annotations

import math
import re
import subprocess
import threading
from collections import Counter
from pathlib import Path

# BNG2.pl's own output, written to a folder the app made from the user's
# own model: the stdlib parser (no external entities by default) is enough.
from xml.etree import ElementTree as ET

from flubnf.settings import BNG

NS = {"g": "http://graphml.graphdrawing.org/xmlns",
      "y": "http://www.yworks.com/xml/graphml"}

#: One BNG2.pl at a time in a model's views folder: both views write the
#: same cm.bngl copy there, so two requests must not interleave.
_LOCK = threading.Lock()


class ContactMapError(ValueError):
    """A model BNG2.pl could not draw, with its words."""


def _with_actions(bngl_text: str, actions: str, what: str) -> str:
    m = re.search(r"^\s*end\s+model\s*$", bngl_text, flags=re.M)
    if not m:
        raise ContactMapError(f"{what} needs a begin model / end model block "
                              "around the model")
    return (bngl_text[:m.end()].rstrip() + "\n\nbegin actions\n" + actions
            + "\nend actions\n")


def visualize_bngl(bngl_text: str) -> str:
    """The model with its actions replaced by the one visualize call."""
    return _with_actions(bngl_text, 'visualize({type=>"contactmap"})',
                         "the contact map")


def network_bngl(bngl_text: str) -> str:
    """The model with its actions replaced by the one generate_network call."""
    return _with_actions(bngl_text, "generate_network({overwrite=>1})",
                         "the reaction network")


def _run_bng(source: str, workdir: Path, out_name: str, timeout: int,
             what: str) -> str:
    """Write the copy as cm.bngl in workdir, run BNG2.pl on it, and return
    the text of the file it must have written; its words when it did not."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    out = workdir / out_name
    with _LOCK:
        (workdir / "cm.bngl").write_text(source, encoding="utf-8", newline="\n")
        if out.exists():
            out.unlink()                   # never a stale file for a new model
        r = subprocess.run(["perl", BNG, "cm.bngl"], capture_output=True,
                           text=True, cwd=str(workdir), timeout=timeout)
        if not out.is_file():
            raise ContactMapError(f"BNG2.pl could not {what}:\n"
                                  + (r.stdout or "")[-600:] + (r.stderr or "")[-300:])
        return out.read_text(encoding="utf-8", errors="replace")


def graphml_from_bngl(bngl_text: str, workdir: Path, timeout: int = 120) -> str:
    """Run BNG2.pl on the visualize-only copy in workdir; the GraphML text."""
    return _run_bng(visualize_bngl(bngl_text), workdir, "cm_contactmap.graphml",
                    timeout, "draw the contact map")


def network_from_bngl(bngl_text: str, workdir: Path, timeout: int = 120) -> str:
    """Run BNG2.pl on the generate-only copy in workdir; the .net text."""
    return _run_bng(network_bngl(bngl_text), workdir, "cm.net", timeout,
                    "generate the network")


def _label(node) -> str:
    lab = node.find("./g:data//y:NodeLabel", NS)
    return (lab.text or "").strip() if lab is not None else ""


def _is_group(node) -> bool:
    return node.get("{http://www.yworks.com/xml/yfiles-common/1.0/java}foldertype") == "group" \
        or node.get("yfiles.foldertype") == "group"


def parse(xml_text: str) -> dict:
    """Molecules with their components and states, and the bonds.

    Returns {"molecules": [{"name", "components": [{"name", "states"}]}],
    "bonds": [[[mol_index, comp_index], [mol_index, comp_index]], ...]}.
    """
    root = ET.fromstring(xml_text)
    graph = root.find("g:graph", NS)
    if graph is None:
        raise ContactMapError("no graph in the GraphML BNG2.pl wrote")
    molecules, by_id = [], {}
    for mi, node in enumerate(graph.findall("g:node", NS)):
        mol = {"name": _label(node), "components": []}
        sub = node.find("g:graph", NS)
        if sub is not None:
            for ci, cnode in enumerate(sub.findall("g:node", NS)):
                comp = {"name": _label(cnode), "states": []}
                ssub = cnode.find("g:graph", NS)
                if ssub is not None:
                    comp["states"] = [_label(s) for s in ssub.findall("g:node", NS)]
                mol["components"].append(comp)
                by_id[cnode.get("id")] = [mi, ci]
        molecules.append(mol)
    bonds = []
    for edge in graph.iter("{%s}edge" % NS["g"]):
        a, b = by_id.get(edge.get("source")), by_id.get(edge.get("target"))
        if a and b:
            bonds.append([a, b])
    return {"molecules": molecules, "bonds": bonds}


# ------------------------------------------------------------ the contact map

CHAR = 7.2          # px per character at the 12 px label size
PAD = 10
GAP = 22            # between molecule panels, sideways and between rows
WRAP = 640          # wrap panels into rows past this width
HEAD = 26           # the header strip of a panel
COMP_H = 22         # a component box
STATE_H = 18        # a state ellipse
BOND_RISE = 64      # a bond's control point, above the panels it joins
BOND_ROOM = 26      # room above the first row for the arcs


def _w(text: str, minimum: float) -> float:
    return max(minimum, CHAR * len(text) + 2 * PAD)


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def _empty(label: str, note: str) -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 40" '
            f'width="320" height="40" role="img" aria-label="{label}">'
            f'<text x="0" y="24" fill="var(--mut)" font-size="12">{note}</text></svg>')


def svg(cm: dict) -> str:
    """An inline SVG of the map in RuleBender's style. Colours are CSS
    tokens of the page (--card, --bg, --ink, --mut, --accent, --accent-ink).

    Each molecule type is a rounded panel (fill --bg, stroke --ink) with a
    header strip (--accent at a quarter) carrying its name; its components
    are boxes (--card) in the panel body, each component's states small
    ellipses attached under it, and every bond an arc (--accent-ink)
    between the two component boxes. A molecule without components is a
    header-only panel. Panels fill rows up to WRAP px, GAP px apart.
    """
    mols = cm.get("molecules") or []
    bonds = cm.get("bonds") or []
    if not mols:
        return _empty("empty contact map", "no molecule types")
    boxes, comps = [], {}          # per molecule: (x, y, w, h, cells); per (mi, ci): top centre
    x, y, row_h = 0.0, float(BOND_ROOM if bonds else 0), 0.0
    for mol in mols:
        cws = [_w(c["name"], 30) for c in mol["components"]]
        sws = [sum(_w(s, 24) for s in c["states"]) + 4 * max(len(c["states"]) - 1, 0)
               for c in mol["components"]]
        cell = [max(a, b) for a, b in zip(cws, sws)]
        has_states = any(c["states"] for c in mol["components"])
        w = max(_w(mol["name"], 70), sum(cell) + 8 * max(len(cell) - 1, 0) + 2 * PAD)
        h = HEAD
        if mol["components"]:
            h += 8 + COMP_H + (4 + STATE_H if has_states else 0) + 8
        if x > 0 and x + w > WRAP:
            x, y, row_h = 0.0, y + row_h + GAP, 0.0
        boxes.append((x, y, w, h, cell))
        row_h = max(row_h, h)
        x += w + GAP
    width = max(b[0] + b[2] for b in boxes) + 2
    height = y + row_h + 2
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
             f'width="{width:.0f}" height="{height:.0f}" role="img" '
             f'aria-label="contact map: {len(mols)} molecule types, {len(bonds)} bonds" '
             'font-family="DM Sans, system-ui, sans-serif" font-size="12">'
             '<g transform="translate(1 1)">']
    body = []
    for mi, (bx, by, bw, bh, cell) in enumerate(boxes):
        mol = mols[mi]
        # the panel: its ground, the header strip rounded at the top only
        # (a body-coloured cover squares the strip's bottom), the outline
        body.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="8" '
                    'fill="var(--bg)"/>')
        if mol["components"]:
            body.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{HEAD + 8}" rx="8" '
                        'fill="var(--accent)" fill-opacity="0.25"/>')
            body.append(f'<rect x="{bx:.1f}" y="{by + HEAD:.1f}" width="{bw:.1f}" '
                        f'height="{bh - HEAD - 8:.1f}" fill="var(--bg)"/>')
        else:
            body.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="8" '
                        'fill="var(--accent)" fill-opacity="0.25"/>')
        body.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="8" '
                    'fill="none" stroke="var(--ink)" stroke-width="1.2"/>')
        body.append(f'<text x="{bx + bw / 2:.1f}" y="{by + 17.5:.1f}" text-anchor="middle" '
                    f'fill="var(--ink)" font-weight="600">{_esc(mol["name"])}</text>')
        cx, cy = bx + PAD, by + HEAD + 8
        for ci, comp in enumerate(mol["components"]):
            cw = cell[ci]
            body.append(f'<rect x="{cx:.1f}" y="{cy:.1f}" width="{cw:.1f}" height="{COMP_H}" rx="4" '
                        'fill="var(--card)" stroke="var(--ink)"/>')
            body.append(f'<text x="{cx + cw / 2:.1f}" y="{cy + 15:.1f}" text-anchor="middle" '
                        f'fill="var(--ink)">{_esc(comp["name"])}</text>')
            comps[(mi, ci)] = (cx + cw / 2, cy)
            widths = [_w(s, 24) for s in comp["states"]]
            sx = cx + (cw - (sum(widths) + 4 * max(len(widths) - 1, 0))) / 2
            ey = cy + COMP_H + 4
            for st, sw in zip(comp["states"], widths):
                body.append(f'<ellipse cx="{sx + sw / 2:.1f}" cy="{ey + STATE_H / 2:.1f}" '
                            f'rx="{sw / 2:.1f}" ry="{STATE_H / 2:.1f}" '
                            'fill="var(--accent)" fill-opacity="0.35" stroke="var(--accent-ink)"/>')
                body.append(f'<text x="{sx + sw / 2:.1f}" y="{ey + 13:.1f}" text-anchor="middle" '
                            f'fill="var(--ink)" font-size="11">{_esc(st)}</text>')
                sx += sw + 4
            cx += cw + 8
    edges = []
    for a, b in bonds:
        pa, pb = comps.get(tuple(a)), comps.get(tuple(b))
        if not pa or not pb:
            continue
        top = min(boxes[a[0]][1], boxes[b[0]][1])
        mx, my = (pa[0] + pb[0]) / 2, top - BOND_RISE
        edges.append(f'<path d="M{pa[0]:.1f},{pa[1]:.1f} Q{mx:.1f},{my:.1f} {pb[0]:.1f},{pb[1]:.1f}" '
                     'fill="none" stroke="var(--accent-ink)" stroke-width="2"/>')
    parts += body + edges + ["</g></svg>"]
    return "".join(parts)


# ------------------------------------------------------- the reaction network

MAX_SPECIES = 12    # past either count the network is reported, not drawn
MAX_REACTIONS = 20
SP_H = 24           # a species box
SP_GAP = 44         # between species boxes
RX_R = 7            # a reaction circle
RX_FIRST = 52       # from the species line to the first row of circles
RX_ROW = 44         # between rows of circles
LABEL_CHAR = 6.6    # px per character at the 11 px rate label size
#: A label's halo in the card colour, so an edge crossing it stays readable.
HALO = ' stroke="var(--card)" stroke-width="3" paint-order="stroke"'


def _blocks(text: str) -> dict:
    """The named blocks of a .net file: block name -> its content lines,
    stripped, comments and blank lines dropped."""
    out, name, lines = {}, None, []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"begin\s+(.+?)\s*$", s)
        if m and name is None:
            name, lines = m.group(1), []
            continue
        if name is not None and re.match(r"end\s+" + re.escape(name) + r"\s*$", s):
            out[name] = lines
            name = None
            continue
        if name is not None:
            lines.append(s)
    return out


def _resolve(rate: str, laws: dict) -> str:
    """A rate law with its _rateLawN names replaced by their expressions;
    any other name (gammaH, omega) is left as it is."""
    def sub(m):
        expr = laws.get(m.group(1))
        if expr is None:
            return m.group(0)
        if m.start() == 0 and m.end() == len(rate):
            return expr
        return f"({expr})" if re.search(r"[-+*/^ ]", expr) else expr
    return re.sub(r"\b(_rateLaw\d+)\b(?:\(\))?", sub, rate)


def parse_net(text: str) -> dict:
    """The species and reactions of a .net file BNG2.pl wrote.

    Returns {"species": [{"index", "pattern"}], "reactions": [{"index",
    "reactants": [i..], "products": [i..], "rate": "<expression>",
    "rule": "_R2"}]}. Species lines read "index pattern initial"; reaction
    lines "index r1,r2 p1,p2 ratelaw #comment", a 0 standing for no
    reactants or no products. A _rateLawN rate is resolved to its
    expression from the parameters block ("23 _rateLaw3 rho*gamma #
    ConstantExpression") or the functions block ("5 _rateLaw2()
    beta()/N"); a plain parameter name stays as it is.
    """
    blocks = _blocks(text)
    laws = {}
    for line in blocks.get("parameters", []):
        parts = line.split("#", 1)[0].split()
        if len(parts) >= 3 and parts[1].startswith("_rateLaw"):
            laws[parts[1]] = " ".join(parts[2:])
    for line in blocks.get("functions", []):
        parts = line.split("#", 1)[0].split(None, 2)
        if len(parts) >= 3 and parts[1].startswith("_rateLaw"):
            laws[parts[1].split("(")[0]] = parts[2].strip()
    species = []
    for line in blocks.get("species", []):
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            species.append({"index": int(parts[0]), "pattern": parts[1]})
    reactions = []
    for line in blocks.get("reactions", []):
        body, _, comment = line.partition("#")
        parts = body.split()
        if len(parts) < 4 or not parts[0].isdigit():
            continue
        reactions.append({
            "index": int(parts[0]),
            "reactants": [int(i) for i in parts[1].split(",") if i.isdigit() and int(i) > 0],
            "products": [int(i) for i in parts[2].split(",") if i.isdigit() and int(i) > 0],
            "rate": _resolve(" ".join(parts[3:]), laws),
            "rule": comment.split()[0] if comment.split() else ""})
    return {"species": species, "reactions": reactions}


def svg_network(net: dict) -> str:
    """An inline SVG of the network, or a one-line note with the counts
    when it is too large to draw (past MAX_SPECIES or MAX_REACTIONS).

    Species are rounded boxes on one line, in the order they appear;
    reactions are small circles (fill --card, stroke --mut) on rows above
    and below the line, alternating, each at the middle of its species and
    on the first row of its side with room for it and its rate label.
    Solid edges run from a reactant to the circle and from the circle to a
    product (arrowhead at the product); a species on both sides of one
    reaction, a catalyst, gets one dashed edge; a zero-order source draws
    only its product edge.
    """
    sp = net.get("species") or []
    rx = net.get("reactions") or []
    if not sp:
        return _empty("empty reaction network", "no species")
    if len(sp) > MAX_SPECIES or len(rx) > MAX_REACTIONS:
        return (f"{len(sp)} species and {len(rx)} reactions: too many to draw "
                f"(the drawing stops at {MAX_SPECIES} species and "
                f"{MAX_REACTIONS} reactions)")
    pos, x = {}, 0.0                  # species index -> (x, width)
    for s in sp:
        w = _w(s["pattern"], 40)
        pos[s["index"]] = (x, w)
        x += w + SP_GAP
    rows = {1: [], -1: []}            # side (1 above) -> rows -> taken spans
    placed = []
    for k, r in enumerate(rx):
        members = []
        for i in r["reactants"] + r["products"]:
            if i in pos and i not in members:
                members.append(i)
        if not members:
            continue
        cx = sum(pos[i][0] + pos[i][1] / 2 for i in members) / len(members)
        lw = LABEL_CHAR * len(r["rate"])
        span = (cx - RX_R - 6, cx + RX_R + 6 + lw + 6)
        side = 1 if k % 2 == 0 else -1
        row = next((j for j, taken in enumerate(rows[side])
                    if all(span[1] <= a or span[0] >= b for a, b in taken)), None)
        if row is None:
            rows[side].append([])
            row = len(rows[side]) - 1
        rows[side][row].append(span)
        placed.append((r, cx, side, row, lw))
    n_up, n_down = len(rows[1]), len(rows[-1])
    top = 4 + (RX_FIRST + (n_up - 1) * RX_ROW + RX_R if n_up else 0)
    height = top + SP_H + 4 + (RX_FIRST + (n_down - 1) * RX_ROW + RX_R if n_down else 0)
    width = max([x - SP_GAP] + [cx + RX_R + 6 + lw for _, cx, _, _, lw in placed]) + 4
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
             f'width="{width:.0f}" height="{height:.0f}" role="img" '
             f'aria-label="reaction network: {len(sp)} species, {len(rx)} reactions" '
             'font-family="DM Sans, system-ui, sans-serif" font-size="12">'
             '<defs><marker id="arw" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" '
             'markerHeight="8" orient="auto"><path d="M0,0 L10,5 L0,10 z" '
             'fill="var(--accent-ink)"/></marker></defs><g transform="translate(1 0)">']
    edges, nodes = [], []
    for s in sp:
        sx, sw = pos[s["index"]]
        nodes.append(f'<rect x="{sx:.1f}" y="{top:.1f}" width="{sw:.1f}" height="{SP_H}" rx="6" '
                     'fill="var(--card)" stroke="var(--ink)"/>')
        nodes.append(f'<text x="{sx + sw / 2:.1f}" y="{top + 16:.1f}" text-anchor="middle" '
                     f'fill="var(--ink)">{_esc(s["pattern"])}</text>')
    for r, cx, side, row, lw in placed:
        cy = top - RX_FIRST - row * RX_ROW if side == 1 else top + SP_H + RX_FIRST + row * RX_ROW
        nodes.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{RX_R}" fill="var(--card)" '
                     f'stroke="var(--mut)" stroke-width="1.2"><title>{_esc(r["rule"])} '
                     f'{_esc(r["rate"])}</title></circle>')
        nodes.append(f'<text x="{cx + RX_R + 6:.1f}" y="{cy + 4:.1f}" fill="var(--ink)" '
                     f'font-size="11"{HALO}>{_esc(r["rate"])}</text>')
        reactants, products = Counter(r["reactants"]), Counter(r["products"])
        for i in sorted(set(reactants) | set(products)):
            if i not in pos:
                continue
            ax, ay = pos[i][0] + pos[i][1] / 2, (top if side == 1 else top + SP_H)
            dx, dy = ax - cx, ay - cy
            d = math.hypot(dx, dy) or 1.0
            bx, by = cx + dx / d * RX_R, cy + dy / d * RX_R     # on the circle's rim
            nr, npd = reactants[i], products[i]
            tag = f'data-rx="{r["index"]}" data-sp="{i}" stroke="var(--accent-ink)" stroke-width="1.5"'
            if nr and npd:
                arrow = ' marker-end="url(#arw)"' if npd > nr else ""
                edges.append(f'<line x1="{bx:.1f}" y1="{by:.1f}" x2="{ax:.1f}" y2="{ay:.1f}" '
                             f'{tag} stroke-dasharray="5 4"{arrow}/>')
                continue
            if nr:
                edges.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" {tag}/>')
            else:
                edges.append(f'<line x1="{bx:.1f}" y1="{by:.1f}" x2="{ax:.1f}" y2="{ay:.1f}" '
                             f'{tag} marker-end="url(#arw)"/>')
            n = nr or npd
            if n > 1:                                          # the stoichiometry
                edges.append(f'<text x="{ax + 0.35 * (bx - ax) + 5:.1f}" y="{ay + 0.35 * (by - ay) + 3:.1f}" '
                             f'fill="var(--mut)" font-size="10"{HALO}>{n}</text>')
    parts += edges + nodes + ["</g></svg>"]
    return "".join(parts)


# ------------------------------------------------- the graphs the page draws
#
# The routes hand the page these graphs beside the server SVG, and
# model-views.js draws them in the browser, where the drawing can pan,
# zoom, drag and highlight. Nothing here is a picture: ids and labels.

def _species_label(pattern: str) -> str:
    """A species for a label: "S()" reads S; "A(b!1).B(a!1)" stays."""
    return re.sub(r"\(\)", "", pattern) or pattern


def _unique(indices: list) -> list:
    out = []
    for i in indices:
        if i not in out:
            out.append(i)
    return out


def network_graph(net: dict) -> dict:
    """The reaction network as a species graph for the page to draw.

    Nodes are the species (kind "species", id "s<index>", the label its
    pattern without empty parentheses) and, where a reaction needs one,
    a source or sink dot (kind "source" or "sink"). For each reaction the
    net change per species is its count among the products minus its
    count among the reactants: every species consumed on net gets a
    "transfer" edge to every species produced on net, labelled with the
    rate (S -> I, beta()/N). A reactant that is not consumed on net (a
    catalyst, or one the reaction also makes: I in S + I -> I + I) is an
    influence on those edges, drawn as a dashed line to the arrow's
    middle. A reaction that produces without consuming draws a dashed
    "catalytic" edge from each such reactant to each product (I -> Hadm
    for I -> I + Hadm) or, with no reactant at all, a "source" edge from
    a source dot (0 -> counter). One that consumes without producing
    draws a "sink" edge to a sink dot. One that changes nothing draws
    nothing. Every edge carries its reaction's rule name and a one-line
    text for the status line: "S + I -> I + I, rate beta()/N, rule _R2".

    Returns {"nodes": [{"id", "label", "kind", "text"}], "edges": [{"id",
    "from", "to", "label", "kind", "rule", "text"}], "influences":
    [{"from": node id, "edge": edge id}]}.
    """
    species = net.get("species") or []
    label = {s["index"]: _species_label(s["pattern"]) for s in species}
    nodes = [{"id": f"s{s['index']}", "label": label[s["index"]], "kind": "species",
              "text": f"species {s['index']}: {s['pattern']}"} for s in species]
    edges, influences = [], []
    for r in net.get("reactions") or []:
        reactants = [i for i in r["reactants"] if i in label]
        products = [i for i in r["products"] if i in label]
        change = Counter(products)
        change.subtract(Counter(reactants))
        consumed = [i for i in _unique(reactants) if change[i] < 0]
        produced = [i for i in _unique(products) if change[i] > 0]
        drivers = [i for i in _unique(reactants) if change[i] >= 0]
        lhs = " + ".join(label[i] for i in reactants) or "0"
        rhs = " + ".join(label[i] for i in products) or "0"
        text = f"{lhs} -> {rhs}, rate {r['rate']}"
        if r.get("rule"):
            text += f", rule {r['rule']}"
        made = []

        def edge(frm: str, to: str, kind: str) -> None:
            eid = f"e{len(edges) + 1}"
            edges.append({"id": eid, "from": frm, "to": to, "label": r["rate"],
                          "kind": kind, "rule": r.get("rule", ""), "text": text})
            made.append(eid)

        if consumed and produced:
            for a in consumed:
                for b in produced:
                    edge(f"s{a}", f"s{b}", "transfer")
        elif produced:
            if drivers:
                for d in drivers:
                    for b in produced:
                        edge(f"s{d}", f"s{b}", "catalytic")
            else:
                src = f"src{r['index']}"
                nodes.append({"id": src, "label": "", "kind": "source", "text": text})
                for b in produced:
                    edge(src, f"s{b}", "source")
            continue                        # the drivers drew their own edges
        elif consumed:
            snk = f"snk{r['index']}"
            nodes.append({"id": snk, "label": "", "kind": "sink", "text": text})
            for a in consumed:
                edge(f"s{a}", snk, "sink")
        for d in drivers:
            for eid in made:
                influences.append({"from": f"s{d}", "edge": eid})
    return {"nodes": nodes, "edges": edges, "influences": influences}


def contact_graph(cm: dict) -> dict:
    """The contact map with ids for the page to draw: {"molecules":
    [{"id": "m<i>", "name", "components": [{"id": "m<i>c<j>", "name",
    "states": [...]}]}], "bonds": [{"from": component id, "to": component
    id}]}, in the order parse() read them."""
    molecules = []
    for mi, mol in enumerate(cm.get("molecules") or []):
        molecules.append({"id": f"m{mi}", "name": mol["name"], "components": [
            {"id": f"m{mi}c{ci}", "name": c["name"], "states": list(c.get("states") or [])}
            for ci, c in enumerate(mol.get("components") or [])]})
    bonds = [{"from": f"m{a[0]}c{a[1]}", "to": f"m{b[0]}c{b[1]}"}
             for a, b in cm.get("bonds") or []]
    return {"molecules": molecules, "bonds": bonds}
