"""Home (GET /): the outlook map, its model toggle and the diagram feed.

The outlook is cached per (run, results.json mtime). On a cold first paint
home serves the preparing silhouette and polls GET /api/outlook-ready until
server.py's startup warm pass sets state._WARM_DONE; that pass computes the
outlook through _outlook_block here. An APIRouter server.py includes.
"""
from __future__ import annotations

import html as _htmlmod
import sys
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core import horizons as _hzmod
from app.core import ttlcache
from app.ui import shared, state
from app.ui.templating import templates
from app.ui.versions import VERSIONS

router = APIRouter()


# === Cold start: has the warm pass landed (the pass: server.py) ===
def _outlook_ready() -> bool:
    """Whether home can render its outlook inline without paying the first
    science import: warm pass done, or pandas already loaded. False only on
    a cold first paint (home then serves the preparing silhouette)."""
    return state._WARM_DONE.is_set() or "pandas" in sys.modules


# === Home (/): outlook map, diagram feed -> home.html ===
def _outlook_cards(res: dict | None, rid: str | None = None) -> tuple:
    """(fips -> hover card for svg_map, source meta) for the home outlook.

    Exact path: the run's report bundle (report_inputs.json), so home shows
    the weekly report's categories; used as-is when it holds >= 2 per-model
    card sets. Otherwise one card set per stored model is approximated from
    results.json quantiles (categorical_probs_from_quantiles): meta
    approx=True, meta["by_model"] funds the toggle. A pre-v3 bundle that
    cannot fund a toggle keeps its exact single-model cards. Card-less
    states get empty cards so the full silhouette renders."""
    import json as _json

    from app.core import report_v2
    from app.core.report import categorical_probs_from_quantiles
    from app.core.report_v2 import CATS
    from app.core.runs import APP_STATE
    bundle_cards = bundle_meta = None
    if rid:
        try:
            b = APP_STATE / "workroots" / rid / report_v2.BUNDLE_NAME
            if b.is_file():
                bundle = _json.loads(b.read_text())
                if (bundle.get("version")
                        in report_v2.SUPPORTED_BUNDLE_VERSIONS):
                    cards = {c["fips"]: c
                             for c in (bundle.get("cards") or {}).values()
                             if isinstance(c, dict) and c.get("fips")}
                    model = bundle.get("cards_model") or "pf"
                    if (model not in report_v2.RETIRED_MODELS
                            and any(c.get("probs") for c in cards.values())):
                        bundle_cards = cards
                        bundle_meta = {"model": model, "approx": False,
                                       "label": report_v2.MODEL_LABEL.get(
                                           model, report_v2.MODEL_LABEL["pf"]),
                                       # bundle v4 coverage; None -> 'no data'
                                       "fitted_fips": bundle.get(
                                           "fitted_fips"),
                                       # bundle v6: the real gaps, and why
                                       # a state has no forecast
                                       "gap_fips": bundle.get("gap_fips"),
                                       "no_forecast": bundle.get(
                                           "no_forecast") or {}}
                        # >= 2 per-model card sets: exact cards and toggle
                        cbm = bundle.get("cards_by_model") or {}
                        if sum(1 for cs in cbm.values()
                               if any(isinstance(c, dict) and c.get("probs")
                                      for c in (cs or {}).values())) >= 2:
                            return bundle_cards, bundle_meta
        except Exception:
            bundle_cards = bundle_meta = None   # broken bundle: approximate
    _l = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
    n2f = dict(zip(_l.location_name, _l.location.str.zfill(2)))
    n2a = dict(zip(_l.location_name, _l.abbreviation))
    n2p = dict(zip(_l.location_name, _l.population.astype(float)))
    models = (res or {}).get("models", {})
    # PF first, then the Groundhog (a legacy run's blend is not shown)
    model = next((m for m in ("pf", "analogue") if models.get(m)), "pf")
    observed = (res or {}).get("observed", {})
    by_model: dict = {}
    models = _hzmod.models_to_canonical(models)
    for mname, md in models.items():
        cards = {}
        for loc, qd in (md or {}).items():
            fips = n2f.get(loc, "")
            q1 = (qd or {}).get("0")      # one week ahead, canonical
            obs = observed.get(loc) or []
            # tolerate the pre-quantile results schema (medians-only floats)
            if len(fips) != 2 or not isinstance(q1, dict) or not obs:
                continue
            lo = float(obs[-1][1])
            probs = categorical_probs_from_quantiles(q1, lo, int(n2p[loc]), 0)
            if not probs:
                continue
            vals = [float(v) for v in q1.values()]
            med1 = float(q1.get("0.5", vals[len(vals) // 2]))
            # hover_html reaches innerHTML: escape the name at the source
            hover = (f"<b>{_htmlmod.escape(loc)}</b><br>current: {lo:.0f}"
                     f"<br>1-wk median: {med1:.0f}<br>" +
                     "<br>".join(f"{c.replace('_',' ')}: {probs.get(c,0):.0%}"
                                 for c in CATS))
            cards[fips] = {"probs": probs, "name": loc,
                           "abbr": n2a.get(loc, ""),
                           "fips": fips, "hover_html": hover}
        if cards:
            by_model[mname] = cards
    # the retired blend is never the map, even on a legacy run
    from app.core.report_v2 import RETIRED_MODELS
    by_model = {m: c for m, c in by_model.items() if m not in RETIRED_MODELS}
    if model not in by_model and by_model:
        model = next(iter(by_model))
    # no toggle possible: an exact single-model bundle beats the approximation
    if bundle_cards is not None and len(by_model) < 2:
        return bundle_cards, bundle_meta
    cards = dict(by_model.get(model) or {})
    for name, fips in n2f.items():
        if len(fips) == 2:
            cards.setdefault(fips, {"name": name, "abbr": n2a.get(name, ""),
                                    "fips": fips})
    from app.core.report_v2 import MODEL_LABEL
    return cards, {"model": model, "approx": True,
                   "label": MODEL_LABEL.get(model, MODEL_LABEL["pf"]),
                   "by_model": by_model}


def _outlook_models(rid: str | None) -> dict:
    """{model: {fips: card}} from the bundle's cards_by_model (v3), models
    with data only; {} for older bundles (home then uses _outlook_cards'
    approximate sets)."""
    import json as _json

    from app.core import report_v2
    from app.core.runs import APP_STATE
    if not rid:
        return {}
    try:
        b = APP_STATE / "workroots" / rid / report_v2.BUNDLE_NAME
        if not b.is_file():
            return {}
        bundle = _json.loads(b.read_text())
        if bundle.get("version") not in report_v2.SUPPORTED_BUNDLE_VERSIONS:
            return {}
        out = {}
        for m, cards in (bundle.get("cards_by_model") or {}).items():
            byf = {c["fips"]: c for c in (cards or {}).values()
                   if isinstance(c, dict) and c.get("fips")
                   and c.get("probs")}
            if byf:
                out[m] = byf
        return out
    except Exception:
        return {}          # a broken bundle degrades to the plain map


def _diagram_data(res: dict | None) -> dict:
    """Per-location annotations for the compartment diagram: fitted-parameter
    medians (results.json 'params'), last observation, 1-week median. No
    template reads the 'diagram' key today; test_pages covers this."""
    out = {"date": "", "has_pf2s": False, "locations": {}, "order": []}
    if not res:
        return out
    try:
        out["date"] = res.get("forecast_date", "") or ""
        params = res.get("params") or {}
        pf_p = params.get("pf") or {}
        p2_p = params.get("pf2s") or {}
        models = _hzmod.models_to_canonical(res.get("models") or {})
        out["has_pf2s"] = bool(p2_p) or bool(models.get("pf2s"))
        observed = res.get("observed") or {}
        picked = (models.get("pf") or models.get("analogue")
                  or models.get("ensemble") or {})
        for loc in set(pf_p) | set(p2_p) | set(observed) | set(picked):
            e = {}
            if isinstance(pf_p.get(loc), dict) and pf_p[loc]:
                e["pf"] = pf_p[loc]
            if isinstance(p2_p.get(loc), dict) and p2_p[loc]:
                e["pf2s"] = p2_p[loc]
            obs = observed.get(loc) or []
            if obs:
                e["obs"] = obs[-1]
            q1 = (picked.get(loc) or {}).get("0")   # one week ahead
            if isinstance(q1, dict) and q1.get("0.5") is not None:
                e["med1"] = float(q1["0.5"])
            if e:
                out["locations"][str(loc)] = e
        out["order"] = sorted(
            out["locations"],
            key=lambda l: (l.upper() not in ("US", "US (NATIONAL)"), l))
    except Exception:
        return {"date": "", "has_pf2s": False, "locations": {}, "order": []}
    return out


def _outlook_results_mtime(rid: str | None) -> float:
    """Outlook cache-key term: the run's results.json mtime (0.0 if none)."""
    if not rid:
        return 0.0
    from app.core.runs import APP_STATE
    try:
        return (APP_STATE / "workroots" / rid / "results.json").stat().st_mtime
    except OSError:
        return 0.0


@ttlcache.ttl_cache(ttl_s=300.0)
def _outlook_block_cached(rid: str | None, mtime: float) -> dict:
    """Home outlook (map, caption facts, model toggle), cached per (run,
    results mtime) so the long TTL never serves a stale map."""
    import json as _json
    res = None
    if rid:
        from app.core.runs import APP_STATE
        try:
            res = _json.loads((APP_STATE / "workroots" / rid
                               / "results.json").read_text())
        except Exception:
            res = None
    # latest run's outlook, else the empty-country silhouette
    map_svg, outlook_date, outlook_n = "", "", 0
    outlook_src: dict = {}
    outlook_toggle = ""
    try:
        from app.core import report_v2, usmap
        from app.core.usmap import map_legend, svg_map
        cards = {}
        try:
            cards, outlook_src = _outlook_cards(res, rid)
            if any(c.get("probs") for c in cards.values()):
                outlook_date = (res or {}).get("forecast_date", "")
            else:
                outlook_src = {}      # an empty map needs no model label
        except Exception:
            pass                      # no LOCATIONS/hub -> bare silhouette
        with_data = {c["abbr"] for c in cards.values() if c.get("probs")}
        # caption counts only colored jurisdictions (US has no state shape)
        outlook_n = len(with_data - {"US"})
        # fitted_fips (bundle v4) lets hovers tell a reporting gap from 'not
        # fitted'; absent -> hovers claim only 'no data'
        scope = outlook_src.get("fitted_fips") if outlook_src else None
        scope = set(scope) if scope is not None else None
        gaps = outlook_src.get("gap_fips") if outlook_src else None
        gaps = set(gaps) if gaps is not None else None
        why = (outlook_src.get("no_forecast") or {}) if outlook_src else {}
        map_svg = ("<div style='max-width:880px;margin:0 auto'>"
                   "<script>window.MAP_LINK='/output/report';</script>"
                   + svg_map(cards, clickable=with_data, scope_fips=scope,
                             gap_fips=gaps,
                             reasons=why.get(outlook_src.get("model")))
                   + map_legend() + "</div>")
        # toggle from the v3 bundle's per-model cards, else the approximate
        # sets; fewer than two models -> label only, never a dead control
        try:
            by_model = _outlook_models(rid) if outlook_src else {}
            if not by_model and outlook_src.get("approx"):
                by_model = outlook_src.get("by_model") or {}
            order = report_v2.toggle_models(by_model)
            if len(order) >= 2:
                default = (outlook_src.get("model")
                           if outlook_src.get("model") in order
                           else order[0])
                payload = {m: {"states": usmap.state_swap_payload(
                                   by_model[m], scope_fips=scope,
                                   gap_fips=gaps, reasons=why.get(m)),
                               "us": {}}
                           for m in order}
                outlook_toggle = usmap.model_toggle(
                    order, report_v2.MODEL_LABEL, default, payload,
                    group_id="outlook-model", btn_class="quiet",
                    active_class="gold", wrap_class="row viewtabs",
                    short_labels=report_v2.MODEL_SHORT)
        except Exception:
            outlook_toggle = ""
    except Exception:
        pass
    return {"map_svg": map_svg, "outlook_date": outlook_date,
            "outlook_n": outlook_n,
            "label": outlook_src.get("label", ""),
            "approx": bool(outlook_src.get("approx")),
            "toggle": outlook_toggle}


def _outlook_block(rid: str | None) -> dict:
    return _outlook_block_cached(rid, _outlook_results_mtime(rid))


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    _t0 = time.perf_counter()
    state._trace("home: request begin")
    try:
        rid, res = shared._latest_results()
    except Exception:
        rid, res = None, None
    pending = not _outlook_ready()
    if pending:
        # give the warm pass 1.5 s so a warm machine paints complete
        state._WARM_DONE.wait(1.5)
        pending = not _outlook_ready()
    if pending:
        # truly cold start: silhouette + preparing note now; the page polls
        # /api/outlook-ready and reloads once
        from app.core.usmap import map_legend, svg_map
        ob = {"map_svg": ("<div style='max-width:880px;margin:0 auto'>"
                          + svg_map({}, clickable=set()) + map_legend()
                          + "</div>"),
              "outlook_date": "", "outlook_n": 0,
              "label": "", "approx": False, "toggle": ""}
    else:
        ob = _outlook_block(rid)
    state._trace(f"home: outlook ready at +{time.perf_counter() - _t0:.2f}s "
                 f"(pending={pending}), rendering")
    return templates.TemplateResponse(request, "home.html", {
        "active": "Home", "map_svg": ob["map_svg"],
        "outlook_date": ob["outlook_date"],
        "outlook_n": ob["outlook_n"],
        "outlook_model_label": ob["label"],
        "outlook_approx": ob["approx"],
        "outlook_toggle": ob["toggle"],
        "outlook_pending": pending,
        "versions": VERSIONS, "diagram": _diagram_data(res),
        "missing": __import__("flubnf.settings", fromlist=["check"]).check(verbose=False)})


@router.get("/api/outlook-ready")
def api_outlook_ready():
    """Whether home's outlook now renders inline (polled by the cold first
    paint's preparing state)."""
    return {"ready": _outlook_ready()}
