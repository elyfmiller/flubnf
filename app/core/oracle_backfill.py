"""VERIFICATION CLI ONLY (`flubnf oracle backfill` / `flubnf oracle
reproduce`); never on the console path.

Backfill and reproduce: proves the app's code reproduces the registered
Oracle screens from their saved forecasts, with no refit. A season's Oracle
SIHRS is run and viewed by a console replay (retro.run_season), never
through a backfilled root.

BACKFILL. Applies oracle.apply_week to each stored week's `pf` of a source
root, through the storage boundary both ways, into a NEW root whose weeks
carry `pf` (the member), `pf_filter` (the source's pf), `analogue`
(verbatim), the sidecar, oracle.json and oracle_bank/. The destination may
not be the source, inside it, under app/state (the sealed and live trees),
or a non-empty tree unless forced.

REPRODUCE. retro.score_season on the backfilled root (the console's scorer
and cell rule; the screens were scored under the earlier rule, truth and
median above 0, so today's rule reproduces them to about the third
decimal), pooled via us_national.pooled_frame; relWIS per season and
overall on the record cells (each member's own) and the common cells, plus
active2 when 2023-24 is among the roots; printed beside the screen's
relwis_tables (screen_scores.json: LB; screen_b2_scores.json: LBGH). FLUBNF_HUB
must be the hub whose truth and baseline the screen used.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pandas as pd

from app.core import oracle as oracle_mod
from app.core import retro

REPO = Path(__file__).resolve().parents[2]

#: settings.output_floor in a backfilled record. The member is the Oracle
#: step on the source's stored pf with no floor after it (run_week floors
#: after the step), so a floored source's "applied" must not carry over;
#: the source's own entry stays in backfill.source_settings
FLOOR_NOT_REAPPLIED = ("not applied after the Oracle step (a backfill from "
                       "stored samples; the source's record says how its pf "
                       "was stored)")


def _sha256(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _under(p: Path, root: Path) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


def guard_out(source, out, force: bool = False) -> Path:
    """Where a backfill may write: never the source, never under it, never
    under the repository's app/state, never a non-empty tree unless forced.
    Returns the resolved destination."""
    src, dst = Path(source).resolve(), Path(out).resolve()
    if dst == src or _under(dst, src):
        raise ValueError(f"the backfill would write into its own source ({src}); "
                         "name a new root")
    state = (REPO / "app" / "state").resolve()
    if _under(dst, state):
        raise ValueError(f"the backfill never writes under {state}: the sealed "
                         "and live retrospective trees live there; name a new root")
    if dst.exists() and any(dst.iterdir()) and not force:
        raise ValueError(f"{dst} exists and is not empty; pass force to write "
                         "into it")
    return dst


def backfill_season(source, out, season: str, *, force: bool = False,
                    keep_filter: bool = True, progress=None) -> dict:
    """The member for every stored week of `source` into `out`. Returns a
    summary; per-week records land beside each week."""
    src = Path(source).resolve()
    dst = guard_out(src, out, force)
    files = retro.season_sample_files(src)
    if not files:
        raise ValueError(f"no stored weeks under {src}")
    meta_src = retro.read_meta(src)
    settings = dict(meta_src.get("settings") or {})
    k_default = int(settings.get("weeks_to_drop") or 0)
    dst.mkdir(parents=True, exist_ok=True)
    done, skipped = [], []
    t0 = time.time()
    for fp in files:
        asof = fp.parent.name
        rec = retro.read_samples(fp)                      # canonical
        pf = rec.get("pf")
        wd = dst / "weeks" / asof
        if not isinstance(pf, dict) or not pf:
            skipped.append(asof)                          # an analogue-only week
            if progress:
                progress(asof, "skipped: no pf block")
            continue
        wd.mkdir(parents=True, exist_ok=True)
        member, prov = oracle_mod.apply_week(
            pf, asof, wd, weeks_to_drop=k_default,
            drop_same_day=bool(settings.get("drop_same_day")))
        prov["backfill"] = {"source_root": str(src), "source_samples": str(fp),
                            "source_samples_sha256": _sha256(fp),
                            "keep_filter": bool(keep_filter), "utc": oracle_mod._utc()}
        oracle_mod.write_provenance(wd, prov)
        stored = {"asof": rec.get("asof", asof), "pf": member}
        if keep_filter:
            stored[oracle_mod.FILTER_KEY] = pf
        for key in ("analogue", "pf2s", "pf_failures"):
            if key in rec:
                stored[key] = rec[key]
        retro.write_week_samples(wd, stored)
        done.append(asof)
        if progress:
            progress(asof, f"{prov['bank']['label']}, active {prov['cells']['active']} "
                           f"of {prov['cells']['locations']}")
    now = time.time()
    meta = {"season": season, "status": "done", "started_utc": t0, "finished_utc": now,
            "heartbeat_utc": now, "elapsed_s": now - t0, "segment_start_utc": None,
            "total_weeks": len(files), "weeks_completed": len(done),
            "week_seconds": {}, "week_partial_s": {},
            "settings": {**settings, "engine": "pf", "season": season,
                         "oracle": "applied (backfill from stored samples, no refit)",
                         "output_floor": FLOOR_NOT_REAPPLIED},
            "backfill": {"source_root": str(src), "source_settings": settings,
                         "source_run_meta_keys": sorted(meta_src),
                         "weeks_done": done, "weeks_skipped": skipped,
                         "keep_filter": bool(keep_filter),
                         "prereg_sha256": oracle_mod.OR.PREREG_SHA256,
                         "b2_sha256": oracle_mod.OR.B2_SHA256,
                         "addendum_a2_sha256": oracle_mod.OR.ADDENDUM_A2_SHA256,
                         "bank_stream": oracle_mod.MX.STREAM,
                         "utc": oracle_mod._utc()}}
    retro.write_meta(dst, meta)
    return {"out": dst, "weeks": done, "skipped": skipped,
            "seconds": round(now - t0, 1)}


# ------------------------------------------------------------- reproduce

def sidecars_current(root) -> bool:
    """Whether every stored week of a root has a current quantile sidecar,
    which is what lets score_season read it without writing anything."""
    for fp in retro.season_sample_files(root):
        if retro.read_week_quantiles(fp.parent) is None:
            return False
    return True


def score_root(root, season: str, *, read_only: bool = False) -> pd.DataFrame:
    """The app's own scorer on a root, pooled (US excluded). With
    read_only, refuses a root whose sidecars are not current rather than
    letting the scorer write them."""
    from app.core.us_national import pooled_frame
    if read_only and not sidecars_current(root):
        raise ValueError(f"{root}: a week's quantile sidecar is absent or stale, "
                         "and scoring it would write into the root; refused")
    df = retro.score_season(Path(root), season)
    if df.empty:
        return df
    df = pooled_frame(df)
    df["season"] = season
    return df


def relwis_tables(df: pd.DataFrame, models=("pf", "analogue")) -> dict:
    """relWIS by season and over every season in the frame, on the record
    definition (each model's own scored cells) and on the common set
    (cells every named model scored), each with its cell count."""
    out = {}
    if df is None or df.empty:
        return out
    scopes = {s: df[df.season == s] for s in sorted(df.season.unique())}
    if len(scopes) > 2 and {"2024-25", "2025-26"} <= set(scopes):
        scopes["active2"] = df[df.season.isin(["2024-25", "2025-26"])]
    if len(scopes) > 1:
        scopes["all"] = df
    for name, g in scopes.items():
        entry = {"record": {}, "common": {}}
        keysets = []
        for m in models:
            gm = g[g.model == m]
            if len(gm):
                entry["record"][m] = {"relwis": float(gm.wis.sum() / gm.base_wis.sum()),
                                      "cells": int(len(gm))}
                keysets.append(set(zip(gm.fips, gm["asof"], gm.horizon)))
        if len(keysets) == len(models) and keysets:
            common = set.intersection(*keysets)
            for m in models:
                gm = g[g.model == m]
                gc = gm[[k in common for k in zip(gm.fips, gm["asof"], gm.horizon)]]
                entry["common"][m] = {"relwis": float(gc.wis.sum() / gc.base_wis.sum()),
                                      "cells": int(len(gc))}
        out[name] = entry
    return out


def screen_tables(screen_json) -> dict:
    """The screen's relwis_tables for LB, LB25 and NULL (and, from the B2
    screen, the shipped LBGH and LB25GH), as printed beside the reproduced
    numbers: common and native by scope, seed 1 and the per-seed list."""
    d = json.loads(Path(screen_json).read_text())
    rt = d.get("relwis_tables") or {}
    seeds = [str(s) for s in d.get("seeds") or []]
    out = {"seeds": seeds, "frozen_document_sha256": d.get("frozen_document_sha256"),
           "b2_frozen_sha256": d.get("b2_frozen_sha256"),
           "member_arm": "LBGH" if "LBGH" in rt else "LB"}
    for arm in ("NULL", "LB", "LB25", "LBGH", "LB25GH"):
        if arm not in rt and arm in ("LBGH", "LB25GH"):
            continue
        t = rt.get(arm) or {}
        out[arm] = {"common": t.get("common") or {}, "native": t.get("native") or {},
                    "native_cells": t.get("native_cells"),
                    "per_seed_common": t.get("per_seed_common") or {}}
    return out


def reproduce(roots: list, *, source_roots: list | None = None,
              screen_json=None) -> dict:
    """Score one or more backfilled season roots (and, read only, their
    sources for the NULL) and lay the numbers beside the screen's."""
    # check the read-only promise before any scoring (or hub read)
    for r in (source_roots or []):
        if not sidecars_current(r):
            raise ValueError(f"{r}: a week's quantile sidecar is absent or stale, "
                             "and scoring it would write into the root; refused")
    frames = []
    for r in roots:
        r = Path(r)
        if not (r / "weeks").is_dir():
            # said plainly (pandas' own words were "No objects to concatenate")
            raise FileNotFoundError(f"{r}: not a season root (no weeks/ "
                                    "folder of stored weeks)")
        meta = retro.read_meta(r)
        season = str(meta.get("season") or r.name)
        frames.append(score_root(r, season))
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True) if frames else pd.DataFrame()
    res = {"roots": [str(r) for r in roots], "member": relwis_tables(df),
           "cells_scored": int(len(df)),
           "pooled_scope": ("pooled3" if df is not None and not df.empty
                            and df.season.nunique() > 2 else "active2")}
    if source_roots:
        sf = []
        for r in source_roots:
            r = Path(r)
            meta = retro.read_meta(r)
            season = str(meta.get("season") or r.name)
            sf.append(score_root(r, season, read_only=True))
        sdf = pd.concat([f for f in sf if not f.empty], ignore_index=True) if sf else pd.DataFrame()
        res["null"] = relwis_tables(sdf)
        res["source_roots"] = [str(r) for r in source_roots]
    if screen_json:
        res["screen"] = screen_tables(screen_json)
    return res


