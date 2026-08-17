"""Weekly HTML report — the flagship shareable.

Opening view: a US tile-grid choropleth of categorical rate-change forecasts
(the FluSight bins), one tile per jurisdiction, colored by the modal category
with opacity from its probability. Self-contained HTML: inline CSS/SVG, no
external assets, viewable from a file:// open or a static host.

Missing data renders as explicit hatched gap markers (constitutional rule 10)
-- never a smooth line implying data existed.

NOTE: categorical cutpoints below follow the FluSight rate-change definition
(rate difference per 100k, horizon-scaled). Marked for verification against
the season's official hub definition before first submission.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

# Tile-grid positions (col, row) — the standard US state tile map.
TILES = {
 "AK": (0, 0), "ME": (11, 0), "VT": (10, 1), "NH": (11, 1),
 "WA": (1, 2), "ID": (2, 2), "MT": (3, 2), "ND": (4, 2), "MN": (5, 2),
 "IL": (6, 2), "WI": (7, 2), "MI": (8, 2), "NY": (9, 2), "RI": (10, 2), "MA": (11, 2),
 "OR": (1, 3), "NV": (2, 3), "WY": (3, 3), "SD": (4, 3), "IA": (5, 3),
 "IN": (6, 3), "OH": (7, 3), "PA": (8, 3), "NJ": (9, 3), "CT": (10, 3),
 "CA": (1, 4), "UT": (2, 4), "CO": (3, 4), "NE": (4, 4), "MO": (5, 4),
 "KY": (6, 4), "WV": (7, 4), "VA": (8, 4), "MD": (9, 4), "DE": (10, 4),
 "AZ": (2, 5), "NM": (3, 5), "KS": (4, 5), "AR": (5, 5), "TN": (6, 5),
 "NC": (7, 5), "SC": (8, 5), "DC": (9, 5),
 "OK": (4, 6), "LA": (5, 6), "MS": (6, 6), "AL": (7, 6), "GA": (8, 6),
 "HI": (0, 7), "TX": (4, 7), "FL": (9, 7), "PR": (10, 7),
}

CATS = ("large_decrease", "decrease", "stable", "increase", "large_increase")
COLORS = {"large_decrease": "#1a66a8", "decrease": "#7fb2d9",
          "stable": "#b8b8b0", "increase": "#e79a6b", "large_increase": "#c03a2b",
          "no_data": "#e8e6e0"}


def categorical_probs(samples, last_observed: float, population: int,
                      horizon: int = 1) -> dict:
    """P(category) from forecast samples vs the current level.

    Cutpoints: rate difference per 100k, scaled by horizon (VERIFY against the
    official hub definition for the season before first submission).
    """
    s = np.asarray(samples, float)
    s = s[np.isfinite(s)]
    if not s.size or population <= 0:
        return {}
    diff_rate = (s - last_observed) / population * 1e5
    k = {1: 1.0, 2: 1.0, 3: 2.0, 4: 2.5}.get(horizon, 1.0)
    lo, hi = 0.3 * k, 1.7 * k
    p = {
        "large_increase": float(np.mean(diff_rate >= hi)),
        "increase": float(np.mean((diff_rate >= lo) & (diff_rate < hi))),
        "stable": float(np.mean(np.abs(diff_rate) < lo)),
        "decrease": float(np.mean((diff_rate <= -lo) & (diff_rate > -hi))),
        "large_decrease": float(np.mean(diff_rate <= -hi)),
    }
    return p


def _tile(abbr: str, probs: dict, x: int, y: int, size: int = 56) -> str:
    if not probs:
        return (f'<g><rect x="{x}" y="{y}" width="{size-4}" height="{size-4}" '
                f'rx="6" fill="{COLORS["no_data"]}"/>'
                f'<text x="{x+size//2-2}" y="{y+size//2+3}" class="tl">{abbr}</text>'
                f'<title>{abbr}: no data (reporting gap)</title></g>')
    modal = max(probs, key=probs.get)
    op = 0.35 + 0.65 * probs[modal]
    tip = ", ".join(f"{c.replace('_',' ')} {probs.get(c,0):.0%}" for c in CATS)
    return (f'<g><rect x="{x}" y="{y}" width="{size-4}" height="{size-4}" rx="6" '
            f'fill="{COLORS[modal]}" fill-opacity="{op:.2f}"/>'
            f'<text x="{x+size//2-2}" y="{y+size//2+3}" class="tl">{abbr}</text>'
            f'<title>{abbr}: {tip}</title></g>')


def choropleth_svg(state_probs: dict, size: int = 56) -> str:
    """state_probs: abbr -> P(category) dict ({} = explicit no-data tile)."""
    w = (max(c for c, _ in TILES.values()) + 1) * size
    h = (max(r for _, r in TILES.values()) + 1) * size
    tiles = [
        _tile(a, state_probs.get(a, {}), c * size, r * size, size)
        for a, (c, r) in TILES.items()]
    legend = "".join(
        f'<g transform="translate({i*150+10},{h+10})">'
        f'<rect width="14" height="14" rx="3" fill="{COLORS[c]}"/>'
        f'<text x="20" y="11" class="lg">{c.replace("_", " ")}</text></g>'
        for i, c in enumerate(CATS))
    return (f'<svg viewBox="0 0 {w} {h+40}" xmlns="http://www.w3.org/2000/svg" '
            f'style="max-width:100%;height:auto">'
            f'<style>.tl{{font:600 13px system-ui;fill:#222;text-anchor:middle}}'
            f'.lg{{font:12px system-ui;fill:#444}}</style>{"".join(tiles)}{legend}</svg>')


def weekly_report(reference_date: str, state_probs: dict,
                  extras_html: str = "") -> str:
    """The static weekly page. state_probs keyed by state ABBR."""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>FluBNF — week of {reference_date}</title>
<style>
 body{{font:15px/1.5 system-ui;margin:0;background:#faf9f6;color:#1e1e1c}}
 main{{max-width:960px;margin:0 auto;padding:2rem 1rem}}
 h1{{font-size:1.5rem}} .sub{{color:#666}}
 .card{{background:#fff;border:1px solid #e4e1da;border-radius:12px;
        padding:1.2rem;margin:1rem 0}}
</style></head><body><main>
<h1>US influenza forecast — week of {reference_date}</h1>
<p class="sub">Categorical rate-change outlook by jurisdiction. Tile color =
most likely category; intensity = its probability. Hover for the full
distribution. Grey tiles: no reported data (reporting gap — shown, not
smoothed over).</p>
<div class="card">{choropleth_svg(state_probs)}</div>
{extras_html}
</main></body></html>"""


def write_report(out_path: Path, **kw) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(weekly_report(**kw))
    return out_path
