"""The contact map of a BNGL model, drawn from BNG2.pl's own reading of it.

BioNetGen's visualize action (type contactmap) writes a yEd GraphML file:
every molecule type is a node (a group node when it has components), each
component a child node, a component's states a nested group of state
nodes, and every bond the rules can form an edge between two component
nodes. parse() reduces that file to molecules, components, states and
bonds; svg() lays them out as an inline SVG whose colours are the page's
own tokens, so the drawing reads in every theme. Nothing here runs the
engine: BNG2.pl is asked for the map alone, on a copy of the model whose
actions block is replaced by the one visualize call.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

# BNG2.pl's own output, written to a folder the app made from the user's
# own model: the stdlib parser (no external entities by default) is enough.
from xml.etree import ElementTree as ET

from flubnf.settings import BNG

NS = {"g": "http://graphml.graphdrawing.org/xmlns",
      "y": "http://www.yworks.com/xml/graphml"}


class ContactMapError(ValueError):
    """A model BNG2.pl could not draw, with its words."""


def visualize_bngl(bngl_text: str) -> str:
    """The model with its actions replaced by the one visualize call."""
    m = re.search(r"^\s*end\s+model\s*$", bngl_text, flags=re.M)
    if not m:
        raise ContactMapError("the contact map needs a begin model / end "
                              "model block around the model")
    return (bngl_text[:m.end()].rstrip() + "\n\nbegin actions\n"
            'visualize({type=>"contactmap"})\nend actions\n')


def graphml_from_bngl(bngl_text: str, workdir: Path, timeout: int = 120) -> str:
    """Run BNG2.pl on the visualize-only copy in workdir; the GraphML text."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "cm.bngl").write_text(visualize_bngl(bngl_text),
                                     encoding="utf-8", newline="\n")
    out = workdir / "cm_contactmap.graphml"
    if out.exists():
        out.unlink()                       # never a stale map for a new model
    r = subprocess.run(["perl", BNG, "cm.bngl"], capture_output=True,
                       text=True, cwd=str(workdir), timeout=timeout)
    if not out.is_file():
        raise ContactMapError("BNG2.pl could not draw the contact map:\n"
                              + (r.stdout or "")[-600:] + (r.stderr or "")[-300:])
    return out.read_text(encoding="utf-8", errors="replace")


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


# ------------------------------------------------------------ the drawing

CHAR = 7.2          # px per character at the 12 px label size
PAD = 10
GAP = 22            # between molecules
ROW_GAP = 26
WRAP = 640          # wrap molecules into rows past this width


def _w(text: str, minimum: float) -> float:
    return max(minimum, CHAR * len(text) + 2 * PAD)


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def svg(cm: dict) -> str:
    """An inline SVG of the map. Colours are CSS tokens of the page
    (--card, --bg, --ink, --mut, --line, --accent, --accent-ink)."""
    mols = cm.get("molecules") or []
    if not mols:
        return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 40" '
                'width="320" height="40" role="img" aria-label="empty contact map">'
                '<text x="0" y="24" fill="var(--mut)" font-size="12">no molecule '
                'types</text></svg>')
    boxes, comps = [], {}          # per molecule: (x, y, w, h); per (mi, ci): centre
    x = y = 0.0
    row_h = 0.0
    for mi, mol in enumerate(mols):
        cws = [_w(c["name"], 30) for c in mol["components"]]
        sws = [sum(_w(s, 22) for s in c["states"]) + 4 * max(len(c["states"]) - 1, 0)
               for c in mol["components"]]
        cell = [max(a, b) for a, b in zip(cws, sws)]
        has_states = any(c["states"] for c in mol["components"])
        w = max(_w(mol["name"], 70), sum(cell) + 8 * max(len(cell) - 1, 0) + 2 * PAD)
        h = 30 + (30 if mol["components"] else 0) + (26 if has_states else 0) + 6
        if x > 0 and x + w > WRAP:
            x, y, row_h = 0.0, y + row_h + ROW_GAP, 0.0
        boxes.append((x, y, w, h, cell))
        row_h = max(row_h, h)
        x += w + GAP
    width = max(b[0] + b[2] for b in boxes)
    height = y + row_h
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
             f'width="{width:.0f}" height="{height:.0f}" role="img" '
             f'aria-label="contact map: {len(mols)} molecule types, {len(cm.get("bonds") or [])} bonds" '
             'font-family="DM Sans, system-ui, sans-serif" font-size="12">']
    body = []
    for mi, (bx, by, bw, bh, cell) in enumerate(boxes):
        mol = mols[mi]
        body.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="8" '
                    'fill="var(--bg)" stroke="var(--ink)" stroke-width="1.2"/>')
        body.append(f'<text x="{bx + bw / 2:.1f}" y="{by + 19:.1f}" text-anchor="middle" '
                    f'fill="var(--ink)" font-weight="600">{_esc(mol["name"])}</text>')
        cx = bx + PAD
        for ci, comp in enumerate(mol["components"]):
            cw = cell[ci]
            cy = by + 32
            body.append(f'<rect x="{cx:.1f}" y="{cy:.1f}" width="{cw:.1f}" height="22" rx="5" '
                        'fill="var(--card)" stroke="var(--ink)"/>')
            body.append(f'<text x="{cx + cw / 2:.1f}" y="{cy + 15:.1f}" text-anchor="middle" '
                        f'fill="var(--ink)">{_esc(comp["name"])}</text>')
            comps[(mi, ci)] = (cx + cw / 2, cy + 11)
            sx = cx
            for st in comp["states"]:
                sw = _w(st, 22)
                body.append(f'<rect x="{sx:.1f}" y="{cy + 28:.1f}" width="{sw:.1f}" height="18" rx="9" '
                            'fill="var(--accent)" fill-opacity="0.35" stroke="var(--accent-ink)"/>')
                body.append(f'<text x="{sx + sw / 2:.1f}" y="{cy + 41:.1f}" text-anchor="middle" '
                            f'fill="var(--ink)" font-size="11">{_esc(st)}</text>')
                sx += sw + 4
            cx += cw + 8
    edges = []
    for a, b in cm.get("bonds") or []:
        pa, pb = comps.get(tuple(a)), comps.get(tuple(b))
        if not pa or not pb:
            continue
        mx, my = (pa[0] + pb[0]) / 2, min(pa[1], pb[1]) - 26
        edges.append(f'<path d="M{pa[0]:.1f},{pa[1]:.1f} Q{mx:.1f},{my:.1f} {pb[0]:.1f},{pb[1]:.1f}" '
                     'fill="none" stroke="var(--accent-ink)" stroke-width="2"/>')
    parts += edges + body + ["</svg>"]
    return "".join(parts)