def _fmt(v) -> str:
    return "" if v is None else f"{float(v):.4f}"


def report_lines(res: dict) -> list:
    """The reproduce result as lines for a terminal, the screen's number
    beside each reproduced one where the scope matches."""
    lines = []
    scr = res.get("screen") or {}
    seed1 = (scr.get("seeds") or [""])[0]
    arm = scr.get("member_arm") or "LB"
    scope_map = {"all": res.get("pooled_scope") or "active2"}
    for scope, entry in (res.get("member") or {}).items():
        sscope = scope_map.get(scope, scope)
        lines.append(f"{scope}:")
        for setname in ("record", "common"):
            for m, v in (entry.get(setname) or {}).items():
                who = {"pf": "Oracle SIHRS (pf)", "analogue": "Groundhog"}.get(m, m)
                line = f"  {setname:<7} {who:<20} relWIS {v['relwis']:.4f} on {v['cells']:,} cells"
                if m == "pf" and scr:
                    lb = scr.get(arm) or {}
                    key = "common" if setname == "common" else "native"
                    s_val = (lb.get(key) or {}).get(sscope)
                    ps = (lb.get("per_seed_common") or {}).get(sscope) or []
                    s1 = ps[0] if ps else None
                    lines.append(f"{line}   screen {arm} {key} (seed mean) {_fmt(s_val)}"
                                 + (f", seed {seed1} {_fmt(s1)}" if s1 is not None else "")
                                 + (f", native cells {lb.get('native_cells')}"
                                    if key == "native" and scope == "all" else ""))
                else:
                    lines.append(line)
        nul = ((res.get("null") or {}).get(scope) or {})
        for setname in ("record", "common"):
            v = (nul.get(setname) or {}).get("pf")
            if v:
                line = (f"  {setname:<7} {'plain filter (NULL)':<20} relWIS {v['relwis']:.4f} "
                        f"on {v['cells']:,} cells")
                if scr:
                    key = "common" if setname == "common" else "native"
                    s_val = ((scr.get("NULL") or {}).get(key) or {}).get(sscope)
                    line += f"   screen NULL {key} {_fmt(s_val)}"
                lines.append(line)
    return lines
