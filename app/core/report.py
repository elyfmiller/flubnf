"""LEGACY (v1 tile-grid weekly report): superseded by report_v2. Kept as a
module because callers import the categorical shims through it (server,
site_build); choropleth_svg and its tile grid remain only for
app/tests/test_core.py.

The categorical probabilities are app.core.categorical's: the hub's own
rate-trend definition, one CDF path for every model. The two shims keep
their historical names.
"""
from __future__ import annotations

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
                      horizon: int = 0) -> dict:
    """P(category) from forecast draws (app.core.categorical). `horizon` is
    the hub horizon (0 = one week ahead)."""
    from app.core import categorical as _cat
    return _cat.probs_from_samples(samples, last_observed, population, horizon)


def categorical_probs_from_quantiles(qmap: dict, last_observed: float,
                                     population: int,
                                     horizon: int = 0) -> dict:
    """P(category) from a stored quantile grid {level: value}
    (app.core.categorical). `horizon` is the hub horizon (0 = one week ahead)."""
    from app.core import categorical as _cat
    return _cat.probs_from_quantiles(qmap, last_observed, population, horizon)


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
