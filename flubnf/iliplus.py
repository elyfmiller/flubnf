"""SHIPPED (used by the FluBNF console, app/).

Vintage-true ILI+ donor bank.

    ILI+ = ILINet %ILI  x  clinical percent positive

The product removes the large, seasonal non-influenza ILI background, so
ILI+ growth ratios track hospital-admission growth ratios.

The clinical half reuses :mod:`flubnf.nrevss` (vintages, cache, holiday-gap
fallback, MMWR arithmetic) via ``nrevss.fetch_typed``; percent positive is
DERIVED as ``(total_a + total_b) / total_specimens`` rather than read from
Delphi's field, which is rounded to 2 dp. The difference is immaterial to
scores (pooled relWIS 0.668774 vs 0.668775); ``percent_positive="reported"``
exists only to reproduce the frozen pre-registered numbers. The ILINet half
(``fluview``) lives here and imports nrevss's MMWR helpers, so the two
endpoints cannot disagree about epiweeks.

VINTAGE: ``fetch_ili`` requests ``issues=<asof epiweek>`` like
``fetch_typed``; weeks a snapshot lacks are absent, never imputed.
``asof=None`` (latest issue) is NOT vintage-true. It is acceptable only
because donors come from strictly prior seasons (at least 46 weeks old at
use), where ILINet revision measured negligible (lab archive,
research/iliplus-splice). Widen the calendar bandwidth or allow same-season
donors and the vintage path is the only defensible one.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from . import nrevss
from .nrevss import _as_date, _ew, _ew_shift, mmwr_week, week_ending

BASE_URL = "https://api.delphi.cmu.edu/epidata/fluview/"
HTTP_TIMEOUT = nrevss.HTTP_TIMEOUT

#: Raw ILINet responses, one file per (region, issue), beside the NREVSS
#: cache (app/state, gitignored).
CACHE_DIR = Path(__file__).resolve().parents[1] / "app" / "state" / "iliplus"

_COLUMNS = ["date", "ili"]


def build_url(region: str, ew_start: int, ew_end: int, issue=None) -> str:
    """The exact query URL (pure; unit-tested).

    ``issue=None`` omits the parameter, which asks Delphi for the latest
    issue of each week rather than a vintage.
    """
    params = {"regions": region, "epiweeks": f"{ew_start}-{ew_end}"}
    if issue is not None:
        params["issues"] = str(issue)
    return BASE_URL + "?" + urllib.parse.urlencode(params)


#: Delphi rate-limits bulk callers (HTTP 429 partway through a 52-state
#: build), hence the retry and the inter-region pause.
RETRY_ON_429 = 5
RETRY_BACKOFF_S = 3.0

#: Regions per request when warming the caches (Delphi accepts a comma list):
#: fewer requests is the real fix for the 429.
BATCH = 12


def _http_json(url: str, timeout: float = HTTP_TIMEOUT) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "flubnf-iliplus"})
    for attempt in range(RETRY_ON_429):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < RETRY_ON_429 - 1:
                time.sleep(RETRY_BACKOFF_S * (2 ** attempt))
                continue
            raise RuntimeError(
                f"ILINet fetch failed (HTTP {e.code} from Delphi Epidata): "
                f"{url}: {e}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise RuntimeError(
                f"ILINet fetch failed (network error contacting Delphi "
                f"Epidata): {url}: {e}") from e
    raise RuntimeError(f"ILINet fetch gave up after {RETRY_ON_429} "
                       f"rate-limited attempts: {url}")   # pragma: no cover


def _retry_429(fn, *args, **kw):
    """Run a fetch that raises RuntimeError on HTTP failure, retrying when the
    message carries a 429. For the NREVSS half, whose fetcher has no retry."""
    for attempt in range(RETRY_ON_429):
        try:
            return fn(*args, **kw)
        except RuntimeError as e:
            if "429" in str(e) and attempt < RETRY_ON_429 - 1:
                time.sleep(RETRY_BACKOFF_S * (2 ** attempt))
                continue
            raise


def _snapshot(region: str, issue, ew_start: int, ew_end: int,
              cache_dir=None) -> list:
    """Rows of the (region, issue) snapshot covering [ew_start, ew_end].

    Mirrors ``nrevss._snapshot``, caching the raw response BEFORE any
    fallback so a replay is served entirely from disk.
    """
    cache_dir = Path(cache_dir) if cache_dir is not None else CACHE_DIR
    tag = "latest" if issue is None else str(issue)
    path = cache_dir / f"{region}_{tag}.json"
    if path.exists():
        blob = json.loads(path.read_text())
        a, b = blob.get("epiweeks", (0, -1))
        # A "latest" snapshot is requested open-ended, so only the lower bound
        # is checked (else every build misses and refetches: 429). Delete the
        # file to refresh it.
        covered = a <= ew_start and (issue is None or ew_end <= b)
        if covered:
            rows = (blob["response"].get("epidata") or [])
            return [r for r in rows if ew_start <= r["epiweek"] <= ew_end]
    env = _http_json(build_url(region, ew_start, ew_end, issue))
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows_seen = env.get("epidata") or []
    upper = max((r["epiweek"] for r in rows_seen), default=ew_start)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({
        "region": region,
        "issue": issue,
        # record what was covered, not the open-ended request
        "epiweeks": [ew_start, ew_end if issue is not None else upper],
        "response": env,
    }, indent=1))
    tmp.replace(path)
    return env.get("epidata") or []


def fetch_ili(region: str, season_start_iso, asof_iso=None,
              cache_dir=None) -> pd.DataFrame:
    """ILINet %ILI for `region`, AS KNOWN at `asof_iso`.

    Columns [date, ili] (epiweek Saturday), sorted. ``asof_iso=None`` takes
    the latest issue (see the module docstring). With an as-of, an empty
    issue (holiday gap) falls back to the two preceding issues, as in
    ``nrevss.fetch_typed``.
    """
    ew_start = _ew(season_start_iso)
    if asof_iso is None:
        rows = _snapshot(region, None, ew_start, 999999, cache_dir=cache_dir)
    else:
        ew_end = _ew(asof_iso)
        rows = []
        for back in range(3):
            issue = _ew_shift(ew_end, -back)
            # an issue holds no later epiweeks; clamping also hits the cache
            rows = _snapshot(region, issue, ew_start, min(ew_end, issue),
                             cache_dir=cache_dir)
            if rows:
                break
    if not rows:
        return pd.DataFrame(columns=_COLUMNS)
    best: dict = {}
    for r in rows:
        k = r["epiweek"]
        if r.get("wili") is None and r.get("ili") is None:
            continue
        if k not in best or (r.get("issue") or 0) > (best[k].get("issue") or 0):
            best[k] = r
    # PREFER wili: identical to ili for states (the shipped bank), but the
    # population-weighted standard for HHS/census/national rows.
    recs = [{"date": week_ending(*divmod(k, 100)),
             "ili": float(r["wili"] if r.get("wili") is not None else r["ili"])}
            for k, r in sorted(best.items())]
    return pd.DataFrame(recs, columns=_COLUMNS)


def _warm(url: str, regions, issue, ew_start: int, ew_end: int,
          cache_dir: Path, name_issue) -> None:
    """Fetch several regions in ONE request and write per-region cache files.

    Writes the exact layout ``nrevss._snapshot`` and ``_snapshot`` read, so
    it only WARMS those caches; the per-region readers stay the authority on
    parsing and vintages. A region absent from the response gets an empty
    file, or it would be refetched forever.
    """
    env = _http_json(url)
    rows = env.get("epidata") or []
    by_region: dict = {r: [] for r in regions}
    for row in rows:
        by_region.setdefault(str(row.get("region", "")).lower(), []).append(row)
    cache_dir.mkdir(parents=True, exist_ok=True)
    for region in regions:
        path = cache_dir / f"{region}_{name_issue}.json"
        if path.exists():
            continue
        tmp = path.with_suffix(".json.tmp")
        mine = by_region.get(region, [])
        tmp.write_text(json.dumps({
            "region": region,
            "issue": issue,
            "epiweeks": [ew_start,
                         ew_end if issue is not None
                         else max((r["epiweek"] for r in mine),
                                  default=ew_start)],
            "response": {"result": 1, "message": "warmed", "epidata": mine},
        }, indent=1))
        tmp.replace(path)


def warm_caches(regions, season_start_iso, asof_iso=None, *,
                cache_dir=None, nrevss_cache_dir=None,
                batch: int = BATCH, pause_s: float = 0.4) -> None:
    """Populate both response caches for `regions` in batched requests.

    ``build_bank`` calls this. Cached regions are skipped, so a rerun after
    a partial failure fetches only what is missing.
    """
    ew_start = _ew(season_start_iso)
    icache = Path(cache_dir) if cache_dir is not None else CACHE_DIR
    ncache = (Path(nrevss_cache_dir) if nrevss_cache_dir is not None
              else nrevss.CACHE_DIR)
    if asof_iso is None:
        issue, tag, ew_end = None, "latest", 999999
    else:
        issue = _ew(asof_iso)
        tag, ew_end = str(issue), min(_ew(asof_iso), issue)
    todo_i = [r for r in regions if not (icache / f"{r}_{tag}.json").exists()]
    todo_n = [r for r in regions if not (ncache / f"{r}_{tag}.json").exists()]
    for src, todo, base, cdir in (
            ("ilinet", todo_i, BASE_URL, icache),
            ("clinical", todo_n, nrevss.BASE_URL, ncache)):
        for i in range(0, len(todo), batch):
            grp = todo[i:i + batch]
            params = {"regions": ",".join(grp),
                      "epiweeks": f"{ew_start}-{ew_end}"}
            if issue is not None:
                params["issues"] = str(issue)
            url = base + "?" + urllib.parse.urlencode(params)
            _retry_429(_warm, url, grp, issue, ew_start, ew_end, cdir, tag)
            if pause_s:
                time.sleep(pause_s)


def state_regions(locations_csv=None) -> list:
    """Lowercase Delphi region codes for the jurisdictions of the donor pool.

    US national is excluded: ILINet's national row is a weighted average of
    the states, not their sum, so a different quantity from a state series.
    """
    loc = nrevss._locations(locations_csv)
    out = []
    for a in loc["abbreviation"]:
        a = str(a).strip().lower()
        if a and a != "us":
            out.append(a)
    return sorted(set(out))


def _reported_pct(region: str, asof_iso, cache_dir=None) -> dict:
    """date -> Delphi's own two-decimal ``percent_positive`` for `region`.

    Read from the same cached snapshot ``nrevss.fetch_typed`` uses. Only for
    rebuilding the pre-registered bank exactly; derived is the default.
    """
    cache_dir = (Path(cache_dir) if cache_dir is not None
                 else nrevss.CACHE_DIR)
    tag = "latest" if asof_iso is None else str(_ew(asof_iso))
    out: dict = {}
    for name in (f"{region}_{tag}.json",):
        path = cache_dir / name
        if not path.exists():
            continue
        rows = (json.loads(path.read_text())["response"].get("epidata") or [])
        best: dict = {}
        for r in rows:
            k = r["epiweek"]
            if r.get("percent_positive") is None:
                continue
            if k not in best or (r.get("issue") or 0) > (best[k].get("issue") or 0):
                best[k] = r
        for k, r in best.items():
            out[week_ending(*divmod(k, 100))] = float(r["percent_positive"])
    return out


def build_bank(season_start_iso, asof_iso=None, *, regions=None,
               locations_csv=None, cache_dir=None, nrevss_cache_dir=None,
               min_specimens: int = 1, pause_s: float = 0.4,
               percent_positive: str = "derived") -> dict:
    """(region, date) -> ILI+, the auxiliary donor bank.

    Keys are (lowercase region code, epiweek-Saturday ``datetime.date``),
    the shape ``flubnf.analogue.donor_ratios`` reads; they need not match
    the admissions bank's (the pool is cross-location).

    A cell survives only when BOTH halves are present and positive and the
    week has at least ``min_specimens`` specimens. Missing weeks are
    dropped, never imputed, and there is no HHS fallback (unlike
    ``nrevss.a_share_series``): a region's series under a state key would be
    the wrong geography.

    ``percent_positive``: ``"derived"`` (default) from the typed counts;
    Delphi's 2-dp rounding is a large relative error at off-season
    positivity (up to 43 percent below 0.5 percent). ``"reported"`` uses the
    rounded field, only to reproduce the pre-registered bank.
    """
    if percent_positive not in ("derived", "reported"):
        raise ValueError(
            f"percent_positive must be 'derived' or 'reported', got "
            f"{percent_positive!r}")
    regions = state_regions(locations_csv) if regions is None else list(regions)
    # One batched pass fills both caches; every read below is then local.
    warm_caches(regions, season_start_iso, asof_iso, cache_dir=cache_dir,
                nrevss_cache_dir=nrevss_cache_dir, pause_s=pause_s)
    bank: dict = {}
    for region in regions:
        ili = _retry_429(fetch_ili, region, season_start_iso, asof_iso,
                         cache_dir=cache_dir)
        if ili.empty:
            continue
        clin = _retry_429(nrevss.fetch_typed, region, season_start_iso,
                          asof_iso, cache_dir=nrevss_cache_dir) \
            if asof_iso is not None else _retry_429(
                _latest_typed, region, season_start_iso, nrevss_cache_dir)
        if clin.empty:
            continue
        m = ili.merge(clin, on="date", how="inner")
        reported = (_reported_pct(region, asof_iso, nrevss_cache_dir)
                    if percent_positive == "reported" else None)
        for r in m.itertuples():
            spec = int(r.total_specimens or 0)
            if spec < min_specimens:
                continue
            if reported is not None:
                pct = reported.get(r.date)
                if pct is None:
                    continue
            else:
                pct = (int(r.total_a or 0) + int(r.total_b or 0)) / spec * 100.0
            v = float(r.ili) * pct
            if not (v > 0):
                continue
            d = _as_date(r.date)
            # the analogue keys donors by ITS epiweek; a disagreeing date
            # would land in the wrong calendar bin (never seen 2010-2026)
            y, w = mmwr_week(d)
            from .analogue import epiweek as _an_epiweek
            if _an_epiweek(d) != w:                      # pragma: no cover
                continue
            bank[(region, d)] = v
    return bank


def _latest_typed(region: str, season_start_iso, cache_dir):
    """Latest-issue clinical counts, the no-vintage counterpart of
    ``nrevss.fetch_typed``; kept out of nrevss, whose contract is
    vintage-true."""
    ew_start = _ew(season_start_iso)
    cache_dir = Path(cache_dir) if cache_dir is not None else nrevss.CACHE_DIR
    path = cache_dir / f"{region}_latest.json"
    if path.exists():
        blob = json.loads(path.read_text())
        rows = blob["response"].get("epidata") or []
    else:
        url = (nrevss.BASE_URL + "?" + urllib.parse.urlencode(
            {"regions": region, "epiweeks": f"{ew_start}-999999"}))
        env = nrevss._http_json(url)
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"region": region, "issue": None,
                                   "epiweeks": [ew_start, 999999],
                                   "response": env}, indent=1))
        tmp.replace(path)
        rows = env.get("epidata") or []
    best: dict = {}
    for r in rows:
        k = r["epiweek"]
        if k < ew_start:
            continue
        if k not in best or (r.get("issue") or 0) > (best[k].get("issue") or 0):
            best[k] = r
    recs = [{"date": week_ending(*divmod(k, 100)),
             "total_a": int(r["total_a"] or 0),
             "total_b": int(r["total_b"] or 0),
             "total_specimens": int(r["total_specimens"] or 0)}
            for k, r in sorted(best.items())]
    return pd.DataFrame(recs, columns=nrevss._COLUMNS)


def write_bank(bank: dict, path) -> Path:
    """Write a bank as the ``"region|YYYY-MM-DD": value`` JSON that
    ``app.core.engines.analogue.load_aux_bank`` reads.

    The one writer for that reader, so the format cannot drift.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {f"{r}|{d.isoformat()}": float(v)
               for (r, d), v in sorted(bank.items(), key=lambda kv: (kv[0][0],
                                                                     kv[0][1]))}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload))
    tmp.replace(path)
    return path
